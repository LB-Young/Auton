from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from auton.datasets.contracts import AssetUse, TeacherUse
from auton.kernel.documents import digest
from auton.model.contracts import Contract


class LearningConfig(Contract):
    directory: Path = Path(".auton_local/learning")
    max_documents: int = Field(default=30000, ge=100, le=100000)
    poll_seconds: float = Field(default=5, ge=0.1, le=3600)
    max_cases_per_tick: int = Field(default=4, ge=1, le=40)
    background: bool = True

    @property
    def digest(self) -> str:
        return digest(self.model_dump(mode="json", exclude={"directory"}))


class LearningPolicyCommand(Contract):
    expected_version: int | None = Field(default=None, ge=0)
    enabled: bool = False
    local_training_authorized: bool = False
    data_license_reference: str = Field(default="", max_length=1000)
    teacher_uses: tuple[TeacherUse, ...] = Field(default=(), max_length=20)
    external_asset_uses: tuple[AssetUse, ...] = Field(default=(), max_length=100)
    allow_local_only_data: bool = False
    allow_remote_review: bool = False
    # Lifetime call allowance, including unknown dispatches and retries. Never reset on restart.
    max_review_calls: int = Field(default=0, ge=0, le=100000)
    review_decisions: bool = True

    @model_validator(mode="after")
    def authorized(self) -> "LearningPolicyCommand":
        if self.enabled and (
            not self.local_training_authorized or len(self.data_license_reference) < 10
        ):
            raise ValueError("Enabled curation needs an explicit data-use attestation")
        return self


class LearningPolicy(Contract):
    version: int = 0
    command: LearningPolicyCommand


class LearningCase(Contract):
    id: str
    version: int = 0
    conversation_id: str
    project_id: str
    run_id: str
    run_version: int | None = None
    attempt: int = 0
    stage: Literal[
        "collected", "assessing", "reviewing", "building", "ready", "hold", "rejected"
    ] = "collected"
    reasons: tuple[str, ...] = ()
    reserved_review_calls: int = 0
    assessment_id: str | None = None
    review_ids: tuple[str, ...] = ()
    decision_outcomes: dict[str, str] = Field(default_factory=dict)
    dataset_ids: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    example_keys: tuple[str, ...] = ()
    split: Literal["train", "validation"] = "train"
    policy_version: int | None = None


class LearningRetry(Contract):
    expected_version: int = Field(ge=0)


class LearningStatus(Contract):
    policy: LearningPolicy | None
    reserved_review_calls: int
    cases: tuple[LearningCase, ...]
    activation: Literal["no_training_started"] = "no_training_started"


class LearningManifest(Contract):
    executor_train_artifact_ids: tuple[str, ...] = ()
    executor_validation_artifact_ids: tuple[str, ...] = ()
    decision_train_artifact_ids: tuple[str, ...] = ()
    decision_validation_artifact_ids: tuple[str, ...] = ()
    activation: Literal["no_training_started"] = "no_training_started"
