from asyncio import Queue
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from auton.kernel.ports import LifecycleHandle


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class CreateSession(Contract):
    request_id: str = Field(min_length=1, max_length=100)


class SendMessage(Contract):
    request_id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=8000)


class StopRun(Contract):
    request_id: str = Field(min_length=1, max_length=100)
    run_id: str


class Artifact(Contract):
    id: str
    title: str
    filename: str
    content: str
    source: Literal["demo"] = "demo"


class Message(Contract):
    id: str
    role: Literal["user", "assistant"]
    content: str


class Session(Contract):
    id: str
    title: str = "新对话"
    created_at: str
    status: Literal["idle", "running", "stopping", "stopped", "completed"] = "idle"
    run_id: str | None = None
    goal_id: str | None = None
    goal_revision: int = 1
    sequence: int = 0
    messages: list[Message] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    source: Literal["demo"] = "demo"


class SessionEvent(Contract):
    event_id: str
    sequence: int
    session_id: str
    goal_id: str | None
    run_id: str | None
    goal_revision: int
    kind: Literal["session.updated"] = "session.updated"
    schema_version: Literal["1"] = "1"
    timestamp: str
    payload: Session


class ErrorBody(Contract):
    code: str
    message: str


class Responder(Protocol):
    def respond(self, prompt: str) -> str: ...


class ConversationPort(LifecycleHandle, Protocol):
    def list_sessions(self, owner: str) -> list[Session]: ...

    def create_session(self, owner: str, request: CreateSession) -> Session: ...

    def get_session(self, owner: str, session_id: str) -> Session: ...

    async def send(self, owner: str, session_id: str, request: SendMessage) -> Session: ...

    async def stop(self, owner: str, session_id: str, request: StopRun) -> Session: ...

    def subscribe(self, owner: str, session_id: str) -> Queue[SessionEvent]: ...

    def unsubscribe(self, session_id: str, queue: Queue[SessionEvent]) -> None: ...
