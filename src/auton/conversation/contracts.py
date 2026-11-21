import hashlib

from pydantic import Field

from auton.agent.contracts import AgentRun
from auton.model.contracts import Contract


class ConversationCreate(Contract):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    title: str = Field(min_length=1, max_length=100)
    project_path: str | None = Field(default=None, max_length=4096)


class WorkspaceConversation(Contract):
    id: str
    title: str
    project_id: str
    workspace_id: str
    project_path: str | None = None


class ConversationTurn(Contract):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    expected_turns: int = Field(ge=0, lt=40)
    text: str = Field(min_length=1, max_length=4000)
    model_id: str = Field(min_length=1, max_length=100)
    allow_remote: bool = False

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class ConversationView(Contract):
    conversation: WorkspaceConversation
    turns: tuple[AgentRun, ...] = ()
