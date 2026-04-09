"""Skills — semantic search (embedding-based skill retrieval).

当前实现：基于关键词的轻量检索。
M7 升级为 ChromaDB 向量检索。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from .registry import SkillRegistry


@dataclass
class SearchResult:
    """检索结果"""

    skill_name: str
    score: float  # 0.0–1.0，越高越相关
    match_type: str  # "keyword" / "name" / "description"
    matched_text: str  # 命中的文本片段


class SkillSearcher:
    """技能语义检索器

    当前：关键词匹配（M7 升级为向量检索）
    """

    # 高权重关键词（命中得更高分）
    HIGH_WEIGHT_KEYWORDS = (
        "create",
        "build",
        "new",
        "add",
        "delete",
        "remove",
        "list",
        "show",
        "get",
        "update",
        "edit",
        "modify",
        "check",
        "run",
        "execute",
        "deploy",
        "test",
        "review",
        "search",
        "fetch",
        "api",
        "git",
        "github",
        "db",
        "database",
        "sql",
        "debug",
        "fix",
        "error",
    )

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self._registry = registry or SkillRegistry.get_instance()
        self._logger = logger.bind(name="SkillSearcher")

    def search(
        self,
        query: str,
        top_k: int = 5,
        cwd: Path | None = None,
    ) -> list[SearchResult]:
        """根据 query 检索最相关的 Skill

        Args:
            query: 用户输入（或 system prompt 片段）
            top_k: 返回 top-k 结果
            cwd: 当前工作目录

        Returns:
            按 score 降序排列的 SearchResult 列表
        """
        if cwd is not None:
            self._registry = SkillRegistry.get_instance(cwd=cwd)

        self._registry.ensure_loaded()
        query_lower = query.lower()
        query_words = set(query_lower.split())

        results: list[SearchResult] = []

        for skill in self._registry.list_all():
            score, match_type, matched = self._compute_score(skill, query_lower, query_words)
            if score > 0:
                results.append(
                    SearchResult(
                        skill_name=skill.name,
                        score=score,
                        match_type=match_type,
                        matched_text=matched[:100],
                    )
                )

        # 按 score 降序
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def _compute_score(
        self,
        skill,
        query_lower: str,
        query_words: set[str],
    ) -> tuple[float, str, str]:
        """计算单条 skill 的相关性分数"""
        score = 0.0
        match_type = ""
        matched = ""

        # 1. 名称精确匹配（最高）
        if skill.name.replace("-", " ") in query_lower.replace("-", " "):
            score = max(score, 0.9)
            match_type = "name"
            matched = skill.name

        # 2. 名称包含 query 词
        name_words = set(skill.name.replace("-", " ").split())
        overlap = query_words & name_words
        if overlap:
            score = max(score, 0.7 + 0.05 * len(overlap))
            match_type = "name"
            matched = skill.name

        # 3. description 关键词匹配
        desc_lower = skill.description.lower()
        desc_words = set(desc_lower.split())

        # 高权重关键词命中
        for kw in self.HIGH_WEIGHT_KEYWORDS:
            if kw in desc_lower and kw in query_lower:
                score = max(score, 0.5)
                match_type = "keyword"
                matched = kw

        # 一般关键词重叠
        desc_overlap = query_words & desc_words
        if desc_overlap:
            # 重叠越多分越高
            overlap_score = min(0.6, 0.3 + 0.05 * len(desc_overlap))
            if score < overlap_score:
                score = overlap_score
                match_type = "description"
                matched = " ".join(sorted(desc_overlap))

        return score, match_type, matched

    def search_by_names(self, names: list[str]) -> list[SearchResult]:
        """按名称列表精确查找（用于 /skill info）"""
        self._registry.ensure_loaded()
        results = []
        for name in names:
            skill = self._registry.get(name)
            if skill:
                results.append(
                    SearchResult(
                        skill_name=skill.name,
                        score=1.0,
                        match_type="name",
                        matched_text=skill.description[:80],
                    )
                )
        return results
