from collections.abc import Sequence
from typing import Protocol

from auton.agent.contracts import AgentRun
from auton.constitution.config import Principal
from auton.experience.contracts import (
    CheckpointReference,
    IndexedEvent,
    RecoveryCommand,
    Trajectory,
)
from auton.kernel.events import StoredEvent
from auton.kernel.ports import LifecycleHandle


class ProjectionPort(LifecycleHandle, Protocol):
    async def position(self) -> int: ...
    async def apply(self, rows: Sequence[StoredEvent], processed_at: str) -> None: ...
    async def checkpoint(self, run_id: str) -> CheckpointReference | None: ...
    async def select(
        self, run_id: str, goal_id: str, operations: tuple[str, ...], limit: int
    ) -> list[IndexedEvent]: ...
    async def rebuild(self) -> None: ...


class ExperiencePort(LifecycleHandle, Protocol):
    async def trajectory(
        self, principal: Principal, project: str, run_id: str, purpose: str = "inspect"
    ) -> Trajectory: ...
    async def recover(
        self, principal: Principal, project: str, run_id: str, command: RecoveryCommand
    ) -> AgentRun: ...
    async def rebuild(self, principal: Principal) -> None: ...
