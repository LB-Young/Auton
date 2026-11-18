import hashlib
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, model_validator

from auton.agent.contracts import Acceptance, CreateRun, RunLimits, RunStatus
from auton.model.contracts import Contract
from auton.tools.contracts import ToolPlan, ToolReceipt

Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]


class DelegationConfig(Contract):
    directory: Path = Path(".auton_local/delegation")
    max_active_parents: int = Field(default=2, ge=1, le=4)
    max_children: int = Field(default=6, ge=1, le=8)
    max_parallel: int = Field(default=2, ge=1, le=4)
    max_parents: int = Field(default=100, ge=1, le=1000)
    child_timeout_seconds: float = Field(default=600, ge=1, le=3600)


class ChildSpec(Contract):
    id: Identifier
    role: Literal["worker", "researcher"] = "worker"
    goal: str = Field(min_length=1, max_length=3000)
    model_id: str = Field(min_length=1, max_length=100)
    depends_on: tuple[Identifier, ...] = Field(default=(), max_length=8)
    limits: RunLimits
    acceptance: Acceptance
    allowed_tools: tuple[Literal["file.read", "file.write", "mcp.sha256"], ...]

    @model_validator(mode="after")
    def permissions(self) -> "ChildSpec":
        if len(self.depends_on) != len(set(self.depends_on)) or len(self.allowed_tools) != len(
            set(self.allowed_tools)
        ):
            raise ValueError("Duplicate dependencies or permissions")
        if self.role == "researcher" and (
            self.acceptance.kind != "research" or "file.write" in self.allowed_tools
        ):
            raise ValueError("Research role is read-only")
        return self


class DelegationCreate(Contract):
    request_id: Identifier
    project_id: Identifier
    workspace_id: Identifier
    goal: str = Field(min_length=1, max_length=4000)
    boundaries: tuple[Annotated[str, Field(max_length=250)], ...] = Field(default=(), max_length=12)
    public: bool = False
    limits: RunLimits
    children: tuple[ChildSpec, ...] = Field(min_length=1, max_length=8)
    merge_order: tuple[Identifier, ...] = Field(min_length=1, max_length=8)
    separator: str = Field(default="", max_length=200)
    acceptance: Acceptance
    expected_previous_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def dag(self) -> "DelegationCreate":
        mapping = {child.id: child for child in self.children}
        if len(mapping) != len(self.children):
            raise ValueError("Duplicate child id")
        visited: set[str] = set()
        pending = set(mapping)
        while pending:
            ready = {key for key in pending if set(mapping[key].depends_on).issubset(visited)}
            if not ready:
                raise ValueError("Cyclic, self or missing dependency")
            pending -= ready
            visited |= ready
        if len(set(self.merge_order)) != len(self.merge_order) or not set(
            self.merge_order
        ).issubset(mapping):
            raise ValueError("Merge selects distinct declared children")
        if self.acceptance.kind != "file":
            raise ValueError("Initial supervisor integration is a bounded UTF-8 file")
        for identity in self.merge_order:
            if mapping[identity].acceptance.kind != "file":
                raise ValueError("Only verified file artifacts can be merged")
        for field in ("max_steps", "max_tokens", "max_cost_microusd", "max_tool_calls"):
            allocated = sum(int(getattr(child.limits, field)) for child in self.children)
            # One tool write is reserved for the integrator.
            if allocated + (field == "max_tool_calls") > int(getattr(self.limits, field)):
                raise ValueError("Child reservations and integration exceed parent budget")
        for child in self.children:
            if child.limits.max_output_tokens > self.limits.max_output_tokens:
                raise ValueError("Child output cap exceeds parent")
        for target in (self.acceptance.path, *(c.acceptance.path for c in self.children)):
            if target is not None:
                path = PurePosixPath(target)
                if (
                    str(path) != target
                    or path.is_absolute()
                    or any(p in {"..", "."} for p in target.split("/"))
                    or "\\" in target
                    or "\x00" in target
                ):
                    raise ValueError("File paths must be canonical relative paths")
        return self


class ChildState(Contract):
    id: str
    command: CreateRun | None = None
    run_id: str | None = None
    status: RunStatus | Literal["pending", "verified", "dispatch_intent"] = "pending"
    version: int | None = None
    started_at: float | None = None
    report_id: str | None = None
    reason: str = "dependency_not_ready"
    tokens: int = 0
    cost_microusd: int = 0
    unknown_tools: int = 0
    unknown_calls: int = 0
    tool_calls: int = 0
    pending_operation_id: str | None = None
    pending_preview: str | None = None
    approval_command_id: str | None = None


class DelegationView(Contract):
    id: str
    version: int = 0
    goal_revision: int = 1
    command: DelegationCreate
    input_snapshot_id: str
    children: tuple[ChildState, ...]
    status: Literal[
        "draft",
        "running",
        "waiting_approval",
        "integrating",
        "integrated",
        "blocked",
        "cancelling",
        "cancelled",
    ] = "draft"
    reason: str = "user_authored_dag_ready"
    integration: ToolPlan | None = None
    integration_receipt: ToolReceipt | None = None
    approved_integration: bool = False
    attribution: Literal["interaction-group-only"] = "interaction-group-only"
    interaction_group: tuple[str, ...]
    total_tokens: int = 0
    total_cost_microusd: int = 0
    total_tool_calls: int = 0
    unknown_tools: int = 0
    unknown_calls: int = 0
    benefit_claim: Literal["not_established"] = "not_established"
    created_at: float
    updated_at: float
    source: Literal["runtime", "test"]


class DelegationCommand(Contract):
    request_id: Identifier
    expected_version: int = Field(ge=0)
    action: Literal["start", "resume", "cancel", "approve_child", "approve_integration"]
    child_id: Identifier | None = None

    @model_validator(mode="after")
    def child_action(self) -> "DelegationCommand":
        if (self.action == "approve_child") != (self.child_id is not None):
            raise ValueError("Only child approval names a child")
        return self


def identity(owner: str, value: str) -> str:
    return hashlib.sha256((owner + "\0" + value).encode()).hexdigest()


class DelegationStatus(Contract):
    mode: Literal["user-authored-file-supervisor"] = "user-authored-file-supervisor"
    host_limits: RunLimits
    max_children: int
    max_parallel: int
    child_timeout_seconds: float


class ContrastCommand(Contract):
    request_id: Identifier
    baseline_run_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_version: int = Field(ge=0)


class SingleMultiContrast(Contract):
    supervisor_id: str
    baseline_run_id: str
    comparable: bool
    reasons: tuple[str, ...]
    baseline_outcome: str
    multi_outcome: str
    baseline_calls: int
    worker_calls: int
    baseline_tokens: int
    worker_tokens: int
    baseline_cost_microusd: int
    worker_cost_microusd: int
    cost_delta_microusd: int
    source: Literal["runtime", "test"]
    evidence_scope: Literal["one-paired-workflow-only"] = "one-paired-workflow-only"
    improvement_established: Literal[False] = False
