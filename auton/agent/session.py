"""Agent Session — 会话管理

Session 管理一个完整的对话会话：
  - 消息历史（List[Message]）
  - 步骤计数
  - 上下文 token 统计
  - compact 压缩逻辑
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Sequence

from loguru import logger

from .message import Message
from .types import SessionMeta, SessionStatus
from .token_utils import estimate_tokens_from_messages

if TYPE_CHECKING:
    pass


@dataclass
class Session:
    """会话对象"""
    meta: SessionMeta
    messages: list[Message] = field(default_factory=list)
    status: SessionStatus = "idle"
    _token_count: int = 0
    _logger = logger.bind(name="Session")

    @classmethod
    def create(
        cls,
        *,
        project_path: str | None = None,
        session_id: str | None = None,
    ) -> "Session":
        """创建新会话"""
        now = datetime.now()
        return cls(
            meta=SessionMeta(
                session_id=session_id or str(uuid.uuid4()),
                created_at=now,
                updated_at=now,
                project_path=project_path,
            ),
            messages=[],
        )

    # ─── 消息管理 ────────────────────────────────────────────────────────

    def add_user_message(self, content: str) -> Message:
        """添加用户消息"""
        msg = Message(role="user")
        msg.add_text(content)
        self.messages.append(msg)
        self._touch()
        return msg

    def add_assistant_message(self) -> Message:
        """添加空的助手消息（等待 LLM 填充）"""
        msg = Message(role="assistant")
        self.messages.append(msg)
        return msg

    def last_assistant_message(self) -> Message | None:
        """获取最后一个 assistant message"""
        for msg in reversed(self.messages):
            if msg.role == "assistant":
                return msg
        return None

    def update_status(self, status: SessionStatus, reason: str = "") -> None:
        self.status = status
        self._logger.info("session={id} status={status} reason={reason}",
                          id=self.meta.session_id, status=status, reason=reason)

    # ─── Compact ────────────────────────────────────────────────────────────

    def compact(
        self,
        *,
        protect_turns: int = 2,
        recent_token_budget: int = 40_000,
        min_tail_messages: int = 2,
    ) -> "CompactResult":
        """上下文压缩：保留首条 + 最近 k 轮，其余转成摘要"""
        total = len(self.messages)
        if total <= 2:
            return CompactResult()

        # 已存在的历史压缩摘要属于稳定前缀，不应被再次压成“摘要的摘要”。
        stable_prefix_end = 1
        while stable_prefix_end < total:
            msg = self.messages[stable_prefix_end]
            text = msg.get_text().strip()
            if msg.role == "system" and text.startswith("[历史压缩]"):
                stable_prefix_end += 1
                continue
            break

        compressible_total = total - stable_prefix_end
        if compressible_total <= 1:
            return CompactResult()

        turn_starts = self._real_user_turn_starts(self.messages, start=stable_prefix_end)
        preserved_turns = min(protect_turns, len(turn_starts)) if turn_starts else 0

        if preserved_turns > 0:
            tail_start = turn_starts[-preserved_turns]
        else:
            tail_start = max(stable_prefix_end + 1, total - min_tail_messages)

        recent_tokens = self._estimate_tokens(self.messages[tail_start:])
        while tail_start > stable_prefix_end and recent_tokens > recent_token_budget:
            if preserved_turns > 1:
                preserved_turns -= 1
                tail_start = turn_starts[-preserved_turns]
            elif self._contains_internal_user_messages(self.messages[tail_start:]):
                break
            else:
                tail_start = min(total - 1, tail_start + 1)
            recent_tokens = self._estimate_tokens(self.messages[tail_start:])

        middle = self.messages[stable_prefix_end:tail_start]
        if not middle:
            return CompactResult()

        summary_lines: list[str] = []
        for msg in middle:
            text = msg.get_text()
            if text:
                if msg.role == "system" and text.strip().startswith("[历史压缩]"):
                    continue
                summary_lines.append(f"[{msg.role}] {text[:120]}")
        summary_text = (
            f"[历史压缩] 合并 {len(middle)} 条消息，保留关键信息：\n- "
            + "\n- ".join(summary_lines[:6])
        )

        summary_msg = Message(role="system")
        summary_msg.add_text(summary_text)

        kept_head = self.messages[:stable_prefix_end]
        kept_tail = self.messages[tail_start:]
        self.messages = kept_head + [summary_msg] + kept_tail

        self.meta.compaction_count += 1
        self._touch()
        self._logger.info(
            "compact session={id} compacted={n} protect={p}",
            id=self.meta.session_id,
            n=len(middle),
            p=protect_turns,
        )

        return CompactResult(
            compacted_count=len(middle),
            summary_text=summary_text,
            compressed_message_ids=[m.message_id for m in middle],
            summary_message_id=summary_msg.message_id,
        )

    def should_compact(self, threshold: int = 150_000) -> bool:
        """判断是否需要压缩（token 接近上限）"""
        return self._token_count >= threshold

    def update_token_count(self, count: int) -> None:
        self._token_count = count

    # ─── 工具 ──────────────────────────────────────────────────────────────

    def _touch(self) -> None:
        """更新 updated_at"""
        self.meta.updated_at = datetime.now()

    def to_summary_dict(self) -> dict:
        """会话摘要（用于写入 index）"""
        return {
            "session_id": self.meta.session_id,
            "started_at": self.meta.created_at.isoformat(),
            "ended_at": self.meta.updated_at.isoformat(),
            "compaction_count": self.meta.compaction_count,
            "message_count": len(self.messages),
        }

    @staticmethod
    def _estimate_tokens(messages: Sequence[Message]) -> int:
        return estimate_tokens_from_messages(messages)

    @staticmethod
    def _real_user_turn_starts(messages: Sequence[Message], *, start: int = 0) -> list[int]:
        """返回真实用户轮次的起点索引。

        工具结果与命令结果虽然以 user message 形式写入 session，但它们属于
        内部续上下文消息，不能被当作新的“用户轮次”边界，否则 compact 会把
        最近一轮工具交互拆断。
        """
        starts: list[int] = []
        for idx in range(start, len(messages)):
            msg = messages[idx]
            if msg.role != "user":
                continue
            text = msg.get_text().strip()
            if text.startswith("[tool:") or text.startswith("[command:"):
                continue
            starts.append(idx)
        return starts

    @staticmethod
    def _contains_internal_user_messages(messages: Sequence[Message]) -> bool:
        for msg in messages:
            if msg.role != "user":
                continue
            text = msg.get_text().strip()
            if text.startswith("[tool:") or text.startswith("[command:"):
                return True
        return False


@dataclass
class CompactResult:
    compacted_count: int = 0
    summary_text: str = ""
    compressed_message_ids: list[str] = field(default_factory=list)
    summary_message_id: str | None = None
