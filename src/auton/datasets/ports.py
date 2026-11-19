from typing import Protocol

from auton.constitution.config import Principal
from auton.datasets.contracts import (
    DataGrant,
    DataGrantCommand,
    DatasetArtifact,
    DatasetBuild,
    DatasetSnapshot,
    DatasetStatus,
    DatasetWithdrawal,
    ExportCommand,
)
from auton.kernel.ports import LifecycleHandle


class DatasetPort(LifecycleHandle, Protocol):
    def status(self) -> DatasetStatus: ...
    async def grant(self, principal: Principal, command: DataGrantCommand) -> DataGrant: ...
    async def grants(self, principal: Principal, project: str) -> tuple[DataGrant, ...]: ...
    async def build(self, principal: Principal, command: DatasetBuild) -> DatasetSnapshot: ...
    async def get(self, principal: Principal, identity: str) -> DatasetSnapshot: ...
    async def list(self, principal: Principal, project: str) -> tuple[DatasetSnapshot, ...]: ...
    async def withdraw(
        self, principal: Principal, command: DatasetWithdrawal
    ) -> tuple[str, ...]: ...
    async def export(
        self, principal: Principal, identity: str, command: ExportCommand
    ) -> DatasetArtifact: ...
    async def read_artifact(
        self, principal: Principal, identity: str
    ) -> tuple[DatasetArtifact, bytes]: ...
