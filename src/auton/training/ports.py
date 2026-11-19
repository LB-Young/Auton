from pathlib import Path
from typing import Literal, Protocol

from auton.constitution.config import Principal
from auton.kernel.ports import LifecycleHandle
from auton.model.contracts import Contract
from auton.training.contracts import (
    TrainingBundle,
    TrainingControl,
    TrainingJob,
    TrainingJobCommand,
    TrainingPlan,
    TrainingPlanCommand,
    TrainingStatus,
)


class WorkerState(Contract):
    status: Literal["absent", "running", "succeeded", "failed"]
    reason: str = ""


class TrainingBackendPort(Protocol):
    async def start(
        self, identity: str, job_directory: Path, base: Path, manifest_digest: str
    ) -> None: ...
    async def state(self, identity: str, manifest_digest: str) -> WorkerState: ...
    async def stop(self, identity: str, manifest_digest: str) -> None: ...


class ExecutorTrainingPort(LifecycleHandle, Protocol):
    def status(self) -> TrainingStatus: ...
    async def plan(self, principal: Principal, command: TrainingPlanCommand) -> TrainingPlan: ...
    async def plans(self, principal: Principal, project: str) -> tuple[TrainingPlan, ...]: ...
    async def create(self, principal: Principal, command: TrainingJobCommand) -> TrainingJob: ...
    async def get(self, principal: Principal, identity: str) -> TrainingJob: ...
    async def jobs(self, principal: Principal, project: str) -> tuple[TrainingJob, ...]: ...
    async def control(
        self, principal: Principal, identity: str, command: TrainingControl
    ) -> TrainingJob: ...
    async def bundles(self, principal: Principal, project: str) -> tuple[TrainingBundle, ...]: ...
