"""Memory MD Manager — MEMORY.md 索引管理器

负责从 SUMMARY.md 蒸馏高价值条目，写入 MEMORY.md 顶层索引。
遵循 Claude Code 的 MEMORY.md 格式（无 frontmatter）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from loguru import logger

from .types import MemoryEntry, MemoryType, SummaryBlock


class MemoryMDManager:
    """MEMORY.md 索引管理器

    职责：
      - 从 SUMMARY.md 的 block 摘要中提取高价值条目
      - 按主题聚合后写入 MEMORY.md 索引
      - 支持增量追加（不重复已有条目）
    """

    def __init__(self) -> None:
        self._logger = logger.bind(name="MemoryMDManager")

    # ─── 蒸馏逻辑 ───────────────────────────────────────────────────────

    RELEVANCE_KEYWORDS = (
        # 高价值关键词 — 命中这些词的 block 值得沉淀到 MEMORY.md
        "决策",
        "决定",
        "结论",
        "偏好",
        "规范",
        "规则",
        "约束",
        "架构",
        "方案",
        "选择",
        "修改",
        "重构",
        "bug",
        "安全",
        "配置",
        "关键",
        "重要",
        "用户要求",
        "必须",
        "禁止",
    )

    def is_high_value(self, block: SummaryBlock) -> bool:
        """判断一个 block 是否值得沉淀到 MEMORY.md"""
        summary_lower = block.summary.lower()
        return any(kw in summary_lower for kw in self.RELEVANCE_KEYWORDS)

    def distill_entry(self, block: SummaryBlock) -> str:
        """将 SummaryBlock 蒸馏为 MEMORY.md 的一条索引行

        格式：[标题](SUMMARY.md#session:block)
        """
        # 生成简短标题
        title = self._generate_title(block)
        # Markdown link 到 SUMMARY.md
        ref = f"SUMMARY.md#{block.session_id}:block_{block.index:03d}"
        line = f"- [{title}]({ref}) — {block.summary}"
        # 限制单行长度
        if len(line) > 200:
            line = line[:197] + "..."
        return line

    def _generate_title(self, block: SummaryBlock) -> str:
        """生成简短标题"""
        # 从 intent 提取
        if block.intent:
            intent = block.intent[:40]
            if len(block.intent) > 40:
                intent += "…"
            return f"{block.session_id}:{block.index:03d} — {intent}"

        # 从文件列表提取
        if block.files:
            files_str = ", ".join(Path(f).name for f in block.files[:2])
            return f"{block.session_id}:{block.index:03d} — {files_str}"

        # 从 summary 提取
        summary = block.summary[:40]
        if len(block.summary) > 40:
            summary += "…"
        return f"{block.session_id}:{block.index:03d} — {summary}"

    # ─── 批量蒸馏 ───────────────────────────────────────────────────────

    def distill_blocks(
        self,
        blocks: list[SummaryBlock],
    ) -> list[str]:
        """将 SummaryBlock 列表蒸馏为 MEMORY.md 条目列表

        Returns:
            MEMORY.md 中的一行一行字符串列表
        """
        entries = []
        for block in blocks:
            if self.is_high_value(block):
                entries.append(self.distill_entry(block))
        return entries

    def distill_summary_to_memory(
        self,
        summary_path: Path,
        memory_path: Path,
    ) -> int:
        """从 SUMMARY.md 读取所有 block，蒸馏高价值条目到 MEMORY.md

        Returns:
            新增条目数量
        """
        import re

        if not summary_path.exists():
            return 0

        summary_text = summary_path.read_text(encoding="utf-8")
        memory_text = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""

        # 解析 SUMMARY.md 中的所有 block 行
        block_lines: list[str] = []
        current_session = ""
        for line in summary_text.splitlines():
            # session 头
            m = re.match(r"## (.+\.jsonl)", line.strip())
            if m:
                current_session = m.group(1).replace(".jsonl", "")
                continue
            # block 行
            bm = re.match(r"- block_(\d+): (.*)", line.strip())
            if bm and current_session:
                block_index = int(bm.group(1))
                block_summary = bm.group(2).strip()
                block_lines.append((current_session, block_index, block_summary))

        # 读取已有 MEMORY.md 条目（去重）
        existing_refs = set()
        if memory_path.exists():
            for m in re.finditer(r"\((SUMMARY\.md#[^)]+)\)", memory_text):
                existing_refs.add(m.group(1))

        # 蒸馏
        new_entries: list[str] = []
        for session_id, block_index, block_summary in block_lines:
            ref = f"SUMMARY.md#{session_id}:block_{block_index:03d}"
            if ref in existing_refs:
                continue
            # 判断是否高价值
            if any(kw in block_summary.lower() for kw in self.RELEVANCE_KEYWORDS):
                title = f"{session_id}:{block_index:03d} — {block_summary[:60]}"
                new_entries.append(f"- [{title}]({ref}) — {block_summary}")

        if new_entries:
            with open(memory_path, "a", encoding="utf-8") as f:
                f.write("\n" + "\n".join(new_entries) + "\n")

        return len(new_entries)

    # ─── MEMORY.md 头 ────────────────────────────────────────────────────

    def ensure_header(self, memory_path: Path, context: str = "") -> None:
        """确保 MEMORY.md 有正确头部（文件不存在时）"""
        if memory_path.exists():
            return
        header = (
            "本文档是项目记忆顶层索引，"
            "详细的会话分段总结见 [SUMMARY.md](SUMMARY.md)。\n\n"
        )
        if context:
            header += context + "\n\n"
        memory_path.write_text(header, encoding="utf-8")
