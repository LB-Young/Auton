"""Session Summarizer — 会话摘要生成器

将 append-only jsonl 转换为分 block 的详细摘要（SUMMARY.md），
再进一步蒸馏为 MEMORY.md 索引条目。

存储与检索分离原则：
  - SessionStore 只管 append jsonl
  - SessionSummarizer 只管读 jsonl，生成分段摘要
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from loguru import logger

from .types import SummaryBlock


@dataclass
class Block:
    """从 jsonl 中提取的一个逻辑 block"""

    index: int  # 序号（从 1 开始）
    messages: list[dict]  # 该 block 的原始消息
    user_intent: str = ""  # 用户意图（从 user-message 提取）
    agent_decisions: list[str] = field(default_factory=list)  # 关键决策
    involved_files: list[str] = field(default_factory=list)  # 涉及文件
    key_conclusions: list[str] = field(default_factory=list)  # 关键结论
    pending_todos: list[str] = field(default_factory=list)  # 待跟进

    def to_summary_block(self, session_id: str) -> SummaryBlock:
        parts = []

        # 主要总结
        if self.user_intent:
            parts.append(f"用户请求：{self.user_intent}。")
        if self.key_conclusions:
            parts.append(f"结论：{'；'.join(self.key_conclusions)}。")
        if self.agent_decisions:
            parts.append(f"决策：{'；'.join(self.agent_decisions)}。")
        if self.involved_files:
            parts.append(f"涉及文件：{', '.join(self.involved_files)}。")
        if self.pending_todos:
            parts.append(f"待跟进：{'；'.join(self.pending_todos)}。")

        summary = "".join(parts) if parts else "对话块，无显著结论。"

        return SummaryBlock(
            session_id=session_id,
            block_index=self.index,
            summary=summary,
            intent=self.user_intent,
            files=self.involved_files,
            decisions=self.agent_decisions,
            todos=self.pending_todos,
        )


class SessionSummarizer:
    """会话摘要生成器

    读取 jsonl，识别 block 边界，生成分 block 的详细摘要。
    """

    def __init__(self) -> None:
        self._logger = logger.bind(name="SessionSummarizer")

    # ─── Block 识别策略 ─────────────────────────────────────────────────

    BLOCK_MARKERS = (
        "user-message",  # 新的用户消息 → 新的 block
        "compact",  # 压缩事件 → 新 block
    )

    def split_blocks(self, events: list[dict]) -> list[Block]:
        """将事件流拆分为逻辑 block

        规则：
          - 每个 user-message 开始一个新 block
          - compact 事件开始一个新 block
          - 一个 block 内包含：user-message + 后续所有 assistant/tool 事件
        """
        blocks: list[Block] = []
        current: list[dict] = []
        block_index = 0

        for event in events:
            ev_type = event.get("type", "")

            if ev_type in self.BLOCK_MARKERS:
                if current:
                    # 保存当前 block
                    block_index += 1
                    blocks.append(self._build_block(block_index, current))
                    current = []

            current.append(event)

        # 最后一块
        if current:
            block_index += 1
            blocks.append(self._build_block(block_index, current))

        return blocks

    def _build_block(self, index: int, messages: list[dict]) -> Block:
        """从消息列表构建 Block"""
        block = Block(index=index, messages=messages)

        for msg in messages:
            ev_type = msg.get("type", "")
            content = msg.get("content", "")

            if ev_type == "user-message" and not block.user_intent:
                block.user_intent = self._extract_intent(content)

            elif ev_type == "assistant":
                # 从 assistant 消息提取关键决策
                text = self._extract_text_from_assistant(msg)
                if text:
                    decisions = self._extract_decisions(text)
                    block.agent_decisions.extend(decisions)
                    conclusions = self._extract_conclusions(text)
                    block.key_conclusions.extend(conclusions)

            elif ev_type in ("tool-call", "tool_use"):
                # 记录涉及的文件
                tool = msg.get("tool", msg.get("name", ""))
                file_match = msg.get("tool_input", {})
                if isinstance(file_match, dict):
                    path = file_match.get("path", file_match.get("file", ""))
                    if path and isinstance(path, str):
                        block.involved_files.append(path)

        return block

    def _extract_intent(self, text: str) -> str:
        """从用户消息中提取意图（简短摘要）"""
        text = text.strip()
        if len(text) > 100:
            return text[:100] + "…"
        return text

    def _extract_text_from_assistant(self, msg: dict) -> str:
        """从 assistant 消息提取文本内容"""
        if isinstance(msg.get("content"), str):
            return msg["content"]
        parts = msg.get("parts", [])
        text_parts = []
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("content", ""))
            elif isinstance(part, dict) and part.get("type") == "reasoning":
                # 跳过思考过程
                pass
        return " ".join(text_parts)

    def _extract_decisions(self, text: str) -> list[str]:
        """从文本中提取决策性语句"""
        decisions = []
        patterns = [
            r"决定\s*[：:]\s*([^\n。]+)",
            r"采用\s*([^\n。]+)\s*方案",
            r"选择\s*([^\n。]+)\s*方案",
            r"修改为\s*([^\n。]+)",
        ]
        for pat in patterns:
            for m in re.finditer(pat, text):
                decisions.append(m.group(1).strip())
        return decisions[:3]  # 最多 3 条

    def _extract_conclusions(self, text: str) -> list[str]:
        """从文本中提取结论性语句"""
        conclusions = []
        patterns = [
            r"因此\s*([^\n。]+)",
            r"最终\s*([^\n。]+)",
            r"总结\s*[：:]\s*([^\n。]+)",
            r"得到\s*([^\n。]+)",
        ]
        for pat in patterns:
            for m in re.finditer(pat, text):
                conclusions.append(m.group(1).strip())
        return conclusions[:3]

    # ─── 摘要生成 ───────────────────────────────────────────────────────

    def summarize_session(
        self,
        events: list[dict],
        session_id: str,
    ) -> list[SummaryBlock]:
        """读取 jsonl 事件列表，返回所有 block 的摘要

        Args:
            events: read_session() 返回的事件列表
            session_id: session ID（用于引用）

        Returns:
            按 block 序号排列的 SummaryBlock 列表
        """
        blocks = self.split_blocks(events)
        return [b.to_summary_block(session_id) for b in blocks]

    def summarize_to_markdown(
        self,
        events: list[dict],
        session_id: str,
        title: str | None = None,
    ) -> str:
        """将 session 事件直接生成为 SUMMARY.md 格式的 Markdown

        Args:
            events: jsonl 事件列表
            session_id: session ID
            title: 可选的标题
        """
        blocks = self.summarize_session(events, session_id)
        if not blocks:
            return ""

        lines = [f"## {session_id}.jsonl"]
        for block in blocks:
            lines.append(block.to_line())

        return "\n".join(lines)

    # ─── 从 SessionStore 读取并摘要 ──────────────────────────────────────

    def summarize_from_store(
        self,
        base_dir: Path,
        session_id: str,
    ) -> list[SummaryBlock]:
        """从 session jsonl 文件读取并摘要

        Args:
            base_dir: session jsonl 所在目录
            session_id: session ID
        """
        jsonl_path = base_dir / f"{session_id}.jsonl"
        if not jsonl_path.exists():
            return []
        events = []
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
        return self.summarize_session(events, session_id)
