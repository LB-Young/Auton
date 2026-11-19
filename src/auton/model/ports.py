from collections.abc import AsyncGenerator
from typing import Protocol

from auton.constitution.config import Principal
from auton.kernel.ports import ApplicationError, LifecycleHandle
from auton.model.config import ModelSpec
from auton.model.contracts import ModelChunk, ModelInfo, ModelRequest, ModelResult, ModelUsage
from auton.model.publication_contracts import ModelActivation, ModelAssignment, ModelProfile


class ModelError(ApplicationError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        dispatched: bool = False,
        usage: ModelUsage | None = None,
    ) -> None:
        super().__init__(429 if code == "rate_limited" else 503, code, message)
        self.retryable = retryable
        self.dispatched = dispatched
        self.usage = usage


class ProviderPort(LifecycleHandle, Protocol):
    def stream(
        self, request: ModelRequest, spec: ModelSpec
    ) -> AsyncGenerator[ModelChunk, None]: ...


class ModelGatewayPort(LifecycleHandle, Protocol):
    def runtime_assignment(self, principal: Principal, goal_id: str) -> ModelAssignment | None: ...
    def catalog(self, principal: Principal | None = None) -> list[ModelInfo]: ...
    async def resolve_model(
        self,
        principal: Principal,
        project: str,
        goal: str,
        requested: str,
        creation_digest: str = "",
        goal_text: str = "",
        data_domain: str = "local-only",
    ) -> str: ...
    async def count_local_tokens(self, request: ModelRequest) -> tuple[int, str]: ...
    async def validate_runtime(
        self,
        principal: Principal,
        model_id: str,
        goal_id: str,
        goal_text: str = "",
        data_domain: str = "local-only",
    ) -> None: ...

    def stream(self, request: ModelRequest) -> AsyncGenerator[ModelChunk, None]: ...

    async def generate(self, request: ModelRequest) -> ModelResult: ...


class ModelPublicationPort(LifecycleHandle, Protocol):
    def visible(self, owner: str, model_id: str) -> bool: ...
    def authorize(self, principal: Principal, model_id: str, goal: str) -> None: ...
    async def resolve(
        self,
        principal: Principal,
        project: str,
        goal: str,
        requested: str,
        creation_digest: str = "",
        goal_text: str = "",
        data_domain: str = "local-only",
    ) -> str: ...
    async def activate(
        self, principal: Principal, command: ModelActivation, expected: int | None
    ) -> ModelProfile: ...
    async def control(
        self, principal: Principal, project: str, release: str, action: str, expected: int
    ) -> ModelProfile: ...

    async def profile(self, principal: Principal, project: str) -> ModelProfile | None: ...
    async def grant_evaluation(
        self, principal: Principal, project: str, goal: str, model_id: str, creation_digest: str
    ) -> None: ...
