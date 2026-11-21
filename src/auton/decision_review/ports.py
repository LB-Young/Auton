from typing import Protocol

from auton.constitution.config import Principal
from auton.decision_review.contracts import (
    CalibrationView,
    HumanRevision,
    MetaCaseCommand,
    ProtectedReviewInput,
    ReviewCommand,
    ReviewExport,
    ReviewRecord,
    ReviewStatus,
)
from auton.kernel.ports import LifecycleHandle


class DecisionReviewPort(LifecycleHandle, Protocol):
    async def protected_inputs(self, principal: Principal) -> tuple[ProtectedReviewInput, ...]: ...
    def status(self) -> ReviewStatus: ...
    async def review(self, principal: Principal, command: ReviewCommand) -> ReviewRecord: ...
    async def get(self, principal: Principal, identity: str) -> ReviewRecord: ...
    async def list(self, principal: Principal, project: str) -> tuple[ReviewRecord, ...]: ...
    async def revise(
        self, principal: Principal, identity: str, command: HumanRevision
    ) -> ReviewRecord: ...
    async def annotate_meta(
        self, principal: Principal, command: MetaCaseCommand
    ) -> CalibrationView: ...
    async def calibrations(self, principal: Principal) -> tuple[CalibrationView, ...]: ...
    async def eligible(self, principal: Principal, project: str) -> tuple[ReviewExport, ...]: ...
