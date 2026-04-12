"""Skills — loader: scans all skill paths and builds a registry."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterator

from loguru import logger

from .frontmatter import parse_skill_file, FrontmatterError
from .types import Skill, SkillSource


class SkillLoader:
    """从多个路径扫描 Skill 并解析"""

    SKILL_FILE = "SKILL.md"

    def __init__(self) -> None:
        self._logger = logger.bind(name="SkillLoader")

    # ─── 技能路径解析 ───────────────────────────────────────────────

    def get_skill_paths(self, cwd: Path | None = None) -> dict[SkillSource, list[Path]]:
        """返回各来源的 skill 目录列表

        Returns:
            {source: [dir_paths]}
        """
        import auton

        if cwd is None:
            cwd = Path.cwd()

        home = Path.home()

        return {
            SkillSource.WORKSPACE: self._find_skill_dirs(cwd),  # 当前工作目录
            SkillSource.PROJECT: self._find_skill_dirs(cwd),  # 项目根（与 workspace 相同，待 find_project_root）
            SkillSource.USER: [home / ".auton" / "skill"],
            SkillSource.BUILTIN: [Path(auton.__file__).parent / "skills" / "builtin"],
        }

    def _find_skill_dirs(self, start: Path) -> list[Path]:
        """从 start 向上查找所有 .auton/skill/ 目录"""
        dirs: list[Path] = []
        for parent in [start] + list(start.parents):
            skills_dir = parent / ".auton" / "skill"
            if skills_dir.exists() and skills_dir.is_dir():
                dirs.append(skills_dir)
        return dirs

    # ─── 扫描 ──────────────────────────────────────────────────────

    def scan_skill_dirs(
        self,
        cwd: Path | None = None,
    ) -> dict[SkillSource, list[Skill]]:
        """扫描所有路径，返回所有已解析的 Skill，按来源分组

        Returns:
            {source: [Skill]}
        """
        paths_by_source = self.get_skill_paths(cwd)
        result: dict[SkillSource, list[Skill]] = {
            src: [] for src in SkillSource
        }

        for source, dirs in paths_by_source.items():
            for base_dir in dirs:
                if not base_dir.exists():
                    continue
                for skill_dir in base_dir.iterdir():
                    if not skill_dir.is_dir():
                        continue
                    skill_file = skill_dir / self.SKILL_FILE
                    if not skill_file.exists():
                        continue
                    try:
                        skill = self._load_skill(skill_file, source)
                        result[source].append(skill)
                    except FrontmatterError as exc:
                        self._logger.warning(
                            "skip skill {d}: {e}",
                            d=skill_dir.name,
                            e=exc,
                        )
                    except Exception as exc:
                        self._logger.warning(
                            "error loading {d}: {e}",
                            d=skill_dir.name,
                            e=exc,
                        )

        return result

    def iter_all_skills(self, cwd: Path | None = None) -> Iterator[Skill]:
        """迭代所有扫描到的 Skill"""
        by_source = self.scan_skill_dirs(cwd)
        for source, skills in by_source.items():
            for skill in skills:
                yield skill

    # ─── 加载单个 ──────────────────────────────────────────────────

    def _load_skill(self, skill_file: Path, source: SkillSource) -> Skill:
        """解析一个 SKILL.md 文件"""
        fm, body = parse_skill_file(skill_file)

        return Skill(
            name=fm.name,
            description=fm.description,
            body=body,
            source=source,
            path=skill_file,
            disable_model_invocation=fm.disable_model_invocation,
            user_invocable=fm.user_invocable,
            load_experiences=fm.load_experiences,
            emoji=fm.metadata.emoji,
            required_bins=fm.metadata.requires.get("bins", []),
        )

    def load_skill(self, name: str, cwd: Path | None = None) -> Skill | None:
        """按名称加载单个 Skill（从所有来源）"""
        by_source = self.scan_skill_dirs(cwd)

        # 按优先级遍历（workspace > project > user > builtin）
        import auton

        if cwd is None:
            cwd = Path.cwd()

        # 收集所有同名 skill，取最高优先级
        candidates: list[tuple[int, Skill]] = []  # (priority, skill)

        for source, skills in by_source.items():
            for skill in skills:
                if skill.name == name:
                    priority = self._get_priority(source, cwd)
                    candidates.append((priority, skill))

        if not candidates:
            return None

        # 取优先级最高的
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def _get_priority(self, source: SkillSource, cwd: Path) -> int:
        """获取技能优先级（数字越小优先级越高）"""
        from .types import SKILL_SOURCE_PRIORITY

        base = SKILL_SOURCE_PRIORITY[source]
        # workspace 和 project 的优先级根据是否与 cwd 匹配来区分
        if source in (SkillSource.WORKSPACE, SkillSource.PROJECT):
            project_root = self._find_project_root(cwd)
            if project_root and (cwd == project_root or project_root in cwd.parents):
                return base
            elif source == SkillSource.WORKSPACE:
                return base
            else:
                return base + 10  # 降权
        return base

    def _find_project_root(self, cwd: Path) -> Path | None:
        """查找项目根目录"""
        for parent in [cwd] + list(cwd.parents):
            if (parent / ".auton").exists():
                return parent
        return None
