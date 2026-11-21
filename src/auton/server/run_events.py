import asyncio
from typing import Literal, Protocol

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import Field, ValidationError

from auton.agent.contracts import AgentRun, TransientProgress, checkpoint_event_id
from auton.agent.ports import AgentRuntimePort
from auton.constitution.config import Principal
from auton.kernel.events import EventScope
from auton.kernel.ports import ApplicationError
from auton.kernel.storage import EventLogPort
from auton.model.contracts import Contract
from auton.server.identity import IdentityPort, ServerSettings


class RunSnapshot(Contract):
    run: AgentRun
    cursor: int
    checkpoint_event_id: str
    transient: TransientProgress | None = None


class RunFrame(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["snapshot", "checkpoint", "delta", "heartbeat", "reset_required"]
    run_id: str
    cursor: int = Field(ge=0)
    version: int
    goal_revision: int
    persisted: bool
    reason: str | None = None
    progress: TransientProgress | None = None


class RunEventStreamPort(Protocol):
    async def snapshot(self, principal: Principal, run_id: str) -> RunSnapshot: ...
    async def connect(
        self, socket: WebSocket, principal: Principal, token: str, run_id: str, after: int
    ) -> None: ...


class RunEventStream:
    def __init__(
        self,
        config: ServerSettings,
        agent: AgentRuntimePort,
        events: EventLogPort,
        identity: IdentityPort,
    ) -> None:
        self.config, self.agent, self.events, self.identity = config, agent, events, identity
        self.active: dict[str, int] = {}

    async def snapshot(self, principal: Principal, run_id: str) -> RunSnapshot:
        run = await self.agent.get(principal, run_id)
        event_id = checkpoint_event_id(principal.owner, run_id, run.version)
        stored = await self.events.lookup(event_id)
        if stored is None:
            raise ApplicationError(
                409, "snapshot_source_missing", "Exact run checkpoint is unavailable"
            )
        progress = await self.agent.transient(principal, run_id)
        if progress and (
            progress.version != run.version or progress.request_id != run.model_request_id
        ):
            progress = None
        return RunSnapshot(
            run=run, cursor=stored.cursor, checkpoint_event_id=event_id, transient=progress
        )

    async def connect(
        self, socket: WebSocket, principal: Principal, token: str, run_id: str, after: int
    ) -> None:
        if self.active.get(principal.owner, 0) >= 4:
            await socket.close(code=1013)
            return
        if self.identity.owner(token) != principal.owner:
            raise ApplicationError(
                403, "session_scope_mismatch", "Socket identity does not match the actor"
            )
        self.active[principal.owner] = self.active.get(principal.owner, 0) + 1
        try:
            await self._serve(socket, principal, token, run_id, after)
        except WebSocketDisconnect:
            pass
        finally:
            self.active[principal.owner] -= 1
            if not self.active[principal.owner]:
                self.active.pop(principal.owner, None)

    async def _serve(
        self, socket: WebSocket, principal: Principal, token: str, run_id: str, after: int
    ) -> None:
        state = await self.snapshot(principal, run_id)
        await socket.accept()

        async def send(frame: RunFrame) -> None:
            self.identity.owner(token)
            await asyncio.wait_for(
                socket.send_json(frame.model_dump(mode="json")), self.config.stream_send_timeout
            )

        async def disconnected() -> None:
            while True:
                message = await socket.receive()
                if message["type"] == "websocket.disconnect":
                    return
                # This channel is read-only; commands always use authenticated HTTP.
                if message.get("bytes") or len(str(message.get("text", ""))) > 1024:
                    return

        receiver = asyncio.create_task(disconnected())
        try:
            invalid = after < 0 or after > state.cursor
            if after and not invalid:
                rows = await self.events.read(
                    after=after - 1, limit=1, scope=EventScope.model_validate({"run_id": run_id})
                )
                invalid = (
                    not rows or rows[0].cursor != after or rows[0].event.kind != "agent.checkpoint"
                )
            if invalid:
                await send(
                    RunFrame(
                        kind="reset_required",
                        run_id=run_id,
                        cursor=state.cursor,
                        version=state.run.version,
                        goal_revision=state.run.goal_revision,
                        persisted=False,
                        reason="cursor_invalid",
                    )
                )
                after = state.cursor
            await send(
                RunFrame(
                    kind="snapshot",
                    run_id=run_id,
                    cursor=state.cursor,
                    version=state.run.version,
                    goal_revision=state.run.goal_revision,
                    persisted=True,
                )
            )
            scan = after
            public_cursor = state.cursor
            sequence: tuple[str, int] | None = None
            idle = 0
            while not receiver.done():
                self.identity.owner(token)
                rows = await self.events.read(
                    after=scan,
                    limit=self.config.stream_page_size,
                    scope=EventScope.model_validate({"run_id": run_id}),
                )
                for row in rows:
                    scan = row.cursor
                    if row.event.kind != "agent.checkpoint":
                        continue
                    run = AgentRun.model_validate(row.event.payload["run"])
                    if row.event.event_id != checkpoint_event_id(
                        principal.owner, run_id, run.version
                    ):
                        raise ApplicationError(
                            403, "event_scope_mismatch", "Checkpoint scope mismatch"
                        )
                    await send(
                        RunFrame(
                            kind="checkpoint",
                            run_id=run_id,
                            cursor=row.cursor,
                            version=run.version,
                            goal_revision=run.goal_revision,
                            persisted=True,
                        )
                    )
                    public_cursor = max(public_cursor, row.cursor)
                progress = await self.agent.transient(principal, run_id)
                if progress and sequence != (progress.request_id, progress.sequence):
                    sequence = (progress.request_id, progress.sequence)
                    await send(
                        RunFrame(
                            kind="delta",
                            run_id=run_id,
                            cursor=public_cursor,
                            version=progress.version,
                            goal_revision=progress.goal_revision,
                            persisted=False,
                            progress=progress,
                        )
                    )
                if not rows:
                    idle += 1
                    if idle >= 40:
                        latest = await self.agent.get(principal, run_id)
                        await send(
                            RunFrame(
                                kind="heartbeat",
                                run_id=run_id,
                                cursor=public_cursor,
                                version=latest.version,
                                goal_revision=latest.goal_revision,
                                persisted=False,
                            )
                        )
                        idle = 0
                    try:
                        await asyncio.wait_for(asyncio.shield(receiver), 0.1)
                    except TimeoutError:
                        pass
                else:
                    idle = 0
        except (
            ApplicationError,
            TimeoutError,
            OSError,
            RuntimeError,
            WebSocketDisconnect,
            ValidationError,
        ):
            try:
                await socket.close(code=1013)
            except (RuntimeError, OSError, WebSocketDisconnect):
                pass
        finally:
            receiver.cancel()
            from anyio import CancelScope

            with CancelScope(shield=True):
                await asyncio.gather(receiver, return_exceptions=True)
                try:
                    await asyncio.wait_for(socket.close(), 1)
                except (TimeoutError, RuntimeError, OSError, WebSocketDisconnect):
                    pass


class EventStreamFactory:
    def create(
        self,
        config: ServerSettings,
        agent: AgentRuntimePort,
        events: EventLogPort,
        identity: IdentityPort,
    ) -> RunEventStreamPort:
        return RunEventStream(config, agent, events, identity)
