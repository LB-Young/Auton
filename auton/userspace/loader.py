"""Userspace Loader — 加载用户在 ~/.auton 中安装的能力

每次 Session 启动时调用 ``UserspaceLoader.load()``，它会：

  1. **Skills**     — 通过 SkillRegistry 自动加载（SkillLoader 会扫描 ~/.auton/skills/）
  2. **Subagents**  — 扫描 ~/.auton/subagents/<name>/AGENT.md，注册为声明式 Subagent
  3. **Workflows**  — 扫描 ~/.auton/workflows/*.{yaml,yml}，注册为可调用工作流
  4. **auton.md**   — 注入用户全局指令到系统提示词（已在 SystemPromptBuilder.load_context_from_disk 中处理）

Subagent 格式（AGENT.md frontmatter）
--------------------------------------
::

    ---
    name: my-reviewer
    description: 专门负责代码 review 的 subagent
    model: claude-sonnet-4-20250514   # 可选，默认继承主 Agent
    max_turns: 10                      # 可选
    ---

    你是一个专注于代码质量的审核专家...（系统提示词正文）

Workflow 格式（*.yaml）
-----------------------
::

    name: deploy-check
    description: 部署前检查流程
    steps:
      - name: run-tests
        tool: bash
        args: {command: "pytest"}
      - name: security-scan
        subagent: security

"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from .bootstrap import UserspaceLayout, get_layout
from ..core.config import is_capability_enabled


# ─── 声明式 Subagent（从 AGENT.md 加载）────────────────────────────────────────

@dataclass
class UserSubagentDef:
    """用户安装的声明式 Subagent 定义"""

    name: str
    description: str
    system_prompt: str
    model: str | None = None
    max_turns: int | None = None
    timeout_seconds: int = 300
    path: Path = field(default_factory=Path)

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "max_turns": self.max_turns,
            "timeout_seconds": self.timeout_seconds,
        }


# ─── 工作流定义（从 *.yaml 加载）────────────────────────────────────────────────

@dataclass
class UserWorkflowDef:
    """用户定义的工作流"""

    name: str
    description: str
    steps: list[dict[str, Any]]
    path: Path = field(default_factory=Path)


# ─── 加载结果 ────────────────────────────────────────────────────────────────────

@dataclass
class UserspaceContent:
    """一次 load() 的加载结果"""

    subagents: list[UserSubagentDef] = field(default_factory=list)
    workflows: list[UserWorkflowDef] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.subagents and not self.workflows

    def summary(self) -> str:
        parts = []
        if self.subagents:
            parts.append(f"subagents×{len(self.subagents)}")
        if self.workflows:
            parts.append(f"workflows×{len(self.workflows)}")
        if self.errors:
            parts.append(f"errors×{len(self.errors)}")
        return ", ".join(parts) if parts else "empty"


# ─── 主加载器 ────────────────────────────────────────────────────────────────────

class UserspaceLoader:
    """用户空间内容加载器

    负责扫描 ~/.auton 中用户安装的 subagents 和 workflows，并将结果
    注册到对应的 Registry 中。Skills 的加载由 SkillLoader/SkillRegistry
    负责（它会自动扫描 ~/.auton/skills/），此处不重复处理。
    """

    AGENT_FILE = "AGENT.md"

    def __init__(self, layout: UserspaceLayout | None = None) -> None:
        self._layout = layout or get_layout()
        self._log = logger.bind(name="userspace.loader")

    def load(self) -> UserspaceContent:
        """扫描 ~/.auton，加载所有用户内容。

        Returns:
            UserspaceContent：包含所有加载结果和任何加载错误。
        """
        content = UserspaceContent()
        self._load_subagents(content)
        self._load_workflows(content)

        if not content.is_empty:
            self._log.info(
                "userspace 加载完成: {s}",
                s=content.summary(),
            )
        else:
            self._log.debug("userspace 无用户扩展内容")

        return content

    # ─── Subagents ──────────────────────────────────────────────────────────

    def _load_subagents(self, content: UserspaceContent) -> None:
        """扫描 ~/.auton/subagents/<name>/AGENT.md"""
        subagents_dir = self._layout.subagents_dir
        if not subagents_dir.exists():
            return

        for entry in subagents_dir.iterdir():
            if not entry.is_dir():
                continue
            agent_file = entry / self.AGENT_FILE
            if not agent_file.exists():
                continue
            try:
                defn = self._parse_agent_md(agent_file)
                if not is_capability_enabled("extensions", "subagents", defn.name):
                    self._log.info(
                        "跳过用户 subagent {n}（配置中禁用）",
                        n=defn.name,
                    )
                    continue
                content.subagents.append(defn)
                self._log.debug("加载 subagent: {n} from {p}", n=defn.name, p=entry.name)
            except Exception as exc:
                msg = f"加载 subagent {entry.name} 失败: {exc}"
                self._log.warning(msg)
                content.errors.append(msg)

    def _parse_agent_md(self, path: Path) -> UserSubagentDef:
        """解析 AGENT.md 文件（frontmatter + body）"""
        text = path.read_text(encoding="utf-8")

        fm: dict[str, Any] = {}
        body = text

        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                try:
                    fm = yaml.safe_load(parts[1]) or {}
                    body = parts[2].strip()
                except yaml.YAMLError:
                    body = text  # frontmatter 解析失败，整体作为 body

        name = fm.get("name") or path.parent.name
        description = fm.get("description", "")
        model = fm.get("model")
        max_turns = fm.get("max_turns")
        timeout = int(fm.get("timeout_seconds", 300))

        return UserSubagentDef(
            name=name,
            description=description,
            system_prompt=body,
            model=model,
            max_turns=max_turns,
            timeout_seconds=timeout,
            path=path,
        )

    # ─── Workflows ──────────────────────────────────────────────────────────

    def _load_workflows(self, content: UserspaceContent) -> None:
        """扫描 ~/.auton/workflows/*.{yaml,yml}"""
        workflows_dir = self._layout.workflows_dir
        if not workflows_dir.exists():
            return

        for wf_file in sorted(workflows_dir.iterdir()):
            if wf_file.suffix.lower() not in (".yaml", ".yml"):
                continue
            try:
                defn = self._parse_workflow_yaml(wf_file)
                if not is_capability_enabled("extensions", "workflows", defn.name):
                    self._log.info(
                        "跳过用户 workflow {n}（配置中禁用）",
                        n=defn.name,
                    )
                    continue
                content.workflows.append(defn)
                self._log.debug("加载 workflow: {n} from {p}", n=defn.name, p=wf_file.name)
            except Exception as exc:
                msg = f"加载 workflow {wf_file.name} 失败: {exc}"
                self._log.warning(msg)
                content.errors.append(msg)

    def _parse_workflow_yaml(self, path: Path) -> UserWorkflowDef:
        """解析工作流 YAML 文件"""
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        name = data.get("name") or path.stem
        description = data.get("description", "")
        steps = data.get("steps", [])
        return UserWorkflowDef(
            name=name,
            description=description,
            steps=steps,
            path=path,
        )

    # ─── 注入到 SystemPromptBuilder ─────────────────────────────────────────

    def inject_into_prompt(
        self,
        content: UserspaceContent,
        builder: "SystemPromptBuilder",  # type: ignore[name-defined]
    ) -> None:
        """将用户扩展内容以 section 形式注入 SystemPromptBuilder。

        Args:
            content: load() 返回的加载结果
            builder: 当前会话的 SystemPromptBuilder
        """
        from ..agent.system_prompt import SystemPromptBuilder

        if content.subagents:
            lines = ["以下 Subagent 由用户安装，可通过名称调用：\n"]
            for sa in content.subagents:
                desc = f"  - **{sa.name}**: {sa.description}" if sa.description else f"  - **{sa.name}**"
                lines.append(desc)
            builder.add_section(
                "\n".join(lines),
                title="User Subagents",
                priority=45,
            )

        if content.workflows:
            lines = ["以下工作流由用户定义，可通过 `/workflow run <name>` 触发：\n"]
            for wf in content.workflows:
                desc = f"  - **{wf.name}**: {wf.description}" if wf.description else f"  - **{wf.name}**"
                lines.append(desc)
            builder.add_section(
                "\n".join(lines),
                title="User Workflows",
                priority=46,
            )
