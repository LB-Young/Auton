import hashlib
from typing import Literal

from pydantic import Field, JsonValue

from auton.constitution.config import Principal
from auton.model.contracts import Contract

ToolName = Literal["file.read", "file.list", "file.write", "process.run", "mcp.sha256"]


class ToolDescriptor(Contract):
    id: ToolName
    title: str
    effect: Literal["read", "write", "process"]
    approval_required: bool
    input_schema: dict[str, JsonValue]
    isolation: str


class ToolWorkspace(Contract):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    owner: str
    title: str = Field(min_length=1, max_length=100)
    goal_id: str
    read_only: bool
    revision: int = 1
    root_path: str | None = None
    root_device: int | None = None
    root_inode: int | None = None


class LocalDirectories(Contract):
    path: str
    parent: str | None
    directories: tuple[str, ...]
    truncated: bool = False


class FileList(Contract):
    path: str = Field(default="", max_length=400)


class ToolRequest(Contract):
    operation_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    principal: Principal
    workspace_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    goal_id: str = Field(min_length=1, max_length=200)
    goal_revision: int = Field(default=1, ge=1)
    tool: ToolName
    arguments: dict[str, JsonValue]

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class FileRead(Contract):
    path: str = Field(min_length=1, max_length=400)
    start_line: int = Field(default=1, ge=1)
    max_lines: int | None = Field(default=None, ge=1, le=200)


class FileWrite(Contract):
    path: str = Field(min_length=1, max_length=400)
    content: str = Field(max_length=131072)
    expected_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
        description=(
            "SHA256 of the EXISTING file BEFORE this write (compare-and-swap). "
            "Omit or use null when creating a new file. "
            "This is never the intended/new output or delivery SHA256."
        ),
    )


class ProcessRun(Contract):
    program: Literal["python.version", "python.syntax_check"]
    source: str = Field(default="", max_length=131072)


class HashText(Contract):
    text: str = Field(max_length=16384)


class ToolPlan(Contract):
    operation_id: str
    request_digest: str
    workspace_id: str
    tool: ToolName
    title: str
    preview: str
    requires_approval: bool
    policy_version: str
    status: Literal["prepared"] = "prepared"


class ToolApproval(Contract):
    id: str
    operation_id: str
    expires_at: float


class ToolArtifact(Contract):
    id: str
    path: str
    sha256: str
    size_bytes: int
    media_type: Literal["text/plain"] = "text/plain"


class ToolReceipt(Contract):
    operation_id: str
    request_digest: str
    tool: ToolName
    workspace_id: str
    outcome: Literal["succeeded", "failed", "unknown"]
    code: str
    output: str
    attempt: int = 1
    reconciled: bool = False
    evidence: str
    exit_code: int | None = None
    artifact: ToolArtifact | None = None
    untrusted: Literal[True] = True
    source: Literal["local"] = "local"


class AdapterResult(Contract):
    output: str
    code: str = "ok"
    exit_code: int | None = None
    sha256: str | None = None
    size_bytes: int = 0


def workspace_event_id(owner: str, workspace_id: str) -> str:
    return "tool-workspace:" + hashlib.sha256((owner + "\0" + workspace_id).encode()).hexdigest()


def operation_event_id(owner: str, operation_id: str, stage: str) -> str:
    hashed = hashlib.sha256((owner + "\0" + operation_id).encode()).hexdigest()
    return f"tool:{hashed}:{stage}"
