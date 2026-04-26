"""Agent — SessionProcessor 核心循环

SessionProcessor 是会话的主循环处理器，负责：
  1. 从 session.messages 构建 LLM 上下文
  2. 调用 LLM 流式生成响应（emit 事件）
  3. 执行工具调用并将结果注入上下文
  4. 根据 DecisionPolicy 决策：继续 / 压缩 / 停止

设计原则：
  - 纯业务逻辑：不包含任何 Web/CLI 特定的 I/O
  - 事件驱动：通过 EventBus emit 各类事件，外部可订阅做可视化
  - 持久化透明：所有状态变更同时写入 SessionStore（JSONL 文件）
  - 命令优先：任何用户消息先检查是否为 / 命令，是则直接执行不调 LLM
"""

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

    主循环逻辑（run / run_stream 共享）：
        while True:
            1. build context from session + system_prompt
            2. stream LLM response (emit events)
            3. execute pending tool calls
            4. policy.decide() → continue / compact / stop

    摘要与记忆由 MemoryWatcher 后台进程统一负责，每 10 分钟定期扫描。
    SessionProcessor 不直接管理记忆，只在工具执行时触发 MemoryReadHook 记录检索。
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
        # 核心依赖（只读）
        self.session = session                      # 会话对象（消息历史）
        self.llm = llm                              # LLM Provider
        self.session_store = session_store          # 持久化层
        self.events = event_bus or get_event_bus()  # 事件总线
        self.policy = policy or DecisionPolicy()    # 决策策略
        # System Prompt：会话启动时由 SessionFactory 一次性构建完整，
        # 包含 skills/tools/MCP 等静态背景知识，后续不再变化（不参与 compact）。
        self._system_prompt = system_prompt

        # 工具注册表：list 转为 dict，按名称索引，加速工具查找
        self.tools = {t.name: t for t in tools}

        # ContextBuilder：根据 session.messages 构建 LLM 请求上下文
        # tools 参数传入 schema（JSON schema 格式），LLM 据此生成结构化工具调用
        self._ctx_builder = ContextBuilder(llm, [t.schema() for t in tools])

        # 持久化索引：指向 session.messages 中最后一个已持久化消息的索引
        # 新消息的索引 > _last_stored_msg_index 才会被持久化。
        # 这避免了重复写入同一消息（多轮循环中同一消息可能被遍历多次）。
        self._last_stored_msg_index = -1

        self._command_registry = command_registry   # / 命令注册表（懒加载）
        self.last_command_result = None              # 最后一次命令执行结果

        # Skill 性能追踪：active_skills 由调用方注入，存 Skill 对象列表
        self._active_skills: list = active_skills or []
        self._skill_trackers: dict = {}             # skill_name → SkillPerfTracker
        self._skill_fragment_ids: dict = {}         # skill_name → (fragment_id, msg_id_start)
        self._turn_index: int = 0                   # 全局轮次计数器
        self._turn_start_time: float = 0.0

        # 记忆读取 Hook（检索命中分析）
        self._memory_read_hook: "MemoryReadHook | None" = None

        # 工具输出最大字符数：基于模型上下文窗口，防止单条输出撑爆上下文
        # 计算逻辑：context_window * 4 chars/token * 0.4（留 60% 给其他消息）
        context_window = getattr(llm, "context_window", 8192)
        self._max_tool_output_chars: int = max(4_000, min(40_000, context_window * 4 * 2 // 5))

        self._logger = logger.bind(name="SessionProcessor")

    def set_memory_read_hook(self, hook: "MemoryReadHook") -> None:
        """注入 MemoryReadHook，启用检索命中分析。

        由外层（SessionFactory / Gateway）在创建 SessionProcessor 后调用：
            from auton.memory.memory_read_hook import MemoryReadHook
            from auton.memory.retrieval_analytics import RetrievalAnalytics
            analytics = RetrievalAnalytics(storage_path)
            processor.set_memory_read_hook(MemoryReadHook(analytics))

        为什么需要这个 hook？
          MemoryReadHook 在工具执行时拦截文件读取事件，
          记录"哪个 query 命中了哪段记忆"，用于记忆系统的自我优化。
          外部注入设计使得 SessionProcessor 不直接依赖记忆模块。
        """
        self._memory_read_hook = hook

    # ─── 主循环 ────────────────────────────────────────────────────────────

    async def run(self) -> ProcessResult:
        """运行主循环直到结束，返回最终结果。

        这是 CLI 模式（非流式）的入口，与 run_stream() 共享相同的主循环逻辑。
        区别在于：run() 等待完整执行后返回结果，run_stream() 逐事件 yield。

        run() vs run_stream() 的选择：
          - CLI：用户期望看到最终输出，用 run()
          - Web/API：需要实时推送打字效果，用 run_stream()
        """
        # 命令优先：检查用户消息是否为 / 命令（如 /compact）
        handled, cmd_result = await self._try_handle_command()
        if handled:
            return ProcessResult(
                status="stop",
                reason=cmd_result.content if cmd_result else "command handled",
            )

        # 更新 session 状态为 running，并 emit 事件
        self.session.update_status("running")
        self.events.emit_sync(
            SessionStatusChangeEvent(
                session_id=self.session.meta.session_id,
                status="running",
            )
        )

        # 首次持久化：存储所有已有的 user 消息（从 -1 到当前末尾）
        # 注意：system 消息在下面 "系统提示词只存一次" 阶段统一处理
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
            # ═══════════════════════════════════════════════════════════════
            # 步骤 1：构建 LLM 上下文
            # ═══════════════════════════════════════════════════════════════
            # system_prompt 在 __init__ 时一次性拼装完整（含 skills/tools/subagents/MCP），
            # 后续不再变化；compact 只压缩 session.messages，system_prompt 不参与。
            _query = self._last_user_query()
            ctx = self._ctx_builder.build(
                self.session,
                system_prompt=self._system_prompt,
            )
            self._update_token_count(ctx)

            # 同步当前 query 到记忆读取 Hook（用于检索命中分析）
            # MemoryReadHook 记录"哪个 query 读取了哪个文件"，用于记忆系统的自我优化。
            if self._memory_read_hook and _query:
                self._memory_read_hook.set_current_query(_query)

            # 系统提示词只存一次（合并 session.messages 中的 system 消息到末尾）
            # 为什么需要合并？
            #   Web 层注入的项目上下文是 role=system 的 Message，存在于 session.messages 中。
            #   这些消息需要持久化到 JSONL 文件中。
            #   但 System Prompt 本身（_system_prompt）已经在 SessionFactory.build() 时写入了，
            #   这里只需要写入 session.messages 中的动态 system 消息。
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

            # ═══════════════════════════════════════════════════════════════
            # 步骤 2：LLM 流式生成
            # ═══════════════════════════════════════════════════════════════
            # add_assistant_message 创建一个空的 assistant message，
            # 等待 LLM 事件填充（text_delta / tool_use 等）。
            assistant_msg = self.session.add_assistant_message()
            async for event in self.llm.stream(ctx):
                await self._handle_llm_event(event, assistant_msg)

            # ═══════════════════════════════════════════════════════════════
            # 步骤 3：执行工具调用
            # ═══════════════════════════════════════════════════════════════
            # 执行所有 pending 状态的 tool calls，将结果注入为 user message。
            # 如果有工具执行，下一轮 LLM 会继续（tool result 作为新的 user message）。
            await self._execute_tools(assistant_msg)

            # ═══════════════════════════════════════════════════════════════
            # 步骤 4：持久化助手消息
            # ═══════════════════════════════════════════════════════════════
            # 完整的 assistant message（包含所有 text + tool_use parts）写入 JSONL。
            self.session_store.append_assistant_message(self.session.meta.session_id, assistant_msg)

            # ═══════════════════════════════════════════════════════════════
            # 步骤 5：持久化本轮新增的 user message（工具结果等）
            # ═══════════════════════════════════════════════════════════════
            # 工具执行后，结果被追加为新的 user message（role=user）。
            # 这些新消息需要持久化。
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

            # ═══════════════════════════════════════════════════════════════
            # 步骤 6：决策（continue / compact / stop）
            # ═══════════════════════════════════════════════════════════════
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

        命令优先于 LLM：任何以 / 开头的用户消息都先尝试匹配命令，
        匹配成功后直接执行，不调用 LLM。这样节省 token 并加快响应。

        为什么在主循环最前面执行？
          用户可能输入 "/compact" 来手动触发上下文压缩，
          这时候不需要也不应该走 LLM 流程。

        Returns:
            (handled, result): handled=True 表示已处理（不需要 LLM）
        """
        from ..commands import CommandContext, CommandResult, get_command_registry

        # 懒加载命令注册表（避免循环导入）
        if self._command_registry is None:
            self._command_registry = get_command_registry()

        # 获取最后一条 user message（倒序遍历，找最近的那条）
        last_user_text = ""
        for msg in reversed(self.session.messages):
            if msg.role == "user":
                last_user_text = msg.get_text()
                break
        if not last_user_text:
            return False, None

        # 尝试匹配命令（CommandRegistry 会检查前缀是否为 /）
        command, args = self._command_registry.match(last_user_text)
        if command is None:
            return False, None

        # 构建命令上下文，传入 session / session_store / llm
        cmd_ctx = CommandContext(
            session=self.session,
            session_store=self.session_store,
            llm=self.llm,
            config=None,  # type: ignore[arg-type] — config 在 registry 层注入
        )

        self._logger.info("handling command /{name}", name=command.name)

        # ═══════════════════════════════════════════════════════════════════
        # /compact 命令的特殊处理
        # ═══════════════════════════════════════════════════════════════════
        # 为什么 /compact 需要特殊处理？
        #   /compact 是控制命令，不应进入后续 LLM 上下文。
        #   需要先从 session.messages 中移除这条命令消息，再执行压缩。
        #   否则命令本身会被压缩，导致上下文不干净。
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
        """流式运行主循环，yield 每条事件（供 Web 层推送）。

        与 run() 的区别：
          - run() 等待完整执行后返回 ProcessResult
          - run_stream() 逐事件 yield，调用方（FastAPI）实时推送给客户端

        事件类型（yield 给外部）：
          - CommandResult：/ 命令的执行结果
          - TextDeltaEvent / TextFinishEvent：LLM 文本输出
          - ToolCallEvent：工具调用开始
          - ToolResultEvent：工具执行结果
          - ProcessResult：决策结果（stop/continue/compact）
          - SessionCompactEvent：压缩完成事件

        结束条件（return）：
          - 执行了 / 命令
          - tools_executed=False 且 decision.status == continue（无工具链，正常结束）
          - decision.status == "stop"（对话结束）
        """
        # 命令优先检查（与 run() 相同）
        handled, cmd_result = await self._try_handle_command()
        if handled:
            if cmd_result:
                yield cmd_result
            yield ProcessResult(status="stop", reason="command handled")
            return

        while True:
            # ═══════════════════════════════════════════════════════════════
            # 步骤 1：构建 LLM 上下文（与 run() 逻辑相同）
            # ═══════════════════════════════════════════════════════════════
            query = self._last_user_query()
            ctx = self._ctx_builder.build(
                self.session,
                system_prompt=self._system_prompt,
            )
            self._update_token_count(ctx)
            if self._memory_read_hook and query:
                self._memory_read_hook.set_current_query(query)

            # 系统提示词只存一次（与 run() 相同）
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

            # ═══════════════════════════════════════════════════════════════
            # 步骤 2：持久化新出现的 user message
            # ═══════════════════════════════════════════════════════════════
            # 为什么在 LLM 调用前持久化 user message？
            #   确保即使 LLM 调用失败，用户消息也已写入磁盘，不会丢失。
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
            # 记录本轮开始时间，用于计算 LLM 调用的总耗时（影响 skill 性能追踪）
            import time as _time
            self._turn_start_time = _time.time()
            self._record_skill_turn_start(query)

            # ═══════════════════════════════════════════════════════════════
            # 步骤 3：LLM 流式生成（逐事件 yield 给 Web 层）
            # ═══════════════════════════════════════════════════════════════
            assistant_msg = self.session.add_assistant_message()
            async for event in self.llm.stream(ctx):
                await self._handle_llm_event(event, assistant_msg)
                # 关键：每条 LLM 事件都直接 yield 给调用方（FastAPI StreamingResponse）
                yield event

            # ═══════════════════════════════════════════════════════════════
            # 步骤 4：执行工具调用
            # ═══════════════════════════════════════════════════════════════
            await self._execute_tools(assistant_msg)
            self.session_store.append_assistant_message(self.session.meta.session_id, assistant_msg)

            # 检查本轮是否有工具执行（有工具结果说明需要下一轮 LLM 继续）
            tools_executed = any(
                p.status in ("completed", "error")
                for p in assistant_msg.get_tools()
            )
            tool_calls_this_turn = len(assistant_msg.get_tools())

            # ═══════════════════════════════════════════════════════════════
            # 步骤 5：持久化本轮新增的 user message（工具结果等）
            # ═══════════════════════════════════════════════════════════════
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

            # ═══════════════════════════════════════════════════════════════
            # 步骤 6：决策
            # ═══════════════════════════════════════════════════════════════
            decision = self._decide()

            # ── Skill 追踪：本轮结束 ────────────────────────────────────────
            # 只在本次请求的最后一轮（不再 continue）才记录结束事件
            # 如果 tools_executed=True 且 decision != stop，说明还有下一轮，不记录
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
            # 无工具调用且 decision != stop：正常结束，return
            if not tools_executed:
                return

    def prepare_streaming_session(self, session: Session) -> None:
        """Web 层专用：初始化流式会话状态，避免直接访问私有属性。

        在调用 run_stream() 之前调用，用于指定消息持久化的起始索引。

        为什么需要这个方法？
          新请求到来时（Web 层每次请求都是新的 HTTP 连接），
          _last_stored_msg_index 需要重置为当前 session.messages 的末尾。
          否则新请求中的消息会被错误地跳过（因为 index < _last_stored_msg_index）。
          通过公开方法而非直接修改私有属性，保持封装性。
        """
        self._last_stored_msg_index = len(session.messages) - 1

    def _persist_pending_messages(self) -> None:
        """将当前 session 中尚未落盘的消息按原角色持久化。

        用途：在执行 /compact 等命令前，先把内存中的消息全部写入磁盘，
        避免压缩后消息丢失。

        为什么按 role 分开处理？
          user / system / assistant 消息的持久化方法不同：
          - user：append_user_message(session_id, content, message_id)
          - system：append_system_message(session_id, content)
          - assistant：append_assistant_message(session_id, msg_object)
        """
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
        """将 LLM 流式事件转换为内部事件并 emit 到 EventBus。

        LLM Provider（Anthropic / OpenAI 等）产生的事件格式统一化：
          - text_start / text_delta / text_finish：文本输出
          - reasoning_start / reasoning_delta：推理过程（MiniMax thinking）
          - tool_use：工具调用请求
          - content_block_stop：内容块结束（标记工具调用解析完毕）

        为什么每个事件都要 emit？
          Web 层订阅 EventBus 可以获取实时状态：
          - text_delta → 前端打字效果
          - tool_use → 显示"正在调用 xxx 工具"
          - tool_result → 显示工具执行结果
          这样前端可以实现完整的实时反馈 UI。

        为什么 reasoning 事件不 emit？
          reasoning（内部思考过程）通常不需要展示给用户，
          只在 msg.parts 中记录，供后续分析使用。
        """
        # TextPart：LLM 开始输出文本
        if event.type == "text_start":
            msg.add_text()
            self.events.emit_sync(
                SessionStatusChangeEvent(
                    session_id=self.session.meta.session_id,
                    status="running",
                    step_id=str(self.session.meta.step_count),
                )
            )
        # TextDelta：文本增量（逐 token），emit 给 Web 层做打字效果
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
        # TextFinish：文本生成完毕，emit 完整内容
        elif event.type == "text_finish":
            self.events.emit_sync(
                TextFinishEvent(
                    session_id=self.session.meta.session_id,
                    content=msg.get_text(),
                )
            )
        # ReasoningPart（MiniMax thinking）：内部推理过程，记录但不做 UI 展示
        elif event.type == "reasoning_start":
            msg.add_reasoning()
        elif event.type == "reasoning_delta":
            reasoning_parts = [p for p in msg.parts if p.type == "reasoning"]
            if reasoning_parts:
                reasoning_parts[0].append(event.delta)
        elif event.type == "reasoning_finish":
            pass  # already captured via delta
        # ToolUse：LLM 请求调用工具
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
        # ContentBlockStop：内容块结束（标记工具调用解析完毕）
        elif event.type == "content_block_stop":
            pass  # handled in tool execution

    async def _execute_tools(self, msg: Message) -> None:
        """执行所有 pending 状态的 tool calls。

        执行流程：
          1. 遍历 assistant_msg 中所有 pending 状态的 tool parts
          2. 根据 tool_name 查找工具实例
          3. 调用 tool.execute(**input)，获取 ToolResult
          4. 清理输出（base64 替换 + 截断）
          5. 将结果注入为 user message（续上下文）
          6. emit ToolResultEvent

        为什么工具结果要注入为 user message？
          LLM 的多轮对话机制是基于"用户消息 → LLM 响应"的交替结构。
          工具执行结果需要作为新的"用户消息"传入下一轮 LLM，
          这样 LLM 才能基于工具输出继续推理和响应。

        为什么错误也要注入？
          工具执行失败时，返回结构化 JSON 错误，LLM 可以感知并尝试恢复。
        """
        for part in msg.get_tools():
            if part.status != "pending":
                continue

            # 标记为 running，防止重复执行
            part.status = "running"
            tool = self.tools.get(part.tool_name)

            # 工具不存在（未知工具名）：返回错误，不抛异常
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

                # ═══ 关键：清理工具输出 ═══════════════════════════════════
                # 在结果进入任何内存结构之前，先把 base64 数据 URI 落盘替换为路径引用。
                # 这是唯一的拦截点：之后 part.tool_output、ToolResultEvent、
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
                # MemoryReadHook 分析"哪个 query 读取了哪个文件"，
                if self._memory_read_hook is not None:
                    self._memory_read_hook.on_tool_result(
                        tool_name=part.tool_name,
                        tool_input=part.tool_input,
                        result=clean_output,
                        session_id=self.session.meta.session_id,
                    )
                # 添加 tool result 作为 user message 续上下文
                # 格式：[tool: tool_name]\noutput
                # 由 run/run_stream 的存储循环统一写入 SessionStore
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
        """根据当前状态决策：continue / compact / stop。

        DecisionPolicy 根据以下输入做决策：
          - message_count：消息总数（影响 token 消耗）
          - token_count：当前上下文 token 数（触发 compact 的主要指标）
          - last_user_message：最后一条用户消息（可能包含特殊指令）
          - step_count：总步数（防止无限循环）

        为什么需要 policy 分离？
          决策逻辑可能随业务需求变化（调整 compact 阈值、添加 stop 条件等）。
          独立 policy 对象使得决策逻辑可测试、可替换。
        """
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
        """估算当前上下文 token 数并更新到 session。

        为什么需要手动更新？
          DecisionPolicy 需要根据 token_count 决定是否触发 compact。
          每次 LLM 调用前需要重新估算，因为 session.messages 可能增加了新消息。

        为什么用 estimate_context_tokens 而不是直接让 LLM 返回？
          不同 LLM Provider 返回的 usage 字段不同（有的有，有的没有）。
          统一用本地估算确保跨 provider 一致性。
        """
        token_count = estimate_context_tokens(ctx.messages, ctx.system_prompt)
        self.session.update_token_count(token_count)

    # ─── Compact / Stop ─────────────────────────────────────────────────

    async def _do_compact(self) -> int:
        """执行上下文压缩：用 LLM 生成摘要，替换历史消息。

        为什么需要压缩？
          LLM 上下文窗口有限，随着对话进行，session.messages 越来越大，
          超过阈值后 token 消耗急剧增加且容易超限。
          compact 通过压缩历史消息为摘要来控制 token 数量。

        为什么优先用 LLM 摘要而不是直接截断？
          直接截断会丢失大量信息，LLM 无法理解压缩前的上下文。
          LLM 生成的摘要保留了关键信息，压缩效果好。

        降级策略：
          LLM 摘要失败（如网络错误）时降级到简单截断，
          保留每条消息前 100 字符，保证不会卡死。
        """
        self.session.update_status("compact")
        before_token_count = self.session._token_count

        preparation = self.session.prepare_compact(
            protect_turns=self.policy.recent_protect_turns,
            recent_token_budget=self.policy.recent_token_budget,
        )
        # is_empty 表示历史太短，不需要压缩（如最近 2 轮以内）
        if preparation.is_empty:
            self.session.update_status("running")
            return 0

        # 优先使用 LLM 结构化摘要，失败时降级到简单截断
        # 为什么用 try/except 而不是 if 判断？
        #   generate_compact_summary 可能因 LLM 超时、超限等原因抛异常，
        #   这些异常无法通过预检查避免，所以用 try/except 兜底。
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
        """完成压缩后的收尾工作：持久化 + 更新状态 + emit 事件。

        为什么压缩后要写入 system message？
          摘要内容作为 system 消息追加到 session.messages 中，
          这样下次 LLM 调用时上下文包含摘要，保留历史记忆。

        为什么更新 _last_stored_msg_index？
          压缩后 session.messages 内容变化（历史被替换为摘要），
          持久化索引需要重新对齐。
        """
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
        """Session 显式结束：归档记录 + 触发 skill 优化。

        为什么归档后还要触发 skill 优化？
          SessionProcessor 追踪了每个 skill 的使用情况（调用次数、耗时、token 消耗）。
          会话结束时，如果有 skill 触发了性能告警（alert_triggered=True），
          后台会启动优化流程（更新 SKILL.md 描述、调整触发条件等）。

        为什么用 fire-and-forget（asyncio.create_task）？
          Skill 优化是异步的，不应该阻塞主进程。
          用户已经收到了 LLM 响应，不应该等待优化完成。
        """
        self.session.update_status("idle", reason=reason)
        session_id = self.session.meta.session_id
        self.session_store.archive_session(
            session_id=session_id,
            started_at=self.session.meta.created_at.isoformat(),
            ended_at=self.session.meta.updated_at.isoformat(),
            compaction_count=self.session.meta.compaction_count,
        )
        # 后台：触发已标记的 skill 优化（fire-and-forget，不阻塞）
        self._trigger_pending_skill_optimizations()
        self._logger.info("session stopped reason={r}", r=reason)

    def _trigger_pending_skill_optimizations(self) -> None:
        """扫描所有 skill，对 alert_triggered=True 的在后台触发优化。

        为什么需要扫描？
          SessionProcessor 在每次 LLM 调用时记录 skill 的性能数据（耗时、token 消耗）。
          如果某个 skill 持续表现不佳（如超时率高、LLM 反复调用但很少实际使用），
          SkillPerfTracker 会标记 alert_triggered=True。
          会话结束时统一扫描，避免每个 skill 独立触发优化。
        """
        import asyncio
        from ..skills import get_skills_with_pending_alerts

        skills_dir = self.session_store.base / "skill"
        if not skills_dir.exists():
            return

        try:
            pending_trackers = get_skills_with_pending_alerts(skills_dir)
        except Exception:
            return

        for tracker in pending_trackers:
            asyncio.create_task(
                self._optimize_skill_async(tracker),
                name=f"skill-optimize-{tracker.skill.name}",
            )
            self._logger.info(
                "queued skill optimization: {n} (alert_triggered=true)",
                n=tracker.skill.name,
            )

    async def _optimize_skill_async(self, tracker) -> None:
        """后台执行单个 skill 的优化。异常内部消化，不影响主进程。

        为什么用 try/except 包裹整个方法？
          Skill 优化失败不应该影响主进程（用户已经收到 LLM 响应）。
          异常被捕获后记录日志，然后静默丢弃。
        """
        from ..skills.optimizer import SkillOptimizer

        try:
            optimizer = SkillOptimizer(tracker, self.llm)
            result = await optimizer.optimize()
            self._logger.info(
                "skill {n} optimized: updated={u} error={e}",
                n=tracker.skill.name,
                u=result.skill_md_updated,
                e=result.error,
            )
        except Exception:
            self._logger.exception("skill optimization failed: {n}", n=tracker.skill.name)

    # ─── Skill 追踪辅助方法 ────────────────────────────────────────────────────

    def _get_skill_tracker(self, skill):
        """懒初始化 SkillPerfTracker，缓存到 _skill_trackers。

        为什么用懒加载而不是直接初始化？
          SkillPerfTracker 可能需要读取 skill 文件或初始化状态，
          如果会话没有使用任何 skill，直接初始化是浪费。
          懒加载确保只在真正需要时才初始化。
        """
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
        """获取最后一条用户消息文本（截断到 500 字符）。

        为什么截断到 500 字符？
          SkillPerfTracker 只需要知道 query 的概要，而不是完整内容。
          截断节省存储空间，同时保留足够的语义信息。
        """
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
        """本轮 LLM 调用开始：为所有 active_skills 记录 invoke_start 事件。

        为什么要记录 turn 开始？
          SkillPerfTracker 需要计算 skill 的使用率、耗时、token 消耗。
          通过记录 start 和 end，可以精确测量每次 skill 调用的性能。

        为什么需要 msg_id_start？
          用于关联 skill 事件和 session 中的具体消息范围。
          知道 skill 调用发生在哪段消息之间，对性能分析很重要。

        为什么需要 fragment_id？
          一个 skill 在一次会话中可能被多次调用（多个 fragment）。
          fragment_id 用于唯一标识每次调用，方便后续关联 end 事件。
        """
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
        """本次请求最后一轮结束：为所有 active_skills 调用 record_invocation_end。

        为什么只在本轮最后一轮记录 end？
          如果 tools_executed=True 且 decision != stop，说明还有下一轮 LLM 调用。
          SkillPerfTracker 应该只记录"用户发起的请求"的完整生命周期，
          而不是每个内部 LLM 轮次。

        为什么 success 的判断逻辑是 decision.status != "stop" or not assistant_msg.get_tools()？
          success = True 表示"本次用户请求正常完成"：
            - decision.status != "stop"：对话还没结束
            - or not assistant_msg.get_tools()：就算结束了但没有工具调用（自然结束）
          反之 success = False 表示"对话被提前终止（如 policy 决定 stop）"。
        """
        if not self._active_skills:
            return
        import time as _time
        session_id = self.session.meta.session_id
        duration_ms = (_time.time() - self._turn_start_time) * 1000
        session_path = self.session_store.session_path(session_id)
        msg_id_end = self._last_message_id()

        for skill in self._active_skills:
            # pop：从 _skill_fragment_ids 中取出并删除（避免重复记录）
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
