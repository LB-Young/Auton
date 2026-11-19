import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from auton.model.contracts import Contract, ModelMessage, ToolSpec

Id = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
DatasetKind = Literal["executor", "router", "decision"]
DataSplit = Literal["train", "validation"]


class DatasetConfig(Contract):
    directory: Path = Path(".auton_local/datasets")
    max_documents: int = Field(default=10000, ge=100, le=100000)
    max_sources: int = Field(default=100, ge=1, le=200)
    max_examples: int = Field(default=1000, ge=1, le=5000)
    max_example_bytes: int = Field(default=64000, ge=2000, le=256000)
    max_snapshot_bytes: int = Field(default=16000000, ge=10000, le=64000000)
    max_export_bytes: int = Field(default=8000000, ge=10000, le=32000000)
    source_revision: Literal["trajectory-datasets-v1"] = "trajectory-datasets-v1"

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json(exclude={"directory"}).encode()).hexdigest()


class TeacherUse(Contract):
    model_id: str = Field(min_length=1, max_length=200)
    declared_revision: str = Field(min_length=1, max_length=200)
    terms_reference: str = Field(min_length=10, max_length=1000)
    training_use_confirmed_by_user: bool = False


class AssetUse(Contract):
    asset_id: Id
    content_sha256: Digest
    license_reference: str = Field(min_length=10, max_length=1000)
    training_use_confirmed_by_user: bool = False


class DataGrantCommand(Contract):
    request_id: Id
    project_id: Id
    run_ids: tuple[str, ...] = Field(min_length=1, max_length=200)
    purposes: tuple[DatasetKind, ...] = Field(min_length=1, max_length=3)
    data_license_reference: str = Field(min_length=10, max_length=1000)
    local_training_authorized: bool = False
    teacher_uses: tuple[TeacherUse, ...] = Field(default=(), max_length=20)
    external_asset_uses: tuple[AssetUse, ...] = Field(default=(), max_length=100)
    allow_local_only_data: bool = False

    @model_validator(mode="after")
    def unique(self) -> "DataGrantCommand":
        if len(set(self.run_ids)) != len(self.run_ids) or len(set(self.purposes)) != len(
            self.purposes
        ):
            raise ValueError("Grant source ids and purposes must be distinct")
        if len({(t.model_id, t.declared_revision) for t in self.teacher_uses}) != len(
            self.teacher_uses
        ):
            raise ValueError("Teacher permission scopes must be distinct")
        return self


class DataGrant(Contract):
    id: Digest
    version: int = 0
    command: DataGrantCommand
    revoked: bool = False
    source_scope: Literal["owner_project_local_training"] = "owner_project_local_training"
    license_truth: Literal["user_attestation_not_legal_verification"] = (
        "user_attestation_not_legal_verification"
    )


class SubjectRef(Contract):
    run_id: str = Field(min_length=1, max_length=200)
    expected_version: int = Field(ge=0)
    assessment_report_id: Digest | None = None
    review_id: Digest | None = None
    family: Id
    origin_group: Id
    split: DataSplit = "train"


class RouterPair(Contract):
    left_run_id: str = Field(min_length=1, max_length=200)
    right_run_id: str = Field(min_length=1, max_length=200)


class DatasetBuild(Contract):
    request_id: Id
    project_id: Id
    kind: DatasetKind
    grant_id: Digest
    subjects: tuple[SubjectRef, ...] = Field(min_length=1, max_length=200)
    router_pairs: tuple[RouterPair, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def valid(self) -> "DatasetBuild":
        if len({s.run_id for s in self.subjects}) != len(self.subjects):
            raise ValueError("Only one frozen source checkpoint per run in a build")
        if self.kind == "router" and not self.router_pairs:
            raise ValueError("Router samples need actually compared source runs")
        if self.kind != "router" and self.router_pairs:
            raise ValueError("Only router builds accept observed comparison pairs")
        if self.kind == "decision" and any(s.review_id is None for s in self.subjects):
            raise ValueError("Decision samples require a current qualified review")
        return self


class SourceProof(Contract):
    run_id: str
    version: int
    goal_revision: int
    checkpoint_id: str
    checkpoint_digest: Digest
    source_digest: Digest
    input_snapshot_id: str
    assessment_report_id: str | None = None
    review_id: str | None = None
    review_version: int | None = None
    event_refs: tuple[str, ...] = ()
    declared_model: dict[str, JsonValue] = Field(default_factory=dict)
    source: Literal["runtime", "test"]


class TrainingExample(Contract):
    lineage_tokens: tuple[str, ...] = ()
    id: Digest
    kind: DatasetKind
    family: str
    origin_group: str
    split: DataSplit
    group_id: str = ""
    normalized_input: str
    normalized_target: str
    input_messages: tuple[ModelMessage, ...] = ()
    target_message: ModelMessage | None = None
    following_tool_results: tuple[ModelMessage, ...] = ()
    tools: tuple[ToolSpec, ...] = ()
    # Message-level intent. M18 must derive exact token masks using the actual
    # tokenizer/template, rather than trusting a generic assistant-only default.
    loss_message_indices: tuple[int, ...] = ()
    structured_input: dict[str, JsonValue] = Field(default_factory=dict)
    structured_target: dict[str, JsonValue] = Field(default_factory=dict)
    proofs: tuple[SourceProof, ...]
    input_fingerprints: tuple[str, ...]
    engineering_only: bool = False


class RejectedSubject(Contract):
    run_id: str
    reasons: tuple[str, ...]


class DatasetSnapshot(Contract):
    id: Digest
    version: int = 0
    command: DatasetBuild
    config_digest: Digest
    grant_digest: Digest
    status: Literal["ready", "blocked", "engineering_only"] = "blocked"
    examples: tuple[TrainingExample, ...] = ()
    rejected: tuple[RejectedSubject, ...] = ()
    content_digest: Digest
    source_groups: int = 0
    training_ready: bool = False
    current_evidence_valid: bool = True
    invalidation_reasons: tuple[str, ...] = ()
    activation: Literal["no_training_started"] = "no_training_started"
    created_at: float


class DatasetWithdrawal(Contract):
    request_id: Id
    project_id: Id
    run_id: str | None = Field(default=None, min_length=1, max_length=200)
    grant_id: Digest | None = None
    reason: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def one_scope(self) -> "DatasetWithdrawal":
        if (self.run_id is None) == (self.grant_id is None):
            raise ValueError("Withdraw one source run or one grant")
        return self


class ExportCommand(Contract):
    request_id: Id
    expected_content_digest: Digest
    split: DataSplit = "train"
    purpose: Literal["local_training", "local_validation"]

    @model_validator(mode="after")
    def matching_scope(self) -> "ExportCommand":
        if (self.split == "train") != (self.purpose == "local_training"):
            raise ValueError("Validation may not be requested for gradient training")
        return self


class DatasetArtifact(Contract):
    id: Digest
    version: int = 0
    snapshot_id: Digest
    command: ExportCommand
    sha256: Digest
    size: int
    example_count: int
    manifest_digest: Digest
    format: Literal["auton-local-learning-jsonl-v1"] = "auton-local-learning-jsonl-v1"


class DatasetStatus(Contract):
    config_digest: Digest
    source_revision: str
    max_sources: int
    protected_splits: tuple[str, ...] = ("test", "meta", "reviewer_meta", "optimization_arena")
    training: Literal["separate_worker_capability"] = "separate_worker_capability"
