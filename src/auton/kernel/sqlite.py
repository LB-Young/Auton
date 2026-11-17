import hashlib
import json
import threading
from collections.abc import Callable, Sequence
from typing import TypeVar

import apsw
from anyio import to_thread
from pydantic import ValidationError

from auton.kernel.config import KernelConfig
from auton.kernel.events import AppendReceipt, Event, EventScope, StorageInfo, StoredEvent
from auton.kernel.storage import StorageError, matches, validate_page

SCHEMA_VERSION = 2
APPLICATION_ID = 0x4155544E
T = TypeVar("T")


def storage_error(error: Exception, outcome: str = "not_committed") -> StorageError:
    code = "storage_io"
    if isinstance(error, (apsw.BusyError, apsw.LockedError)):
        code = "storage_busy"
    elif isinstance(error, apsw.FullError):
        code = "storage_full"
    elif isinstance(error, (apsw.CorruptError, apsw.NotADBError)):
        code = "storage_corrupt"
    elif isinstance(error, apsw.ReadOnlyError):
        code = "storage_readonly"
    return StorageError(
        code,
        "Event storage operation failed; inspect storage health before retrying",
        outcome="unknown" if outcome == "unknown" else "not_committed",
        retryable=code == "storage_busy",
    )


class SQLiteEventLog:
    """Single serialized connection; process-safe SQLite transactions and idempotent ids.

    No raw SQL or destructive event mutation is exposed by the public Port.
    Blocking disk operations run in a worker; cancellation does not abandon commits.
    """

    def __init__(self, config: KernelConfig) -> None:
        self.config = config
        self._connection: apsw.Connection | None = None
        self._lock = threading.RLock()

    async def _call(self, operation: Callable[[], T]) -> T:
        try:
            return await to_thread.run_sync(operation, abandon_on_cancel=False)
        except (apsw.Error, OSError) as error:
            raise storage_error(error) from error

    def _db(self) -> apsw.Connection:
        if self._connection is None:
            raise StorageError("not_ready", "Event store is not ready")
        return self._connection

    async def start(self) -> None:
        await self._call(self._open)

    def _open(self) -> None:
        with self._lock:
            if self._connection is not None:
                return
            # APSW embeds its own SQLite; never silently use an older system library.
            if tuple(map(int, apsw.sqlitelibversion().split("."))) < (3, 51, 3):
                raise StorageError("unsupported_sqlite", "SQLite >= 3.51.3 is required for WAL")
            path = self.config.event_path
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            existed = path.exists()
            connection = apsw.Connection(str(path))
            try:
                if not existed:
                    path.chmod(0o600)
                connection.set_busy_timeout(self.config.busy_timeout_ms)
                if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise StorageError("storage_corrupt", "Database integrity check failed")
                version = int(connection.pragma("user_version"))
                application = int(connection.pragma("application_id"))
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    )
                }
                if version not in (0, 1, SCHEMA_VERSION) or application not in (0, APPLICATION_ID):
                    raise StorageError("unsupported_schema", "Unsupported event database version")
                if (version == 0 and tables) or (version > 0 and tables != {"event_log"}):
                    raise StorageError("unsupported_schema", "Unrecognized event database layout")
                if version > 0:
                    expected = {"cursor", "event_id", "document"}
                    if version == 2:
                        expected.add("digest")
                    columns = {
                        str(row[1]) for row in connection.execute("PRAGMA table_info(event_log)")
                    }
                    if columns != expected:
                        raise StorageError(
                            "storage_corrupt", "Event table schema does not match version"
                        )
                connection.execute("BEGIN IMMEDIATE")
                try:
                    self._migrate(connection, version)
                    connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                    connection.execute("COMMIT")
                except BaseException:
                    if not connection.get_autocommit():
                        connection.execute("ROLLBACK")
                    raise
                if str(connection.pragma("journal_mode", "WAL")).lower() != "wal":
                    raise StorageError("unsupported_journal", "WAL could not be enabled")
                connection.pragma("synchronous", "FULL")
                if int(connection.pragma("synchronous")) != 2:
                    raise StorageError("unsupported_durability", "FULL synchronization is required")
                self._connection = connection
            except BaseException:
                connection.close()
                raise

    def _migrate(self, connection: apsw.Connection, version: int) -> None:
        if version == 0:
            connection.execute(
                "CREATE TABLE event_log (cursor INTEGER PRIMARY KEY AUTOINCREMENT, "
                "event_id TEXT NOT NULL UNIQUE, document TEXT NOT NULL)"
            )
        if version < 2:
            connection.execute("ALTER TABLE event_log ADD COLUMN digest TEXT NOT NULL DEFAULT ''")
            for cursor, document in list(
                connection.execute("SELECT cursor, document FROM event_log")
            ):
                event = Event.model_validate_json(str(document))
                connection.execute(
                    "UPDATE event_log SET document=?, digest=? WHERE cursor=?",
                    (event.canonical(), event.digest(), cursor),
                )

    async def close(self) -> None:
        def close() -> None:
            with self._lock:
                if self._connection is not None:
                    self._connection.close()
                    self._connection = None

        await self._call(close)

    @staticmethod
    def _decode(cursor: int, document: str, digest: str) -> StoredEvent:
        try:
            if json.loads(document).get("schema_version") != 1:
                raise StorageError("unsupported_event_schema", "Unknown event schema version")
            if hashlib.sha256(document.encode()).hexdigest() != digest:
                raise StorageError("storage_corrupt", "Event digest mismatch")
            return StoredEvent(cursor=cursor, event=Event.model_validate_json(document))
        except (ValidationError, ValueError, AttributeError) as error:
            raise StorageError("storage_corrupt", "Invalid stored event") from error

    async def append(self, events: Sequence[Event]) -> AppendReceipt:
        # Snapshot before crossing threads: callers cannot mutate an in-flight fact.
        prepared = []
        for event in events:
            document = event.canonical()
            prepared.append(
                (event.event_id, document, hashlib.sha256(document.encode()).hexdigest())
            )
        if len(prepared) > 1000 or sum(len(row[1].encode()) for row in prepared) > 8 * 1024 * 1024:
            raise ValueError("Event batch exceeds 1000 events or 8 MiB")

        def append() -> AppendReceipt:
            with self._lock:
                connection = self._db()
                committing = False
                connection.execute("BEGIN IMMEDIATE")
                try:
                    records = []
                    for event_id, document, digest in prepared:
                        previous = connection.execute(
                            "SELECT cursor, document, digest FROM event_log WHERE event_id=?",
                            (event_id,),
                        ).fetchone()
                        if previous:
                            if str(previous[1]) != document or str(previous[2]) != digest:
                                raise StorageError(
                                    "event_conflict", "Event id has different content"
                                )
                            cursor = int(previous[0])
                        else:
                            connection.execute(
                                "INSERT INTO event_log(event_id,document,digest) VALUES(?,?,?)",
                                (event_id, document, digest),
                            )
                            cursor = connection.last_insert_rowid()
                        records.append(self._decode(cursor, document, digest))
                    committing = True
                    self._commit(connection)
                    return AppendReceipt(records=records)
                except BaseException as error:
                    rolled_back = False
                    if not connection.get_autocommit():
                        try:
                            connection.execute("ROLLBACK")
                            rolled_back = True
                        except apsw.Error:
                            pass
                    if isinstance(error, apsw.Error):
                        outcome = "unknown" if committing and not rolled_back else "not_committed"
                        raise storage_error(error, outcome) from error
                    raise

        return await self._call(append)

    def _commit(self, connection: apsw.Connection) -> None:
        connection.execute("COMMIT")

    async def lookup(self, event_id: str) -> StoredEvent | None:
        def lookup() -> StoredEvent | None:
            with self._lock:
                row = (
                    self._db()
                    .execute(
                        "SELECT cursor, document, digest FROM event_log WHERE event_id=?",
                        (event_id,),
                    )
                    .fetchone()
                )
                return self._decode(int(row[0]), str(row[1]), str(row[2])) if row else None

        return await self._call(lookup)

    async def read(
        self, after: int = 0, limit: int = 100, scope: EventScope | None = None
    ) -> list[StoredEvent]:
        validate_page(after, limit)

        def read() -> list[StoredEvent]:
            with self._lock:
                # Cursor pagination remains stable across gaps; filtering happens
                # before limiting. JSON indices can be added with projections later.
                records = []
                for cursor, document, digest in self._db().execute(
                    "SELECT cursor,document,digest FROM event_log WHERE cursor>? ORDER BY cursor",
                    (after,),
                ):
                    record = self._decode(int(cursor), str(document), str(digest))
                    if matches(record.event, scope):
                        records.append(record)
                        if len(records) == limit:
                            break
                return records

        return await self._call(read)

    def info(self) -> StorageInfo:
        return StorageInfo(
            backend="sqlite",
            ready=self._connection is not None,
            durable=True,
            schema_version=SCHEMA_VERSION,
            sqlite_version=apsw.sqlitelibversion(),
            journal_mode="WAL",
            synchronous="FULL",
        )
