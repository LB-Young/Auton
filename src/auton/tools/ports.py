from typing import Protocol

from auton.constitution.config import Principal
from auton.kernel.ports import ApplicationError, LifecycleHandle
from auton.tools.contracts import (
    AdapterResult,
    ToolApproval,
    ToolDescriptor,
    ToolPlan,
    ToolReceipt,
    ToolRequest,
    ToolWorkspace,
)


class ToolError(ApplicationError):
    def __init__(self, code: str, message: str, *, uncertain: bool = False) -> None:
        super().__init__(
            409 if code in {"file_changed", "operation_conflict"} else 403, code, message
        )
        self.uncertain = uncertain


class ToolAdapterPort(Protocol):
    async def invoke(self, request: ToolRequest, workspace: ToolWorkspace) -> AdapterResult: ...


class ToolHostPort(LifecycleHandle, Protocol):
    async def workspace(self, principal: Principal, workspace_id: str) -> ToolWorkspace: ...
    async def artifact(self, principal: Principal, operation_id: str) -> tuple[str, bytes]: ...
    def catalog(self) -> list[ToolDescriptor]: ...
    async def create_workspace(
        self, principal: Principal, workspace_id: str, title: str, read_only: bool
    ) -> ToolWorkspace: ...
    async def workspaces(self, principal: Principal) -> list[ToolWorkspace]: ...
    async def prepare(self, request: ToolRequest) -> ToolPlan: ...
    async def approve(self, principal: Principal, operation_id: str) -> ToolApproval: ...
    async def execute(
        self, principal: Principal, operation_id: str, approval_id: str | None = None
    ) -> ToolReceipt: ...
    async def reconcile(self, principal: Principal, operation_id: str) -> ToolReceipt: ...
    async def receipt(self, principal: Principal, operation_id: str) -> ToolReceipt: ...
