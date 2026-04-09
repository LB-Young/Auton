"""Skills — injector: builds system prompt fragments with relevant skills."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from loguru import logger

from .registry import SkillRegistry
from .semantic_search import SkillSearcher, SearchResult
from .types import Skill


# 每个 skill 注入的最大 body 长度（token 估算）
MAX_SKILL_BODY_CHARS = 3000


class SkillInjector:
    """技能注入器

    根据上下文从 registry 中选取 top-k 最相关的 Skill，
    构建 system prompt 片段注入 LLM context。
    """

    # 最大注入 skill 数量
    DEFAULT_TOP_K = 5
    MAX_INJECT = 10

    def __init__(
        self,
        registry: SkillRegistry | None = None,
        searcher: SkillSearcher | None = None,
    ) -> None:
        self._registry = registry or SkillRegistry.get_instance()
        self._searcher = searcher or SkillSearcher(self._registry)
        self._logger = logger.bind(name="SkillInjector")

    def inject_for_query(
        self,
        query: str,
        cwd: Path | None = None,
        top_k: int | None = None,
    ) -> str:
        """根据 query 注入相关 skill 内容

        Returns:
            要追加到 system prompt 的字符串
        """
        results = self._searcher.search(query, top_k=top_k or self.DEFAULT_TOP_K, cwd=cwd)

        if not results:
            return ""

        parts = ["## Relevant Skills\n"]
        for result in results:
            skill = self._registry.get(result.skill_name)
            if skill is None:
                continue
            parts.append(self._format_skill(skill, result))
            parts.append("")

        return "\n".join(parts).strip()

    def inject_for_names(
        self,
        names: list[str],
        cwd: Path | None = None,
    ) -> str:
        """按名称注入指定 skill（用于 /skill info 或显式触发）"""
        self._registry.ensure_loaded()
        parts = ["## Activated Skills\n"]

        for name in names:
            skill = self._registry.get(name)
            if skill is None:
                parts.append(f"> Skill `{name}` not found.\n")
                continue
            result = SearchResult(skill_name=name, score=1.0, match_type="name", matched_text="")
            parts.append(self._format_skill(skill, result))
            parts.append("")

        return "\n".join(parts).strip()

    def _format_skill(self, skill: Skill, result: SearchResult) -> str:
        """将单个 skill 格式化为 system prompt 片段"""
        lines = [
            f"### Skill: {skill.name}",
            f"**Source**: {skill.source.value}",
            "",
        ]

        # 注入 body（截断超长内容）
        body = skill.body
        if len(body) > MAX_SKILL_BODY_CHARS:
            body = body[:MAX_SKILL_BODY_CHARS] + "\n\n_(truncated)_"

        lines.append(body)
        lines.append("")

        # experiences（如果开启）
        if skill.load_experiences and skill.has_experiences:
            experiences = skill.get_experiences()
            if experiences:
                lines.append("**Experiences** (lessons learned):")
                # experiences 可能很长，只取前 500 字
                if len(experiences) > 500:
                    experiences = experiences[:500] + "\n_(truncated)_"
                lines.append(experiences)
                lines.append("")

        return "\n".join(lines)

    def get_skill_metadata_for_system(self, skill_names: list[str]) -> str:
        """仅为 system prompt 生成轻量元数据（description 列表）

        用于 LLM 判断自己是否应该调用某个 skill（不注入完整内容）
        """
        self._registry.ensure_loaded()
        lines = ["## Available Skills\n"]

        for name in skill_names:
            skill = self._registry.get(name)
            if skill:
                emoji = f"{skill.emoji} " if skill.emoji else ""
                lines.append(f"- **{emoji}{skill.name}**: {skill.description}")

        return "\n".join(lines)
