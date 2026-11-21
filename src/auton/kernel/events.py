import hashlib
import json
from typing import Annotated, Literal, NewType

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

GoalId = NewType("GoalId", str)
TaskId = NewType("TaskId", str)
RunId = NewType("RunId", str)
AttemptId = NewType("AttemptId", str)
OperationId = NewType("OperationId", str)
Identifier = Annotated[str, Field(min_length=1, max_length=200)]


class EventScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    project_id: Identifier | None = None
    session_id: Identifier | None = None
    goal_id: GoalId | None = None
    task_id: TaskId | None = None
    run_id: RunId | None = None
    attempt_id: AttemptId | None = None
    operation_id: OperationId | None = None
    goal_revision: int = Field(default=1, ge=1)


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    event_id: Identifier
    kind: str = Field(min_length=1, max_length=150, pattern=r"^[a-zA-Z][a-zA-Z0-9_.-]*$")
    schema_version: Literal[1] = 1
    timestamp: AwareDatetime
    scope: EventScope = Field(default_factory=EventScope)
    source: Literal["system", "demo", "runtime", "test"]
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    def canonical(self) -> str:
        # Serialization also detaches mutable payloads from stored facts.
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )

    def digest(self) -> str:
        return hashlib.sha256(self.canonical().encode()).hexdigest()


class StoredEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    cursor: int = Field(ge=1)
    event: Event


class AppendReceipt(BaseModel):
    outcome: Literal["committed"] = "committed"
    records: list[StoredEvent]


class StorageInfo(BaseModel):
    backend: Literal["sqlite", "memory"]
    ready: bool
    durable: bool
    schema_version: int
    sqlite_version: str | None = None
    journal_mode: str
    synchronous: str
