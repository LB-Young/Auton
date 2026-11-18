import hashlib
from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from auton.judgment.contracts import JudgmentResult
from auton.model.contracts import Contract, ModelMessage, ModelResult, ToolCall
from auton.tools.contracts import ToolName, ToolPlan, ToolReceipt


class AgentConfig(Contract):
    max_steps: int = Field(default=8, ge=1, le=20)
    max_tokens: int = Field(default=16000, ge=512, le=100000)
    max_cost_microusd: int = Field(default=10000, ge=1, le=1000000)
    max_tool_calls: int = Field(default=8, ge=1, le=30)
    max_active_runs: int = Field(default=2, ge=1, le=4)
    max_output_tokens: int = Field(default=512, ge=32, le=1024)
    directory: str = ".auton_local/agent"


class Acceptance(Contract):
    kind: Literal["file", "research"]
    path: str | None = Field(default=None, max_length=400)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    min_sources: int = Field(default=1, ge=1, le=6)

    @model_validator(mode="after")
    def file_target(self) -> "Acceptance":
        if self.kind == "file" and (not self.path or not self.sha256):
            raise ValueError("File acceptance needs a path and independent expected SHA256")
        return self


class CreateRun(Contract):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    project_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    workspace_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    model_id: str = Field(min_length=1, max_length=100)
    goal: str = Field(min_length=1, max_length=4000)
    boundaries: tuple[Annotated[str, Field(max_length=300)], ...] = Field(default=(), max_length=16)
    data_domain: Literal["public", "local-only"] = "local-only"
    allowed_tools: tuple[ToolName, ...] = Field(default=("file.read", "mcp.sha256"), max_length=4)
    acceptance: Acceptance

    @model_validator(mode="after")
    def tools_match_acceptance(self) -> "CreateRun":
        if len(set(self.allowed_tools)) != len(self.allowed_tools):
            raise ValueError("Duplicate allowed tool")
        if self.acceptance.kind == "research" and any(
            t not in {"file.read", "mcp.sha256"} for t in self.allowed_tools
        ):
            raise ValueError("Research tasks are read-only")
        if self.acceptance.kind == "file" and "file.write" not in self.allowed_tools:
            raise ValueError("File task needs explicit file.write permission")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


RunStatus = Literal[
    "queued",
    "running",
    "waiting_approval",
    "blocked",
    "pausing",
    "paused",
    "cancelling",
    "cancelled",
    "succeeded",
    "failed",
]


class RunCommand(Contract):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    expected_goal_revision: int = Field(ge=1)
    expected_version: int | None = Field(default=None, ge=0)
    action: Literal["pause", "cancel", "resume", "approve", "reconcile", "revise"]
    goal: str | None = Field(default=None, min_length=1, max_length=4000)

    @model_validator(mode="after")
    def goal_only_for_revision(self) -> "RunCommand":
        if (self.action == "revise") != (self.goal is not None):
            raise ValueError("Only revise requires a new goal")
        return self


class AcceptanceCheck(Contract):
    outcome: Literal["passed", "failed", "unknown"]
    checker: Literal["file-sha256-v1", "retrieval-citations-v1"]
    evidence: tuple[str, ...]
    semantic_quality_verified: Literal[False] = False


class AgentRun(Contract):
    session_id: str = ""
    id: str
    version: int = 0
    goal_revision: int = 1
    command: CreateRun
    status: RunStatus = "queued"
    phase: Literal["idle", "judgment", "context", "model", "tool", "acceptance"] = "idle"
    reason: str = "queued"
    steps: int = 0
    budget_limits: dict[str, int] = Field(default_factory=dict)
    executor_spec: dict[str, JsonValue] = Field(default_factory=dict)
    tokens_used: int = 0
    cost_microusd: int = 0
    model_results: tuple[ModelResult, ...] = ()
    history: tuple[ModelMessage, ...] = ()
    pending_calls: tuple[ToolCall, ...] = ()
    plans: tuple[ToolPlan, ...] = ()
    receipts: tuple[ToolReceipt, ...] = ()
    approvals: dict[str, str] = Field(default_factory=dict)
    context_ids: tuple[str, ...] = ()
    judgment_ids: tuple[str, ...] = ()
    judgments: tuple[JudgmentResult, ...] = ()
    input_cutoff_unit: Literal["run-checkpoint-version"] = "run-checkpoint-version"
    executor_selection: Literal["user-explicit"] = "user-explicit"
    model_request_id: str | None = None
    pending_goal: str | None = None
    stop_requested: bool = False
    final_text: str = ""
    check: AcceptanceCheck | None = None
    source: Literal["runtime", "test"]
    runtime_revision: Literal["single-agent-v1", "single-agent-v2"] = "single-agent-v2"


def checkpoint_event_id(owner: str, run_id: str, version: int) -> str:
    digest = hashlib.sha256((owner + "\0" + run_id).encode()).hexdigest()
    return f"agent:{digest}:{version}"


class TransientProgress(Contract):
    request_id: str
    goal_revision: int
    version: int
    sequence: int
    text: str
    persisted: Literal[False] = False


class RunPage(Contract):
    items: tuple[AgentRun, ...]
    next_cursor: int | None
