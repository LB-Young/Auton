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

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from loguru import logger

from ..agent.agent import SessionProcessor
from ..agent.session import Session
from ..agent.session_store import SessionStore
from ..core.config import get_config
from ..core.events import EventBus
from ..llm.prompt import build_system_prompt
from .types import SessionContext

if TYPE_CHECKING:
    from ..llm.base import LLMProvider
    from ..skills.injector import SkillInjector
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

        # ── 7. 系统提示词 ─────────────────────────────────────────────────────
        system_prompt = self._build_prompt(
            store=store,
            active_root=active_root,
            cwd=cwd,
            storage_dir=Path(config.memory.storage_dir),
        )

        # ── 8. SkillInjector ─────────────────────────────────────────────────
        skill_injector = self._create_skill_injector()

        # ── 9. SessionProcessor ───────────────────────────────────────────────
        processor = SessionProcessor(
            session=session,
            llm=llm,
            tools=tools,
            session_store=store,
            event_bus=bus,
            system_prompt=system_prompt,
            skill_injector=skill_injector,
        )

        return SessionContext(
            processor=processor,
            session=session,
            session_store=store,
            llm=llm,
            event_bus=bus,
            skill_injector=skill_injector,
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
        selected = provider or cfg.provider

        if selected == "minimax":
            from ..llm import MiniMaxProvider
            return MiniMaxProvider(
                model=model or cfg.model,
                api_key=cfg.api_key,
                base_url=cfg.base_url,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
                timeout=cfg.timeout,
            )
        from ..llm import AnthropicProvider
        return AnthropicProvider(
            model=model or cfg.model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            timeout=cfg.timeout,
        )

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

    def _build_prompt(
        self,
        store: SessionStore,
        active_root: Path | None,
        cwd: Path,
        storage_dir: Path,
    ) -> str:
        memory_ctx = ""
        project_ctx = ""
        try:
            today = datetime.date.today().strftime("%Y-%m-%d")

            # 日期记忆
            date_mem = storage_dir / "dates" / today / "memory" / "memory.md"
            if date_mem.exists():
                memory_ctx = date_mem.read_text(encoding="utf-8")

            # 项目记忆
            if active_root:
                proj_mem = storage_dir / "projects" / active_root.name / "memory" / "MEMORY.md"
                if proj_mem.exists():
                    memory_ctx = (
                        proj_mem.read_text(encoding="utf-8") + "\n\n" + memory_ctx
                    ).strip()

            # 用户全局指令 ~/.auton/auton.md
            global_guide = Path.home() / ".auton" / "auton.md"
            if global_guide.exists():
                project_ctx = global_guide.read_text(encoding="utf-8")

            # 项目级指令（CLAUDE.md / AGENTS.md / .auton.md）
            search_dir = active_root or cwd
            for guide_name in ("CLAUDE.md", "AGENTS.md", ".auton.md"):
                guide_path = search_dir / guide_name
                if guide_path.exists():
                    txt = guide_path.read_text(encoding="utf-8")
                    project_ctx = (
                        (project_ctx + "\n\n" + txt).strip() if project_ctx else txt
                    )
                    break
        except Exception as exc:
            self._log.debug("prompt context load error: {e}", e=exc)

        return build_system_prompt(
            project_context=project_ctx,
            memory_context=memory_ctx,
            include_env=True,
            session_mode=store.mode,
        )

    def _create_skill_injector(self) -> "SkillInjector | None":
        try:
            from ..skills.injector import SkillInjector
            return SkillInjector()
        except Exception as exc:
            self._log.debug("SkillInjector init failed: {e}", e=exc)
            return None
