import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from auton.assess.rubric import RUBRIC_DIGEST
from auton.model.contracts import Contract

Split = Literal["train", "development", "test", "meta"]
Verdict = Literal["pass", "fail", "unknown"]


class AssessConfig(Contract):
    directory: Path = Path(".auton_local/assess")
    judge_model: str = "deepseek-v4-pro"
    rubric_revision: Literal["assess-rubric-v1"] = "assess-rubric-v1"
    min_calibration_samples: int = Field(default=30, ge=30, le=1000)
    min_calibration_lower: float = Field(default=0.8, ge=0.8, le=1)
    max_cases: int = Field(default=500, ge=1, le=10000)
    max_documents: int = Field(default=10000, ge=100, le=100000)
    max_active_jobs: int = Field(default=2, ge=1, le=4)
    max_window_uses: int = Field(default=1, ge=1, le=3)
    max_calibration_calls: int = Field(default=128, ge=60, le=2048)
    checker_revision: Literal["deterministic-checks-v2"] = "deterministic-checks-v2"
    statistics_revision: Literal["family-wilson-kappa-v1"] = "family-wilson-kappa-v1"

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            (
                self.model_dump_json(exclude={"directory"})
                + RUBRIC_DIGEST
                + PROTECTED_NORMALIZATION_REVISION
            ).encode()
        ).hexdigest()


class EvalCase(Contract):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    family: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    domain: str = Field(default="general", pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    tags: tuple[Annotated[str, Field(min_length=1, max_length=64)], ...] = Field(
        default=(), max_length=8
    )
    origin_group: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    split: Split
    prompt: str = Field(min_length=1, max_length=4000)
    kind: Literal["file", "research"]
    expected_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    target_path: str | None = Field(default=None, max_length=400)
    critical: bool = False
    data_domain: Literal["public", "local-only"] = "local-only"
    source: Literal["human_seed", "benchmark", "episode", "test_fixture"]
    human_verdict: Verdict = "unknown"
    human_answer: str | None = Field(default=None, max_length=6000)
    evidence_text: dict[str, str] = Field(default_factory=dict, max_length=12)

    @model_validator(mode="after")
    def valid(self) -> "EvalCase":
        if self.kind == "file" and (not self.expected_sha256 or not self.target_path):
            raise ValueError("File case requires an independent expected digest and path")
        if self.split in {"test", "meta"} and self.source == "episode":
            raise ValueError("Observed operational episodes are not fresh protected holdout")
        if self.split != "meta" and (
            self.human_answer is not None or self.human_verdict != "unknown"
        ):
            raise ValueError("Gold judge calibration labels belong only to meta")
        if self.split == "meta" and (self.human_answer is None or self.human_verdict == "unknown"):
            raise ValueError("Meta needs explicit human answer and gold label")
        if any(len(key) > 200 or len(value) > 1000 for key, value in self.evidence_text.items()):
            raise ValueError("Case evidence exceeds bounded reference/text limits")
        return self


class CaseInfo(Contract):
    id: str
    family: str
    split: Split
    kind: str
    critical: bool
    digest: str


class CaseBank(Contract):
    revision: str
    cases: tuple[CaseInfo, ...]
    counts: dict[str, int]


class ImportCases(Contract):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    expected_revision: str
    cases: tuple[EvalCase, ...] = Field(min_length=1, max_length=100)


class BlindWindowCommand(Contract):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    bank_revision: str
    split: Literal["test", "meta"]
    purpose: Literal["release", "calibration"]
    candidate_revision: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def purpose_matches(self) -> "BlindWindowCommand":
        if (self.split == "meta") != (self.purpose == "calibration"):
            raise ValueError("Meta is only for judge calibration; test is only for release")
        return self


class BlindWindow(Contract):
    id: str
    bank_revision: str
    split: Literal["test", "meta"]
    split_digest: str
    purpose: str
    candidate_revision: str
    max_uses: int


class EvaluateCommand(Contract):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    project_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    run_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_version: int = Field(ge=0, le=65535)
    case_id: str | None = Field(default=None, max_length=80)
    bank_revision: str | None = Field(default=None, max_length=64)
    window_id: str | None = Field(default=None, max_length=100)
    semantic: bool = False
    repeats: int = Field(default=1, ge=1, le=3)


class Signal(Contract):
    name: str
    source: Literal["deterministic", "model-judge", "human", "unverified-self-report"]
    verdict: Verdict
    evidence: tuple[str, ...] = ()
    reason: str
    critical: bool = False


class JudgeVerdict(Contract):
    verdict: Verdict
    confidence: float = Field(ge=0, le=1)
    evidence: tuple[str, ...] = Field(default=(), max_length=12)
    reason: str = Field(max_length=2000)


class JudgeObservation(Contract):
    request_id: str
    rubric_revision: str
    configuration_digest: str
    verdict: Verdict
    reason: str
    evidence: tuple[str, ...] = ()
    reported_model: str | None = None
    fingerprint: str | None = None
    source: Literal["remote", "test", "unavailable"]
    self_eval_bias: bool = False
    tokens: int | None = 0
    cost_microusd: int | None = 0
    dispatch_outcome: Literal["not_dispatched", "confirmed", "unknown"] = "not_dispatched"
    # Confidence is an uncalibrated self-report, never a correctness probability.
    reported_confidence: float | None = None


class Metrics(Contract):
    scope: Literal["run-lifetime"] = "run-lifetime"
    confirmed_model_calls: int
    unconfirmed_model_calls: int
    tokens: int
    cost_microusd: int
    tool_attempts: int
    failed_tools: int
    unknown_tools: int
    extra_model_calls: int
    usage_complete: bool
    model_latency_ms: int


class EvalReport(Contract):
    current_evidence_valid: bool = True
    id: str
    request_id: str
    project_id: str
    run_id: str
    checkpoint_event_id: str
    checkpoint_digest: str
    checkpoint_version: int
    goal_revision: int
    config_digest: str
    rubric_revision: str
    case_id: str | None
    bank_revision: str | None
    split: Literal["operational", "train", "development", "test", "meta"]
    family: str
    groups: tuple[str, ...]
    split_digest: str | None
    source: Literal["runtime", "test"]
    status: Literal["complete", "blocked"]
    outcome: Literal["pass", "fail", "unknown", "environment_error", "incomplete"]
    semantic_verdict: Verdict
    signals: tuple[Signal, ...]
    judges: tuple[JudgeObservation, ...]
    metrics: Metrics
    candidate_revision: str
    evaluation_cost_microusd: int | None
    evaluation_unknown_calls: int
    conditions_digest: str
    environment_verified: bool = False
    quality_release_eligible: bool = False
    reasons: tuple[str, ...]


class EvalJob(Contract):
    id: str
    command: EvaluateCommand
    status: Literal["running", "complete", "blocked"]
    reason: str
    report: EvalReport | None = None


class Aggregate(Contract):
    scope: Literal["descriptive-only"] = "descriptive-only"
    source_counts: dict[str, int]
    split_counts: dict[str, int]
    release_eligible: int
    evaluation_cost_microusd: int
    evaluation_unknown_calls: int
    total: int
    passed: int
    failed: int
    unknown: int
    environment_errors: int
    incomplete: int
    known_denominator: int
    pass_rate: float | None
    wilson_lower: float | None
    wilson_upper: float | None
    critical_failures: int
    tokens: int
    cost_microusd: int
    groups: dict[str, dict[str, int]]


class CalibrationCommand(Contract):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    bank_revision: str
    window_id: str
    confirm_public: bool = False
    repeats: int = Field(default=2, ge=2, le=3)


class GroupCalibration(Contract):
    samples: int
    families: int
    known: int
    correct: int
    wilson_lower: float | None
    qualified: bool


class CalibrationReport(Contract):
    judge_calls: int
    unknown_judge_calls: int
    confirmed_judge_tokens: int
    confirmed_judge_cost_microusd: int
    meta_digest: str
    groups: dict[str, GroupCalibration]
    supported_groups: tuple[str, ...]
    id: str
    bank_revision: str
    judge_identity: str | None
    rubric_revision: str
    configuration_digest: str
    samples: int
    families: int
    known: int
    positive_gold: int
    negative_gold: int
    agreement: float | None
    kappa: float | None
    wilson_lower: float | None
    coverage: float
    repeat_disagreements: int
    critical_samples: int
    critical_errors: int
    critical_missing: int
    source_qualified: bool
    passed: bool
    reasons: tuple[str, ...]


class Comparison(Contract):
    baseline: str
    candidate: str
    comparable: bool
    reasons: tuple[str, ...]
    token_delta: int
    cost_delta_microusd: int
    outcome_changed: bool


class CaseRunBinding(Contract):
    case_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    run_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_version: int = Field(ge=0, le=65535)


class BatchEvaluation(Contract):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    project_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    bank_revision: str
    window_id: str
    runs: tuple[CaseRunBinding, ...] = Field(min_length=1, max_length=100)
    semantic: bool = False
    repeats: int = Field(default=1, ge=1, le=3)


class BatchResult(Contract):
    expected_cases: int
    complete: bool
    blocked_cases: tuple[str, ...]
    id: str
    bank_revision: str
    window_id: str
    reports: tuple[EvalReport, ...]
    aggregate: Aggregate


class SeedCommand(Contract):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    expected_revision: str


class CompareCommand(Contract):
    baseline: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate: str = Field(pattern=r"^[a-f0-9]{64}$")


class AssessmentStatus(Contract):
    config_digest: str
    rubric_revision: str
    judge_model: str
    min_calibration_samples: int
    min_calibration_lower: float
    active_jobs: int
    max_calibration_calls: int
    private_judge_journal: bool = True


PROTECTED_NORMALIZATION_REVISION = "nfkc-casefold-numeric-v1"


def normalize_protected_input(prompt: str) -> str:
    text = unicodedata.normalize("NFKC", prompt).casefold()
    return " ".join(re.sub(r"\b\d+\b", "#", text).split())


class WindowView(Contract):
    window: BlindWindow
    used: int
    current: bool


class OptimizationTask(Contract):
    """Executable train/dev input, with no meta human answer or calibration label."""

    case_id: str
    family: str
    origin_group: str
    split: Literal["train", "development"]
    prompt: str
    path: str
    sha256: str
    data_domain: Literal["public", "local-only"]
    source: Literal["human_seed", "benchmark", "episode", "test_fixture"]
    critical: bool
