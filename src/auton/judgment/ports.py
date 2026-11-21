from typing import Protocol

from pydantic import JsonValue

from auton.judgment.contracts import DecisionSource, JudgmentInfo, JudgmentRequest, JudgmentResult
from auton.kernel.ports import LifecycleHandle


class JudgmentAdapterPort(LifecycleHandle, Protocol):
    def info(self) -> JudgmentInfo: ...
    async def predict(
        self, request: JudgmentRequest
    ) -> tuple[DecisionSource, dict[str, JsonValue]]: ...


class JudgmentPort(LifecycleHandle, Protocol):
    async def apply(
        self, request: JudgmentRequest, current_state_cutoff: int
    ) -> JudgmentResult: ...

    def info(self) -> JudgmentInfo: ...
    async def decide(self, request: JudgmentRequest) -> JudgmentResult: ...
