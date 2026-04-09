"""AgentManager — Agent 定义加载与 Sub-Agent 生命周期管理（M12 Multi-Agent）"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from .types import AgentDefinition, AgentRun, AgentStatus

if TYPE_CHECKING:
    pass


# ─── 内置 Agent 定义 ────────────────────────────────────────────────────────

_BUILTIN_AGENTS: list[AgentDefinition] = [
    AgentDefinition(
        name="explore",
        description="代码探索专家。当需要全面分析项目结构、理解复杂模块、搜索多种模式时使用。",
        system_prompt="""你是代码探索专家。你擅长全面分析项目结构、理解模块边界、快速定位关键代码。
你专注于观察和总结，不做修改决策。""",
        model=None,
        tools=["read", "glob", "grep"],
        disallowed_tools=[],
        permission_mode="auto",
        max_turns=10,
        skills=[],
        mcp_servers=[],
        background=False,
        isolation=None,
        source="builtin",
    ),
    AgentDefinition(
        name="coder",
        description="编程专家。当需要写代码、改代码、重构、修复 bug 时使用。",
        system_prompt="""你是编程专家。你擅长根据需求写代码、修改现有代码、重构以提升质量。
你遵循最佳实践，注重代码可读性和安全性。""",
        model=None,
        tools=None,  # 全部工具
        disallowed_tools=[],
        permission_mode="default",
        max_turns=20,
        skills=[],
        mcp_servers=[],
        background=False,
        isolation=None,
        source="builtin",
    ),
    AgentDefinition(
        name="reviewer",
        description="审查专家。当需要 review 代码、审查 PR、检查质量时使用。",
        system_prompt="""你是代码审查专家。你擅长发现代码问题、安全漏洞、性能隐患和风格不一致。
审查要客观、有建设性，区分必须修复和建议改进。""",
        model=None,
        tools=["read", "glob", "grep", "bash"],
        disallowed_tools=["write", "edit"],
        permission_mode="auto",
        max_turns=10,
        skills=[],
        mcp_servers=[],
        background=False,
        isolation=None,
        source="builtin",
    ),
    AgentDefinition(
        name="planner",
        description="规划专家。当需要任务分解、方案设计、架构决策时使用。",
        system_prompt="""你是规划专家。你擅长将复杂需求分解为可执行的步骤，评估风险，设计方案。
你输出结构清晰、分层有序，适合直接执行。""",
        model=None,
        tools=["read", "glob", "grep"],
        disallowed_tools=[],
        permission_mode="auto",
        max_turns=8,
        skills=[],
        mcp_servers=[],
        background=False,
        isolation=None,
        source="builtin",
    ),
]


# ─── AgentManager ────────────────────────────────────────────────────────────

@dataclass
class _RunningTask:
    """运行中的 asyncio Task"""
    task: asyncio.Task[str]
    run: AgentRun


class AgentManager:
    """Agent 管理器

    职责：
      - 加载内置 + 用户 + 项目 agent 定义
      - 维护活跃的 sub-agent 运行列表
      - 提供 agent 检索
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentDefinition] = {}
        self._runs: dict[str, AgentRun] = {}        # run_id -> AgentRun
        self._running_tasks: dict[str, _RunningTask] = {}  # run_id -> asyncio Task
        self._logger = logger.bind(name="AgentManager")
        self._load_agents()

    # ─── 加载 ──────────────────────────────────────────────────────────────

    def _load_agents(self) -> None:
        """加载所有 agent（builtin + 用户 + 项目）"""
        # 内置
        for agent in _BUILTIN_AGENTS:
            self._agents[agent.name] = agent
        self._logger.debug("loaded {n} builtin agents", n=len(_BUILTIN_AGENTS))

        # 用户级：~/.auton/agents/
        user_dir = Path.home() / ".auton" / "agents"
        if user_dir.exists():
            self._load_from_dir(user_dir, source="user")

        # 项目级：.auton/agents/
        import os
        cwd = Path.cwd()
        project_dir = cwd / ".auton" / "agents"
        if project_dir.exists():
            self._load_from_dir(project_dir, source="project")

        self._logger.info("loaded {n} total agents", n=len(self._agents))

    def _load_from_dir(self, directory: Path, source: str) -> None:
        """从目录加载 *.md agent 定义"""
        if not directory.is_dir():
            return
        for file_path in sorted(directory.glob("*.md")):
            agent = self._parse_agent_md(file_path.read_text(encoding="utf-8"), source)
            if agent:
                self._agents[agent.name] = agent
                self._logger.debug("loaded agent {name} from {path}", name=agent.name, path=file_path)

    def _parse_agent_md(self, content: str, source: str) -> AgentDefinition | None:
        """解析 Markdown agent 定义文件"""
        # 前置元数据：--- ... --- 块
        frontmatter_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        body = content[frontmatter_match.end():] if frontmatter_match else content
        frontmatter_str = frontmatter_match.group(1) if frontmatter_match else ""

        name = Path(content.split("\n")[0] if "\n" in content else content).stem  # fallback
        description = ""
        model: str | None = None
        tools: list[str] | None = None
        disallowed_tools: list[str] = []
        permission_mode = "default"
        max_turns: int | None = None
        skills: list[str] = []
        mcp_servers: list[str] = []
        background = False
        isolation: str | None = None

        # 解析 frontmatter
        for line in frontmatter_str.splitlines():
            line = line.strip()
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key == "name":
                    name = value
                elif key == "description":
                    description = value
                elif key == "model":
                    model = value if value else None
                elif key == "permissionMode":
                    permission_mode = value or "default"
                elif key == "maxTurns":
                    try:
                        max_turns = int(value)
                    except ValueError:
                        pass
                elif key == "omitClaudeMd":
                    pass  # Auton 不使用 claude.md
                elif key == "isolation":
                    isolation = value if value else None

        # 解析 tools/skills/mcpServers 列表（格式: "  - toolname"）
        in_tools = False
        in_skills = False
        in_mcp = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "tools:":
                in_tools = True
                in_skills = False
                in_mcp = False
                tools = []
            elif stripped == "skills:":
                in_skills = True
                in_tools = False
                in_mcp = False
                skills = []
            elif stripped == "mcpServers:":
                in_mcp = True
                in_tools = False
                in_skills = False
                mcp_servers = []
            elif stripped.startswith("- ") and (in_tools or in_skills or in_mcp):
                item = stripped[2:].strip()
                if in_tools and tools is not None:
                    tools.append(item)
                elif in_skills:
                    skills.append(item)
                elif in_mcp:
                    mcp_servers.append(item)
            elif stripped and not stripped.startswith("-") and (in_tools or in_skills or in_mcp):
                if ":" not in stripped:
                    in_tools = in_skills = in_mcp = False

        return AgentDefinition(
            name=name,
            description=description,
            system_prompt=body.strip(),
            model=model,
            tools=tools,
            disallowed_tools=disallowed_tools,
            permission_mode=permission_mode,
            max_turns=max_turns,
            skills=skills,
            mcp_servers=mcp_servers,
            background=background,
            isolation=isolation,
            source=source,
        )

    # ─── 查询 ──────────────────────────────────────────────────────────────

    def get(self, name: str) -> AgentDefinition | None:
        """根据名称获取 agent 定义"""
        return self._agents.get(name)

    def list(self) -> list[AgentDefinition]:
        """列出所有 agent"""
        return list(self._agents.values())

    def list_by_tools(self, tools: list[str]) -> list[AgentDefinition]:
        """按工具筛选 agent"""
        result = []
        for agent in self._agents.values():
            if agent.tools is None:
                result.append(agent)
            elif all(t in agent.tools for t in tools):
                result.append(agent)
        return result

    def list_runs(self, status: AgentStatus | None = None) -> list[AgentRun]:
        """列出运行记录"""
        runs = list(self._runs.values())
        if status:
            runs = [r for r in runs if r.status == status]
        return sorted(runs, key=lambda r: r.created_at, reverse=True)

    def get_run(self, run_id: str) -> AgentRun | None:
        """获取运行记录"""
        return self._runs.get(run_id)

    # ─── 运行 ──────────────────────────────────────────────────────────────

    def create_run(
        self,
        name: str,
        prompt: str,
        parent_session_id: str,
    ) -> AgentRun | None:
        """创建 sub-agent 运行"""
        agent = self.get(name)
        if not agent:
            self._logger.warning("agent not found: {name}", name=name)
            return None

        run_id = uuid.uuid4().hex[:12]
        run = AgentRun(
            run_id=run_id,
            agent_name=name,
            parent_session_id=parent_session_id,
            status="pending",
            prompt=prompt,
        )
        self._runs[run_id] = run
        self._logger.info("created agent run {run_id} agent={name}", run_id=run_id, name=name)
        return run

    async def start_run(self, run_id: str) -> str:
        """启动 agent 运行（异步），返回结果文本"""
        run = self._runs.get(run_id)
        if not run:
            return f"Run not found: {run_id}"

        run.status = "running"
        run.started_at = datetime.now()
        agent = self.get(run.agent_name)
        if not agent:
            run.status = "failed"
            run.error = f"Agent not found: {run.agent_name}"
            return run.error

        try:
            result = await self._run_sub_agent(agent, run)
            run.status = "completed"
            run.result = result
            return result
        except asyncio.CancelledError:
            run.status = "aborted"
            raise
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error = str(exc)
            return f"Agent failed: {exc}"
        finally:
            run.completed_at = datetime.now()
            if run_id in self._running_tasks:
                del self._running_tasks[run_id]

    async def _run_sub_agent(self, agent: AgentDefinition, run: AgentRun) -> str:
        """运行 sub-agent 并返回结果"""
        # 构建子会话
        from ..agent.session import Session
        from ..agent.agent import SessionProcessor
        from ..agent.session_store import SessionStore
        from ..llm.factory import get_llm_provider
        from ..tools.registry import get_registry
        from ..core.events import EventBus

        session = Session.create(project_path=None, session_id=run.run_id)
        session.add_user_message(run.prompt)

        # 过滤工具
        registry = get_registry()
        all_tools = registry.get_tools()
        if agent.tools is not None:
            available = {t.name for t in all_tools}
            allowed = set(agent.tools) - set(agent.disallowed_tools)
            allowed = [t for t in all_tools if t.name in allowed]
        elif agent.disallowed_tools:
            allowed = [t for t in all_tools if t.name not in agent.disallowed_tools]
        else:
            allowed = all_tools

        # LLM
        llm = get_llm_provider()

        # 构建 system prompt（包含 agent 上下文）
        system_parts = [
            f"## {agent.name} Agent",
            "",
            agent.system_prompt,
            "",
            f"**当前任务（来自主 Agent）**:",
            run.prompt,
        ]
        system_prompt = "\n".join(system_parts)

        # 事件总线
        event_bus = EventBus()

        # SessionProcessor
        store = SessionStore()
        processor = SessionProcessor(
            session=session,
            llm=llm,
            tools=allowed,
            session_store=store,
            event_bus=event_bus,
        )

        # 处理（单轮，等待完成）
        # 注入 system prompt 片段到 session
        session.messages.insert(0, type(session.messages[0])(
            role="system"
        ) if session.messages else None)

        # 简单处理：让 session processor 处理到 stop
        try:
            from ..agent.types import ProcessResult
            async for event in processor.process():
                if hasattr(event, "type") and event.type == "step_finish":
                    break
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Agent processing error: {exc}") from exc

        # 提取 assistant 响应
        texts: list[str] = []
        for msg in reversed(session.messages):
            if msg.role == "assistant":
                for part in msg.parts:
                    if hasattr(part, "text") and part.text:
                        texts.append(part.text)
        return "\n\n".join(texts) if texts else "(no response)"

    def abort_run(self, run_id: str) -> bool:
        """中止运行中的 agent"""
        task_info = self._running_tasks.get(run_id)
        if not task_info:
            run = self._runs.get(run_id)
            if run and run.status == "running":
                run.status = "aborted"
                return True
            return False

        task_info.task.cancel()
        task_info.run.status = "aborted"
        self._logger.info("aborted run {run_id}", run_id=run_id)
        return True
