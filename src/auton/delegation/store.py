"""Private supervisor state and durable output leases; writes never imply tool approval."""

import fcntl
import hashlib
import json
import os
import unicodedata

import anyio
import apsw
from pydantic import JsonValue

from auton.delegation.contracts import (
    DelegationConfig,
    DelegationView,
    SingleMultiContrast,
    identity,
)
from auton.kernel.events import Event, EventScope
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.kernel.storage import EventLogPort


class WorkspaceLeases:
    def __init__(self, store: "DelegationStore") -> None:
        self.store = store

    def acquire(self, owner: str, workspace: str, path: str, parent: str) -> None:
        # Conservatively reserve aliases used by case-insensitive / Unicode-normalizing disks.
        path = unicodedata.normalize("NFD", path).casefold()
        db = self.store.database()
        for target, holder in db.execute(
            "SELECT path,parent FROM leases WHERE owner=? AND workspace=?", (owner, workspace)
        ):
            if holder != parent and (
                path == target or path.startswith(target + "/") or target.startswith(path + "/")
            ):
                raise ApplicationError(
                    409, "delegation_write_conflict", "Another supervisor owns this output path"
                )
        db.execute("INSERT OR IGNORE INTO leases VALUES(?,?,?,?)", (owner, workspace, path, parent))


class WorkspaceLeaseFactory:
    def create(self, store: "DelegationStore") -> WorkspaceLeases:
        return WorkspaceLeases(store)


class DelegationStore:
    def __init__(
        self, config: DelegationConfig, events: EventLogPort, runtime: RuntimeDependencies
    ) -> None:
        self.config, self.events, self.runtime = config, events, runtime
        self.db: apsw.Connection | None = None
        self.lease: int | None = None
        self.leases = WorkspaceLeaseFactory().create(self)

    async def start(self) -> None:
        def open_database() -> None:
            root = self.config.directory
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = root / "supervisors.sqlite3"
            if root.is_symlink() or path.is_symlink():
                raise ApplicationError(
                    503, "delegation_path_invalid", "Supervisor database cannot be a symlink"
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
                    503, "delegation_owned", "Another supervisor service owns state"
                ) from error
            self.db = apsw.Connection(str(path))
            path.chmod(0o600)
            self.db.set_busy_timeout(1000)
            if int(self.db.pragma("user_version")) not in {0, 1}:
                raise ApplicationError(
                    503, "delegation_schema_incompatible", "Unknown supervisor schema"
                )
            self.db.pragma("journal_mode", "wal")
            self.db.pragma("synchronous", "full")
            with self.db:
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS states(owner TEXT,id TEXT,version INTEGER,"
                    "document TEXT,digest TEXT,PRIMARY KEY(owner,id,version))"
                )
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS heads(owner TEXT,id TEXT,version INTEGER,"
                    "PRIMARY KEY(owner,id))"
                )
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS commands(owner TEXT,request TEXT,parent TEXT,"
                    "digest TEXT,PRIMARY KEY(owner,request))"
                )
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS leases(owner TEXT,workspace TEXT,path TEXT,"
                    "parent TEXT,PRIMARY KEY(owner,workspace,path))"
                )
                self.db.pragma("user_version", 1)

        await anyio.to_thread.run_sync(open_database)

    async def close(self) -> None:
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.lease is not None:
            os.close(self.lease)
            self.lease = None

    def database(self) -> apsw.Connection:
        if self.db is None:
            raise ApplicationError(503, "delegation_not_ready", "Supervisor storage is unavailable")
        return self.db

    async def load(self, owner: str, parent: str) -> DelegationView:
        def read() -> DelegationView:
            row = (
                self.database()
                .execute(
                    "SELECT s.document,s.digest FROM states s JOIN heads h USING(owner,id,version) "
                    "WHERE owner=? AND id=?",
                    (owner, parent),
                )
                .fetchone()
            )
            if row is None:
                raise ApplicationError(404, "delegation_missing", "No owned supervisor")
            document = str(row[0])
            if hashlib.sha256(document.encode()).hexdigest() != row[1]:
                raise ApplicationError(
                    409, "delegation_corrupt", "Supervisor document digest mismatch"
                )
            return DelegationView.model_validate_json(document)

        value = await anyio.to_thread.run_sync(read)
        await self.audit(owner, value)
        return value

    async def list(self, owner: str) -> tuple[DelegationView, ...]:
        def ids() -> list[str]:
            return [
                str(row[0])
                for row in self.database().execute(
                    "SELECT id FROM heads WHERE owner=? ORDER BY rowid", (owner,)
                )
            ]

        return tuple([await self.load(owner, item) for item in await anyio.to_thread.run_sync(ids)])

    async def receipt(self, owner: str, request: str, parent: str, command: object) -> bool:
        digest = hashlib.sha256(json.dumps(command, sort_keys=True).encode()).hexdigest()

        def read() -> bool:
            row = (
                self.database()
                .execute(
                    "SELECT parent,digest FROM commands WHERE owner=? AND request=?",
                    (owner, request),
                )
                .fetchone()
            )
            if row is None:
                return False
            if row != (parent, digest):
                raise ApplicationError(
                    409, "delegation_command_conflict", "Request id has different supervisor input"
                )
            return True

        return await anyio.to_thread.run_sync(read)

    async def save(
        self,
        owner: str,
        value: DelegationView,
        expected: int | None,
        request: str | None = None,
        command: object = None,
    ) -> None:
        document = value.model_dump_json()

        def write() -> None:
            db = self.database()
            with db:
                old = db.execute(
                    "SELECT version FROM heads WHERE owner=? AND id=?", (owner, value.id)
                ).fetchone()
                if (int(old[0]) if old else None) != expected:
                    raise ApplicationError(
                        409, "delegation_version_changed", "Supervisor has changed"
                    )
                if old is None:
                    count = db.execute(
                        "SELECT count(*) FROM heads WHERE owner=?", (owner,)
                    ).fetchone()
                    if count and int(count[0]) >= self.config.max_parents:
                        raise ApplicationError(
                            429, "delegation_capacity", "Supervisor history capacity reached"
                        )
                    assert value.command.acceptance.path
                    self.leases.acquire(
                        owner, value.command.workspace_id, value.command.acceptance.path, value.id
                    )
                if value.status in {"integrated", "cancelled"}:
                    db.execute("DELETE FROM leases WHERE owner=? AND parent=?", (owner, value.id))
                db.execute(
                    "INSERT INTO states VALUES(?,?,?,?,?)",
                    (
                        owner,
                        value.id,
                        value.version,
                        document,
                        hashlib.sha256(document.encode()).hexdigest(),
                    ),
                )
                db.execute(
                    "INSERT OR REPLACE INTO heads VALUES(?,?,?)", (owner, value.id, value.version)
                )
                if request:
                    fingerprint = hashlib.sha256(
                        json.dumps(command, sort_keys=True).encode()
                    ).hexdigest()
                    db.execute(
                        "INSERT INTO commands VALUES(?,?,?,?)",
                        (owner, request, value.id, fingerprint),
                    )

        await anyio.to_thread.run_sync(write)
        await self.audit(owner, value)

    async def contrast(
        self, owner: str, request_id: str, value: SingleMultiContrast, command: dict[str, JsonValue]
    ) -> None:
        event_id = "delegation-contrast:" + identity(owner, value.supervisor_id + request_id)
        payload: dict[str, JsonValue] = {
            "comparison": value.model_dump(mode="json"),
            "command": command,
        }
        old = await self.events.lookup(event_id)
        if old:
            if old.event.payload != payload:
                raise ApplicationError(
                    409,
                    "delegation_contrast_changed",
                    "Comparison input or evidence changed; use a new request id",
                )
            return
        await self.events.append(
            [
                Event(
                    event_id=event_id,
                    kind="delegation.contrast",
                    timestamp=self.runtime.now(),
                    source=value.source,
                    scope=EventScope.model_validate({"run_id": value.supervisor_id}),
                    payload=payload,
                )
            ]
        )

    async def audit(self, owner: str, value: DelegationView) -> None:
        event_id = "delegation:" + identity(owner, value.id) + ":" + str(value.version)
        old = await self.events.lookup(event_id)
        if old:
            if DelegationView.model_validate(old.event.payload["supervisor"]) != value:
                raise ApplicationError(
                    409,
                    "delegation_audit_mismatch",
                    "Supervisor differs from its audited checkpoint",
                )
            return
        from datetime import UTC, datetime

        await self.events.append(
            [
                Event(
                    event_id=event_id,
                    kind="delegation.checkpoint",
                    timestamp=datetime.fromtimestamp(value.updated_at, UTC),
                    scope=EventScope.model_validate(
                        {
                            "project_id": value.command.project_id,
                            "run_id": value.id,
                            "goal_revision": value.goal_revision,
                        }
                    ),
                    source=value.source,
                    payload={"supervisor": value.model_dump(mode="json")},
                )
            ]
        )
