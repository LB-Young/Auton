from typing import Protocol

from auton.constitution.config import (
    ActionRequest,
    ConstitutionConfig,
    PolicyDecision,
    Principal,
    PublicPolicy,
    Usage,
)
from auton.constitution.contracts import Reservation


class PolicyControlPort(Protocol):
    def public(self) -> PublicPolicy: ...

    def preview(self, request: ActionRequest) -> PolicyDecision: ...

    async def reconfigure(
        self,
        principal: Principal,
        config: ConstitutionConfig,
        expected_version: str,
    ) -> str: ...


class ExecutionControlPort(Protocol):
    async def validate_action(self, request: ActionRequest) -> None: ...

    async def register_goal(
        self, principal: Principal, goal_id: str, revision: int = 1
    ) -> None: ...

    async def reserve(
        self,
        request: ActionRequest,
        estimate: Usage,
        request_id: str,
        approval_id: str | None = None,
    ) -> Reservation: ...

    async def begin(self, principal: Principal, identifier: str) -> Reservation: ...

    async def settle(self, principal: Principal, identifier: str, actual: Usage) -> Reservation: ...

    async def release(self, principal: Principal, identifier: str) -> Reservation: ...
