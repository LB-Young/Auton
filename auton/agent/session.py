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
from typing import TYPE_CHECKING

from loguru import logger

from .message import Message
from .types import SessionMeta, SessionStatus

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

    def compact(self) -> int:
        """上下文压缩：保留首尾消息，中间消息压缩为摘要

        Returns:
            被压缩的消息数量
        """
        if len(self.messages) <= 2:
            return 0

        # 保留首尾消息，中间压缩为摘要
        kept = [self.messages[0], self.messages[-1]]
        compacted_count = len(self.messages) - 2

        # 构建压缩摘要消息
        summary_parts = []
        for msg in self.messages[1:-1]:
            text = msg.get_text()
            if text:
                summary_parts.append(f"[{msg.role}]: {text[:100]}...")

        summary_msg = Message(role="system")
        summary_msg.add_text(
            f"[Compacted {compacted_count} messages: "
            + "; ".join(summary_parts[:5])
            + "]"
        )
        kept.insert(1, summary_msg)

        self.messages = kept
        self.meta.compaction_count += 1
        self._touch()
        self._logger.info("compact session={id} compacted={n}",
                          id=self.meta.session_id, n=compacted_count)
        return compacted_count

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
