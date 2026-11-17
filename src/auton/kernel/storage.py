from collections.abc import Sequence
from typing import Literal, Protocol

from auton.kernel.events import AppendReceipt, Event, EventScope, StorageInfo, StoredEvent
from auton.kernel.ports import ApplicationError, LifecycleHandle


class StorageError(ApplicationError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        outcome: Literal["not_committed", "unknown"] = "not_committed",
        retryable: bool = False,
    ) -> None:
        super().__init__(409 if code == "event_conflict" else 503, code, message)
        self.outcome = outcome
        self.retryable = retryable


class EventLogPort(LifecycleHandle, Protocol):
    async def append(self, events: Sequence[Event]) -> AppendReceipt: ...

    async def lookup(self, event_id: str) -> StoredEvent | None: ...

    async def read(
        self, after: int = 0, limit: int = 100, scope: EventScope | None = None
    ) -> list[StoredEvent]: ...

    def info(self) -> StorageInfo: ...


def matches(event: Event, scope: EventScope | None) -> bool:
    if scope is None:
        return True
    return all(
        getattr(event.scope, key) == value
        for key, value in scope.model_dump(exclude_unset=True).items()
    )


def validate_page(after: int, limit: int) -> None:
    if after < 0 or not 1 <= limit <= 1000:
        raise ValueError("Cursor must be >= 0 and limit must be between 1 and 1000")
