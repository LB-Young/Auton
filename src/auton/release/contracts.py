from pathlib import Path
from typing import Literal

from pydantic import Field

from auton.agent.contracts import Acceptance
from auton.datasets.contracts import Digest, Id
from auton.kernel.documents import digest
from auton.model.contracts import Contract


class ReleaseConfig(Contract):
    directory: Path = Path(".auton_local/release")
    max_documents: int = Field(default=10000, ge=100, le=100000)
    min_independent_families: int = Field(default=30, ge=20, le=1000)
    min_quality_lower: float = Field(default=0.9, ge=0.8, le=1)
    max_observations: int = Field(default=500, ge=20, le=5000)
    max_initial_percentage: int = Field(default=5, ge=1, le=10)
    schema_revision: Literal["release-control-v1"] = "release-control-v1"

    @property
    def digest(self) -> str:
        return digest(self.model_dump(mode="json", exclude={"directory"}))


class ReleaseScope(Contract):
    domains: tuple[Id, ...] = Field(default=("general",), min_length=1, max_length=8)
    languages: tuple[Literal["zh", "en", "mixed", "other"], ...] = ("zh", "en")
    decision_points: tuple[
        Literal["information_sufficiency", "executor_tier", "tool_domain", "skill_match"], ...
    ] = ()
    data_domains: tuple[Literal["public", "local-only"], ...] = ("public",)


class ReleasePlanCommand(Contract):
    request_id: Id
    project_id: Id
    kind: Literal["genome", "executor_model", "decision_model"]
    source_id: Digest
    mode: Literal["offline", "canary", "active"] = "offline"
    percentage: int = Field(default=5, ge=1, le=100)
    target_model_id: str | None = Field(default=None, max_length=100)
    baseline_model_id: str = Field(default="deepseek-v4-pro", max_length=100)
    scope: ReleaseScope = Field(default_factory=ReleaseScope)
    report_ids: tuple[Digest, ...] = Field(default=(), max_length=100)
    baseline_report_ids: tuple[Digest, ...] = Field(default=(), max_length=100)
    decision_evaluation_id: Digest | None = None


class ReleaseEvidence(Contract):
    source_digest: Digest
    target_digest: Digest
    evidence_digest: Digest
    eligible: bool
    blockers: tuple[str, ...]
    independent_families: int = 0
    quality_lower: float | None = None
    report_ids: tuple[str, ...] = ()


class ReleaseRecord(Contract):
    id: Digest
    version: int = 0
    command: ReleasePlanCommand
    config_digest: Digest
    report: ReleaseEvidence
    status: Literal[
        "blocked",
        "ready",
        "approved",
        "activating",
        "active",
        "offline_registered",
        "paused",
        "rollback_pending",
        "rolled_back",
        "failed",
    ]
    validation_event_id: str | None = None
    approval_event_id: str | None = None
    effect_version: int | None = None
    reason: str = ""
    current_evidence_valid: bool = True
    observation_ids: tuple[str, ...] = ()
    affected_run_ids: tuple[str, ...] = ()
    created_at: float


class ReleaseApproval(Contract):
    request_id: Id
    expected_version: int = Field(ge=0)
    expected_evidence_digest: Digest
    risks_reviewed: bool = False


class ReleaseControl(Contract):
    request_id: Id
    expected_version: int = Field(ge=0)
    action: Literal["activate", "pause", "rollback"]


class ReleaseObservation(Contract):
    request_id: Id
    expected_version: int = Field(ge=0)
    report_id: Digest


class ReleaseStatus(Contract):
    policy_revision: str
    min_independent_families: int
    auto_approval: Literal[False] = False
    decision_online_routing: Literal["teacher_only"] = "teacher_only"


class ReleaseValidationRun(Contract):
    request_id: Id
    goal: str = Field(min_length=1, max_length=4000)
    acceptance: Acceptance
    data_domain: Literal["public", "local-only"] = "local-only"
