import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from auton.constitution.config import Principal
from auton.model.contracts import Contract, ModelMessage, ToolSpec


class ContextConfig(Contract):
    tokenizer_directory: Path = Path("weights/context-tokenizers")
    max_evidence: int = Field(default=6, ge=0, le=12)
    chunk_characters: int = Field(default=1800, ge=200, le=4000)
    hosted_overhead_tokens: int = Field(default=512, ge=256, le=2048)


class PendingOperation(Contract):
    operation_id: str = Field(min_length=1, max_length=200)
    status: Literal["unknown", "awaiting_approval", "completed", "failed"]
    receipt_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class TaskState(Contract):
    delivery: dict[str, JsonValue] = Field(default_factory=dict)
    goal: str = Field(min_length=1, max_length=4000)
    boundaries: tuple[Annotated[str, Field(max_length=300)], ...] = Field(default=(), max_length=20)
    pending: tuple[PendingOperation, ...] = Field(default=(), max_length=30)


class ContextRequest(Contract):
    request_id: str = Field(min_length=1, max_length=100)
    principal: Principal
    project_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    goal_id: str = Field(min_length=1, max_length=100)
    goal_revision: int = Field(default=1, ge=1)
    state_cutoff: int = Field(default=0, ge=0)
    model_id: str = Field(min_length=1, max_length=100)
    state: TaskState
    history: tuple[ModelMessage, ...] = Field(default=(), max_length=300)
    tools: tuple[ToolSpec, ...] = Field(default=(), max_length=16)
    data_domain: Literal["public", "local-only", "secret"] = "local-only"
    max_output_tokens: int = Field(default=256, ge=1, le=2048)
    asset_snapshot_id: str | None = None
    previous_context_id: str | None = None

    @model_validator(mode="after")
    def input_limits(self) -> "ContextRequest":
        if any(message.role == "system" for message in self.history):
            raise ValueError("Caller history cannot add system messages")
        if len(self.model_dump_json().encode()) > 1024 * 1024:
            raise ValueError("Context input exceeds the bounded history limit")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class SourceLocation(Contract):
    asset_id: str
    source: str
    start_character: int
    end_character: int


class Evidence(Contract):
    locations: tuple[SourceLocation, ...]
    asset_ids: tuple[str, ...]
    source_references: tuple[str, ...]
    start_character: int
    end_character: int
    content_digest: str
    text: str
    score: float
    trust: Literal["untrusted"] = "untrusted"


class ContextSnapshot(Contract):
    id: str
    request_digest: str
    configuration_digest: str
    receipt_digests: dict[str, str] = Field(default_factory=dict)
    project_id: str
    goal_id: str
    goal_revision: int
    state_cutoff: int
    model_id: str
    declared_model_revision: str
    data_domain: Literal["public", "local-only"]
    policy_version: str
    asset_snapshot_id: str
    status: Literal["ready", "blocked"]
    reasons: tuple[str, ...]
    tokenizer_revision: str
    counter_source: Literal["official-local", "test-fixture", "unavailable"]
    input_tokens: int | None
    admission_tokens: int | None
    context_limit: int
    output_reserved: int
    remaining_tokens: int | None
    messages: tuple[ModelMessage, ...]
    tools: tuple[ToolSpec, ...]
    evidence: tuple[Evidence, ...]
    excluded_evidence: tuple[str, ...]
    dropped_history_groups: int
    instructions_revision: Literal["context-system-v1"] = "context-system-v1"
    retrieval_revision: Literal["lexical-bigram-v1"] = "lexical-bigram-v1"
    compression_revision: Literal["whole-turn-retention-v1"] = "whole-turn-retention-v1"
    checkpoint_modified: Literal[False] = False
