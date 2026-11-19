"""Decision quality and trajectory contribution are separate, versioned claims."""

import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, JsonValue

from auton.judgment.contracts import Answer, JudgmentRequest, JudgmentResult
from auton.model.contracts import Contract

Id = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Verdict = Literal["KEEP", "DROP", "HOLD"]


class DecisionReviewConfig(Contract):
    directory: Path = Path(".auton_local/decision-review")
    reviewer_model: str = "deepseek-v4-pro"
    max_documents: int = Field(default=10000, ge=100, le=100000)
    max_active_jobs: int = Field(default=1, ge=1, le=2)
    max_stage_cost_microusd: int = Field(default=20000, ge=1, le=50000)
    max_input_bytes: int = Field(default=14000, ge=1000, le=20000)
    min_meta_families: int = Field(default=100, ge=100, le=1000)
    min_meta_per_verdict: int = Field(default=30, ge=30, le=200)
    max_keep_contamination_upper: float = Field(default=0.01, gt=0, le=0.01)
    min_meta_coverage: float = Field(default=0.9, ge=0.9, le=1)
    min_meta_kappa: float = Field(default=0.6, ge=0.6, le=1)
    rubric_revision: Literal["decision-review-v1"] = "decision-review-v1"

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json(exclude={"directory"}).encode()).hexdigest()


class ReviewCommand(Contract):
    request_id: Id
    project_id: Id
    run_id: str = Field(min_length=1, max_length=200)
    expected_run_version: int = Field(ge=0)
    judgment_id: str = Field(min_length=1, max_length=100)
    question_id: Id
    assessment_report_id: Digest | None = None
    public: bool = False


class EvidenceFact(Contract):
    id: str
    digest: Digest
    kind: str
    cursor: int
    text: str = Field(max_length=1000)


class ReviewSubject(Contract):
    request: JudgmentRequest
    decision: JudgmentResult
    answer: Answer
    checkpoint_id: str
    checkpoint_digest: Digest
    run_version: int
    goal_revision: int
    source: Literal["runtime", "test"]
    before_evidence: tuple[EvidenceFact, ...]
    after_evidence: tuple[EvidenceFact, ...]
    source_digest: Digest
    blockers: tuple[str, ...]
    assessment_report_id: str | None = None
    assessment_passed: bool = False
    assessment_current: bool = False
    causal_link_verified: bool = False
    efficiency_comparison_verified: bool = False
    environment_failure: bool = False
    goal_changed: bool = False
    interaction_group: str | None = None
    actual_model_ids: tuple[str, ...] = ()
    actual_fingerprints: tuple[str, ...] = ()


class Reasonableness(Contract):
    verdict: Literal["supported", "unreasonable", "unknown"]
    knowledge_at_time: Literal["sufficient", "insufficient", "unknown"]
    evidence_refs: tuple[str, ...] = Field(min_length=0, max_length=12)
    explanation: str = Field(min_length=1, max_length=1500)


class Contribution(Contract):
    verdict: Literal["beneficial", "harmful", "environment_only", "unknown"]
    causal_support: Literal["controlled", "corrective_chain", "observational", "none"]
    efficiency: Literal["beneficial", "avoidable_detour", "necessary_exploration", "unknown"]
    evidence_refs: tuple[str, ...] = Field(min_length=0, max_length=16)
    explanation: str = Field(min_length=1, max_length=1500)


class StageReceipt(Contract):
    model_declaration_digest: str | None = None
    request_id: str
    input_digest: Digest
    verdict: Reasonableness | Contribution | None = None
    reported_model: str | None = None
    fingerprint: str | None = None
    source: Literal["runtime", "test", "unavailable"] = "unavailable"
    dispatch: Literal["confirmed", "not_dispatched", "unknown"] = "not_dispatched"
    tokens: int | None = 0
    cost_microusd: int | None = 0
    reason: str
    evidence_refs: tuple[str, ...] = ()


class HumanRevision(Contract):
    request_id: Id
    expected_version: int = Field(ge=0)
    proposed_verdict: Verdict
    reason: str = Field(min_length=10, max_length=2000)
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=20)
    # User observations are provenance, never fabricated independent model gold.
    source: Literal["user_observation"] = "user_observation"


class ReviewRecord(Contract):
    id: str
    version: int = 0
    command: ReviewCommand
    config_digest: Digest
    subject: ReviewSubject
    stage_a: StageReceipt | None = None
    stage_b: StageReceipt | None = None
    status: Literal["pending", "stage_a", "stage_b", "complete", "blocked"] = "pending"
    verdict: Verdict = "HOLD"
    proposed_verdict: Verdict = "HOLD"
    reason_codes: tuple[str, ...] = ()
    human_revisions: tuple[HumanRevision, ...] = ()
    qualification_signature: str | None = None
    evidence_current: bool = True
    positive_training_eligible: bool = False
    audit_retained: Literal[True] = True


class MetaCaseCommand(Contract):
    request_id: Id
    review_id: Digest
    expected_review_version: int = Field(ge=0)
    family: Id
    origin_group: Id
    gold: Verdict
    explanation: str = Field(min_length=20, max_length=2000)
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=20)
    label_source: Literal["human_annotation"] = "human_annotation"
    confirm_independent_human_annotation: bool = False


class MetaCase(Contract):
    id: str
    version: int = 0
    command: MetaCaseCommand
    reviewer_signature: str | None
    subject_digest: Digest
    source: Literal["runtime", "test"]
    recommended: Verdict
    observed_at_version: int
    active: bool = True


class CalibrationView(Contract):
    config_digest: Digest
    reviewer_signature: str | None = None
    eligible: bool = False
    independent_families: int = 0
    coverage: float = 0
    kappa: float | None = None
    predicted_keep: int = 0
    keep_errors: int = 0
    keep_contamination_upper: float | None = None
    per_verdict: dict[str, int] = Field(default_factory=dict)
    reasons: tuple[str, ...]
    protected_review_ids: tuple[str, ...] = ()


class ReviewStatus(Contract):
    config_digest: Digest
    reviewer_model: str
    rubric_revision: str
    online_adoption: Literal["unchanged"] = "unchanged"
    positive_rule: Literal["current_calibrated_adopted_beneficial_KEEP_only"] = (
        "current_calibrated_adopted_beneficial_KEEP_only"
    )
    automatic_admission: Literal["requires_human_meta_calibration"] = (
        "requires_human_meta_calibration"
    )


class ReviewExport(Contract):
    id: str
    version: int
    source_digest: Digest
    input: dict[str, JsonValue]
    target: dict[str, JsonValue]
    qualification_signature: str
    verdict: Literal["KEEP"] = "KEEP"


class ProtectedReviewInput(Contract):
    run_id: str
    project_id: str
    normalized_state_sha256: Digest
    reason: Literal["reviewer_meta"] = "reviewer_meta"
