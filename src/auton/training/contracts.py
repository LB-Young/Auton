"""Portable training orchestration. Hardware and base models belong to deployment config."""

from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from auton.datasets.contracts import Digest, Id
from auton.kernel.documents import digest
from auton.model.contracts import Contract

ENCODER_CHOICE_TEMPLATE = (
    "auton-encoder-choice-v1: state\nquestion.instructions\noption.description"
)


class BaseModelSpec(Contract):
    id: Id
    directory: Path
    architecture: Literal["causal_lm", "encoder_choice"] = "causal_lm"
    repository: str = Field(min_length=1, max_length=200)
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    license_reference: str = Field(min_length=10, max_length=1000)
    files: dict[str, Digest] = Field(min_length=2, max_length=100)
    tool_parser: Literal["tagged_json", "json"] = "tagged_json"
    template_sha256: Digest


class TrainingConfig(Contract):
    workload: Literal["executor", "decision"] = "executor"
    directory: Path = Path(".auton_local/training")
    backend: Literal["disabled", "docker"] = "disabled"
    image: str = Field(default="", max_length=300)
    base_models: tuple[BaseModelSpec, ...] = ()
    device: Literal["auto", "cpu", "cuda"] = "auto"
    max_documents: int = Field(default=10000, ge=100, le=100000)
    max_steps: int = Field(default=1000, ge=1, le=100000)
    max_wall_seconds: int = Field(default=3600, ge=10, le=86400)
    memory_mb: int = Field(default=8192, ge=512, le=1048576)
    cpus: int = Field(default=4, ge=1, le=256)
    max_output_bytes: int = Field(default=536870912, ge=1048576, le=8589934592)
    min_free_bytes: int = Field(default=1073741824, ge=1048576)
    max_active_jobs: int = Field(default=1, ge=1, le=8)

    @model_validator(mode="after")
    def configured(self) -> "TrainingConfig":
        import re

        if (
            self.backend == "docker"
            and re.fullmatch(r"[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}", self.image) is None
        ):
            raise ValueError("Training requires an operator-reviewed image pinned by digest")
        if len({b.id for b in self.base_models}) != len(self.base_models):
            raise ValueError("Base model ids must be unique")
        return self

    @property
    def digest(self) -> str:
        source = {
            p.name: __import__("hashlib").sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob("*.py"))
        }
        return digest(
            {
                "config": self.model_dump(mode="json", exclude={"directory"}),
                "implementation": source,
            }
        )


class TrainingPlanCommand(Contract):
    request_id: Id
    project_id: Id
    base_model_id: Id
    train_artifact_id: Digest
    additional_train_artifact_ids: tuple[Digest, ...] = Field(default=(), max_length=199)
    additional_validation_artifact_ids: tuple[Digest, ...] = Field(default=(), max_length=199)
    allow_cross_project_sources: bool = False
    validation_artifact_id: Digest | None = None
    replay_artifact_id: Digest | None = None
    anchor_artifact_id: Digest | None = None
    steps: int = Field(default=100, ge=1, le=100000)
    learning_rate: float = Field(default=0.0001, gt=0, le=0.01)
    rank: int = Field(default=8, ge=1, le=128)
    seed: int = Field(default=42, ge=0, le=2147483647)
    max_sequence_length: int = Field(default=2048, ge=64, le=32768)
    abstention_threshold: float = Field(default=0.7, ge=0.5, le=0.99)
    engineering_probe: bool = False


class TrainingPlan(Contract):
    id: Digest
    version: int = 0
    command: TrainingPlanCommand
    config_digest: Digest
    manifest_digest: Digest
    base_manifest_digest: Digest | None = None
    dataset_manifests: dict[str, Digest] = Field(default_factory=dict)
    examples: dict[str, int] = Field(default_factory=dict)
    groups: dict[str, int] = Field(default_factory=dict)
    status: Literal["ready", "blocked"] = "blocked"
    blockers: tuple[str, ...] = ()
    current_evidence_valid: bool = True
    activation: Literal["candidate_only"] = "candidate_only"


class TrainingJobCommand(Contract):
    request_id: Id
    plan_id: Digest
    expected_plan_digest: Digest


class TrainingControl(Contract):
    request_id: Id
    expected_version: int = Field(ge=0)
    action: Literal["cancel", "resume"]


class TrainingCheckpoint(Contract):
    step: int = Field(ge=0)
    files: dict[str, Digest]
    manifest_digest: Digest


class TrainingJob(Contract):
    id: Digest
    version: int = 0
    command: TrainingJobCommand
    project_id: str
    plan_digest: Digest
    status: Literal[
        "queued", "running", "succeeded", "failed", "cancelled", "interrupted", "blocked"
    ]
    attempt: int = 0
    completed_steps: int = 0
    checkpoint: TrainingCheckpoint | None = None
    reason: str = ""
    metrics: dict[str, JsonValue] = Field(default_factory=dict)
    bundle_id: Digest | None = None
    created_at: float
    started_at: float | None = None


class TrainingBundle(Contract):
    id: Digest
    version: int = 0
    project_id: str
    job_id: Digest
    plan_id: Digest
    files: dict[str, Digest]
    lineage_digest: Digest
    auxiliary_files: dict[str, Digest] = Field(default_factory=dict)
    metrics: dict[str, JsonValue]
    kind: Literal["executor", "decision"] = "executor"
    source: Literal["runtime", "test"]
    quality_release_eligible: Literal[False] = False
    release_blockers: tuple[str, ...] = ("independent_deployment_evaluation_required",)
    source_current: bool = True
    activation: Literal["offline_candidate"] = "offline_candidate"


class TrainingStatus(Contract):
    workload: Literal["executor", "decision"] = "executor"
    backend: str
    configured: bool
    model_ids: tuple[str, ...]
    lifecycle: Literal["manual_start_candidate_only"] = "manual_start_candidate_only"
    worker_protocol: Literal["auton-training-worker-v1"] = "auton-training-worker-v1"


class DecisionTrainingConfig(TrainingConfig):
    directory: Path = Path(".auton_local/decision-training")
    workload: Literal["executor", "decision"] = "decision"

    @model_validator(mode="after")
    def decision_only(self) -> "DecisionTrainingConfig":
        if self.workload != "decision":
            raise ValueError("Decision training cannot use executor supervision")
        return self
