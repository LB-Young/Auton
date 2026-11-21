from typing import Protocol

from auton.agent.contracts import checkpoint_event_id
from auton.constitution.config import Principal
from auton.experience.contracts import CheckpointReference
from auton.kernel.events import StoredEvent
from auton.kernel.ports import ApplicationError
from auton.kernel.storage import EventLogPort


class CheckpointRepositoryPort(Protocol):
    async def owned_seed(self, principal: Principal, project: str, run_id: str) -> StoredEvent: ...
    async def valid(
        self, principal: Principal, project: str, reference: CheckpointReference
    ) -> bool: ...


class CheckpointRepository:
    def __init__(self, events: EventLogPort) -> None:
        self.events = events

    async def owned_seed(self, principal: Principal, project: str, run_id: str) -> StoredEvent:
        value = await self.events.lookup(checkpoint_event_id(principal.owner, run_id, 0))
        if (
            value is None
            or value.event.scope.run_id != run_id
            or value.event.scope.project_id != project
        ):
            raise ApplicationError(404, "trajectory_not_found", "No owned run in this project")
        return value

    async def valid(
        self, principal: Principal, project: str, reference: CheckpointReference
    ) -> bool:
        if reference.event_id != checkpoint_event_id(
            principal.owner, reference.run_id, reference.version
        ):
            return False
        value = await self.events.lookup(reference.event_id)
        return bool(
            value
            and value.cursor == reference.cursor
            and value.event.digest() == reference.digest
            and value.event.scope.project_id == project
            and value.event.scope.run_id == reference.run_id
        )


class CheckpointRepositoryFactory:
    def create(self, events: EventLogPort) -> CheckpointRepositoryPort:
        return CheckpointRepository(events)
