"""Agent — SessionProcessor 核心循环"""

from __future__ import annotations

import asyncio
import json
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
from .session import CompactResult, Session
from .session_store import SessionStore
from .token_utils import estimate_context_tokens
from .types import LLMContext, ProcessResult

if TYPE_CHECKING:
    from ..tools.base import Tool, ToolResult
    from ..skills.injector import SkillInjector
    from ..memory.memory_read_hook import MemoryReadHook


class SessionProcessor:
    """Session 主循环处理器

    while True:
        1. build context from session + memory
        2. stream LLM response (emit events)
        3. handle tool calls
        4. policy.decide() → continue / compact / stop

    摘要与记忆由 MemoryWatcher 后台进程统一负责，每 10 分钟定期扫描。
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
        active_skills: "list | None" = None,
        system_prompt: str = "",
    ) -> None:
        self.session = session
        self.llm = llm
        self.tools = {t.name: t for t in tools}
        self.session_store = session_store
        self.events = event_bus or get_event_bus()
        self.policy = policy or DecisionPolicy()
        self._ctx_builder = ContextBuilder(llm, [t.schema() for t in tools])
        self._logger = logger.bind(name="SessionProcessor")
        self._last_stored_msg_index = -1
        self._command_registry = command_registry
        self.last_command_result = None
        # System Prompt：会话启动时构建一次，包含完整上下文（skills/tools/subagents/MCP）
        self._system_prompt = system_prompt
        # Skill 性能追踪：active_skills 由调用方注入，存 Skill 对象列表
        self._active_skills: list = active_skills or []
        self._skill_trackers: dict = {}   # skill_name → SkillPerfTracker
        self._skill_fragment_ids: dict = {}  # skill_name → (fragment_id, msg_id_start) 元组
        self._turn_index: int = 0         # 全局轮次计数器
        self._turn_start_time: float = 0.0
        # 记忆读取 Hook（检索命中分析）
        self._memory_read_hook: "MemoryReadHook | None" = None
        # 工具输出最大字符数：基于模型上下文窗口，防止单条输出撑爆上下文
        # 计算逻辑：context_window * 4 chars/token * 0.4（留 60% 给其他消息）
        context_window = getattr(llm, "context_window", 8192)
        self._max_tool_output_chars: int = max(4_000, min(40_000, context_window * 4 * 2 // 5))

    def set_memory_read_hook(self, hook: "MemoryReadHook") -> None:
        """注入 MemoryReadHook，启用检索命中分析。

        由外层（SessionFactory / Gateway）在创建 SessionProcessor 后调用：
            from auton.memory.memory_read_hook import MemoryReadHook
            from auton.memory.retrieval_analytics import RetrievalAnalytics
            analytics = RetrievalAnalytics(storage_path)
            processor.set_memory_read_hook(MemoryReadHook(analytics))
        """
        self._memory_read_hook = hook

    # ─── 主循环 ────────────────────────────────────────────────────────────

    async def run(self) -> ProcessResult:
        """运行主循环直到结束，返回最终结果"""
        handled, cmd_result = await self._try_handle_command()
        if handled:
            return ProcessResult(
                status="stop",
                reason=cmd_result.content if cmd_result else "command handled",
            )

        self.session.update_status("running")
        self.events.emit_sync(
            SessionStatusChangeEvent(
                session_id=self.session.meta.session_id,
                status="running",
            )
        )

        # 首次：存储所有已有的 user 消息（system 消息在 ctx.system_prompt 阶段统一合并写入）
        for i in range(self._last_stored_msg_index + 1, len(self.session.messages)):
            msg = self.session.messages[i]
            if msg.role == "user":
                content = msg.get_text()
                self.session_store.append_user_message(
                    self.session.meta.session_id,
                    content,
                    message_id=msg.message_id,
                )
        self._last_stored_msg_index = len(self.session.messages) - 1

        while True:
            # 1. 构建上下文：system_prompt 在 __init__ 时一次性拼装完整
            #    （含 skills/tools/subagents/MCP），后续不再变化；
            #    compact 只压缩 session.messages，system_prompt 不参与
            _query = self._last_user_query()
            ctx = self._ctx_builder.build(
                self.session,
                system_prompt=self._system_prompt,
            )
            self._update_token_count(ctx)
            # 同步当前 query 到记忆读取 Hook（用于检索命中分析）
            if self._memory_read_hook and _query:
                self._memory_read_hook.set_current_query(_query)

            # 系统提示词只存一次（合并 session.messages 中的 system 消息到末尾）
            if not self._ctx_builder.system_stored:
                extra_systems: list[str] = []
                for msg in self.session.messages:
                    if msg.role == "system":
                        text = msg.get_text()
                        if text.strip():
                            extra_systems.append(text)
                combined_prompt = ctx.system_prompt
                if extra_systems:
                    combined_prompt = (ctx.system_prompt or "") + "\n\n" + "\n\n".join(extra_systems)
                if combined_prompt:
                    self.session_store.append_system_message(
                        self.session.meta.session_id,
                        combined_prompt,
                    )
                self._ctx_builder.mark_system_stored()

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
                    content = msg.get_text()
                    self.session_store.append_user_message(
                        self.session.meta.session_id,
                        content,
                        message_id=msg.message_id,
                    )
            self._last_stored_msg_index = len(self.session.messages) - 1

            # 6. 决策
            decision = self._decide()

            if decision.status == "compact":
                self._last_stored_msg_index = len(self.session.messages) - 1
                await self._do_compact()
                continue
            elif decision.status == "stop":
                # 触发2：session 结束
                await self._do_stop(decision.reason)
                return decision
            # continue: 工具链未完成，继续下一轮 LLM

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

        if command.name == "compact" and hasattr(command, "execute_compact"):
            try:
                # /compact 是控制命令，不应进入后续上下文；先移除用户刚输入的命令消息，
                # 再对当前真实对话历史执行压缩。
                for i in range(len(self.session.messages) - 1, -1, -1):
                    msg = self.session.messages[i]
                    if msg.role == "user" and msg.get_text() == last_user_text:
                        self.session.messages.pop(i)
                        break

                self._persist_pending_messages()
                self.session.update_status("compact")
                before_token_count = self.session._token_count
                result_obj = await command.execute_compact(
                    cmd_ctx,
                    protect_turns=self.policy.recent_protect_turns,
                    recent_token_budget=self.policy.recent_token_budget,
                )
                compacted = await self._finalize_compact(
                    result_obj,
                    before_token_count=before_token_count,
                )
                if compacted > 0:
                    result = CommandResult(
                        content=(
                            f"[compact] 已压缩 {compacted} 条历史消息。\n"
                            "当前 session 已保留摘要与最近上下文，可继续对话。"
                        ),
                        handled=True,
                        metadata={"compacted_count": compacted},
                    )
                else:
                    result = CommandResult(
                        content="[compact] 当前上下文较短，暂无可压缩历史。",
                        handled=True,
                        metadata={"compacted_count": 0},
                    )
            except Exception as exc:
                result = CommandResult(
                    content=f"[error] Command /{command.name} failed: {exc}",
                    success=False,
                    error=str(exc),
                )
            self.last_command_result = result
            return True, result

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
        self.last_command_result = result

        return True, result

    # ─── 主循环 ────────────────────────────────────────────────────────────

    async def run_stream(self) -> AsyncIterator:
        """流式运行，yield 每条事件（供 CLI 渲染）"""
        # 新请求到来，取消 idle 计时（触发1 重置）
        # 检查是否为命令
        handled, cmd_result = await self._try_handle_command()
        if handled:
            if cmd_result:
                yield cmd_result
            yield ProcessResult(status="stop", reason="command handled")
            return

        while True:
            # 构建上下文：system_prompt 已一次性拼装完整（含 skills/tools/subagents/MCP），
            # 后续不再变化；compact 只压缩 session.messages，system_prompt 不参与
            query = self._last_user_query()
            ctx = self._ctx_builder.build(
                self.session,
                system_prompt=self._system_prompt,
            )
            self._update_token_count(ctx)
            # 同步当前 query 到记忆读取 Hook（用于检索命中分析）
            if self._memory_read_hook and query:
                self._memory_read_hook.set_current_query(query)

            # 系统提示词只存一次（合并 session.messages 中的 system 消息到末尾）
            if not self._ctx_builder.system_stored:
                # 收集 session.messages 中的 system 消息内容，拼接到 ctx.system_prompt 末尾
                extra_systems: list[str] = []
                for msg in self.session.messages:
                    if msg.role == "system":
                        text = msg.get_text()
                        if text.strip():
                            extra_systems.append(text)
                combined_prompt = ctx.system_prompt
                if extra_systems:
                    combined_prompt = (ctx.system_prompt or "") + "\n\n" + "\n\n".join(extra_systems)
                if combined_prompt:
                    self.session_store.append_system_message(
                        self.session.meta.session_id,
                        combined_prompt,
                    )
                self._ctx_builder.mark_system_stored()

            # 存储新出现的 user message（跳过已存储的）
            for i in range(self._last_stored_msg_index + 1, len(self.session.messages)):
                msg = self.session.messages[i]
                if msg.role == "user":
                    content = msg.get_text()
                    self.session_store.append_user_message(
                        self.session.meta.session_id,
                        content,
                        message_id=msg.message_id,
                    )
                elif msg.role == "system":
                    pass  # system 消息已合并到上面的 system prompt
            self._last_stored_msg_index = len(self.session.messages) - 1

            # ── Skill 追踪：本轮开始 ────────────────────────────────────────
            import time as _time
            self._turn_start_time = _time.time()
            self._record_skill_turn_start(query)

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
            tool_calls_this_turn = len(assistant_msg.get_tools())

            # 存储本轮新增的 user message（工具结果等）
            for i in range(self._last_stored_msg_index + 1, len(self.session.messages)):
                msg = self.session.messages[i]
                if msg.role == "user":
                    content = msg.get_text()
                    self.session_store.append_user_message(
                        self.session.meta.session_id,
                        content,
                        message_id=msg.message_id,
                    )
            self._last_stored_msg_index = len(self.session.messages) - 1

            decision = self._decide()
            # ── Skill 追踪：本轮结束 ────────────────────────────────────────
            # 只在本次请求的最后一轮（不再 continue）才记录结束事件
            if not tools_executed or decision.status == "stop":
                self._record_skill_turn_end(
                    success=decision.status != "stop" or not assistant_msg.get_tools(),
                    tool_calls=tool_calls_this_turn,
                )

            if decision.status == "compact":
                await self._do_compact()
                continue
            elif decision.status == "stop":
                await self._do_stop(decision.reason)
            self._turn_index += 1
            yield decision
            if not tools_executed:
                return

    def prepare_streaming_session(self, session: Session) -> None:
        """Web 层专用：初始化流式会话状态，避免直接访问私有属性。

        在调用 run_stream() 之前调用，用于指定消息持久化的起始索引。
        """
        self._last_stored_msg_index = len(session.messages) - 1

    def _persist_pending_messages(self) -> None:
        """将当前 session 中尚未落盘的消息按原角色持久化。"""
        for i in range(self._last_stored_msg_index + 1, len(self.session.messages)):
            msg = self.session.messages[i]
            if msg.role == "user":
                self.session_store.append_user_message(
                    self.session.meta.session_id,
                    msg.get_text(),
                    message_id=msg.message_id,
                )
            elif msg.role == "system":
                self.session_store.append_system_message(
                    self.session.meta.session_id,
                    msg.get_text(),
                )
            elif msg.role == "assistant":
                self.session_store.append_assistant_message(
                    self.session.meta.session_id,
                    msg,
                )
        self._last_stored_msg_index = len(self.session.messages) - 1

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
                error_msg = f"Unknown tool: {part.tool_name}"
                part.status = "error"
                part.tool_output = json.dumps({"error": error_msg})
                self.events.emit_sync(
                    ToolErrorEvent(
                        session_id=self.session.meta.session_id,
                        tool_name=part.tool_name,
                        error=error_msg,
                        tool_call_id=part.tool_call_id,
                    )
                )
                continue

            try:
                result: "ToolResult" = await tool.execute(**part.tool_input)
                # 在结果进入任何内存结构之前，先把 base64 数据 URI 落盘替换为路径引用。
                # 这是唯一的拦截点：之后 part.tool_output、ToolResultEvent、
                # user message 乃至 LLM 上下文都不会再包含原始 base64。
                clean_output = self.session_store.sanitize_tool_output(
                    result.content, part.tool_name
                )
                # 截断过大的工具输出，防止单条输出超过模型上下文窗口
                clean_output = _truncate_tool_output(
                    clean_output, self._max_tool_output_chars, part.tool_name
                )
                part.status = "completed"
                part.tool_output = clean_output
                self.events.emit_sync(
                    ToolResultEvent(
                        session_id=self.session.meta.session_id,
                        tool_name=part.tool_name,
                        output=clean_output,
                        tool_call_id=part.tool_call_id,
                    )
                )
                # 记忆读取 Hook：拦截文件读取，记录检索命中来源
                if self._memory_read_hook is not None:
                    self._memory_read_hook.on_tool_result(
                        tool_name=part.tool_name,
                        tool_input=part.tool_input,
                        result=clean_output,
                        session_id=self.session.meta.session_id,
                    )
                # 添加 tool result 作为 user message 续上下文（由 run/run_stream 的存储循环统一写入）
                result_content = f"[tool: {part.tool_name}]\n{clean_output}"
                result_msg = Message(role="user")
                result_msg.add_text(result_content)
                self.session.messages.append(result_msg)
            except Exception as exc:
                error_msg = f"Tool execution failed: {exc}"
                part.status = "error"
                # 返回结构化 JSON 错误，让 LLM 能正确解析并响应
                part.tool_output = json.dumps({"error": error_msg, "tool": part.tool_name})
                self._logger.exception("tool {name} dispatch error", name=part.tool_name)
                self.events.emit_sync(
                    ToolErrorEvent(
                        session_id=self.session.meta.session_id,
                        tool_name=part.tool_name,
                        error=error_msg,
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

    def _update_token_count(self, ctx: LLMContext) -> None:
        token_count = estimate_context_tokens(ctx.messages, ctx.system_prompt)
        self.session.update_token_count(token_count)

    # ─── Compact / Stop ─────────────────────────────────────────────────

    async def _do_compact(self) -> int:
        self.session.update_status("compact")
        before_token_count = self.session._token_count

        preparation = self.session.prepare_compact(
            protect_turns=self.policy.recent_protect_turns,
            recent_token_budget=self.policy.recent_token_budget,
        )
        if preparation.is_empty:
            self.session.update_status("running")
            return 0

        # 优先使用 LLM 结构化摘要，失败时降级到简单截断
        try:
            from .compact_prompts import generate_compact_summary

            summary_text = await generate_compact_summary(
                self.llm,
                self.session.meta.session_id,
                preparation.build_llm_input(),
                has_prior_summary=preparation.has_prior_summary,
            )
            result = self.session.apply_compact(summary_text, preparation)
            self._logger.info(
                "LLM compact done compressed={n} prior={p}",
                n=preparation.messages_to_compress.__len__(),
                p=preparation.has_prior_summary,
            )
        except Exception as exc:
            self._logger.warning(
                "LLM compact failed ({exc}), falling back to truncation",
                exc=exc,
            )
            # generate_compact_summary 抛异常时 apply_compact 尚未被调用，
            # preparation 仍然有效，直接降级为截断摘要
            fallback_lines = [
                f"[{m.role}] {m.get_text()[:100]}"
                for m in preparation.messages_to_compress[:6]
                if m.get_text()
            ]
            fallback_text = (
                f"合并 {len(preparation.messages_to_compress)} 条消息"
                "（LLM 摘要不可用，保留片段）：\n"
                + "\n".join(fallback_lines)
            )
            result = self.session.apply_compact(fallback_text, preparation)

        return await self._finalize_compact(
            result,
            before_token_count=before_token_count,
        )

    async def _finalize_compact(self, result: CompactResult, *, before_token_count: int) -> int:
        if result.compacted_count <= 0:
            self.session.update_status("running")
            return 0

        self.session_store.append_compact_event(
            self.session.meta.session_id,
            before_count=result.compacted_count,
            summary=result.summary_text,
            meta={
                "compressed_message_ids": result.compressed_message_ids,
                "summary_message_id": result.summary_message_id,
            },
        )
        self.session_store.append_system_message(
            self.session.meta.session_id,
            result.summary_text,
        )
        self._last_stored_msg_index = len(self.session.messages) - 1
        after_token_count = self.session._estimate_tokens(self.session.messages)
        self.session.update_token_count(after_token_count)
        self.events.emit_sync(
            SessionCompactEvent(
                session_id=self.session.meta.session_id,
                before_token_count=before_token_count,
                after_token_count=after_token_count,
            )
        )
        self.session.update_status("running")
        self._logger.info("compact completed, messages={n}", n=len(self.session.messages))
        return result.compacted_count

    async def _do_stop(self, reason: str) -> None:
        """Session 显式结束：归档记录。摘要与记忆由 MemoryWatcher 后台处理。"""
        self.session.update_status("idle", reason=reason)
        session_id = self.session.meta.session_id
        self.session_store.archive_session(
            session_id=session_id,
            started_at=self.session.meta.created_at.isoformat(),
            ended_at=self.session.meta.updated_at.isoformat(),
            compaction_count=self.session.meta.compaction_count,
        )
        self._logger.info("session stopped reason={r}", r=reason)

    # ─── Skill 追踪辅助方法 ────────────────────────────────────────────────────

    def _get_skill_tracker(self, skill):
        """懒初始化 SkillPerfTracker，缓存到 _skill_trackers。"""
        name = skill.name
        if name not in self._skill_trackers:
            try:
                from ..skills.perf_tracker import SkillPerfTracker
                self._skill_trackers[name] = SkillPerfTracker(skill)
            except Exception as exc:
                self._logger.warning("failed to init tracker for skill {n}: {e}", n=name, e=exc)
                self._skill_trackers[name] = None
        return self._skill_trackers[name]

    def _last_user_query(self) -> str:
        """获取最后一条用户消息文本。"""
        for msg in reversed(self.session.messages):
            if msg.role == "user":
                return msg.get_text()[:500]
        return ""

    def _last_message_id(self) -> str:
        """获取会话中最后一条消息的 message_id（UUID），用于精确定位片段。"""
        if self.session.messages:
            return self.session.messages[-1].message_id
        return ""

    def _record_skill_turn_start(self, query: str) -> None:
        """本轮 LLM 调用开始：为所有 active_skills 记录 invoke_start 事件。"""
        if not self._active_skills:
            return
        session_id = self.session.meta.session_id
        msg_id_start = self._last_message_id()
        for skill in self._active_skills:
            tracker = self._get_skill_tracker(skill)
            if tracker is None:
                continue
            fragment_id = tracker.record_invocation_start(
                trigger="auto",
                query=query,
                turn_index=self._turn_index,
            )
            self._skill_fragment_ids[skill.name] = (fragment_id, msg_id_start)
            self.session_store.append_skill_invoke_start(
                session_id=session_id,
                skill_name=skill.name,
                fragment_id=fragment_id,
                trigger="auto",
                query=query,
                turn_index=self._turn_index,
                skill_path=str(skill.path),
                msg_id_start=msg_id_start,
            )

    def _record_skill_turn_end(self, success: bool, tool_calls: int) -> None:
        """本次请求最后一轮结束：为所有 active_skills 调用 record_invocation_end。"""
        if not self._active_skills:
            return
        import time as _time
        session_id = self.session.meta.session_id
        duration_ms = (_time.time() - self._turn_start_time) * 1000
        session_path = self.session_store.session_path(session_id)
        msg_id_end = self._last_message_id()

        for skill in self._active_skills:
            stored = self._skill_fragment_ids.pop(skill.name, ("", ""))
            fragment_id, msg_id_start = stored if isinstance(stored, tuple) else (stored, "")
            if not fragment_id:
                continue
            tracker = self._get_skill_tracker(skill)
            if tracker is None:
                continue
            tracker.record_invocation_end(
                fragment_id=fragment_id,
                session_id=session_id,
                turn_index=self._turn_index,
                tool_calls_count=tool_calls,
                llm_turns=1,
                duration_ms=duration_ms,
                success=success,
                trigger="auto",
                query=self._last_user_query(),
                session_path=session_path,
                msg_id_start=msg_id_start,
                msg_id_end=msg_id_end,
            )
            self.session_store.append_skill_invoke_end(
                session_id=session_id,
                skill_name=skill.name,
                fragment_id=fragment_id,
                success=success,
                tool_calls_count=tool_calls,
                llm_turns=1,
                duration_ms=duration_ms,
                msg_id_end=msg_id_end,
            )


# ─── 工具输出截断 ────────────────────────────────────────────────────────────

def _truncate_tool_output(output: str, max_chars: int, tool_name: str = "") -> str:
    """将工具输出截断到 max_chars，防止单条输出超过模型上下文窗口。

    截断时在末尾附加说明，告诉 LLM 输出已被截断。

    Args:
        output:    工具返回的原始文本
        max_chars: 允许的最大字符数（基于 LLM context_window 计算）
        tool_name: 工具名（用于截断提示）

    Returns:
        截断后的文本（如果未超限则原样返回）
    """
    if len(output) <= max_chars:
        return output

    kept = output[:max_chars]
    omitted = len(output) - max_chars
    hint = (
        f"\n\n[⚠ 工具输出已截断：原始输出 {len(output):,} 字符，"
        f"显示前 {max_chars:,} 字符，省略 {omitted:,} 字符。"
        f"如需查看完整输出，请缩小查询范围或分批读取。]"
    )
    return kept + hint
