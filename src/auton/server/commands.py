import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar, cast

from auton.agent.contracts import AgentRun, CreateRun, RunCommand
from auton.agent.ports import AgentRuntimePort
from auton.constitution.config import Principal
from auton.experience.contracts import RecoveryCommand
from auton.experience.ports import ExperiencePort
from auton.kernel.ports import ApplicationError, LifecycleHandle

T = TypeVar("T")


class CommandHandlerPort(LifecycleHandle, Protocol):
    async def create(self, principal: Principal, command: CreateRun) -> AgentRun: ...
    async def apply(self, principal: Principal, run_id: str, command: RunCommand) -> AgentRun: ...
    async def recover(
        self, principal: Principal, project: str, run_id: str, command: RecoveryCommand
    ) -> AgentRun: ...


class CommandHandler:
    def __init__(self, agent: AgentRuntimePort, experience: ExperiencePort) -> None:
        self.agent, self.experience = agent, experience
        self.active: dict[str, tuple[str, asyncio.Task[object]]] = {}
        self.ready = False

    async def start(self) -> None:
        self.ready = True

    async def close(self) -> None:
        self.ready = False
        await asyncio.gather(
            *(value[1] for value in list(self.active.values())), return_exceptions=True
        )

    async def execute(self, key: str, digest: str, operation: Callable[[], Awaitable[T]]) -> T:
        if not self.ready:
            raise ApplicationError(503, "commands_not_ready", "Command service is stopping")
        existing = self.active.get(key)
        if existing and existing[0] != digest:
            raise ApplicationError(
                409, "command_conflict", "Pending request id has different input"
            )
        if existing:
            task = existing[1]
        else:
            if len(self.active) >= 64:
                raise ApplicationError(429, "command_limit", "Too many pending commands")

            async def invoke() -> object:
                return await operation()

            task = asyncio.create_task(invoke())
            self.active[key] = (digest, task)

            def completed(done: asyncio.Task[object]) -> None:
                self.active.pop(key, None)
                if not done.cancelled():
                    done.exception()

            task.add_done_callback(completed)
        # HTTP cancellation cannot cancel a durable command or its background agent run.
        return cast(T, await asyncio.shield(task))

    @staticmethod
    def key(principal: Principal, request_id: str) -> str:
        return hashlib.sha256((principal.owner + "\0" + request_id).encode()).hexdigest()

    async def create(self, principal: Principal, command: CreateRun) -> AgentRun:
        return await self.execute(
            self.key(principal, command.request_id),
            command.digest,
            lambda: self.agent.create(principal, command),
        )

    async def apply(self, principal: Principal, run_id: str, command: RunCommand) -> AgentRun:
        digest = hashlib.sha256((run_id + command.model_dump_json()).encode()).hexdigest()
        return await self.execute(
            self.key(principal, command.request_id),
            digest,
            lambda: self.agent.command(principal, run_id, command),
        )

    async def recover(
        self, principal: Principal, project: str, run_id: str, command: RecoveryCommand
    ) -> AgentRun:
        digest = hashlib.sha256((project + run_id + command.model_dump_json()).encode()).hexdigest()
        return await self.execute(
            self.key(principal, command.request_id),
            digest,
            lambda: self.experience.recover(principal, project, run_id, command),
        )


class CommandHandlerFactory:
    def create(self, agent: AgentRuntimePort, experience: ExperiencePort) -> CommandHandlerPort:
        return CommandHandler(agent, experience)
