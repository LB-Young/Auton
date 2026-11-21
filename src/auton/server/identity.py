import asyncio
import fcntl
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from secrets import token_urlsafe
from typing import Literal, Protocol

import anyio
import apsw
from pydantic import BaseModel, ConfigDict, Field

from auton.kernel.ports import ApplicationError, LifecycleHandle, RuntimeDependencies


class ServerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    directory: Path = Path(".auton_local/server")
    identity_backend: Literal["sqlite", "memory"] = "sqlite"
    identity_ttl_seconds: int = Field(default=2592000, ge=60, le=31536000)
    max_identities: int = Field(default=1000, ge=1, le=10000)
    max_upload_bytes: int = Field(default=131072, ge=1024, le=1048576)
    upload_ttl_seconds: int = Field(default=600, ge=1, le=3600)
    stream_page_size: int = Field(default=32, ge=1, le=100)
    stream_send_timeout: float = Field(default=5, ge=0.1, le=30)


class IdentityInfo(BaseModel):
    identity_id: str
    persistent: bool
    remaining_seconds: int
    expires_at: float
    # The cookie is a bearer credential; it never appears in this public model.


@dataclass(frozen=True)
class IdentityRecord:
    owner: str
    expires_at: float
    revoked: bool = False


class IdentityPort(LifecycleHandle, Protocol):
    def owner(self, token: str) -> str: ...
    def info(self, token: str) -> IdentityInfo: ...
    async def session(self, token: str) -> tuple[str, IdentityInfo]: ...
    async def revoke(self, token: str) -> None: ...
    async def adopt_legacy(self, token: str) -> tuple[str, IdentityInfo]: ...


class IdentityStore:
    def __init__(self, config: ServerSettings, runtime: RuntimeDependencies) -> None:
        self.config, self.runtime = config, runtime
        self.records: dict[str, IdentityRecord] = {}
        self.db: apsw.Connection | None = None
        self.lease: int | None = None
        self.lock = asyncio.Lock()
        self.ready = False

    @staticmethod
    def digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _open(self) -> None:
        self.config.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.config.directory / "identity.sqlite3"
        if self.config.directory.is_symlink() or path.is_symlink():
            raise ApplicationError(
                503, "identity_path_invalid", "Identity storage cannot use a symlink"
            )
        self.lease = os.open(
            self.config.directory / "identity.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(self.lease)
            self.lease = None
            raise ApplicationError(
                503, "identity_store_owned", "Only one service may own identity storage"
            ) from error
        self.db = apsw.Connection(str(path))
        os.chmod(path, 0o600)
        self.db.set_busy_timeout(1000)
        version = int(self.db.pragma("user_version"))
        if version not in {0, 1}:
            raise ApplicationError(
                503, "identity_schema_incompatible", "Unsupported identity schema"
            )
        self.db.pragma("journal_mode", "wal")
        self.db.pragma("synchronous", "full")
        with self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS identities (digest TEXT PRIMARY KEY, "
                "owner TEXT NOT NULL, expires REAL NOT NULL, revoked INTEGER NOT NULL)"
            )
            self.db.pragma("user_version", 1)
        self.records = {
            str(digest): IdentityRecord(str(owner), float(expires), bool(revoked))
            for digest, owner, expires, revoked in self.db.execute(
                "SELECT digest,owner,expires,revoked FROM identities"
            )
        }

    async def start(self) -> None:
        if self.ready:
            return
        if self.config.identity_backend == "sqlite":
            await anyio.to_thread.run_sync(self._open)
        self.ready = True

    async def close(self) -> None:
        self.ready = False

        def close() -> None:
            if self.db is not None:
                self.db.close()
                self.db = None
            if self.lease is not None:
                os.close(self.lease)
                self.lease = None

        await anyio.to_thread.run_sync(close)

    def owner(self, token: str) -> str:
        if not self.ready:
            raise ApplicationError(503, "identity_not_ready", "Identity service is unavailable")
        record = (
            self.records.get(self.digest(token))
            if re.fullmatch(r"[a-zA-Z0-9_-]{43}", token)
            else None
        )
        if record is None or record.revoked or record.expires_at <= self.runtime.now().timestamp():
            raise ApplicationError(401, "session_required", "Reconnect with a valid local session")
        return record.owner

    def info(self, token: str) -> IdentityInfo:
        owner = self.owner(token)
        return IdentityInfo(
            identity_id=self.digest(owner)[:24],
            persistent=self.config.identity_backend == "sqlite",
            remaining_seconds=max(
                1, int(self.records[self.digest(token)].expires_at - self.runtime.now().timestamp())
            ),
            expires_at=self.records[self.digest(token)].expires_at,
        )

    async def _persist(self, digest: str, record: IdentityRecord) -> None:
        def write() -> None:
            if self.config.identity_backend == "sqlite" and self.db is None:
                raise ApplicationError(503, "identity_not_ready", "Identity storage is unavailable")
            if self.db is not None:
                with self.db:
                    self.db.execute(
                        "INSERT OR REPLACE INTO identities VALUES(?,?,?,?)",
                        (digest, record.owner, record.expires_at, int(record.revoked)),
                    )

        await anyio.to_thread.run_sync(write)
        self.records[digest] = record

    async def _prune(self) -> None:
        # Retain legacy tombstones: removing one could re-enable an old bearer.
        expired = [
            digest
            for digest, record in self.records.items()
            if record.expires_at < self.runtime.now().timestamp() - 604800
            and digest != self.digest(record.owner)
        ]

        def delete() -> None:
            if self.db is not None:
                with self.db:
                    self.db.executemany(
                        "DELETE FROM identities WHERE digest=?", ((key,) for key in expired)
                    )

        if expired:
            await anyio.to_thread.run_sync(delete)
            for digest in expired:
                self.records.pop(digest, None)

    async def session(self, token: str) -> tuple[str, IdentityInfo]:
        async with self.lock:
            if token:
                return token, self.info(token)
            if not self.ready:
                raise ApplicationError(503, "identity_not_ready", "Identity service is unavailable")
            await self._prune()
            if len(self.records) >= self.config.max_identities:
                raise ApplicationError(429, "identity_limit", "Local identity limit reached")
            token = token_urlsafe(32)
            record = IdentityRecord(
                "usr_" + token_urlsafe(24),
                self.runtime.now().timestamp() + self.config.identity_ttl_seconds,
            )
            await self._persist(self.digest(token), record)
            return token, self.info(token)

    async def adopt_legacy(self, token: str) -> tuple[str, IdentityInfo]:
        # Caller must prove this old bearer owns a legacy project before adoption.
        async with self.lock:
            if not re.fullmatch(r"[a-zA-Z0-9_-]{43}", token):
                raise ApplicationError(401, "legacy_identity_invalid", "No legacy local cookie")
            if self.digest(token) in self.records:
                raise ApplicationError(409, "identity_already_known", "Use the existing identity")
            if not self.ready:
                raise ApplicationError(503, "identity_not_ready", "Identity service unavailable")
            if len(self.records) + 2 > self.config.max_identities:
                raise ApplicationError(429, "identity_limit", "Local identity limit reached")
            replacement = token_urlsafe(32)
            records = {
                self.digest(replacement): IdentityRecord(
                    token, self.runtime.now().timestamp() + self.config.identity_ttl_seconds
                ),
                self.digest(token): IdentityRecord(token, 0, True),
            }

            def write() -> None:
                if self.config.identity_backend == "sqlite" and self.db is None:
                    raise ApplicationError(
                        503, "identity_not_ready", "Identity storage unavailable"
                    )
                if self.db is not None:
                    with self.db:
                        self.db.executemany(
                            "INSERT OR REPLACE INTO identities VALUES(?,?,?,?)",
                            (
                                (digest, r.owner, r.expires_at, int(r.revoked))
                                for digest, r in records.items()
                            ),
                        )

            await anyio.to_thread.run_sync(write)
            self.records.update(records)
            return replacement, self.info(replacement)

    async def revoke(self, token: str) -> None:
        async with self.lock:
            self.owner(token)
            old = self.records[self.digest(token)]
            await self._persist(self.digest(token), IdentityRecord(old.owner, old.expires_at, True))


class IdentityFactory:
    def create(self, config: ServerSettings, runtime: RuntimeDependencies) -> IdentityPort:
        return IdentityStore(config, runtime)
