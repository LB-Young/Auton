import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from auton.agent.contracts import RunLimits
from auton.assess.contracts import OptimizationTask
from auton.model.contracts import Contract

Id = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class EvolutionConfig(Contract):
    directory: Path = Path(".auton_local/evolve")
    reflection_model: str = "deepseek-v4-pro"
    max_active_jobs: int = Field(default=1, ge=1, le=2)
    max_documents: int = Field(default=10000, ge=100, le=100000)
    max_patch_characters: int = Field(default=1500, ge=100, le=3000)
    max_changed_fraction: float = Field(default=0.5, ge=0.05, le=0.5)
    max_failed_attempts: int = Field(default=3, ge=1, le=3)
    min_development_families: int = Field(default=3, ge=3, le=9)
    min_repeats: int = Field(default=3, ge=3, le=5)
    max_arena_runs: int = Field(default=72, ge=3, le=180)
    max_arena_model_calls: int = Field(default=240, ge=3, le=600)
    max_arena_tokens: int = Field(default=600000, ge=1536, le=2000000)
    max_arena_cost_microusd: int = Field(default=300000, ge=1, le=1000000)
    max_arena_tool_calls: int = Field(default=72, ge=3, le=200)
    arena_timeout_seconds: float = Field(default=1200, ge=1, le=3600)
    max_reflection_cost_microusd: int = Field(default=20000, ge=1, le=50000)
    gate_revision: Literal["skill-gates-v1"] = "skill-gates-v1"

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json(exclude={"directory"}).encode()).hexdigest()


class DiagnoseCommand(Contract):
    request_id: Id
    project_id: Id
    asset_id: Id
    report_ids: tuple[Digest, ...] = Field(min_length=1, max_length=12)


class Diagnosis(Contract):
    id: str
    project_id: str
    asset_id: str
    report_ids: tuple[str, ...]
    category: Literal[
        "asset_hypothesis",
        "tool_environment",
        "execution_capability",
        "missing_information",
        "mixed",
        "unknown",
    ]
    conclusion_scope: Literal["diagnostic-hypothesis-only"] = "diagnostic-hypothesis-only"
    reasons: tuple[str, ...]
    suggested_action: Literal[
        "inspect_tools", "inspect_executor", "collect_evidence", "review_local_patch"
    ]
    usable_train_reports: tuple[str, ...]


class SectionPatch(Contract):
    heading: str = Field(pattern=r"^#{1,6} [^\n]{1,100}$")
    before: str = Field(min_length=1, max_length=12000)
    after: str = Field(min_length=1, max_length=12000)


class ProposalCommand(Contract):
    request_id: Id
    project_id: Id
    diagnosis_id: Digest
    base_snapshot_id: Digest
    asset_id: Id
    expected_content_sha256: Digest
    patch: SectionPatch
    rationale: str = Field(min_length=1, max_length=2000)
    direction: str = Field(min_length=1, max_length=300)


class ReflectCommand(Contract):
    request_id: Id
    project_id: Id
    diagnosis_id: Digest
    base_snapshot_id: Digest
    asset_id: Id
    expected_content_sha256: Digest
    heading: str = Field(pattern=r"^#{1,6} [^\n]{1,100}$")
    public: bool = False
    direction: str = Field(min_length=1, max_length=300)


class ReflectionPatch(Contract):
    new_body: str = Field(min_length=1, max_length=12000)
    rationale: str = Field(min_length=1, max_length=2000)


class GenerationReceipt(Contract):
    request_id: str
    reported_model: str | None = None
    fingerprint: str | None = None
    source: Literal["remote", "test", "unavailable"]
    dispatch: Literal["confirmed", "not_dispatched", "unknown"]
    tokens: int | None
    cost_microusd: int | None
    reason: str


class GateSignal(Contract):
    name: str
    verdict: Literal["pass", "fail", "hold"]
    reasons: tuple[str, ...]
    evidence: tuple[str, ...] = ()


class Proposal(Contract):
    id: str
    version: int = 0
    command: ProposalCommand
    parent_blob_sha256: str
    candidate_content: str
    candidate_sha256: str
    diff: str
    config_digest: str
    status: Literal[
        "proposed", "rejected", "evaluating", "blocked", "review_queue", "ready_for_release"
    ]
    reasons: tuple[str, ...]
    generation: GenerationReceipt | None = None
    gates: tuple[GateSignal, ...] = ()
    source: Literal["human-proposal", "model-proposal", "test"]
    learning_revision: str | None = None
    current_arena_id: str | None = None
    activation: Literal["not_activated"] = "not_activated"


class ToolCheckpoint(Contract):
    name: Id
    tool: Literal["file_write"] = "file_write"
    # These user-owned checks are frozen before candidate evaluation.
    require_absent_or_null_old_digest: bool = True


class ArenaCommand(Contract):
    request_id: Id
    proposal_id: Digest
    expected_proposal_version: int = Field(ge=0)
    bank_revision: Digest
    train_cases: tuple[Id, ...] = Field(min_length=1, max_length=3)
    development_cases: tuple[Id, ...] = Field(min_length=1, max_length=9)
    repeats: int = Field(default=3, ge=1, le=5)
    model_id: str = Field(min_length=1, max_length=100)
    limits: RunLimits
    checkpoints: tuple[ToolCheckpoint, ...] = Field(min_length=1, max_length=4)
    public: bool = False

    @model_validator(mode="after")
    def separate_cases(self) -> "ArenaCommand":
        selected = (*self.train_cases, *self.development_cases)
        if len(selected) != len(set(selected)):
            raise ValueError("Arena cases must be distinct across train and development")
        if len(self.checkpoints) != len({rule.name for rule in self.checkpoints}):
            raise ValueError("Checkpoint names must be unique")
        return self


class ArenaTrial(Contract):
    id: str
    case_id: str
    family: str
    independence_group: str | None = None
    split: Literal["train", "development"]
    variant: Literal["baseline", "candidate", "ablation"]
    repeat: int = Field(ge=0, le=4)
    snapshot_id: str
    workspace_id: str
    run_id: str | None = None
    run_version: int | None = None
    status: str = "pending"
    report_id: str | None = None
    outcome: Literal["pass", "fail", "unknown", "environment_error", "incomplete"] = "incomplete"
    tokens: int = 0
    cost_microusd: int = 0
    confirmed_calls: int = 0
    unknown_calls: int = 0
    tool_calls: int = 0
    pending_preview: str | None = None
    checkpoints_followed: bool = False
    target_retained: bool = False
    environment_verified: bool = False
    comparison_signature: str | None = None
    executor_signature: str | None = None
    source: Literal["runtime", "test"] = "test"
    case_source: Literal["human_seed", "benchmark", "episode", "test_fixture"] = "test_fixture"
    critical: bool = False
    reasons: tuple[str, ...] = ()


class ArenaView(Contract):
    frozen_tasks: tuple[OptimizationTask, ...] = ()
    assessment_config_digest: str = ""
    project_id: Id
    approval_command_id: str | None = None
    resume_command_id: str | None = None
    id: str
    version: int = 0
    command: ArenaCommand
    trials: tuple[ArenaTrial, ...]
    status: Literal[
        "draft", "running", "waiting_approval", "complete", "blocked", "cancelling", "cancelled"
    ] = "draft"
    reason: str
    current_trial: str | None = None
    config_digest: str
    total_tokens: int = 0
    total_cost_microusd: int = 0
    total_model_calls: int = 0
    unknown_model_calls: int = 0
    total_tool_calls: int = 0
    source: Literal["runtime", "test"]
    created_at: float
    gates: tuple[GateSignal, ...] = ()
    ready_for_release: bool = False


class ArenaControl(Contract):
    request_id: Id
    expected_version: int = Field(ge=0)
    action: Literal["start", "resume", "approve_current", "cancel"]


class SubmitProposal(Contract):
    request_id: Id
    expected_version: int = Field(ge=0)
    arena_id: Digest
    expected_learning_revision: str | None
    direction_reviewed: bool = False


class PlaybookEntry(Contract):
    version: int = 0
    id: str
    proposal_id: str
    project_id: str
    asset_id: str
    parent_sha256: str
    direction: str
    outcome: Literal["proposed", "rejected", "blocked", "review_queue", "ready_for_release"]
    reasons: tuple[str, ...]
    evidence: tuple[str, ...]


class EvolutionStatus(Contract):
    config_digest: str
    reflection_model: str
    gate_revision: str
    min_development_families: int
    min_repeats: int
    max_arena_model_calls: int
    activation: Literal["release_control_only"] = "release_control_only"


class GenerationRecord(Contract):
    id: str
    version: int = 0
    command: ReflectCommand
    config_digest: str
    status: Literal["running", "complete", "rejected", "blocked"]
    reason: str
    receipt: GenerationReceipt | None = None
    proposal_id: str | None = None
