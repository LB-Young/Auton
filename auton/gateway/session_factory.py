"""Gateway — SessionFactory

统一构建会话所需的全部运行时对象，消除 cli / web / bot 等接入端的重复初始化代码。

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
          ↑ 以上完整 System Prompt 在 build() 中通过 build_base() 构建一次，
            后续不再变化（不参与 compact）。

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
        layout = ensure_userspace(quiet=True)

        # ── 1. SessionStore & 模式 ────────────────────────────────────────────
        effective_root = project_root or cwd
        store = SessionStore(storage_dir=config.memory.storage_dir)

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
        active_root = store.project_root
        if session is None:
            session = Session.create(
                project_path=str(active_root) if active_root else None
            )

        # ── 3. LLM Provider ───────────────────────────────────────────────────
        llm = self._create_llm(model=model, provider=provider)

        # ── 4. Tools ──────────────────────────────────────────────────────────
        from ..tools import get_default_tools
        perm = permission_mode or config.security.permission_mode
        tools: list[Tool] = get_default_tools(permission_mode=perm, yes_all=yes_all)
        if extra_tools:
            tools = tools + extra_tools

        # ── 5. MCP Servers（可选）────────────────────────────────────────────
        if enable_mcp and config.mcp.auto_start and config.mcp.servers:
            await self._start_mcp(config)

        # ── 6. EventBus ───────────────────────────────────────────────────────
        bus = event_bus or EventBus()

        # ── 7. 系统提示词（内置静态 + 环境 + 记忆/项目文档 + Subagent）─────────
        prompt_builder = SystemPromptBuilder.create_default(
            session_mode=store.mode,
            include_env=True,
            model=getattr(llm, "model", ""),
        )
        prompt_builder.load_context_from_disk(
            active_root=active_root,
            cwd=cwd,
            storage_dir=Path(config.memory.storage_dir),
        )

        # ── 8. 工具/技能能力概览 ────────────────────────────────────────────
        self._inject_tool_catalog(prompt_builder, tools)
        self._inject_skill_context(prompt_builder, active_root or cwd)

        # ── 9. MCP Server 工具信息（Session 级别，动态注入）─────────────────
        self._inject_mcp_context(prompt_builder, config)

        # ── 10. 加载用户扩展（~/.auton/subagents、workflows）────────────────
        userspace_loader = UserspaceLoader(layout)
        userspace_content = userspace_loader.load()
        if not userspace_content.is_empty:
            userspace_loader.inject_into_prompt(userspace_content, prompt_builder)

        # ── 11. System Prompt（会话启动时构建一次，包含完整上下文）
        system_prompt = prompt_builder.build_base()

        # ── 12. SessionProcessor ──────────────────────────────────────────────
        # DecisionPolicy：compact_threshold 基于模型实际上下文窗口自动计算
        from ..agent.policies import DecisionPolicy
        policy = DecisionPolicy(context_window=getattr(llm, "context_window", 8_192))

        processor = SessionProcessor(
            session=session,
            llm=llm,
            tools=tools,
            session_store=store,
            event_bus=bus,
            system_prompt=system_prompt,
            policy=policy,
        )

        return SessionContext(
            processor=processor,
            session=session,
            session_store=store,
            llm=llm,
            event_bus=bus,
            system_prompt=system_prompt,
        )

    # ── 私有辅助方法 ──────────────────────────────────────────────────────────

    def _create_llm(
        self,
        model: str | None = None,
        provider: str | None = None,
    ) -> "LLMProvider":
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
        """将本次会话可直接调用的工具写入系统提示词。"""
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
        """注入技能摘要以及部分 SKILL.md 内容，避免用户再查目录。"""
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
        """压缩描述，避免提示词过长。"""
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."

    @staticmethod
    def _format_skill_body(text: str, limit: int = 1500) -> str:
        """包装 SKILL.md 内容，必要时截断。"""
        content = text.strip()
        if not content:
            return "_SKILL.md 无内容_"
        if len(content) > limit:
            trimmed = content[:limit].rsplit("\n", 1)[0]
            content = trimmed + "\n...（内容截断，详见原文件）"
        return f"```markdown\n{content}\n```"

    async def _start_mcp(self, config) -> None:
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
