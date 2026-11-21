"""Owner-scoped durable conversations; agent runs remain the execution/learning unit."""

import asyncio
from dataclasses import dataclass

from auton.agent.contracts import Acceptance, AgentRun, CreateRun
from auton.agent.ports import AgentRuntimePort
from auton.constitution.config import Principal
from auton.constitution.secrets import Redactor
from auton.conversation.contracts import (
    ConversationCreate,
    ConversationTurn,
    ConversationView,
    WorkspaceConversation,
)
from auton.genome.contracts import Project
from auton.genome.ports import GenomePort
from auton.kernel.documents import key
from auton.kernel.events import Event, EventScope
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.kernel.storage import EventLogPort, StorageError
from auton.model.contracts import ModelMessage
from auton.model.ports import ModelGatewayPort
from auton.tools.ports import ToolHostPort


@dataclass(frozen=True)
class ConversationDependencies:
    agent: AgentRuntimePort
    assets: GenomePort
    tools: ToolHostPort
    models: ModelGatewayPort
    events: EventLogPort
    runtime: RuntimeDependencies


class WorkspaceConversations:
    def __init__(self, deps: ConversationDependencies) -> None:
        self.deps = deps
        self.lock = asyncio.Lock()
        self.active: set[asyncio.Task[AgentRun]] = set()
        self.closing = False

    async def start(self) -> None:
        self.closing = False

    async def close(self) -> None:
        self.closing = True
        await asyncio.gather(*list(self.active), return_exceptions=True)

    @staticmethod
    def scope(principal: Principal) -> EventScope:
        return EventScope(project_id="conversations-" + key(principal.owner, "index")[:40])

    async def append(self, event: Event) -> None:
        try:
            await self.deps.events.append([event])
        except StorageError:
            stored = await self.deps.events.lookup(event.event_id)
            if stored is None or stored.event.payload != event.payload:
                raise

    async def create(
        self, principal: Principal, command: ConversationCreate
    ) -> WorkspaceConversation:
        if principal.role != "user":
            raise ApplicationError(403, "conversation_user_required", "User control required")
        if Redactor().text(command.model_dump_json()) != command.model_dump_json():
            raise ApplicationError(403, "credential_in_input", "Do not store credentials in chat")
        identity = key(principal.owner, command.request_id)[:32]
        event_id = "conversation:" + key(principal.owner, identity)
        async with self.lock:
            found = await self.deps.events.lookup(event_id)
            if found:
                value = WorkspaceConversation.model_validate(found.event.payload["conversation"])
                if value.title != command.title:
                    raise ApplicationError(409, "conversation_conflict", "Request id already used")
                return value
            value = WorkspaceConversation(
                id=identity,
                title=command.title,
                project_id="chat-" + identity,
                workspace_id="chat-" + identity,
            )
            # Isolated empty project: selecting a remote model never grants access to other assets.
            try:
                await self.deps.assets.create_project(
                    principal, Project(id=value.project_id, title=value.title)
                )
            except ApplicationError as error:
                if error.code != "project_exists":
                    raise
            await self.deps.tools.create_workspace(
                principal, value.workspace_id, value.title, False
            )
            await self.append(
                Event(
                    event_id=event_id,
                    kind="conversation.created",
                    timestamp=self.deps.runtime.now(),
                    scope=self.scope(principal),
                    source="runtime",
                    payload={"conversation": value.model_dump(mode="json")},
                )
            )
            return value

    async def list(self, principal: Principal) -> list[WorkspaceConversation]:
        # Bounded history; explicit limit rather than silently scanning all owners' events.
        values: list[WorkspaceConversation] = []
        cursor = 0
        for _ in range(10):
            batch = await self.deps.events.read(
                after=cursor, limit=100, scope=self.scope(principal)
            )
            for item in batch:
                if item.event.kind == "conversation.created":
                    values.append(
                        WorkspaceConversation.model_validate(item.event.payload["conversation"])
                    )
            if len(batch) < 100:
                return list(reversed(values))
            cursor = batch[-1].cursor
        raise ApplicationError(
            429, "conversation_list_limit", "Conversation history exceeds 1000 entries"
        )

    async def view(self, principal: Principal, identity: str) -> ConversationView:
        found = await self.deps.events.lookup("conversation:" + key(principal.owner, identity))
        if found is None:
            raise ApplicationError(404, "conversation_not_found", "No owned conversation")
        conversation = WorkspaceConversation.model_validate(found.event.payload["conversation"])
        turns: list[AgentRun] = []
        for index in range(40):
            event = await self.deps.events.lookup(
                "conversation-turn:" + key(principal.owner, identity) + ":" + str(index)
            )
            if event is None:
                break
            turns.append(await self.deps.agent.get(principal, str(event.event.payload["run_id"])))
        return ConversationView(conversation=conversation, turns=tuple(turns))

    async def send(
        self, principal: Principal, identity: str, command: ConversationTurn
    ) -> AgentRun:
        if self.closing:
            raise ApplicationError(503, "conversation_closing", "Conversation service is stopping")
        # Losing an HTTP response cannot abandon the durable turn link or cancel the agent.
        task = asyncio.create_task(self._send(principal, identity, command))
        self.active.add(task)

        def done(value: asyncio.Task[AgentRun]) -> None:
            self.active.discard(value)
            if not value.cancelled():
                value.exception()

        task.add_done_callback(done)
        return await asyncio.shield(task)

    async def _send(
        self, principal: Principal, identity: str, command: ConversationTurn
    ) -> AgentRun:
        async with self.lock:
            view = await self.view(principal, identity)
            event_id = (
                "conversation-turn:"
                + key(principal.owner, identity)
                + ":"
                + str(command.expected_turns)
            )
            found = await self.deps.events.lookup(event_id)
            if found:
                if found.event.payload["digest"] != command.digest:
                    raise ApplicationError(
                        409, "conversation_turn_conflict", "Refresh before sending another turn"
                    )
                return await self.deps.agent.get(principal, str(found.event.payload["run_id"]))
            if len(view.turns) != command.expected_turns:
                raise ApplicationError(
                    409, "conversation_turn_conflict", "Conversation changed; reload first"
                )
            if view.turns and view.turns[-1].status not in {"succeeded", "failed", "cancelled"}:
                raise ApplicationError(
                    409, "conversation_turn_active", "Finish or stop the current turn first"
                )
            model = next(
                (m for m in self.deps.models.catalog(principal) if m.id == command.model_id), None
            )
            if model is None:
                raise ApplicationError(
                    409, "conversation_model_unknown", "Choose a registered model"
                )
            if model.location == "remote" and not command.allow_remote:
                raise ApplicationError(
                    403,
                    "conversation_remote_consent",
                    "Remote history transfer requires explicit selection",
                )
            history: list[ModelMessage] = []
            for run in view.turns:
                history.append(ModelMessage(role="user", content=run.command.goal))
                if run.final_text:
                    history.append(ModelMessage(role="assistant", content=run.final_text))
            workspace = await self.deps.tools.workspace(principal, view.conversation.workspace_id)
            run = await self.deps.agent.create(
                principal,
                CreateRun(
                    request_id="turn-"
                    + key(principal.owner, identity + ":" + str(command.expected_turns))[:60],
                    project_id=view.conversation.project_id,
                    workspace_id=view.conversation.workspace_id,
                    model_id=model.id,
                    goal=command.text,
                    prior_messages=tuple(history),
                    data_domain="public"
                    if model.location == "remote" and command.allow_remote
                    else "local-only",
                    allowed_tools=()
                    if "tools" not in model.capabilities
                    else (
                        ("file.read", "mcp.sha256")
                        if workspace.read_only
                        else ("file.read", "file.write", "mcp.sha256")
                    ),
                    acceptance=Acceptance(kind="response"),
                ),
            )
            await self.append(
                Event(
                    event_id=event_id,
                    kind="conversation.turn",
                    timestamp=self.deps.runtime.now(),
                    scope=EventScope(project_id=view.conversation.project_id),
                    source=run.source,
                    payload={"run_id": run.id, "digest": command.digest},
                )
            )
            return run
