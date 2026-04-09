"""Agent — SessionProcessor 核心循环"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, AsyncIterator

from loguru import logger

from ..core.events import EventBus, get_event_bus
from ..core.event_types import (
    TextDeltaEvent,
    TextFinishEvent,
    ToolCallEvent,
    ToolErrorEvent,
    ToolResultEvent,
    StepFinishEvent,
    StepStartEvent,
    SessionCompactEvent,
    SessionStatusChangeEvent,
)
from ..llm.base import LLMProvider
from .context import ContextBuilder
from .message import Message
from .policies import DecisionPolicy, PolicyInput
from .session import Session
from .session_store import SessionStore
from .types import ProcessResult

if TYPE_CHECKING:
    from ..tools.base import Tool, ToolResult


class SessionProcessor:
    """Session 主循环处理器

    while True:
        1. build context from session + memory
        2. stream LLM response (emit events)
        3. handle tool calls
        4. policy.decide() → continue / compact / stop
    """

    def __init__(
        self,
        session: Session,
        llm: LLMProvider,
        tools: list["Tool"],
        session_store: SessionStore,
        event_bus: EventBus | None = None,
        policy: DecisionPolicy | None = None,
        command_registry=None,
    ) -> None:
        self.session = session
        self.llm = llm
        self.tools = {t.name: t for t in tools}
        self.session_store = session_store
        self.events = event_bus or get_event_bus()
        self.policy = policy or DecisionPolicy()
        self._ctx_builder = ContextBuilder(llm, [t.schema() for t in tools])
        self._logger = logger.bind(name="SessionProcessor")
        self._last_stored_msg_index = -1  # 跟踪已存储的消息位置
        self._command_registry = command_registry  # 懒加载

    # ─── 主循环 ────────────────────────────────────────────────────────────

    async def run(self) -> ProcessResult:
        """运行主循环直到结束，返回最终结果"""
        self.session.update_status("running")
        self.events.emit_sync(
            SessionStatusChangeEvent(
                session_id=self.session.meta.session_id,
                status="running",
            )
        )

        # 首次：存储所有已有的 user/system 消息
        for i in range(self._last_stored_msg_index + 1, len(self.session.messages)):
            msg = self.session.messages[i]
            if msg.role == "user":
                self.session_store.append_user_message(
                    self.session.meta.session_id,
                    msg.get_text(),
                )
            elif msg.role == "system":
                self.session_store.append_system_message(
                    self.session.meta.session_id,
                    msg.get_text(),
                )
        self._last_stored_msg_index = len(self.session.messages) - 1

        while True:
            # 1. 构建上下文
            ctx = self._ctx_builder.build(self.session)

            # 系统提示词只存一次
            if ctx.system_prompt and not self._ctx_builder._system_stored:
                self.session_store.append_system_message(
                    self.session.meta.session_id,
                    ctx.system_prompt,
                )
                self._ctx_builder._system_stored = True

            # 2. LLM streaming
            assistant_msg = self.session.add_assistant_message()
            async for event in self.llm.stream(ctx):
                await self._handle_llm_event(event, assistant_msg)

            # 3. 处理工具调用
            await self._execute_tools(assistant_msg)

            # 4. 持久化助手消息
            self.session_store.append_assistant_message(self.session.meta.session_id, assistant_msg)

            # 5. 存储本轮新增的 user message（工具结果等）
            for i in range(self._last_stored_msg_index + 1, len(self.session.messages)):
                msg = self.session.messages[i]
                if msg.role == "user":
                    self.session_store.append_user_message(
                        self.session.meta.session_id,
                        msg.get_text(),
                    )
            self._last_stored_msg_index = len(self.session.messages) - 1

            # 6. 决策
            decision = self._decide()

            if decision.status == "compact":
                # compact 后重新从 session 开始读（reset index）
                self._last_stored_msg_index = len(self.session.messages) - 1
                await self._do_compact()
                continue
            elif decision.status == "stop":
                await self._do_stop(decision.reason)
                return decision
            # continue: loop

    # ─── 命令处理 ─────────────────────────────────────────────────────────

    async def _try_handle_command(self) -> tuple[bool, "CommandResult | None"]:
        """检查最后一条用户消息是否为命令，若是则执行并返回结果。

        Returns:
            (handled, result): handled=True 表示已处理（不需要 LLM）
        """
        from ..commands import CommandContext, CommandResult, get_command_registry

        if self._command_registry is None:
            self._command_registry = get_command_registry()

        # 获取最后一条 user message
        last_user_text = ""
        for msg in reversed(self.session.messages):
            if msg.role == "user":
                last_user_text = msg.get_text()
                break
        if not last_user_text:
            return False, None

        # 尝试匹配命令
        command, args = self._command_registry.match(last_user_text)
        if command is None:
            return False, None

        # 构建命令上下文
        cmd_ctx = CommandContext(
            session=self.session,
            session_store=self.session_store,
            llm=self.llm,
            config=None,  # type: ignore[arg-type] — config 在 registry 层注入
        )

        self._logger.info("handling command /{name}", name=command.name)

        try:
            result = await command.handle(args or {})
        except Exception as exc:
            result = CommandResult(
                content=f"[error] Command /{command.name} failed: {exc}",
                success=False,
                error=str(exc),
            )

        # 将命令结果追加为 user message（保持上下文连贯）
        result_msg = Message(role="user")
        result_msg.add_text(f"[command: /{command.name}]\n{result.content}")
        self.session.messages.append(result_msg)

        return True, result

    # ─── 主循环 ────────────────────────────────────────────────────────────

    async def run_stream(self) -> AsyncIterator:
        """流式运行，yield 每条事件（供 CLI 渲染）"""
        # 检查是否为命令
        handled, cmd_result = await self._try_handle_command()
        if handled:
            if cmd_result:
                yield cmd_result
            yield ProcessResult(status="stop", reason="command handled")
            return

        while True:
            ctx = self._ctx_builder.build(self.session)

            # 系统提示词只存一次
            if ctx.system_prompt and not self._ctx_builder._system_stored:
                self.session_store.append_system_message(
                    self.session.meta.session_id,
                    ctx.system_prompt,
                )
                self._ctx_builder._system_stored = True

            # 存储新出现的 user message（跳过已存储的）
            for i in range(self._last_stored_msg_index + 1, len(self.session.messages)):
                msg = self.session.messages[i]
                if msg.role == "user":
                    self.session_store.append_user_message(
                        self.session.meta.session_id,
                        msg.get_text(),
                    )
                elif msg.role == "system":
                    self.session_store.append_system_message(
                        self.session.meta.session_id,
                        msg.get_text(),
                    )
            self._last_stored_msg_index = len(self.session.messages) - 1

            assistant_msg = self.session.add_assistant_message()

            async for event in self.llm.stream(ctx):
                await self._handle_llm_event(event, assistant_msg)
                yield event

            await self._execute_tools(assistant_msg)
            self.session_store.append_assistant_message(self.session.meta.session_id, assistant_msg)

            # 检查本轮是否有工具执行（有工具结果说明需要下一轮 LLM 继续）
            tools_executed = any(
                p.status in ("completed", "error")
                for p in assistant_msg.get_tools()
            )

            # 存储本轮新增的 user message（工具结果等）
            for i in range(self._last_stored_msg_index + 1, len(self.session.messages)):
                msg = self.session.messages[i]
                if msg.role == "user":
                    self.session_store.append_user_message(
                        self.session.meta.session_id,
                        msg.get_text(),
                    )
            self._last_stored_msg_index = len(self.session.messages) - 1

            decision = self._decide()
            if decision.status == "compact":
                await self._do_compact()
                continue
            elif decision.status == "stop":
                await self._do_stop(decision.reason)
            yield decision
            # 只有当本轮执行了工具时才继续循环；否则退出
            if not tools_executed:
                return

    # ─── 事件处理 ─────────────────────────────────────────────────────────

    async def _handle_llm_event(self, event, msg: Message) -> None:
        """将 LLM 流事件转换为内部事件并 emit"""
        # TextPart
        if event.type == "text_start":
            msg.add_text()
            self.events.emit_sync(
                SessionStatusChangeEvent(
                    session_id=self.session.meta.session_id,
                    status="running",
                    step_id=str(self.session.meta.step_count),
                )
            )
        elif event.type == "text_delta":
            text_parts = [p for p in msg.parts if p.type == "text"]
            if text_parts:
                text_parts[0].append(event.delta)
            self.events.emit_sync(
                TextDeltaEvent(
                    session_id=self.session.meta.session_id,
                    delta=event.delta,
                )
            )
        elif event.type == "text_finish":
            self.events.emit_sync(
                TextFinishEvent(
                    session_id=self.session.meta.session_id,
                    content=msg.get_text(),
                )
            )
        # ReasoningPart (MiniMax thinking)
        elif event.type == "reasoning_start":
            msg.add_reasoning()
        elif event.type == "reasoning_delta":
            reasoning_parts = [p for p in msg.parts if p.type == "reasoning"]
            if reasoning_parts:
                reasoning_parts[0].append(event.delta)
        elif event.type == "reasoning_finish":
            pass  # already captured via delta
        # ToolUse
        elif event.type == "tool_use":
            tool_part = msg.add_tool(
                tool_name=event.name,
                tool_input=event.input,
                tool_call_id=event.id,
            )
            self.events.emit_sync(
                ToolCallEvent(
                    session_id=self.session.meta.session_id,
                    tool_name=event.name,
                    tool_input=event.input,
                    tool_call_id=event.id,
                )
            )
        # ContentBlockStop
        elif event.type == "content_block_stop":
            pass  # handled in tool execution

    async def _execute_tools(self, msg: Message) -> None:
        """执行所有 pending 状态的 tool calls"""
        for part in msg.get_tools():
            if part.status != "pending":
                continue

            part.status = "running"
            tool = self.tools.get(part.tool_name)

            if tool is None:
                part.status = "error"
                part.tool_output = f"Unknown tool: {part.tool_name}"
                self.events.emit_sync(
                    ToolErrorEvent(
                        session_id=self.session.meta.session_id,
                        tool_name=part.tool_name,
                        error=f"Unknown tool: {part.tool_name}",
                        tool_call_id=part.tool_call_id,
                    )
                )
                continue

            try:
                result: "ToolResult" = await tool.execute(**part.tool_input)
                part.status = "completed"
                part.tool_output = result.content
                self.events.emit_sync(
                    ToolResultEvent(
                        session_id=self.session.meta.session_id,
                        tool_name=part.tool_name,
                        output=result.content,
                        tool_call_id=part.tool_call_id,
                    )
                )
                # 添加 tool result 作为 user message 续上下文（由 run/run_stream 的存储循环统一写入）
                result_content = f"[tool: {part.tool_name}]\n{result.content}"
                result_msg = Message(role="user")
                result_msg.add_text(result_content)
                self.session.messages.append(result_msg)
            except Exception as exc:
                part.status = "error"
                part.tool_output = str(exc)
                self.events.emit_sync(
                    ToolErrorEvent(
                        session_id=self.session.meta.session_id,
                        tool_name=part.tool_name,
                        error=str(exc),
                        tool_call_id=part.tool_call_id,
                    )
                )

    # ─── 决策 ────────────────────────────────────────────────────────────

    def _decide(self) -> ProcessResult:
        last_user = ""
        for msg in reversed(self.session.messages):
            if msg.role == "user":
                last_user = msg.get_text()
                break

        inp = PolicyInput(
            message_count=len(self.session.messages),
            token_count=self.session._token_count,
            last_user_message=last_user,
            step_count=self.session.meta.step_count,
        )
        return self.policy.decide(inp)

    # ─── Compact / Stop ─────────────────────────────────────────────────

    async def _do_compact(self) -> None:
        self.session.update_status("compact")
        compacted = self.session.compact()
        self.session_store.append_compact_event(
            self.session.meta.session_id,
            before_count=compacted,
            summary="[compacted]",  # 实际 summary 由 session.compact() 生成
        )
        self.events.emit_sync(
            SessionCompactEvent(
                session_id=self.session.meta.session_id,
                compacted_count=compacted,
            )
        )
        self.session.update_status("running")
        self._logger.info("compact completed, messages={n}", n=len(self.session.messages))

    async def _do_stop(self, reason: str) -> None:
        self.session.update_status("idle", reason=reason)
        self.session_store.archive_session(
            session_id=self.session.meta.session_id,
            started_at=self.session.meta.created_at.isoformat(),
            ended_at=self.session.meta.updated_at.isoformat(),
            compaction_count=self.session.meta.compaction_count,
        )
        self._logger.info("session stopped reason={r}", r=reason)
