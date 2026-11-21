import hashlib

from pydantic import JsonValue, ValidationError

from auton.agent.contracts import AgentRun, checkpoint_event_id
from auton.kernel.events import Event, EventScope
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.kernel.storage import EventLogPort, StorageError


def key(owner: str, identity: str) -> str:
    return hashlib.sha256((owner + "\0" + identity).encode()).hexdigest()


class RunRepository:
    def __init__(self, events: EventLogPort, runtime: RuntimeDependencies) -> None:
        self.events, self.runtime = events, runtime

    async def load(self, owner: str, identity: str) -> AgentRun:
        prefix = "agent:" + key(owner, identity) + ":"
        first = await self.events.lookup(prefix + "0")
        if first is None:
            raise ApplicationError(404, "run_not_found", "No owned agent run")
        latest = first
        # Bounded run history; binary lookup avoids replaying unrelated event streams.
        low, high = 0, 1
        while high < 65536:
            found = await self.events.lookup(prefix + str(high))
            if found is None:
                break
            low, latest, high = high, found, high * 2
        while low + 1 < high:
            middle = (low + high) // 2
            found = await self.events.lookup(prefix + str(middle))
            if found:
                low, latest = middle, found
            else:
                high = middle
        try:
            return AgentRun.model_validate(latest.event.payload["run"])
        except ValidationError as error:
            raise ApplicationError(
                409,
                "agent_checkpoint_schema_incompatible",
                "Checkpoint schema is unsupported; execution is blocked",
            ) from error

    async def command_seen(self, owner: str, command_id: str, digest: str) -> str | None:
        value = await self.events.lookup("agent-command:" + key(owner, command_id))
        if value is None:
            return None
        if value.event.payload["digest"] != digest:
            raise ApplicationError(
                409, "agent_command_conflict", "Command id belongs to another input"
            )
        return str(value.event.payload["run_id"])

    async def save(
        self, owner: str, run: AgentRun, command_id: str | None = None, digest: str = ""
    ) -> AgentRun:
        if run.version >= 65536:
            raise ApplicationError(429, "agent_history_limit", "Run reached its checkpoint limit")
        payload: dict[str, JsonValue] = {"run": run.model_dump(mode="json")}
        scope = EventScope.model_validate(
            {
                "project_id": run.command.project_id,
                "session_id": run.session_id,
                "run_id": run.id,
                "goal_id": "agent-goal-" + run.id,
                "goal_revision": run.goal_revision,
            }
        )
        event = Event(
            event_id=checkpoint_event_id(owner, run.id, run.version),
            kind="agent.checkpoint",
            timestamp=self.runtime.now(),
            scope=scope,
            source=run.source,
            payload=payload,
        )
        events = [event]
        if command_id:
            events.append(
                Event(
                    event_id="agent-command:" + key(owner, command_id),
                    kind="agent.command",
                    timestamp=self.runtime.now(),
                    scope=scope,
                    source=run.source,
                    payload={"run_id": run.id, "digest": digest},
                )
            )
        try:
            await self.events.append(events)
        except StorageError:
            stored = await self.events.lookup(event.event_id)
            accepted = await self.events.lookup(events[-1].event_id)
            if (
                stored is None
                or stored.event.payload != payload
                or accepted is None
                or accepted.event.payload != events[-1].payload
            ):
                raise
        return run

    async def list(self, owner: str, project_id: str, session_id: str) -> list[AgentRun]:
        cursor = 0
        ids: set[str] = set()
        scope = EventScope(project_id=project_id, session_id=session_id)
        while True:
            batch = await self.events.read(after=cursor, limit=1000, scope=scope)
            if not batch:
                break
            for item in batch:
                if item.event.kind == "agent.checkpoint" and item.event.scope.run_id:
                    ids.add(str(item.event.scope.run_id))
            cursor = batch[-1].cursor
            if len(ids) > 100:
                raise ApplicationError(
                    429,
                    "agent_list_limit",
                    "Narrow project history before listing more than 100 runs",
                )
        return [await self.load(owner, identity) for identity in sorted(ids)]


class RunRepositoryFactory:
    def create(self, events: EventLogPort, runtime: RuntimeDependencies) -> RunRepository:
        return RunRepository(events, runtime)
