from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue

from auton.model.contracts import Contract


class ExperienceConfig(Contract):
    directory: Path = Path(".auton_local/experience")
    batch_size: int = Field(default=200, ge=1, le=1000)
    max_catchup_events: int = Field(default=20000, ge=100, le=100000)
    max_trace_events: int = Field(default=2000, ge=100, le=5000)


class IndexedEvent(Contract):
    cursor: int
    event_id: str
    digest: str
    kind: str
    run_id: str | None
    goal_id: str | None
    operation_id: str | None
    event_time: str
    processed_at: str
    source: str


class CheckpointReference(Contract):
    session_id: str = ""
    goal_id: str = ""
    project_id: str = ""
    run_id: str
    cursor: int
    event_id: str
    version: int
    runtime_revision: str
    digest: str


class TraceNode(Contract):
    id: str
    cursor: int
    kind: str
    event_time: str
    processed_at: str
    source: str
    goal_revision: int
    late_revision_result: bool = False
    details: dict[str, JsonValue]


class TraceEdge(Contract):
    source: str
    target: str
    relation: Literal[
        "checkpoint", "input", "decision", "authorization", "receipt", "verification", "parent"
    ]


class EpisodeSummary(Contract):
    id: str
    session_id: str
    goal_id: str
    run_id: str
    goal_revision: int
    first_cursor: int
    last_cursor: int
    context_ids: tuple[str, ...]
    model_request_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]
    observed_tokens: int
    estimated_cost_microusd: int
    parent_run_id: str | None = None


class Trajectory(Contract):
    schema_version: Literal[1] = 1
    project_id: str
    run_id: str
    purpose: Literal["inspect", "recovery"]
    projection_schema: Literal[2] = 2
    processing_cursor: int
    checkpoint: CheckpointReference | None
    caught_up: bool
    checkpoint_state: dict[str, JsonValue] = Field(default_factory=dict)
    episodes: tuple[EpisodeSummary, ...] = ()
    nodes: tuple[TraceNode, ...]
    edges: tuple[TraceEdge, ...]
    missing_references: tuple[str, ...]
    recovery_available: bool
    recovery_reasons: tuple[str, ...]
    tokens_used: int | None
    cost_microusd: int | None
    usage_complete: bool
    semantic_quality_verified: Literal[False] = False


class RecoveryCommand(Contract):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    expected_version: int = Field(ge=0)
    expected_goal_revision: int = Field(ge=1)
    checkpoint_event_id: str = Field(min_length=1, max_length=200)
