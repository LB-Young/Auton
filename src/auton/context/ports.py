from typing import Protocol

from auton.constitution.config import Principal
from auton.context.contracts import ContextRequest, ContextSnapshot, Evidence
from auton.genome.contracts import Snapshot
from auton.kernel.ports import LifecycleHandle
from auton.model.contracts import ModelMessage, ModelRequest


class CompressorPort(Protocol):
    def groups(self, history: tuple[ModelMessage, ...]) -> list[tuple[ModelMessage, ...]]: ...

    def retained(
        self, groups: list[tuple[ModelMessage, ...]], drop: int
    ) -> tuple[ModelMessage, ...]: ...


class TokenCounterPort(Protocol):
    def count(self, request: ModelRequest) -> tuple[int, str]: ...


class RetrieverPort(Protocol):
    def retrieve(self, query: str, snapshot: Snapshot) -> tuple[Evidence, ...]: ...


class RerankerPort(Protocol):
    def rank(self, evidence: tuple[Evidence, ...]) -> tuple[Evidence, ...]: ...


class ContextEnginePort(LifecycleHandle, Protocol):
    async def prepare(self, request: ContextRequest) -> ContextSnapshot: ...
    async def snapshot(
        self, principal: Principal, project_id: str, snapshot_id: str
    ) -> ContextSnapshot: ...
