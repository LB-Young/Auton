"""Immutable proposal/job versions plus bounded, recoverable control receipts."""

import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Protocol

import anyio
import apsw
from pydantic import JsonValue

from auton.kernel.events import Event, EventScope
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.kernel.storage import EventLogPort


class DocumentStoreConfig(Protocol):
    @property
    def directory(self) -> Path: ...
    @property
    def max_documents(self) -> int: ...
    @property
    def digest(self) -> str: ...


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def key(owner: str, value: str) -> str:
    return hashlib.sha256((owner + "\0" + value).encode()).hexdigest()


class VersionedDocumentStore:
    def __init__(
        self,
        config: DocumentStoreConfig,
        events: EventLogPort,
        runtime: RuntimeDependencies,
        test: bool,
        namespace: str,
    ) -> None:
        if re.fullmatch(r"[a-z][a-z0-9_]{0,32}", namespace) is None:
            raise ValueError("Store namespace must be a fixed module identifier")
        self.namespace = namespace
        self.config, self.events, self.runtime, self.test = config, events, runtime, test
        self.db: apsw.Connection | None = None
        self.lease: int | None = None
        self.ready = False

    async def start(self) -> None:
        if self.ready:
            return
        if self.db is not None:
            await self.close()

        def open_database() -> None:
            root = self.config.directory
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = root / (self.namespace + ".sqlite3")
            if root.is_symlink() or path.is_symlink():
                raise ApplicationError(
                    503,
                    self.namespace + "_path_invalid",
                    "Versioned document store cannot be a symlink",
                )
            root.chmod(0o700)
            self.lease = os.open(
                root / "service.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
            )
            try:
                fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                os.close(self.lease)
                self.lease = None
                raise ApplicationError(
                    503,
                    self.namespace + "_store_owned",
                    "Another process owns this document store",
                ) from error
            self.db = apsw.Connection(str(path))
            path.chmod(0o600)
            if int(self.db.pragma("user_version")) not in {0, 1}:
                raise ApplicationError(
                    503,
                    self.namespace + "_schema_incompatible",
                    "Unsupported decision_review store schema",
                )
            self.db.set_busy_timeout(1000)
            self.db.pragma("journal_mode", "wal")
            self.db.pragma("synchronous", "full")
            with self.db:
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS documents(kind TEXT,owner TEXT,id TEXT,"
                    "version INTEGER,payload TEXT,digest TEXT,created REAL,"
                    "PRIMARY KEY(kind,owner,id,version))"
                )
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS heads(kind TEXT,owner TEXT,id TEXT,"
                    "version INTEGER,PRIMARY KEY(kind,owner,id))"
                )
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS receipts(owner TEXT,id TEXT,"
                    "kind TEXT,document_id TEXT,digest TEXT,PRIMARY KEY(owner,id))"
                )
                self.db.pragma("user_version", 1)

        try:
            await anyio.to_thread.run_sync(open_database)
        except BaseException:
            await self.close()
            raise
        self.ready = True

    async def close(self) -> None:
        self.ready = False
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.lease is not None:
            os.close(self.lease)
            self.lease = None

    def database(self) -> apsw.Connection:
        if self.db is None or not self.ready:
            raise ApplicationError(
                503, self.namespace + "_not_ready", "Versioned document store is unavailable"
            )
        return self.db

    async def capacity(self, owner: str, needed: int = 1) -> None:
        def count() -> int:
            row = (
                self.database()
                .execute("SELECT count(*) FROM documents WHERE owner=?", (owner,))
                .fetchone()
            )
            return int(row[0]) if row else 0

        if await anyio.to_thread.run_sync(count) + needed > self.config.max_documents:
            raise ApplicationError(
                429, self.namespace + "_capacity", "Versioned document document capacity reached"
            )

    async def get(self, kind: str, owner: str, identity: str) -> dict[str, Any] | None:
        def read() -> tuple[dict[str, Any], int, float] | None:
            row = (
                self.database()
                .execute(
                    "SELECT d.payload,d.digest,d.version,d.created FROM documents d JOIN heads h "
                    "USING(kind,owner,id,version) WHERE kind=? AND owner=? AND id=?",
                    (kind, owner, identity),
                )
                .fetchone()
            )
            if row is None:
                return None
            value: dict[str, Any] = json.loads(str(row[0]))
            if digest(value) != row[1]:
                raise ApplicationError(
                    409, self.namespace + "_document_corrupt", "Versioned document digest mismatch"
                )
            return value, int(row[2]), float(row[3])

        found = await anyio.to_thread.run_sync(read)
        if found is None:
            return None
        value, version, created = found
        await self.audit(kind, owner, identity, version, value, created)
        return value

    async def list(self, kind: str, owner: str) -> tuple[dict[str, Any], ...]:
        def ids() -> list[str]:
            return [
                str(row[0])
                for row in self.database().execute(
                    "SELECT id FROM heads WHERE kind=? AND owner=? ORDER BY rowid", (kind, owner)
                )
            ]

        result = []
        for identity in await anyio.to_thread.run_sync(ids):
            value = await self.get(kind, owner, identity)
            if value is not None:
                result.append(value)
        return tuple(result)

    async def receipt(
        self, owner: str, request: str, kind: str, identity: str, command: object
    ) -> bool:
        fingerprint = digest(command)

        def read() -> bool:
            row = (
                self.database()
                .execute(
                    "SELECT kind,document_id,digest FROM receipts WHERE owner=? AND id=?",
                    (owner, request),
                )
                .fetchone()
            )
            if row is None:
                return False
            if row != (kind, identity, fingerprint):
                raise ApplicationError(
                    409,
                    self.namespace + "_request_conflict",
                    "Request id has different immutable input",
                )
            return True

        return await anyio.to_thread.run_sync(read)

    async def put(
        self,
        kind: str,
        owner: str,
        identity: str,
        value: dict[str, Any],
        expected: int | None,
        request: str | None = None,
        command: object = None,
    ) -> None:
        version = 0 if expected is None else expected + 1
        if version >= 65536:
            raise ApplicationError(
                429,
                self.namespace + "_version_limit",
                "Versioned document document reached history limit",
            )
        await self.capacity(owner)
        created = self.runtime.now().timestamp()

        def write() -> None:
            db = self.database()
            with db:
                old = db.execute(
                    "SELECT version FROM heads WHERE kind=? AND owner=? AND id=?",
                    (kind, owner, identity),
                ).fetchone()
                if (int(old[0]) if old else None) != expected:
                    raise ApplicationError(
                        409,
                        self.namespace + "_version_changed",
                        "Versioned document changed",
                    )
                db.execute(
                    "INSERT INTO documents VALUES(?,?,?,?,?,?,?)",
                    (
                        kind,
                        owner,
                        identity,
                        version,
                        json.dumps(value, ensure_ascii=False),
                        digest(value),
                        created,
                    ),
                )
                db.execute(
                    "INSERT OR REPLACE INTO heads VALUES(?,?,?,?)", (kind, owner, identity, version)
                )
                if request:
                    db.execute(
                        "INSERT INTO receipts VALUES(?,?,?,?,?)",
                        (owner, request, kind, identity, digest(command)),
                    )

        await anyio.to_thread.run_sync(write)
        await self.audit(kind, owner, identity, version, value, created)

    async def audit(
        self,
        kind: str,
        owner: str,
        identity: str,
        version: int,
        value: dict[str, Any],
        created: float,
    ) -> None:
        from datetime import UTC, datetime

        event_id = self.namespace + ":" + key(owner, kind + ":" + identity) + ":" + str(version)
        # Audit keeps lineage/digest only; it never exports candidate-evaluation inputs.
        payload: dict[str, JsonValue] = {
            "kind": kind,
            "document_id": identity,
            "version": version,
            "digest": digest(value),
            "config_digest": self.config.digest,
        }
        old = await self.events.lookup(event_id)
        if old:
            # A config change does not rewrite the immutable historical audit record.
            if any(
                old.event.payload.get(k) != payload[k]
                for k in ("kind", "document_id", "version", "digest")
            ):
                raise ApplicationError(
                    409,
                    self.namespace + "_audit_mismatch",
                    "Versioned document audit digest differs",
                )
            return
        project = value.get("project_id")
        if not isinstance(project, str) and isinstance(value.get("command"), dict):
            project = value["command"].get("project_id")
        scope = EventScope.model_validate(
            {"project_id": project} if isinstance(project, str) else {}
        )
        await self.events.append(
            [
                Event(
                    event_id=event_id,
                    kind=self.namespace + ".document",
                    timestamp=datetime.fromtimestamp(created, UTC),
                    scope=scope,
                    source="test" if self.test else "runtime",
                    payload=payload,
                )
            ]
        )


class VersionedDocumentStoreFactory:
    def create(
        self,
        config: DocumentStoreConfig,
        events: EventLogPort,
        runtime: RuntimeDependencies,
        test: bool,
        namespace: str,
    ) -> VersionedDocumentStore:
        return VersionedDocumentStore(config, events, runtime, test, namespace)
