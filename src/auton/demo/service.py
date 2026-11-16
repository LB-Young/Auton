import asyncio
from hashlib import sha256

from auton.demo.config import DemoConfig
from auton.demo.ports import (
    Artifact,
    CreateSession,
    Message,
    Responder,
    SendMessage,
    Session,
    SessionEvent,
    StopRun,
)
from auton.kernel.ports import ApplicationError, RuntimeDependencies


class ScriptedResponder:
    def respond(self, prompt: str) -> str:
        return (
            "这是一次框架演示，不会调用模型或执行真实任务。\n\n"
            f"你希望探索：**{prompt[:160]}**\n\n"
            "我们可以从三个部分开始：\n\n"
            "1. **明确目标**：把预期结果与约束写清楚。\n"
            "2. **拆分模块**：通过工厂创建实现，使用公共接口连接。\n"
            "3. **验证结果**：保留可复现步骤，逐项验收。\n\n"
            "我生成了一份合成的项目笔记，你可以在右侧查看。"
            "后续里程碑会逐步接入真实模型、工具与任务执行。"
        )


class EchoResponder:
    def respond(self, prompt: str) -> str:
        return f"[Demo · Echo]\n\n{prompt}\n\n这是一条内存回声，不来自真实模型。"


class DemoConversationService:
    """One app-scoped instance; separate owner/session/run state, no global state."""

    def __init__(self, config: DemoConfig, deps: RuntimeDependencies, responder: Responder) -> None:
        self.config = config
        self.deps = deps
        self.responder = responder
        self.sessions: dict[str, Session] = {}
        self.owners: dict[str, str] = {}
        self.creations: dict[tuple[str, str], str] = {}
        self.commands: dict[tuple[str, str], str] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.listeners: dict[str, set[asyncio.Queue[SessionEvent]]] = {}
        self.started = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.started = False
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
        self.listeners.clear()

    def _check_started(self) -> None:
        if not self.started:
            raise ApplicationError(503, "not_ready", "演示服务尚未启动或已关闭")

    def _session(self, owner: str, session_id: str) -> Session:
        self._check_started()
        if self.owners.get(session_id) != owner:
            raise ApplicationError(404, "not_found", "找不到此会话")
        return self.sessions[session_id]

    def list_sessions(self, owner: str) -> list[Session]:
        self._check_started()
        return [
            session.model_copy(deep=True)
            for key, session in reversed(self.sessions.items())
            if self.owners[key] == owner
        ]

    def create_session(self, owner: str, request: CreateSession) -> Session:
        self._check_started()
        key = (owner, request.request_id)
        if key in self.creations:
            return self.get_session(owner, self.creations[key])
        if len(self.sessions) >= self.config.max_sessions:
            raise ApplicationError(429, "demo_limit", "演示会话数量已达上限，重启服务可重置")
        session = Session(id=self.deps.new_id(), created_at=self.deps.now().isoformat())
        self.sessions[session.id] = session
        self.owners[session.id] = owner
        self.creations[key] = session.id
        return session.model_copy(deep=True)

    def get_session(self, owner: str, session_id: str) -> Session:
        return self._session(owner, session_id).model_copy(deep=True)

    def _previous(self, session_id: str, request_id: str, fingerprint: str) -> Session | None:
        previous = self.commands.get((session_id, request_id))
        if previous:
            if previous != fingerprint:
                raise ApplicationError(409, "request_conflict", "同一个请求 ID 不能用于不同命令")
            return self.sessions[session_id].model_copy(deep=True)
        # Bound idempotency storage; never silently forget an accepted command.
        if sum(key[0] == session_id for key in self.commands) >= 200:
            raise ApplicationError(429, "demo_limit", "演示命令数量已达上限，请新建会话")
        return None

    async def send(self, owner: str, session_id: str, request: SendMessage) -> Session:
        session = self._session(owner, session_id)
        fingerprint = sha256(("send:" + request.content).encode()).hexdigest()
        previous = self._previous(session_id, request.request_id, fingerprint)
        if previous:
            return previous
        if session.status in {"running", "stopping"}:
            raise ApplicationError(409, "run_active", "请等待当前演示完成或先停止")
        if not request.content.strip():
            raise ApplicationError(422, "empty_message", "消息不能为空")
        if len(session.messages) + 2 > self.config.max_messages:
            raise ApplicationError(429, "demo_limit", "演示消息数量已达上限，请新建会话")
        answer = self.responder.respond(request.content)
        session.title = request.content.strip()[:28]
        session.run_id = self.deps.new_id()
        session.goal_id = self.deps.new_id()
        session.status = "running"
        session.messages.extend(
            [
                Message(id=self.deps.new_id(), role="user", content=request.content),
                Message(id=self.deps.new_id(), role="assistant", content=""),
            ]
        )
        self._emit(session)
        result = session.model_copy(deep=True)
        self.commands[(session_id, request.request_id)] = fingerprint
        self.tasks[session_id] = asyncio.create_task(self._stream(session, answer))
        return result.model_copy(deep=True)

    async def _stream(self, session: Session, answer: str) -> None:
        try:
            for offset in range(0, len(answer), 5):
                await asyncio.sleep(self.config.chunk_delay_seconds)
                session.messages[-1].content += answer[offset : offset + 5]
                self._emit(session)
            session.artifacts.append(
                Artifact(
                    id=self.deps.new_id(),
                    title="项目起步笔记",
                    filename="project-notes.md",
                    content=(
                        "# 项目起步笔记\n\n> 合成示例 · 未执行真实任务\n\n"
                        f"## 你的目标\n\n{session.messages[-2].content}\n\n"
                        "## 开发顺序\n\n"
                        "- 先搭项目框架和工厂接口\n"
                        "- 建立前后端契约与模块边界\n"
                        "- 逐模块实现并完成验收\n\n"
                        "本文件仅存在于 Demo 内存中，没有写入工作目录或发布。"
                    ),
                )
            )
            session.status = "completed"
            self._emit(session)
        except asyncio.CancelledError:
            session.status = "stopped"
            self._emit(session)
            raise
        finally:
            self.tasks.pop(session.id, None)

    async def stop(self, owner: str, session_id: str, request: StopRun) -> Session:
        session = self._session(owner, session_id)
        fingerprint = "stop:" + request.run_id
        previous = self._previous(session_id, request.request_id, fingerprint)
        if previous:
            return previous
        if session.run_id != request.run_id:
            raise ApplicationError(409, "stale_run", "停止请求不属于当前运行")
        task = self.tasks.get(session_id)
        if task and not task.done():
            session.status = "stopping"
            self._emit(session)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            # Also covers cancellation before the coroutine first starts.
            if session.status == "stopping":
                session.status = "stopped"
                self._emit(session)
            self.tasks.pop(session_id, None)
        result = session.model_copy(deep=True)
        self.commands[(session_id, request.request_id)] = fingerprint
        return result.model_copy(deep=True)

    def _event(self, session: Session) -> SessionEvent:
        return SessionEvent(
            event_id=self.deps.new_id(),
            sequence=session.sequence,
            session_id=session.id,
            goal_id=session.goal_id,
            run_id=session.run_id,
            goal_revision=session.goal_revision,
            timestamp=self.deps.now().isoformat(),
            payload=session.model_copy(deep=True),
        )

    def _emit(self, session: Session) -> None:
        session.sequence += 1
        event = self._event(session)
        for queue in self.listeners.get(session.id, set()):
            if queue.full():
                queue.get_nowait()  # Full snapshots safely supersede older snapshots.
            queue.put_nowait(event)

    def subscribe(self, owner: str, session_id: str) -> asyncio.Queue[SessionEvent]:
        session = self._session(owner, session_id)
        if len(self.listeners.get(session_id, set())) >= 8:
            raise ApplicationError(429, "demo_limit", "此会话的连接过多")
        queue: asyncio.Queue[SessionEvent] = asyncio.Queue(maxsize=1)
        self.listeners.setdefault(session_id, set()).add(queue)
        queue.put_nowait(self._event(session))
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[SessionEvent]) -> None:
        self.listeners.get(session_id, set()).discard(queue)
