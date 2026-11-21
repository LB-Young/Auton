from typing import Protocol

from auton.agent.contracts import AgentRun
from auton.constitution.config import Principal
from auton.kernel.ports import LifecycleHandle
from auton.release.contracts import (
    ReleaseApproval,
    ReleaseControl,
    ReleaseObservation,
    ReleasePlanCommand,
    ReleaseRecord,
    ReleaseStatus,
    ReleaseValidationRun,
)


class ReleasePort(LifecycleHandle, Protocol):
    def status(self) -> ReleaseStatus: ...
    async def plan(self, principal: Principal, command: ReleasePlanCommand) -> ReleaseRecord: ...
    async def get(self, principal: Principal, identity: str) -> ReleaseRecord: ...
    async def list(self, principal: Principal, project: str) -> tuple[ReleaseRecord, ...]: ...
    async def approve(
        self, principal: Principal, identity: str, command: ReleaseApproval
    ) -> ReleaseRecord: ...
    async def control(
        self, principal: Principal, identity: str, command: ReleaseControl
    ) -> ReleaseRecord: ...
    async def observe(
        self, principal: Principal, identity: str, command: ReleaseObservation
    ) -> ReleaseRecord: ...
    async def verify_runtime_source(self, principal: Principal, identity: str) -> None: ...

    async def prepare_validation(self, principal: Principal, identity: str) -> ReleaseRecord: ...
    async def validation_run(
        self, principal: Principal, identity: str, command: ReleaseValidationRun
    ) -> AgentRun: ...
