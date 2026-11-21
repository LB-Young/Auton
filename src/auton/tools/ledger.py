import hashlib

from pydantic import JsonValue

from auton.kernel.events import Event, EventScope
from auton.kernel.ports import RuntimeDependencies
from auton.kernel.storage import EventLogPort, StorageError
from auton.tools.contracts import ToolRequest, operation_event_id
from auton.tools.ports import ToolError


class OperationLedger:
    def __init__(self, events: EventLogPort, runtime: RuntimeDependencies) -> None:
        self.events, self.runtime = events, runtime

    @staticmethod
    def key(owner: str, operation: str) -> str:
        return hashlib.sha256((owner + "\0" + operation).encode()).hexdigest()

    async def get(self, owner: str, operation: str, stage: str) -> dict[str, JsonValue] | None:
        value = await self.events.lookup(operation_event_id(owner, operation, stage))
        return value.event.payload if value else None

    async def put(
        self, request: ToolRequest, stage: str, payload: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        event = Event(
            event_id=operation_event_id(request.principal.owner, request.operation_id, stage),
            kind=f"tool.{stage}",
            timestamp=self.runtime.now(),
            source="runtime",
            scope=EventScope.model_validate(
                {
                    "project_id": request.workspace_id,
                    "goal_id": request.goal_id,
                    "goal_revision": request.goal_revision,
                    "operation_id": request.operation_id,
                }
            ),
            payload={"request_digest": request.digest, **payload},
        )
        existing = await self.get(request.principal.owner, request.operation_id, stage)
        if existing:
            if existing != event.payload:
                raise ToolError("operation_conflict", "An operation id belongs to different data")
            return existing
        try:
            await self.events.append([event])
        except StorageError:
            # Acknowledgement loss is resolved by the deterministic event id, never by
            # dispatching the side effect again.
            stored = await self.get(request.principal.owner, request.operation_id, stage)
            if stored != event.payload:
                raise
        return event.payload


class OperationLedgerFactory:
    def create(self, events: EventLogPort, runtime: RuntimeDependencies) -> OperationLedger:
        return OperationLedger(events, runtime)
