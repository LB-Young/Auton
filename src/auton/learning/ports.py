from typing import Protocol

from auton.constitution.config import Principal
from auton.kernel.ports import LifecycleHandle
from auton.learning.contracts import (
    LearningCase,
    LearningManifest,
    LearningPolicy,
    LearningPolicyCommand,
    LearningRetry,
    LearningStatus,
)


class LearningPort(LifecycleHandle, Protocol):
    async def manifest(self, principal: Principal) -> LearningManifest: ...
    async def observe(self, principal: Principal, conversation_id: str) -> None: ...
    async def configure(
        self, principal: Principal, command: LearningPolicyCommand
    ) -> LearningPolicy: ...
    async def status(self, principal: Principal) -> LearningStatus: ...
    async def tick(self, principal: Principal) -> LearningStatus: ...
    async def retry(
        self, principal: Principal, case_id: str, command: LearningRetry
    ) -> LearningCase: ...
