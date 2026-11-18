import hashlib
from typing import Literal, Protocol

from pydantic import Field, JsonValue

from auton.agent.contracts import checkpoint_event_id
from auton.agent.ports import AgentRuntimePort
from auton.constitution.config import Principal
from auton.kernel.events import Event, EventScope
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.kernel.storage import EventLogPort, StorageError
from auton.model.contracts import Contract


class FeedbackCommand(Contract):
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    expected_goal_revision: int = Field(ge=1)
    checkpoint_version: int = Field(ge=0, le=65535)
    category: Literal["delivery", "approval"] = "delivery"
    rating: Literal["helpful", "unhelpful"]
    note: str = Field(default="", max_length=2000)


class FeedbackReceipt(Contract):
    event_id: str
    run_id: str
    checkpoint_event_id: str
    label_source: Literal["human-feedback"] = "human-feedback"
    verified_quality: Literal[False] = False


class FeedbackPort(Protocol):
    async def submit(
        self, principal: Principal, run_id: str, command: FeedbackCommand
    ) -> FeedbackReceipt: ...


class FeedbackService:
    def __init__(
        self, agent: AgentRuntimePort, events: EventLogPort, runtime: RuntimeDependencies
    ) -> None:
        self.agent, self.events, self.runtime = agent, events, runtime

    async def submit(
        self, principal: Principal, run_id: str, command: FeedbackCommand
    ) -> FeedbackReceipt:
        if principal.role != "user":
            raise ApplicationError(403, "feedback_user_required", "Only users may provide feedback")
        run = await self.agent.get(principal, run_id)
        source_id = checkpoint_event_id(principal.owner, run_id, command.checkpoint_version)
        source = await self.events.lookup(source_id)
        if source is None or source.event.scope.goal_revision != command.expected_goal_revision:
            raise ApplicationError(
                409,
                "feedback_checkpoint_mismatch",
                "Feedback refers to a missing or different goal revision",
            )
        identity = (
            "user-feedback:"
            + hashlib.sha256((principal.owner + "\0" + command.request_id).encode()).hexdigest()
        )
        payload: dict[str, JsonValue] = {
            "run_id": run_id,
            "checkpoint_event_id": source_id,
            "label_source": "human-feedback",
            "verified_quality": False,
            "command": command.model_dump(mode="json"),
        }
        receipt = FeedbackReceipt(event_id=identity, run_id=run_id, checkpoint_event_id=source_id)
        old = await self.events.lookup(identity)
        if old:
            if old.event.payload != payload:
                raise ApplicationError(
                    409, "feedback_conflict", "Feedback request id has different input"
                )
            return receipt
        event = Event(
            event_id=identity,
            kind="agent.user_feedback",
            timestamp=self.runtime.now(),
            scope=EventScope.model_validate(
                {
                    "project_id": run.command.project_id,
                    "session_id": run.session_id,
                    "run_id": run_id,
                    "goal_revision": command.expected_goal_revision,
                }
            ),
            source=run.source,
            payload=payload,
        )
        try:
            await self.events.append([event])
        except StorageError:
            observed = await self.events.lookup(identity)
            if observed is None or observed.event.payload != payload:
                raise
        return receipt


class FeedbackFactory:
    def create(
        self, agent: AgentRuntimePort, events: EventLogPort, runtime: RuntimeDependencies
    ) -> FeedbackPort:
        return FeedbackService(agent, events, runtime)
