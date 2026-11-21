from typing import Protocol

from auton.constitution.config import Principal
from auton.delegation.contracts import (
    ContrastCommand,
    DelegationCommand,
    DelegationCreate,
    DelegationStatus,
    DelegationView,
    SingleMultiContrast,
)
from auton.kernel.ports import LifecycleHandle


class DelegationPort(LifecycleHandle, Protocol):
    def status(self) -> DelegationStatus: ...
    async def contrast(
        self, principal: Principal, parent: str, command: ContrastCommand
    ) -> SingleMultiContrast: ...
    async def create(self, principal: Principal, command: DelegationCreate) -> DelegationView: ...
    async def get(self, principal: Principal, identity: str) -> DelegationView: ...
    async def list(self, principal: Principal, project_id: str) -> tuple[DelegationView, ...]: ...
    async def command(
        self, principal: Principal, identity: str, command: DelegationCommand
    ) -> DelegationView: ...
