"""Conflict Resolver — 记忆冲突管理

处理 auton.md 写入时的冲突检测与裁决。
"""

from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass
from pathlib import Path

from loguru import logger


@dataclass
class Conflict:
    """检测到的冲突"""

    section: str
    reason: str  # 冲突原因描述
    existing_source: str  # 已有内容的来源
    existing_fingerprint: str  # 已有内容指纹
    new_fingerprint: str  # 新内容指纹


class ConflictResolver:
    """记忆冲突检测器

    检测策略：
      - 相同 section + 相同语义 → 静默跳过（避免重复）
      - 相同 section + 语义矛盾 → 标记冲突，保留双方
      - 不同 section → 正常追加
    """

    CONFLICT_INDICATORS = (
        "不要",
        "禁止",
        "never",
        "do not",
        "must not",
        "不可",
        "不允许",
        "不应",
    )

    AGREEMENT_INDICATORS = (
        "应该",
        "可以",
        "推荐",
        "偏好",
        "喜欢",
        "should",
        "may",
        "prefer",
        "like",
    )

    def __init__(self) -> None:
        self._logger = logger.bind(name="ConflictResolver")

    # ─── 语义指纹 ─────────────────────────────────────────────────────

    def fingerprint(self, content: str) -> str:
        """计算内容的语义指纹（归一化后 SHA256）"""
        normalized = self._normalize(content)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _normalize(self, text: str) -> str:
        """归一化文本（去空白、转小写、排序）"""
        # 提取关键词
        words = re.findall(r"\b\w+\b", text.lower())
        words.sort()
        return " ".join(words)

    # ─── 冲突检测 ──────────────────────────────────────────────────────

    def detect_conflict(
        self,
        section: str,
        new_content: str,
        existing_entries: list,
    ) -> Conflict | None:
        """检测新内容与已有条目的冲突

        Args:
            section: 目标节名
            new_content: 拟写入的新内容
            existing_entries: 从 parse_file() 返回的已有条目列表

        Returns:
            Conflict 对象如果有冲突，None 如果无冲突
        """
        # 找同 section 的已有条目
        existing = [e for e in existing_entries if e.section == section]
        if not existing:
            return None

        new_fp = self.fingerprint(new_content)

        for entry in existing:
            existing_fp = self.fingerprint(entry.content)

            if new_fp == existing_fp:
                # 完全相同，静默跳过（调用方处理）
                return Conflict(
                    section=section,
                    reason="identical_content",
                    existing_source=str(entry.source),
                    existing_fingerprint=existing_fp,
                    new_fingerprint=new_fp,
                )

            # 语义矛盾检测
            if self._is_contradictory(new_content, entry.content):
                return Conflict(
                    section=section,
                    reason=self._contradiction_reason(new_content, entry.content),
                    existing_source=str(entry.source),
                    existing_fingerprint=existing_fp,
                    new_fingerprint=new_fp,
                )

        return None

    def _is_contradictory(self, a: str, b: str) -> bool:
        """判断两条内容是否语义矛盾"""
        a_lower = a.lower()
        b_lower = b.lower()

        # 检查 a 中的禁止词是否在 b 中被允许
        for indicator in self.CONFLICT_INDICATORS:
            if indicator in a_lower:
                # 检查 b 中是否有相反的表述
                for agree in self.AGREEMENT_INDICATORS:
                    if agree in b_lower:
                        return True

        # 简单关键词冲突检测
        a_keyword = set(re.findall(r"\b\w{4,}\b", a_lower))
        b_keyword = set(re.findall(r"\b\w{4,}\b", b_lower))
        overlap = a_keyword & b_keyword
        if len(overlap) >= 3:
            # 有重叠关键词，但语义指纹不同，说明有差异
            # 检查是否存在矛盾指示词
            a_has_neg = any(ind in a_lower for ind in self.CONFLICT_INDICATORS)
            b_has_neg = any(ind in b_lower for ind in self.CONFLICT_INDICATORS)
            if a_has_neg != b_has_neg:
                return True

        return False

    def _contradiction_reason(self, new: str, existing: str) -> str:
        """生成冲突原因描述"""
        new_neg = any(ind in new.lower() for ind in self.CONFLICT_INDICATORS)
        existing_neg = any(ind in existing.lower() for ind in self.CONFLICT_INDICATORS)
        if new_neg and not existing_neg:
            return "new_forbids_existing_allows"
        if existing_neg and not new_neg:
            return "existing_forbids_new_allows"
        return "semantic_contradiction"

    # ─── 冲突解决策略 ──────────────────────────────────────────────────

    def resolve(
        self,
        conflict: Conflict,
        priority: Literal["high", "low"] = "high",
    ) -> str:
        """解决冲突，返回最终内容

        Args:
            conflict: 检测到的冲突
            priority: 高优先级内容覆盖低优先级内容

        Returns:
            解决后的内容（可能包含冲突标记）
        """
        if conflict.reason == "identical_content":
            return ""  # 静默跳过

        # 语义矛盾：保留双方，追加冲突标记
        resolution = (
            f"<!-- conflict_detected: {conflict.reason} -->\n"
            f"<!-- existing_source: {conflict.existing_source} -->\n"
            f"<!-- resolution: {priority}_priority_applied -->\n"
        )
        return resolution

    # ─── 去重 ─────────────────────────────────────────────────────────

    def deduplicate(self, entries: list[str]) -> list[str]:
        """对条目列表去重（基于语义指纹）"""
        seen: set[str] = set()
        result: list[str] = []
        for entry in entries:
            fp = self.fingerprint(entry)
            if fp not in seen:
                seen.add(fp)
                result.append(entry)
        return result
