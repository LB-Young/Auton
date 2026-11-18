import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypeVar

import anyio
import apsw

from auton.experience.contracts import CheckpointReference, IndexedEvent
from auton.kernel.events import StoredEvent
from auton.kernel.ports import ApplicationError

T = TypeVar("T")


class SQLiteProjection:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.db: apsw.Connection | None = None
        self.lock = threading.RLock()

    def _open(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.directory.is_symlink():
            raise ApplicationError(
                503, "projection_path_invalid", "Projection directory cannot be a symlink"
            )
        path = self.directory / "projections.sqlite3"
        if path.is_symlink():
            raise ApplicationError(
                503, "projection_path_invalid", "Projection file cannot be a symlink"
            )
        self.db = apsw.Connection(str(path))
        self.db.set_busy_timeout(1000)
        version = int(self.db.pragma("user_version"))
        if version not in {0, 1, 2}:
            raise ApplicationError(
                503,
                "projection_schema_incompatible",
                "Unsupported projection schema; do not interpret unknown checkpoints",
            )
        self.db.pragma("journal_mode", "wal")
        self.db.pragma("synchronous", "full")
        with self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS events (cursor INTEGER PRIMARY KEY, "
                "event_id TEXT UNIQUE NOT NULL, digest TEXT NOT NULL, kind TEXT NOT NULL, "
                "run_id TEXT, goal_id TEXT, operation_id TEXT, event_time TEXT NOT NULL, "
                "source TEXT NOT NULL)"
            )
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), "
                "cursor INTEGER NOT NULL)"
            )
            self.db.execute("INSERT OR IGNORE INTO meta VALUES (1,0)")
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS checkpoints "
                "(run_id TEXT PRIMARY KEY, document TEXT NOT NULL)"
            )
            columns = {row[1] for row in self.db.execute("PRAGMA table_info(events)")}
            if "processed_at" not in columns:
                self.db.execute(
                    "ALTER TABLE events ADD COLUMN processed_at TEXT NOT NULL DEFAULT ''"
                )
            self.db.execute("CREATE INDEX IF NOT EXISTS events_run ON events(run_id)")
            self.db.execute("CREATE INDEX IF NOT EXISTS events_goal ON events(goal_id)")
            self.db.execute("CREATE INDEX IF NOT EXISTS events_operation ON events(operation_id)")
            if version == 1:
                self.db.execute("DELETE FROM events")
                self.db.execute("DELETE FROM checkpoints")
                self.db.execute("UPDATE meta SET cursor=0 WHERE id=1")
            self.db.pragma("user_version", 2)

    def _connection(self) -> apsw.Connection:
        if self.db is None:
            raise ApplicationError(503, "projection_not_ready", "Projection store has not started")
        return self.db

    async def _call(self, operation: Callable[[], T]) -> T:
        def guarded() -> T:
            with self.lock:
                return operation()

        return await anyio.to_thread.run_sync(guarded)

    async def start(self) -> None:
        if self.db is None:
            await self._call(self._open)

    async def close(self) -> None:
        def close() -> None:
            if self.db is not None:
                self.db.close()
                self.db = None

        await self._call(close)

    async def position(self) -> int:
        return await self._call(
            lambda: int(self._connection().execute("SELECT cursor FROM meta WHERE id=1").get)
        )

    async def apply(self, rows: Sequence[StoredEvent], processed_at: str) -> None:
        def apply() -> None:
            db = self._connection()
            with db:
                cursor = int(db.execute("SELECT cursor FROM meta WHERE id=1").get)
                for row in rows:
                    event = row.event
                    old = db.execute(
                        "SELECT event_id,digest FROM events WHERE cursor=?", (row.cursor,)
                    ).get
                    if row.cursor <= cursor:
                        if old != (event.event_id, event.digest()):
                            raise ApplicationError(
                                409,
                                "projection_conflict",
                                "Repeated cursor has different or missing data",
                            )
                        continue
                    db.execute(
                        "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            row.cursor,
                            event.event_id,
                            event.digest(),
                            event.kind,
                            event.scope.run_id,
                            event.scope.goal_id,
                            event.scope.operation_id,
                            event.timestamp.isoformat(),
                            event.source,
                            processed_at,
                        ),
                    )
                    if event.kind == "agent.checkpoint":
                        value = event.payload.get("run")
                        if isinstance(value, dict):
                            raw_version = value.get("version")
                            version = raw_version if type(raw_version) is int else -1
                            ref = CheckpointReference(
                                session_id=str(value.get("session_id", "")),
                                goal_id=str(event.scope.goal_id or ""),
                                project_id=str(event.scope.project_id or ""),
                                run_id=str(value.get("id", "")),
                                cursor=row.cursor,
                                event_id=event.event_id,
                                version=version,
                                runtime_revision=str(value.get("runtime_revision", "unknown")),
                                digest=event.digest(),
                            )
                            old_ref = db.execute(
                                "SELECT document FROM checkpoints WHERE run_id=?", (ref.run_id,)
                            ).get
                            if (
                                old_ref is None
                                or CheckpointReference.model_validate_json(str(old_ref)).version
                                < ref.version
                            ):
                                db.execute(
                                    "INSERT OR REPLACE INTO checkpoints VALUES(?,?)",
                                    (ref.run_id, ref.model_dump_json()),
                                )
                    cursor = row.cursor
                db.execute("UPDATE meta SET cursor=? WHERE id=1", (cursor,))

        await self._call(apply)

    async def checkpoint(self, run_id: str) -> CheckpointReference | None:
        def read() -> CheckpointReference | None:
            value = (
                self._connection()
                .execute("SELECT document FROM checkpoints WHERE run_id=?", (run_id,))
                .get
            )
            return (
                CheckpointReference.model_validate_json(str(value)) if value is not None else None
            )

        return await self._call(read)

    async def select(
        self, run_id: str, goal_id: str, operations: tuple[str, ...], limit: int
    ) -> list[IndexedEvent]:
        def read() -> list[IndexedEvent]:
            placeholders = ",".join("?" for _ in operations) or "NULL"
            rows = (
                self._connection()
                .execute(
                    (
                        "SELECT cursor,event_id,digest,kind,run_id,goal_id,operation_id,"
                        "event_time,source,processed_at FROM events "
                        f"WHERE run_id=? OR goal_id=? OR operation_id IN ({placeholders}) "
                        "ORDER BY cursor LIMIT ?"
                    ),
                    (run_id, goal_id, *operations, limit),
                )
                .fetchall()
            )
            return [
                IndexedEvent.model_validate(
                    dict(
                        zip(
                            (
                                "cursor",
                                "event_id",
                                "digest",
                                "kind",
                                "run_id",
                                "goal_id",
                                "operation_id",
                                "event_time",
                                "source",
                                "processed_at",
                            ),
                            r,
                            strict=True,
                        )
                    )
                )
                for r in rows
            ]

        return await self._call(read)

    async def rebuild(self) -> None:
        def reset() -> None:
            db = self._connection()
            with db:
                db.execute("DELETE FROM events")
                db.execute("DELETE FROM checkpoints")
                db.execute("UPDATE meta SET cursor=0 WHERE id=1")

        await self._call(reset)
