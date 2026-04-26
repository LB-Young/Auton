"""Gateway — SessionFactory

统一构建会话所需的全部运行时对象，消除 cli / web / bot 等接入端的重复初始化代码。

核心职责：
  1. 统一创建 LLM Provider（支持多平台切换）
  2. 统一加载工具列表（含 MCP Server）
  3. 统一组装 System Prompt（静态背景知识，一次性构建）
  4. 统一构建 SessionProcessor（主循环处理器）

设计原则：
  - 单一职责：SessionFactory 只负责构建，不参与主循环
  - 一次性构建：System Prompt 在 build() 时完整拼装，后续不参与 compact
  - 零重复：所有接入端（CLI / Web / Bot）复用同一套构建逻辑

接入新平台时的最简模板：

    from auton.gateway import SessionFactory

    async def handle_message(text: str):
        ctx = await SessionFactory().build(session_mode="project")
        ctx.session.add_user_message(text)
        async for event in ctx.processor.run_stream():
            ...  # 处理自己平台的 I/O
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

from loguru import logger

from ..agent.agent import SessionProcessor
from ..agent.session import Session
from ..agent.session_store import SessionStore
from ..agent.system_prompt import SystemPromptBuilder
from ..core.config import get_config
from ..core.events import EventBus
from ..userspace.bootstrap import ensure_userspace
from ..userspace.loader import UserspaceLoader
from .types import SessionContext

if TYPE_CHECKING:
    from ..llm.base import LLMProvider
    from ..tools.base import Tool


class SessionFactory:
    """统一会话工厂。

    负责：
        1. SessionStore 模式切换（project / date）
        2. LLM Provider 创建
        3. 工具加载（含可选 MCP）
        4. 记忆 & 项目指令加载
        5. 系统提示词组装
        6. SkillInjector 初始化
        7. SessionProcessor 构建

    调用方只需关心自己的 I/O 层。

    设计要点：
      - build() 是唯一公开方法，返回包含所有运行时对象的 SessionContext
      - System Prompt 一次性构建（包含 skills/tools/MCP 等），后续不参与 compact
      - session_store 模式由 session_mode 和 project_root 共同决定
      - DecisionPolicy 根据 LLM context_window 自动计算 compact 阈值
    """

    _log = logger.bind(name="SessionFactory")

    async def build(
        self,
        *,
        session_mode: Literal["auto", "project", "chat"] = "auto",
        project_root: Path | None = None,
        model: str | None = None,
        provider: str | None = None,
        permission_mode: str | None = None,
        yes_all: bool = False,
        enable_mcp: bool = True,
        extra_tools: "list[Tool] | None" = None,
        event_bus: EventBus | None = None,
        session: Session | None = None,
    ) -> SessionContext:
        """构建并返回一个完整的 SessionContext。

        这是 SessionFactory 的唯一公开方法，封装了会话所需的所有初始化逻辑。
        调用方只需关心自己的 I/O 层（驱动 processor.run_stream() 并处理事件）。

        System Prompt 装配顺序（与 OpenClaw 一致，内容直接拼接）：
          1. 静态核心（Identity + 规则）                        — build_base() 时一次性构建
          2. 环境信息（OS / CWD / Git）                       — build_base() 时一次性构建
          3. 项目指令（CLAUDE.md / AGENTS.md / ~/.auton/auton.md 的真实内容）
                                                               — build_base() 时一次性构建
          4. 记忆（Project Memory / Today's Memory 的真实内容） — build_base() 时一次性构建
          5. 内置 Skill 片段（SKILL.md 真实内容）                 — build_base() 时一次性构建
          6. 内置 Subagent 元数据（真实内容）                    — build_base() 时一次性构建
          7. MCP Server 配置及可用工具（Session 级别，真实内容）  — build_base() 时一次性构建
          8. 用户扩展（~/.auton/subagents、workflows 的真实内容）— build_base() 时一次性构建

        为什么 System Prompt 一次性构建，不参与 compact？
          System Prompt 包含的是静态背景知识（skills 列表、工具说明、项目指令等），
          这些内容与会话历史无关，不需要每次循环重复拼接。
          compact 只压缩 session.messages 的消息历史，节省 token 但不影响 LLM 的能力认知。

        Args:
            session_mode: "project" 绑定项目目录，"chat" 按日期存储，
                          "auto" 根据 project_root 是否存在自动选择。
            project_root: 项目根目录，为 None 时使用当前工作目录（仅 project 模式下有效）。
            model:        覆盖配置文件中的模型名称。
            provider:     覆盖配置文件中的 LLM provider（"anthropic" / "minimax"）。
            permission_mode: BashTool 权限模式，为 None 时读配置文件。
            yes_all:      所有工具调用跳过确认（等同于 --yes 标志）。
            enable_mcp:   是否启动 MCP server。
            extra_tools:  额外附加的工具列表。
            event_bus:    外部传入的事件总线，为 None 时自动创建。
            session:      外部传入的 Session（用于恢复历史会话），为 None 时创建新 Session。
        """
        config = get_config()
        cwd = Path.cwd()

        # ── 0. Userspace 校验（~/.auton 完整性）─────────────────────────────
        # 为什么需要 ensure_userspace？
        #   ~/.auton 目录包含 userspace 配置（subagents、workflows、配置等），
        #   如果目录不存在或不完整，ensure_userspace 会自动创建/修复。
        #   quiet=True 表示静默模式，校验失败时不抛出异常。
        layout = ensure_userspace(quiet=True)

        # ── 1. SessionStore & 模式 ────────────────────────────────────────────
        # SessionStore 管理 session 数据的持久化路径：
        #   - project 模式：~/.auton/sessions/{project_hash}/{session_id}/
        #   - date 模式：~/.auton/sessions/{date}/{session_id}/
        # effective_root 决定 project 模式下的项目隔离边界。
        effective_root = project_root or cwd
        store = SessionStore(storage_dir=config.memory.storage_dir)

        # 为什么需要手动 set 模式？
        #   SessionStore 构造函数只能按 cwd 自动判断，无法直接接受 session_mode 参数。
        #   所以先创建，再根据 session_mode 覆盖模式。
        if session_mode == "chat":
            store.set_date_mode()
        elif session_mode == "project":
            store.set_project_root(effective_root)
        else:  # auto
            if project_root:
                store.set_project_root(project_root)
            # 否则 SessionStore 构造时已按 cwd 自动判断，不额外干预

        self._log.info(
            "session_mode={m} store_mode={sm} project={p}",
            m=session_mode,
            sm=store.mode,
            p=store.project_root,
        )

        # ── 2. Session ────────────────────────────────────────────────────────
        # 为什么传入 session 参数时不重新创建？
        #   Web 层恢复历史 session 时已经构建了 Session 对象，
        #   传入已有 session 可以避免丢失消息历史。
        active_root = store.project_root
        if session is None:
            session = Session.create(
                project_path=str(active_root) if active_root else None
            )

        # ── 3. LLM Provider ───────────────────────────────────────────────────
        # create_llm() 是公开静态方法，支持多 provider 自动切换。
        # 为什么用静态方法而不是实例方法？
        #   Web 层有时只需要创建 LLM，不需要完整的 SessionContext。
        #   静态方法允许直接调用 SessionFactory.create_llm()。
        llm = SessionFactory.create_llm(model=model, provider=provider)

        # ── 4. Tools ──────────────────────────────────────────────────────────
        # get_default_tools() 加载内置工具（Bash / Read / Write / Glob / Grep 等）。
        # permission_mode 决定 BashTool 的权限级别（受限 / 宽松 / 完全信任）。
        # yes_all=True 时所有工具调用跳过确认（Web 端默认行为）。
        from ..tools import get_default_tools
        perm = permission_mode or config.security.permission_mode
        tools: list[Tool] = get_default_tools(permission_mode=perm, yes_all=yes_all)
        if extra_tools:
            tools = tools + extra_tools

        # ── 5. MCP Servers（可选）────────────────────────────────────────────
        # 为什么需要条件判断？
        #   MCP Server 启动可能耗时较长，且并非所有部署都配置了 MCP。
        #   enable_mcp=False 时跳过初始化，加快会话启动速度。
        if enable_mcp and config.mcp.auto_start and config.mcp.servers:
            await self._start_mcp(config)

        # ── 6. EventBus ───────────────────────────────────────────────────────
        # 为什么需要 EventBus？
        #   SessionProcessor 内部会 emit 各种事件（text_delta / tool_call / compact 等），
        #   EventBus 作为中央事件总线，允许外部（如 Web 前端）订阅这些事件做可视化。
        #   外部传入时用外部的，不传时创建新的（CLI 模式）。
        bus = event_bus or EventBus()

        # ── 7. 系统提示词（内置静态 + 环境 + 记忆/项目文档 + Subagent）─────────
        # SystemPromptBuilder 是组装系统提示词的核心类。
        # create_default() 包含静态核心内容（Identity + 规则），每个 session 都需要。
        # include_env=True 表示包含 OS / CWD / Git 等环境信息。
        # model 参数用于根据模型特性调整提示词格式（Claude vs GPT 有差异）。
        prompt_builder = SystemPromptBuilder.create_default(
            session_mode=store.mode,
            include_env=True,
            model=getattr(llm, "model", ""),
        )
        # load_context_from_disk 读取以下内容并拼入提示词：
        #   - 项目指令文件（CLAUDE.md / AGENTS.md / ~/.auton/auton.md）
        #   - 记忆文件（Project Memory / Today's Memory）
        # 这些文件内容是动态的（用户修改后下次会话会反映），每次 build 时重新加载。
        prompt_builder.load_context_from_disk(
            active_root=active_root,
            cwd=cwd,
            storage_dir=Path(config.memory.storage_dir),
        )

        # ── 8. 工具/技能能力概览 ────────────────────────────────────────────
        # _inject_tool_catalog 将所有可用工具的名称和描述写入提示词，
        # 让 LLM 知道当前会话可以调用哪些工具。
        # 为什么用工具描述而不传工具 schema？
        #   schema 已经在 tools 参数中传给 LLM（structured output），
        #   提示词中只需要提供人类可读的能力概览即可。
        self._inject_tool_catalog(prompt_builder, tools)
        # _inject_skill_context 读取 SkillRegistry，将可用技能的信息写入提示词。
        # 包括：技能名称、描述、路径、以及前 5 个技能的完整 SKILL.md 内容。
        # 这样 LLM 可以在对话中建议用户使用特定技能，或自行调用技能。
        self._inject_skill_context(prompt_builder, active_root or cwd)

        # ── 9. MCP Server 工具信息（Session 级别，动态注入）─────────────────
        # 与内置工具不同，MCP Server 是动态加载的（session 级别）。
        # 这步注入 MCP Server 的名称、状态（running/stopped）、可用工具列表。
        # 为什么单独处理 MCP 而不放在 _inject_tool_catalog？
        #   MCP Server 可能未启动（stopped 状态），需要特殊处理和展示。
        self._inject_mcp_context(prompt_builder, config)

        # ── 10. 加载用户扩展（~/.auton/subagents、workflows）────────────────
        # UserspaceLoader 读取 ~/.auton/subagents 和 ~/.auton/workflows 目录，
        # 将自定义 subagent 和 workflow 的定义注入提示词。
        # 这样即使不通过 Skill 机制，用户也可以定义自己的 subagent。
        userspace_loader = UserspaceLoader(layout)
        userspace_content = userspace_loader.load()
        if not userspace_content.is_empty:
            userspace_loader.inject_into_prompt(userspace_content, prompt_builder)

        # ── 11. System Prompt（会话启动时构建一次，包含完整上下文）
        # build_base() 将所有 add_section 的内容按优先级顺序拼接为最终字符串。
        # 这个字符串在 __init__ 时传给 SessionProcessor，后续每个 LLM 调用都传入。
        # 为什么一次性构建而不每次循环重新拼接？
        #   System Prompt 包含的是静态背景知识（skills 列表、工具说明、项目指令等），
        #   与会话历史无关，不需要每次循环重复拼接。compact 只压缩 session.messages。
        system_prompt = prompt_builder.build_base()

        # ── 12. SessionProcessor ──────────────────────────────────────────────
        # DecisionPolicy 决定何时 compact（压缩上下文）或 stop（结束会话）。
        # 为什么根据 context_window 计算 compact 阈值？
        #   不同模型的上下文窗口差异很大（8K vs 200K），用固定 token 数不通用。
        #   DecisionPolicy 内部根据 context_window * 0.8 计算触发阈值。
        from ..agent.policies import DecisionPolicy
        policy = DecisionPolicy(context_window=getattr(llm, "context_window", 8_192))

        # SessionProcessor 是会话的主循环处理器，封装了：
        #   - LLM 调用（stream）
        #   - 工具执行
        #   - 上下文压缩（compact）
        #   - 决策逻辑（stop / continue）
        # 它不包含任何 Web/CLI 特定的 I/O 逻辑，纯业务逻辑。
        processor = SessionProcessor(
            session=session,
            llm=llm,
            tools=tools,
            session_store=store,
            event_bus=bus,
            system_prompt=system_prompt,
            policy=policy,
        )

        # SessionContext 是"一切运行时对象的容器"，包含：
        #   - processor: 主循环处理器（调用方驱动 run_stream）
        #   - session: 会话对象（消息历史）
        #   - session_store: 持久化层
        #   - llm: LLM Provider
        #   - event_bus: 事件总线
        #   - system_prompt: 完整系统提示词
        # 调用方只需要关注 processor 和自己的 I/O，其他都是上下文。
        return SessionContext(
            processor=processor,
            session=session,
            session_store=store,
            llm=llm,
            event_bus=bus,
            system_prompt=system_prompt,
        )

    # ── 私有辅助方法 ──────────────────────────────────────────────────────────

    @staticmethod
    def create_llm(
        model: str | None = None,
        provider: str | None = None,
    ) -> "LLMProvider":
        """根据配置创建 LLM Provider 实例（公开静态方法）。

        供 Web 层、CLI 及其他入口复用，避免各自维护独立的创建逻辑。
        当 model / provider 为 None 时，从 config 读取默认值。

        为什么是静态方法？
          Web 层有时只需要创建 LLM，不需要完整的 SessionContext。
          静态方法允许直接调用 SessionFactory.create_llm()，无需实例化。

        为什么凭证（api_key / base_url）有条件判断？
          切换到不同 provider 时，api_key / base_url 交由该 provider 自行从
          各自的环境变量读取，避免把主 Agent 的凭证误传给其他平台。
          同一 provider 时复用配置文件中的凭证。
        """
        config = get_config()
        cfg = config.llm
        main_provider = (cfg.provider or "anthropic").lower()
        selected = (provider or cfg.provider or "anthropic").lower()
        effective_model = model or cfg.model

        # 切换到不同 provider 时，api_key / base_url 交由该 provider 自行从
        # 各自的环境变量读取，避免把主 Agent 的凭证误传给其他平台。
        if selected == main_provider:
            common = dict(
                api_key=cfg.api_key,
                base_url=cfg.base_url,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
                timeout=cfg.timeout,
            )
        else:
            common = dict(
                api_key=None,
                base_url=None,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
                timeout=cfg.timeout,
            )

        if selected == "minimax":
            from ..llm import MiniMaxProvider
            return MiniMaxProvider(model=effective_model, **common)

        if selected in ("openai", "gpt"):
            from ..llm import OpenAIProvider
            return OpenAIProvider(model=effective_model or "gpt-4o", **common)

        if selected in ("qwen", "dashscope", "tongyi"):
            from ..llm import QwenProvider
            return QwenProvider(model=effective_model or "qwen-max", **common)

        if selected == "deepseek":
            from ..llm import DeepSeekProvider
            return DeepSeekProvider(model=effective_model or "deepseek-chat", **common)

        if selected in ("doubao", "ark", "volcengine"):
            from ..llm import DoubaoProvider
            return DoubaoProvider(model=effective_model or "doubao-pro-32k", **common)

        if selected in ("kimi", "moonshot"):
            from ..llm import KimiProvider
            return KimiProvider(model=effective_model or "moonshot-v1-32k", **common)

        if selected == "openrouter":
            from ..llm import OpenRouterProvider
            return OpenRouterProvider(model=effective_model or "openai/gpt-4o", **common)

        if selected in ("gemini", "google"):
            from ..llm import GeminiProvider
            return GeminiProvider(model=effective_model or "gemini-2.0-flash", **common)

        if selected == "ollama":
            from ..llm import OllamaProvider
            return OllamaProvider(model=effective_model or "qwen3:8b", **common)

        if selected in ("lm_studio", "lmstudio", "lm-studio"):
            from ..llm import LMStudioProvider
            return LMStudioProvider(model=effective_model or "local-model", **common)

        if selected == "vllm":
            from ..llm import VLLMProvider
            return VLLMProvider(model=effective_model or "Qwen/Qwen3-8B", **common)

        if selected == "mock":
            from ..llm import MockProvider
            return MockProvider(model=effective_model or "mock-echo", **common)

        # 默认 Anthropic
        from ..llm import AnthropicProvider
        return AnthropicProvider(model=effective_model, **common)

    def _inject_tool_catalog(
        self,
        builder: SystemPromptBuilder,
        tools: "list[Tool]",
    ) -> None:
        """将本次会话可直接调用的工具写入系统提示词。

        为什么用表格形式而不是逐条列举？
          表格更紧凑，适合展示大量工具的概览信息。
        为什么对描述进行截断？
          工具描述可能很长，全部塞入提示词浪费 token。
          _shorten() 将描述压缩到 160 字符以内。
        为什么去重（seen set）？
          某些工具可能在多个来源注册（内置 + MCP），去重避免重复展示。
        """
        if not tools:
            return

        seen: set[str] = set()
        rows = [
            "以下工具可直接调用（名称区分大小写）：",
            "| 工具 | 描述 |",
            "|------|------|",
        ]
        for tool in sorted(tools, key=lambda t: t.name):
            if tool.name in seen:
                continue
            seen.add(tool.name)
            desc = getattr(tool, "description", "").strip() or "（未提供描述）"
            rows.append(f"| `{tool.name}` | {self._shorten(desc)} |")

        builder.add_section(
            "\n".join(rows),
            title="Available Tools",
            priority=SystemPromptBuilder.P_TOOLS,
        )

    def _inject_skill_context(
        self,
        builder: SystemPromptBuilder,
        cwd: Path,
    ) -> None:
        """注入技能摘要以及部分 SKILL.md 内容，避免用户再查目录。

        为什么分两级注入（摘要 + 详情）？
          全部注入所有 SKILL.md 内容会极大增加 token 消耗。
          采用折中方案：所有技能用 <available_skills> 标签列出摘要（轻量），
          前 5 个技能展示完整 SKILL.md 内容（方便直接使用），
          其余技能提示用户自行用 read 工具查看。

        为什么按 source 优先级排序？
          Skill 有多个来源（global / project / local），优先级不同。
          排序确保高优先级的技能显示在前面。
        """
        try:
            from ..skills.registry import SkillRegistry
            from ..skills.types import SKILL_SOURCE_PRIORITY
        except Exception as exc:  # pragma: no cover
            self._log.debug("Skill modules unavailable: {e}", e=exc)
            return

        try:
            registry = SkillRegistry.get_instance(cwd=cwd)
            registry.load(force=True)
            skills = registry.list_all()
        except Exception as exc:
            self._log.debug("Skill registry unavailable: {e}", e=exc)
            return

        if not skills:
            return

        ordered = sorted(
            skills,
            key=lambda s: (SKILL_SOURCE_PRIORITY[s.source], s.name.lower()),
        )

        summary_lines = ["<available_skills>"]
        for skill in ordered:
            summary_lines.extend([
                "  <skill>",
                f"    <name>{skill.name}</name>",
                f"    <description>{skill.description}</description>",
                f"    <source>{skill.source.value}</source>",
                f"    <location>{skill.path}</location>",
                "  </skill>",
            ])
        summary_lines.append("</available_skills>")

        builder.add_section(
            "\n".join(summary_lines),
            title="Available Skills",
            priority=SystemPromptBuilder.P_SKILL_SUMMARY,
        )

        detail_limit = min(5, len(ordered))
        detail_blocks: list[str] = []
        for skill in ordered[:detail_limit]:
            body = skill.get_full_content().strip()
            formatted = self._format_skill_body(body)
            detail_blocks.append(
                f"### {skill.name}（{skill.source.value}）\n"
                f"路径: {skill.path}\n\n{formatted}"
            )

        if len(ordered) > detail_limit:
            remaining = len(ordered) - detail_limit
            detail_blocks.append(
                f"…（其余 {remaining} 个技能请根据上表路径使用 `read` 工具查看完整 SKILL.md）"
            )

        builder.add_section(
            "\n\n".join(detail_blocks),
            title="Skill Guides",
            priority=SystemPromptBuilder.P_SKILL_DETAILS,
        )

    @staticmethod
    def _shorten(text: str, limit: int = 160) -> str:
        """压缩描述，避免提示词过长。

        为什么用 " ".join(text.split())？
          将多个空白字符（空格、换行、制表符）压缩为单个空格，
          效果类似 textwrap.shorten，但不破坏单词边界。
        为什么截断时末尾是 "..."？
          告知 LLM 描述被截断了，避免误解为完整描述。
        """
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."

    @staticmethod
    def _format_skill_body(text: str, limit: int = 1500) -> str:
        """包装 SKILL.md 内容，必要时截断。

        为什么用 rsplit("\n", 1) 截断？
          在第 1500 字符处找最后一个换行符，保证截断点在行尾而非行中，
          避免破坏半行代码或列表项。
        为什么用 markdown 代码块包裹？
          标记为代码块让 LLM 更容易理解这是技能文档内容，
          而非需要执行的指令。
        """
        content = text.strip()
        if not content:
            return "_SKILL.md 无内容_"
        if len(content) > limit:
            trimmed = content[:limit].rsplit("\n", 1)[0]
            content = trimmed + "\n...（内容截断，详见原文件）"
        return f"```markdown\n{content}\n```"

    async def _start_mcp(self, config) -> None:
        """启动所有配置的 MCP Server。

        为什么是 async 方法？
          load_mcp_servers 内部可能需要网络通信（连接远程 MCP Server），
          所以必须是异步的，不能阻塞主线程。
        为什么用 try/except 包裹？
          MCP Server 启动失败不应该导致整个会话无法启动（优雅降级）。
          记录警告日志后继续，LLM 至少可以使用内置工具。
        """
        from ..tools.mcp import load_mcp_servers
        from ..tools.registry import get_registry
        try:
            clients = await load_mcp_servers({"mcp": config.mcp.model_dump()})
            registry = get_registry()
            for name, client in clients.items():
                registry.set_mcp_client(name, client)
            self._log.info("MCP servers started: {s}", s=list(clients.keys()))
        except Exception as exc:
            self._log.warning("MCP load failed: {e}", e=exc)

    def _inject_mcp_context(
        self,
        builder: "SystemPromptBuilder",
        config: "Any",
    ) -> None:
        """将 MCP Server 配置及可用工具注入为 system prompt section。

        与 OpenClaw 做法一致：直接读取真实配置拼接进 prompt，
        而非只写描述。

        为什么 MCP Server 单独处理而不是合并到 _inject_tool_catalog？
          MCP Server 有三种状态（running / stopped / unknown），
          需要用 emoji 直观展示状态，而工具列表不需要。
        为什么需要 registry.get_mcp_client() 判断状态？
          MCP Server 可能配置了但未成功启动（stopped 状态），
          需要从 registry 中查询实际状态来展示。
        """
        try:
            from ..tools.registry import get_registry

            registry = get_registry()
        except Exception as exc:
            self._log.debug("ToolRegistry unavailable: {e}", e=exc)
            return

        servers = config.mcp.servers
        if not servers:
            return

        lines: list[str] = [
            "以下 MCP Server 已配置：\n",
            "| Server | 状态 | 工具 |",
            "|--------|------|------|",
        ]

        for server_cfg in servers:
            try:
                client = registry.get_mcp_client(server_cfg.name)
                if client is not None:
                    tool_names = [t.name for t in registry.list_by_source(f"mcp:{server_cfg.name}")]
                    tool_str = ", ".join(tool_names) if tool_names else "—"
                    lines.append(f"| **{server_cfg.name}** | 🟢 running | {tool_str} |")
                else:
                    lines.append(f"| **{server_cfg.name}** | ⚠️  stopped | — |")
            except Exception:
                lines.append(f"| **{server_cfg.name}** | ❓ unknown | — |")

        builder.add_section(
            "\n".join(lines),
            title="MCP Servers",
            priority=SystemPromptBuilder.P_MCP,
        )
