"""Skills — registry: global singleton skill registry with name-based lookup."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from loguru import logger

from .loader import SkillLoader
from .types import Skill, SkillSource


class SkillRegistry:
    """全局技能注册表（单例）

    提供：
      - 全量列表
      - 按名称查找
      - 按来源过滤
      - 重新加载
    """

    _instance: "SkillRegistry | None" = None

    def __init__(
        self,
        loader: SkillLoader | None = None,
        cwd: Path | None = None,
    ) -> None:
        self._loader = loader or SkillLoader()
        self._cwd = cwd or Path.cwd()
        self._skills: dict[str, Skill] = {}  # name -> Skill（最高优先级）
        self._all_skills: list[Skill] = []  # 所有 skill（含同名不同来源）
        self._by_source: dict[SkillSource, list[Skill]] = {s: [] for s in SkillSource}
        self._logger = logger.bind(name="SkillRegistry")
        self._loaded = False

    @classmethod
    def get_instance(cls, cwd: Path | None = None) -> "SkillRegistry":
        """获取全局单例"""
        if cls._instance is None:
            cls._instance = cls(cwd=cwd)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（测试用）"""
        cls._instance = None

    # ─── 加载 ──────────────────────────────────────────────────────

    def load(self, force: bool = False) -> None:
        """扫描所有来源，构建注册表"""
        if self._loaded and not force:
            return

        self._skills.clear()
        self._all_skills.clear()
        for src in SkillSource:
            self._by_source[src].clear()

        by_source = self._loader.scan_skill_dirs(self._cwd)
        for source, skills in by_source.items():
            for skill in skills:
                self._all_skills.append(skill)
                self._by_source[source].append(skill)
                # 同名 skill，高优先级覆盖低优先级
                if skill.name not in self._skills:
                    self._skills[skill.name] = skill
                else:
                    existing = self._skills[skill.name]
                    if SKILL_SOURCE_PRIORITY[source] < SKILL_SOURCE_PRIORITY[existing.source]:
                        self._skills[skill.name] = skill

        self._loaded = True
        self._logger.info(
            "loaded {n} skills: {s}",
            n=len(self._skills),
            s=", ".join(sorted(self._skills.keys())),
        )

    def ensure_loaded(self) -> None:
        """懒加载"""
        self.load()

    # ─── 查询 ──────────────────────────────────────────────────────

    def get(self, name: str) -> Skill | None:
        """按名称获取 Skill"""
        self.ensure_loaded()
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        """列出所有 Skill（含同名覆盖后版本）"""
        self.ensure_loaded()
        return sorted(self._all_skills, key=lambda s: SKILL_SOURCE_PRIORITY[s.source])

    def list_by_source(self, source: SkillSource) -> list[Skill]:
        """按来源列出 Skill"""
        self.ensure_loaded()
        return sorted(self._by_source[source], key=lambda s: s.name)

    def list_user_invocable(self) -> list[Skill]:
        """列出允许用户手动触发的 Skill"""
        self.ensure_loaded()
        return [s for s in self._all_skills if s.user_invocable]

    def __len__(self) -> int:
        self.ensure_loaded()
        return len(self._skills)

    def __iter__(self) -> Iterator[Skill]:
        self.ensure_loaded()
        return iter(sorted(self._skills.values(), key=lambda s: s.name))

    def __repr__(self) -> str:
        self.ensure_loaded()
        names = sorted(self._skills.keys())
        return f"SkillRegistry({len(self._skills)} skills: {', '.join(names)})"


# 全局优先级映射
from .types import SKILL_SOURCE_PRIORITY  # noqa: E402, F401
