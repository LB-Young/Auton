import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import apsw
import pytest
from pydantic import ValidationError

from auton.kernel.config import KernelConfig
from auton.kernel.events import Event, EventScope
from auton.kernel.factory import ClockFactory, EventLogFactory
from auton.kernel.sqlite import APPLICATION_ID, SQLiteEventLog
from auton.kernel.storage import StorageError


def event(identifier: str, **changes: object) -> Event:
    return Event.model_validate(
        {
            "event_id": identifier,
            "kind": "test.recorded",
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            "source": "test",
            "payload": {"value": identifier},
            **changes,
        }
    )


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
async def test_contract_atomic_batch_idempotency_detachment_and_cursor(
    backend: str,
    tmp_path: Path,
) -> None:
    store = EventLogFactory().create(
        KernelConfig.model_validate(
            {
                "backend": backend,
                "data_directory": tmp_path,
            }
        )
    )
    await store.start()
    try:
        original = event("a")
        first = await store.append([original, event("b")])
        assert first.outcome == "committed"
        original.payload["value"] = "changed-after-write"
        rows = await store.read()
        assert rows[0].event.payload["value"] == "a"
        again = await store.append([event("a")])
        assert again.records[0].cursor == first.records[0].cursor
        with pytest.raises(StorageError, match="different content") as failure:
            await store.append([event("c"), event("a", payload={"different": True})])
        assert failure.value.outcome == "not_committed"
        assert await store.lookup("c") is None
        assert [row.event.event_id for row in await store.read(after=rows[0].cursor)] == ["b"]
        with pytest.raises(ValueError):
            await store.read(after=-1)
    finally:
        await store.close()
        await store.close()


async def test_restart_wal_settings_and_scope_filter_before_limit(tmp_path: Path) -> None:
    config = KernelConfig(data_directory=tmp_path)
    store = EventLogFactory().create(config)
    await store.start()
    await store.append(
        [
            event("a", scope={"project_id": "other"}),
            event("b", scope={"project_id": "wanted"}),
        ]
    )
    await store.close()
    reopened = EventLogFactory().create(config)
    await reopened.start()
    try:
        assert reopened.info().durable
        assert reopened.info().journal_mode == "WAL"
        assert reopened.info().synchronous == "FULL"
        rows = await reopened.read(limit=1, scope=EventScope(project_id="wanted"))
        assert rows[0].event.event_id == "b"
        assert (await reopened.lookup("a")) is not None
    finally:
        await reopened.close()


def make_v1(config: KernelConfig) -> None:
    config.event_path.parent.mkdir(parents=True)
    with apsw.Connection(str(config.event_path)) as connection:
        connection.execute(
            "CREATE TABLE event_log(cursor INTEGER PRIMARY KEY AUTOINCREMENT, "
            "event_id TEXT NOT NULL UNIQUE, document TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO event_log(event_id,document) VALUES(?,?)",
            ("legacy", event("legacy").canonical()),
        )
        connection.pragma("user_version", 1)


async def test_v1_migration_preserves_records(tmp_path: Path) -> None:
    config = KernelConfig(data_directory=tmp_path)
    make_v1(config)
    store = EventLogFactory().create(config)
    await store.start()
    try:
        record = await store.lookup("legacy")
        assert record is not None and record.cursor == 1
        assert record.event == event("legacy")
        assert store.info().schema_version == 2
    finally:
        await store.close()


async def test_failed_migration_rolls_back_schema_and_data(tmp_path: Path) -> None:
    config = KernelConfig(data_directory=tmp_path)
    make_v1(config)

    class FailingMigration(SQLiteEventLog):
        def _migrate(self, connection: apsw.Connection, version: int) -> None:
            super()._migrate(connection, version)
            connection.execute("INSERT INTO nonexistent_table VALUES(1)")

    store = FailingMigration(config)
    with pytest.raises(StorageError):
        await store.start()
    assert not store.info().ready
    with apsw.Connection(str(config.event_path)) as connection:
        assert connection.pragma("user_version") == 1
        assert "digest" not in {
            row[1] for row in connection.execute("PRAGMA table_info(event_log)")
        }
        assert list(connection.execute("SELECT event_id FROM event_log")) == [("legacy",)]
    await store.close()


@pytest.mark.parametrize("bad", ["corrupt", "future", "foreign"])
async def test_unsupported_database_is_rejected_without_replacing_it(
    tmp_path: Path, bad: str
) -> None:
    config = KernelConfig(data_directory=tmp_path)
    config.event_path.parent.mkdir(parents=True)
    if bad == "corrupt":
        config.event_path.write_bytes(b"not an SQLite database")
    else:
        with apsw.Connection(str(config.event_path)) as connection:
            if bad == "future":
                connection.pragma("application_id", APPLICATION_ID)
                connection.pragma("user_version", 99)
            else:
                connection.execute("CREATE TABLE unrelated(secret TEXT)")
    before = config.event_path.read_bytes()
    store = EventLogFactory().create(config)
    with pytest.raises(StorageError):
        await store.start()
    assert config.event_path.read_bytes() == before
    assert not store.info().ready


async def test_multiple_writers_and_lock_timeout(tmp_path: Path) -> None:
    config = KernelConfig(data_directory=tmp_path, busy_timeout_ms=20)
    first, second = EventLogFactory().create(config), EventLogFactory().create(config)
    await first.start()
    await second.start()
    try:
        await asyncio.gather(
            *[(first if index % 2 else second).append([event(str(index))]) for index in range(30)]
        )
        rows = await first.read()
        assert len(rows) == 30 and len({row.cursor for row in rows}) == 30
        with apsw.Connection(str(config.event_path)) as blocker:
            blocker.execute(
                "INSERT INTO event_log(event_id,document,digest) VALUES('block','{}','bad')"
            )
            with pytest.raises(StorageError) as failure:
                await second.append([event("blocked")])
            assert failure.value.code == "storage_busy" and failure.value.retryable
            assert failure.value.outcome == "not_committed"
            # Context rolls back the deliberately invalid test row.
            blocker.execute("DELETE FROM event_log WHERE event_id='block'")
        assert await first.lookup("blocked") is None
    finally:
        await first.close()
        await second.close()


async def test_disk_full_is_not_acknowledged_as_committed(tmp_path: Path) -> None:
    store = SQLiteEventLog(KernelConfig(data_directory=tmp_path))
    await store.start()
    try:
        assert store._connection is not None
        pages = int(store._connection.pragma("page_count"))
        store._connection.pragma("max_page_count", pages)
        with pytest.raises(StorageError) as failure:
            await store.append([event("too-large", payload={"text": "x" * 200000})])
        assert failure.value.code == "storage_full"
        assert failure.value.outcome == "not_committed"
        assert await store.lookup("too-large") is None
    finally:
        await store.close()


@pytest.mark.parametrize("committed", [False, True])
async def test_commit_error_is_reconciled_by_event_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    committed: bool,
) -> None:
    store = SQLiteEventLog(KernelConfig(data_directory=tmp_path))
    await store.start()

    def interrupted_commit(connection: apsw.Connection) -> None:
        if committed:
            connection.execute("COMMIT")
        raise apsw.IOError("injected lost commit acknowledgement")

    monkeypatch.setattr(store, "_commit", interrupted_commit)
    try:
        with pytest.raises(StorageError) as failure:
            await store.append([event("a")])
        assert failure.value.outcome == ("unknown" if committed else "not_committed")
        assert (await store.lookup("a") is not None) == committed
        monkeypatch.undo()
        await store.append([event("a")])
        assert len(await store.read()) == 1
    finally:
        await store.close()


async def test_cursor_gaps_are_not_missing_event_errors(tmp_path: Path) -> None:
    config = KernelConfig(data_directory=tmp_path)
    store = EventLogFactory().create(config)
    await store.start()
    await store.append([event("a")])
    value = event("gap")
    with apsw.Connection(str(config.event_path)) as connection:
        connection.execute(
            "INSERT INTO event_log(cursor,event_id,document,digest) VALUES(10,?,?,?)",
            (value.event_id, value.canonical(), value.digest()),
        )
    try:
        records = await store.read(after=1)
        assert len(records) == 1 and records[0].cursor == 10
    finally:
        await store.close()


async def test_abrupt_process_exit_recovers_committed_but_not_open_transaction(
    tmp_path: Path,
) -> None:
    code = """
import asyncio, os, sys
from pathlib import Path
from datetime import datetime, UTC
from auton.kernel.config import KernelConfig
from auton.kernel.events import Event
from auton.kernel.sqlite import SQLiteEventLog
async def main():
    store = SQLiteEventLog(KernelConfig(data_directory=Path(sys.argv[1])))
    await store.start()
    value = Event(event_id="committed", kind="test.saved",
                  timestamp=datetime.now(UTC), source="test")
    await store.append([value])
    db = store._connection
    db.execute("BEGIN IMMEDIATE")
    db.execute("INSERT INTO event_log(event_id,document,digest) VALUES('unfinished','{}','bad')")
    os._exit(0)
asyncio.run(main())
"""
    child = await asyncio.create_subprocess_exec(sys.executable, "-c", code, str(tmp_path))
    assert await child.wait() == 0
    store = EventLogFactory().create(KernelConfig(data_directory=tmp_path))
    await store.start()
    try:
        assert await store.lookup("committed") is not None
        assert await store.lookup("unfinished") is None
    finally:
        await store.close()


async def test_detects_event_corruption_and_unknown_event_schema(tmp_path: Path) -> None:
    config = KernelConfig(data_directory=tmp_path)
    store = EventLogFactory().create(config)
    await store.start()
    await store.append([event("a")])
    with apsw.Connection(str(config.event_path)) as connection:
        document = json.loads(event("a").canonical())
        document["schema_version"] = 99
        connection.execute(
            "UPDATE event_log SET document=? WHERE event_id='a'", (json.dumps(document),)
        )
    with pytest.raises(StorageError) as failure:
        await store.lookup("a")
    assert failure.value.code == "unsupported_event_schema"
    await store.close()


def test_clock_and_event_schema_validation() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert ClockFactory().create("fixed", now).now() == now
    with pytest.raises(ValueError):
        ClockFactory().create("unknown")
    with pytest.raises(ValidationError):
        event("a", timestamp=datetime(2026, 1, 1))
    with pytest.raises(ValidationError):
        event("a", scope={"goal_revision": 0})
