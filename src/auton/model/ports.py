from collections.abc import AsyncGenerator
from typing import Protocol

from auton.kernel.ports import ApplicationError, LifecycleHandle
from auton.model.config import ModelSpec
from auton.model.contracts import ModelChunk, ModelInfo, ModelRequest, ModelResult, ModelUsage


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
    def catalog(self) -> list[ModelInfo]: ...

    def stream(self, request: ModelRequest) -> AsyncGenerator[ModelChunk, None]: ...

    async def generate(self, request: ModelRequest) -> ModelResult: ...
