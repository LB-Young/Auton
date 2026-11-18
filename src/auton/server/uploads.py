import asyncio
import hashlib
from typing import Literal, Protocol

import anyio
import apsw
from pydantic import Field

from auton.constitution.config import Principal
from auton.genome.contracts import Asset
from auton.genome.ports import GenomePort
from auton.kernel.ports import ApplicationError, LifecycleHandle, RuntimeDependencies
from auton.model.contracts import Contract
from auton.server.identity import ServerSettings


class UploadCommand(Contract):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    project_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    filename: str = Field(min_length=1, max_length=128, pattern=r"^[^/\\\x00-\x1f]+$")
    size_bytes: int = Field(ge=1, le=1048576)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class UploadReceipt(Contract):
    id: str
    project_id: str
    asset_id: str
    sha256: str
    size_bytes: int
    candidates_revision: str | None
    status: Literal["candidate"] = "candidate"


class UploadIntent(Contract):
    id: str
    project_id: str
    filename: str
    size_bytes: int
    sha256: str
    expires_at: float
    receipt: UploadReceipt | None = None


class UploadRecord(Contract):
    owner: str
    command: UploadCommand
    expected: str | None
    intent: UploadIntent


class UploadPort(LifecycleHandle, Protocol):
    async def prepare(self, principal: Principal, command: UploadCommand) -> UploadIntent: ...
    async def complete(
        self, principal: Principal, identity: str, content: bytes
    ) -> UploadReceipt: ...


class UploadService:
    def __init__(
        self, config: ServerSettings, genome: GenomePort, runtime: RuntimeDependencies
    ) -> None:
        self.config, self.genome, self.runtime = config, genome, runtime
        self.db: apsw.Connection | None = None
        self.records: dict[str, UploadRecord] = {}
        self.lock = asyncio.Lock()
        self.ready = False
        self.active: dict[str, asyncio.Task[UploadReceipt]] = {}

    def _open(self) -> None:
        path = self.config.directory / "uploads.sqlite3"
        self.config.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.is_symlink() or self.config.directory.is_symlink():
            raise ApplicationError(
                503, "upload_path_invalid", "Upload metadata path cannot be a symlink"
            )
        self.db = apsw.Connection(str(path))
        import os

        os.chmod(path, 0o600)
        self.db.set_busy_timeout(1000)
        if int(self.db.pragma("user_version")) not in {0, 1}:
            raise ApplicationError(503, "upload_schema_incompatible", "Unsupported upload schema")
        self.db.pragma("journal_mode", "wal")
        self.db.pragma("synchronous", "full")
        with self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS uploads (id TEXT PRIMARY KEY, document TEXT NOT NULL)"
            )
            self.db.pragma("user_version", 1)
        self.records = {
            str(identity): UploadRecord.model_validate_json(str(document))
            for identity, document in self.db.execute("SELECT id,document FROM uploads")
        }

    async def start(self) -> None:
        if self.ready:
            return
        if self.config.identity_backend == "sqlite":
            await anyio.to_thread.run_sync(self._open)
        self.ready = True
        await self.cleanup()

    async def close(self) -> None:
        self.ready = False
        await asyncio.gather(*list(self.active.values()), return_exceptions=True)

        def close() -> None:
            if self.db is not None:
                self.db.close()
                self.db = None

        await anyio.to_thread.run_sync(close)

    async def cleanup(self) -> None:
        expired = [
            identity
            for identity, record in self.records.items()
            if record.intent.expires_at < self.runtime.now().timestamp() - 604800
        ]

        def delete() -> None:
            if self.db is not None:
                with self.db:
                    self.db.executemany(
                        "DELETE FROM uploads WHERE id=?", ((identity,) for identity in expired)
                    )

        if expired:
            await anyio.to_thread.run_sync(delete)
            for identity in expired:
                self.records.pop(identity, None)

    async def save(self, record: UploadRecord) -> None:
        def save() -> None:
            if self.config.identity_backend == "sqlite" and self.db is None:
                raise ApplicationError(503, "upload_not_ready", "Upload storage is unavailable")
            if self.db is not None:
                with self.db:
                    self.db.execute(
                        "INSERT OR REPLACE INTO uploads VALUES(?,?)",
                        (record.intent.id, record.model_dump_json()),
                    )

        await anyio.to_thread.run_sync(save)
        self.records[record.intent.id] = record

    @staticmethod
    def actor(principal: Principal) -> None:
        if principal.role != "user":
            raise ApplicationError(
                403, "upload_user_required", "Only explicit user imports are supported"
            )

    async def prepare(self, principal: Principal, command: UploadCommand) -> UploadIntent:
        self.actor(principal)
        if not self.ready:
            raise ApplicationError(503, "upload_not_ready", "Upload service is stopping")
        async with self.lock:
            await self.cleanup()
            identity = hashlib.sha256(
                (principal.owner + "\0" + command.request_id).encode()
            ).hexdigest()
            old = self.records.get(identity)
            if old:
                if old.command != command:
                    raise ApplicationError(
                        409,
                        "upload_request_conflict",
                        "Upload request id belongs to different input",
                    )
                return old.intent
            if command.size_bytes > self.config.max_upload_bytes:
                raise ApplicationError(
                    413, "upload_too_large", "Upload exceeds the configured byte limit"
                )
            if len(self.records) >= 1000:
                raise ApplicationError(429, "upload_limit", "Upload metadata limit reached")
            state = await self.genome.view(principal, command.project_id)
            intent = UploadIntent(
                id=identity,
                project_id=command.project_id,
                filename=command.filename,
                size_bytes=command.size_bytes,
                sha256=command.sha256,
                expires_at=self.runtime.now().timestamp() + self.config.upload_ttl_seconds,
            )
            await self.save(
                UploadRecord(
                    owner=principal.owner,
                    command=command,
                    expected=state.candidates_revision,
                    intent=intent,
                )
            )
            return intent

    async def complete(self, principal: Principal, identity: str, content: bytes) -> UploadReceipt:
        self.actor(principal)
        if not self.ready:
            raise ApplicationError(503, "upload_not_ready", "Upload service is stopping")
        record = self.records.get(identity)
        if record is None or record.owner != principal.owner:
            raise ApplicationError(404, "upload_not_found", "No owned upload intent")
        if (
            len(content) != record.intent.size_bytes
            or hashlib.sha256(content).hexdigest() != record.intent.sha256
        ):
            raise ApplicationError(
                422, "upload_digest_mismatch", "Upload bytes differ from the declared content"
            )
        if identity not in self.active:
            task = asyncio.create_task(self._complete(principal, identity, content))
            self.active[identity] = task

            def completed(done: asyncio.Task[UploadReceipt]) -> None:
                self.active.pop(identity, None)
                if not done.cancelled():
                    done.exception()

            task.add_done_callback(completed)
        return await asyncio.shield(self.active[identity])

    async def _complete(self, principal: Principal, identity: str, content: bytes) -> UploadReceipt:
        async with self.lock:
            record = self.records[identity]
            if record.intent.receipt:
                return record.intent.receipt
            if record.intent.expires_at <= self.runtime.now().timestamp():
                raise ApplicationError(
                    410, "upload_expired", "Upload intent expired; create a new request"
                )
            try:
                text = content.decode("utf-8")
            except UnicodeError as error:
                raise ApplicationError(
                    422, "upload_encoding", "Only UTF-8 text/Markdown is supported"
                ) from error
            if not text or len(text) > 32000:
                raise ApplicationError(
                    413, "upload_text_limit", "Asset text exceeds the 32000 character limit"
                )
            asset = Asset(
                id="upload_" + identity[:40],
                name=record.intent.filename,
                kind="document",
                origin="user_explicit",
                source=f"upload:{identity}; sha256:{record.intent.sha256}",
                content=text,
            )

            async def existing() -> tuple[bool, str | None]:
                state = await self.genome.view(principal, record.intent.project_id)
                item = next(
                    (r.asset for r in (*state.assets, *state.candidates) if r.asset.id == asset.id),
                    None,
                )
                if item is None:
                    return False, None
                if item != asset:
                    raise ApplicationError(
                        409, "upload_asset_conflict", "Existing upload asset differs"
                    )
                return True, state.candidates_revision

            found, revision = await existing()
            if not found:
                try:
                    state = await self.genome.propose(
                        principal, record.intent.project_id, asset, record.expected
                    )
                    revision = state.candidates_revision
                except ApplicationError:
                    found, revision = await existing()
                    if not found:
                        raise
            receipt = UploadReceipt(
                id=identity,
                project_id=record.intent.project_id,
                asset_id=asset.id,
                sha256=record.intent.sha256,
                size_bytes=len(content),
                candidates_revision=revision,
            )
            await self.save(
                record.model_copy(
                    update={"intent": record.intent.model_copy(update={"receipt": receipt})}
                )
            )
            return receipt


class UploadFactory:
    def create(
        self, config: ServerSettings, genome: GenomePort, runtime: RuntimeDependencies
    ) -> UploadPort:
        return UploadService(config, genome, runtime)
