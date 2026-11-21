from collections.abc import Sequence

from auton.kernel.events import AppendReceipt, Event, EventScope, StorageInfo, StoredEvent
from auton.kernel.storage import StorageError, matches, validate_page


class MemoryEventLog:
    """A non-durable contract implementation for tests only."""

    def __init__(self) -> None:
        self.ready = False
        self.documents: dict[str, tuple[int, str]] = {}

    async def start(self) -> None:
        self.ready = True

    async def close(self) -> None:
        self.ready = False
        self.documents.clear()

    def _check(self) -> None:
        if not self.ready:
            raise StorageError("not_ready", "Event store is not ready")

    async def append(self, events: Sequence[Event]) -> AppendReceipt:
        self._check()
        staged = dict(self.documents)
        records = []
        for event in events:
            document = event.canonical()
            previous = staged.get(event.event_id)
            if previous and previous[1] != document:
                raise StorageError("event_conflict", "Event id already has different content")
            if previous is None:
                previous = (len(staged) + 1, document)
                staged[event.event_id] = previous
            records.append(
                StoredEvent(cursor=previous[0], event=Event.model_validate_json(previous[1]))
            )
        self.documents = staged
        return AppendReceipt(records=records)

    async def lookup(self, event_id: str) -> StoredEvent | None:
        self._check()
        item = self.documents.get(event_id)
        return (
            StoredEvent(cursor=item[0], event=Event.model_validate_json(item[1])) if item else None
        )

    async def read(
        self, after: int = 0, limit: int = 100, scope: EventScope | None = None
    ) -> list[StoredEvent]:
        self._check()
        validate_page(after, limit)
        rows = [
            StoredEvent(cursor=cursor, event=Event.model_validate_json(document))
            for cursor, document in self.documents.values()
            if cursor > after
        ]
        return [row for row in rows if matches(row.event, scope)][:limit]

    def info(self) -> StorageInfo:
        return StorageInfo(
            backend="memory",
            ready=self.ready,
            durable=False,
            schema_version=2,
            journal_mode="memory",
            synchronous="not-applicable",
        )
