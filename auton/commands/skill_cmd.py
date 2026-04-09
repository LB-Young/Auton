"""Skill Command — /skill (M6 implementation)"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..skills import SkillRegistry
from ..skills.skill_creator import SkillCreator
from ..skills.packager import SkillPackager
from ..skills.checker import SkillChecker
from ..skills.semantic_search import SkillSearcher
from ..skills.injector import SkillInjector
from ..skills.types import SkillSource
from .base import Command, CommandResult


def _get_registry() -> SkillRegistry:
    """获取 SkillRegistry 实例"""
    return SkillRegistry.get_instance()


class SkillCommand(Command):
    """技能管理命令（M6 — Skills 里程碑完整实现）"""

    name = "skill"
    description = "管理技能（list/info/create/delete/edit/check/install）"
    patterns = [
        ("/skill",),
        ("/skill", "(list|info|create|delete|edit|check|install)"),
        ("/skill", "info", "<name>"),
        ("/skill", "delete", "<name>"),
        ("/skill", "edit", "<name>"),
        ("/skill", "install", "<file>"),
        ("/skill", "search", "<query>"),
    ]

    async def handle(self, args: dict[str, Any]) -> CommandResult:
        sub = args.get("_subcommand") or "list"

        handler = {
            "list": self._list,
            "info": self._info,
            "create": self._create,
            "delete": self._delete,
            "edit": self._edit,
            "check": self._check,
            "install": self._install,
            "search": self._search,
        }.get(sub)

        if handler:
            return await handler(args)
        return CommandResult(content=self._usage())

    # ─── /skill list ─────────────────────────────────────────────────

    async def _list(self, _args: dict) -> CommandResult:
        """列出所有可用技能（含来源）"""
        registry = _get_registry()
        registry.ensure_loaded()

        if len(registry) == 0:
            content = "暂无已注册的技能。\n\n使用 `/skill create` 创建第一个技能。"
            return CommandResult(content=content)

        lines = [
            f"## 可用技能（共 {len(registry)} 个）\n",
        ]

        # 按来源分组
        for source in SkillSource:
            skills = registry.list_by_source(source)
            if not skills:
                continue
            labels = {
                SkillSource.WORKSPACE: "工作区（.auton/skills/）",
                SkillSource.PROJECT: "项目（.auton/skills/）",
                SkillSource.USER: "用户（~/.auton/skills/）",
                SkillSource.BUILTIN: "内置（src/auton/skills/builtin/）",
            }
            lines.append(f"### {labels[source]} — {len(skills)} 个")
            for skill in sorted(skills, key=lambda s: s.name):
                emoji = f"{skill.emoji} " if skill.emoji else ""
                bins = ""
                if skill.required_bins:
                    available = [b for b in skill.required_bins if shutil.which(b)]
                    if available != skill.required_bins:
                        bins = " ⚠️ 缺失依赖"
                    else:
                        bins = " ✅"
                lines.append(f"- **{emoji}{skill.name}**{bins}")
                lines.append(f"  {skill.description[:80]}")
            lines.append("")

        content = "\n".join(lines)
        return CommandResult(content=content)

    # ─── /skill info <name> ─────────────────────────────────────────

    async def _info(self, args: dict) -> CommandResult:
        """查看指定技能的完整内容"""
        name = args.get("<name>", "").strip()
        if not name:
            return CommandResult(content="用法：`/skill info <name>`", success=False)

        registry = _get_registry()
        skill = registry.get(name)

        if skill is None:
            return CommandResult(content=f"未找到技能：`{name}`", success=False)

        lines = [
            f"# Skill: {skill.name}",
            f"**来源**: {skill.source.value}",
            f"**描述**: {skill.description}",
            "",
        ]

        if skill.required_bins:
            available = [b for b in skill.required_bins if shutil.which(b)]
            status = "✅" if available == skill.required_bins else "⚠️"
            lines.append(f"**依赖** {status}: `{', '.join(skill.required_bins)}`")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(skill.body)
        lines.append("")

        # experiences
        if skill.has_experiences:
            lines.append("---")
            lines.append("")
            lines.append("## Experiences")
            lines.append("")
            lines.append(skill.get_experiences())

        # references
        refs = skill.list_references()
        if refs:
            lines.append("")
            lines.append(f"## References（{len(refs)} 个文件）")
            for ref in refs:
                lines.append(f"- `{ref.name}`")

        # scripts
        scripts = skill.list_scripts()
        if scripts:
            lines.append("")
            lines.append(f"## Scripts（{len(scripts)} 个）")
            for s in scripts:
                is_exec = s.stat().st_mode & 0o111
                exe = "（可执行）" if is_exec else "（无执行权限）"
                lines.append(f"- `{s.name}` {exe}")

        content = "\n".join(lines)
        return CommandResult(content=content)

    # ─── /skill create ──────────────────────────────────────────────

    async def _create(self, _args: dict) -> CommandResult:
        """触发 skill-creator，引导创建新技能（stub — 完整对话流程在 M8 实现）"""
        creator = SkillCreator()
        skills_dir = creator.get_user_skills_dir()
        skills_dir.mkdir(parents=True, exist_ok=True)

        content = (
            "## /skill create — 技能创建\n\n"
            "**skill-creator** 引导你创建一个新技能。当前为交互式引导（stub）。\n\n"
            "请提供以下信息：\n\n"
            "**1. 技能名称**（小写+连字符，如 `postgres-manager`）\n\n"
            "**2. 描述**（何时使用此技能，建议 1-2 句话）\n\n"
            "**3. emoji**（可选，如 🐘）\n\n"
            "**4. 加载 experiences**（y/n，默认 y）\n\n"
            "示例：\n"
            "```\n"
            "/skill create\n"
            "名称：postgres-manager\n"
            "描述：PostgreSQL 数据库管理。使用时机：(1) 创建/删除表\n"
            "  (2) 运行迁移 (3) 查询数据。无需使用：简单 SELECT 直接用 bash。\n"
            "emoji：🐘\n"
            "```\n\n"
            "或者直接告诉我你想建什么技能的描述，我来帮你填写。\n\n"
            "内置技能示例（`skill-creator` SKILL.md）：\n\n"
            "```markdown\n"
            "---\n"
            "name: skill-creator\n"
            "description: Create, edit, or improve AgentSkills. Use when:\n"
            "  (1) user wants to create a new skill, (2) improve existing skill.\n"
            "user-invocable: true\n"
            "---\n"
            "```\n"
        )
        return CommandResult(content=content)

    # ─── /skill delete <name> ───────────────────────────────────────

    async def _delete(self, args: dict) -> CommandResult:
        """删除用户/项目级技能（内置不可删）"""
        name = args.get("<name>", "").strip()
        if not name:
            return CommandResult(content="用法：`/skill delete <name>`", success=False)

        registry = _get_registry()
        skill = registry.get(name)

        if skill is None:
            return CommandResult(content=f"未找到技能：`{name}`", success=False)

        if skill.source == SkillSource.BUILTIN:
            return CommandResult(
                content=f"禁止删除内置技能：`{name}`",
                success=False,
            )

        import shutil

        try:
            shutil.rmtree(skill.skill_dir)
            registry.load(force=True)  # 重新加载
            content = f"✅ 已删除技能：`{name}`（目录：{skill.skill_dir}）"
        except Exception as exc:
            content = f"删除失败：{exc}"
            return CommandResult(content=content, success=False)

        return CommandResult(content=content)

    # ─── /skill edit <name> ─────────────────────────────────────────

    async def _edit(self, args: dict) -> CommandResult:
        """编辑指定技能内容（stub — 完整编辑在 M8 实现）"""
        name = args.get("<name>", "").strip()
        if not name:
            return CommandResult(content="用法：`/skill edit <name>`", success=False)

        registry = _get_registry()
        skill = registry.get(name)

        if skill is None:
            return CommandResult(content=f"未找到技能：`{name}`", success=False)

        return CommandResult(
            content=(
                f"**/skill edit {name}**\n\n"
                f"技能文件位置：`{skill.path}`\n\n"
                "请直接用编辑器打开此文件进行修改。\n\n"
                "修改完成后自动生效，无需重启。"
            ),
        )

    # ─── /skill check ──────────────────────────────────────────────

    async def _check(self, _args: dict) -> CommandResult:
        """检查所有技能的依赖是否满足"""
        checker = SkillChecker()
        report = checker.check_all_and_report()
        return CommandResult(content=report)

    # ─── /skill install <file> ──────────────────────────────────────

    async def _install(self, args: dict) -> CommandResult:
        """从 .skill 包文件安装技能"""
        file_path = args.get("<file>", "").strip()
        if not file_path:
            return CommandResult(content="用法：`/skill install <file>`", success=False)

        pkg_path = Path(file_path).expanduser()
        if not pkg_path.exists():
            return CommandResult(content=f"文件不存在：`{pkg_path}`", success=False)

        creator = SkillCreator()
        packager = SkillPackager()

        try:
            dest_dir = creator.get_user_skills_dir()
            dest_dir.mkdir(parents=True, exist_ok=True)
            skill_dir = packager.extract(pkg_path, dest_dir)
            registry = _get_registry()
            registry.load(force=True)
            content = (
                f"✅ 已安装技能：`{skill_dir.name}`\n\n"
                f"位置：`{skill_dir}`\n\n"
                f"使用 `/skill info {skill_dir.name}` 查看详情。"
            )
        except Exception as exc:
            content = f"安装失败：{exc}"
            return CommandResult(content=content, success=False)

        return CommandResult(content=content)

    # ─── /skill search <query> ───────────────────────────────────────

    async def _search(self, args: dict) -> CommandResult:
        """搜索相关技能"""
        query = args.get("<query>", "").strip()
        if not query:
            return CommandResult(content="用法：`/skill search <关键词>`", success=False)

        searcher = SkillSearcher()
        results = searcher.search(query, top_k=10)

        if not results:
            content = (
                f"**搜索**: {query}\n\n"
                "未找到相关技能。使用 `/skill create` 创建新技能。"
            )
        else:
            lines = [
                f"**搜索**: {query}",
                f"**结果**: {len(results)} 个\n",
            ]
            for r in results:
                registry = _get_registry()
                skill = registry.get(r.skill_name)
                if skill:
                    emoji = f"{skill.emoji} " if skill.emoji else ""
                    lines.append(f"### {emoji}{skill.name}（匹配度: {r.score:.2f}）")
                    lines.append(f"{skill.description[:100]}")
                    lines.append("")

            content = "\n".join(lines)

        return CommandResult(content=content)

    # ─── Usage ─────────────────────────────────────────────────────

    def _usage(self) -> str:
        return """**/skill** — 技能管理命令

## 用法
```
/skill list             — 列出所有可用技能
/skill search <关键词>   — 搜索相关技能
/skill info <name>      — 查看技能详情
/skill create           — 创建新技能（stub）
/skill edit <name>      — 编辑技能文件
/skill delete <name>    — 删除用户/项目级技能
/skill check            — 检查所有技能的依赖
/skill install <file>   — 从 .skill 包安装
```

## 技能来源
- **工作区** `.auton/skills/` — 当前目录
- **项目** `.auton/skills/` — 项目根目录
- **用户** `~/.auton/skills/` — 用户级（skill-creator 默认写入此处）
- **内置** `src/auton/skills/builtin/` — Auton 内置

## 内置技能
- `skill-creator` — 创建新技能
- `github` — GitHub 操作（gh CLI）
- `git-workflow` — 标准化 Git 工作流
- `web-search` — 网页搜索
- `code-review` — 代码审查

## 创建 .skill 包
skill 目录本质是 zip 压缩包（.skill 后缀），便于分享和分发。
"""
