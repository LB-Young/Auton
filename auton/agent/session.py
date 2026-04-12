"""Agent Session — 会话管理

Session 管理一个完整的对话会话：
  - 消息历史（List[Message]）
  - 步骤计数
  - 上下文 token 统计
  - compact 压缩逻辑（支持 LLM 摘要和简单截断两种模式）

compact 策略：
  - prepare_compact()  → 纯计算边界，返回 CompactPreparation，不修改 messages
  - apply_compact()    → 用 LLM（或 fallback）生成的摘要文本写回 messages
  - compact()          → 同步 fallback：简单截断摘要，供降级使用
"""

from __future__ import annotations

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
        self._logger.info(
            "session={id} status={status} reason={reason}",
            id=self.meta.session_id,
            status=status,
            reason=reason,
        )

    # ─── Compact ────────────────────────────────────────────────────────────

    def prepare_compact(
        self,
        *,
        protect_turns: int = 2,
        recent_token_budget: int = 40_000,
        min_tail_messages: int = 2,
    ) -> "CompactPreparation":
        """计算 compact 边界，返回准备对象（不修改 messages）。

        将消息列表划分为三段：
          stable_prefix        — 首条系统消息 + 已有历史压缩摘要（跳过，不再压缩）
          messages_to_compress — 待送入 LLM 摘要的中间消息
          messages_to_keep     — 最近 protect_turns 轮，保持原样传给 LLM

        protect_turns 控制保留最近几轮不压缩；recent_token_budget 限制
        尾部保留的 token 上限，超出时自动减少保留轮次。
        """
        total = len(self.messages)
        if total <= 2:
            return CompactPreparation(
                stable_prefix=list(self.messages),
                messages_to_compress=[],
                messages_to_keep=[],
                has_prior_summary=False,
            )

        # ── 1. 找稳定前缀（首条 + 连续的历史压缩摘要）──────────────────────
        stable_prefix_end = 1
        has_prior_summary = False
        while stable_prefix_end < total:
            msg = self.messages[stable_prefix_end]
            text = msg.get_text().strip()
            if msg.role == "system" and text.startswith("[历史压缩]"):
                stable_prefix_end += 1
                has_prior_summary = True
                continue
            break

        compressible_total = total - stable_prefix_end
        if compressible_total <= 1:
            return CompactPreparation(
                stable_prefix=list(self.messages[:stable_prefix_end]),
                messages_to_compress=[],
                messages_to_keep=list(self.messages[stable_prefix_end:]),
                has_prior_summary=has_prior_summary,
            )

        # ── 2. 确定尾部起点（保留最近 protect_turns 轮）────────────────────
        turn_starts = self._real_user_turn_starts(
            self.messages, start=stable_prefix_end
        )
        preserved_turns = min(protect_turns, len(turn_starts)) if turn_starts else 0

        if preserved_turns > 0:
            tail_start = turn_starts[-preserved_turns]
        else:
            tail_start = max(stable_prefix_end + 1, total - min_tail_messages)

        # ── 3. 若尾部 token 超出预算，缩减保留轮次 ─────────────────────────
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

        return CompactPreparation(
            stable_prefix=list(self.messages[:stable_prefix_end]),
            messages_to_compress=list(middle),
            messages_to_keep=list(self.messages[tail_start:]),
            has_prior_summary=has_prior_summary,
        )

    def apply_compact(
        self,
        summary_text: str,
        preparation: "CompactPreparation",
    ) -> "CompactResult":
        """将 LLM（或 fallback）生成的摘要写回会话消息列表。

        以 [历史压缩] 前缀的 system 消息替换 preparation.messages_to_compress，
        将 stable_prefix、摘要消息、messages_to_keep 依次拼接。
        """
        if not preparation.messages_to_compress:
            return CompactResult()

        full_summary = f"[历史压缩] {summary_text}"
        summary_msg = Message(role="system")
        summary_msg.add_text(full_summary)

        self.messages = (
            preparation.stable_prefix
            + [summary_msg]
            + preparation.messages_to_keep
        )

        self.meta.compaction_count += 1
        self._touch()
        self._logger.info(
            "compact applied session={id} compressed={n} has_prior={p}",
            id=self.meta.session_id,
            n=len(preparation.messages_to_compress),
            p=preparation.has_prior_summary,
        )

        return CompactResult(
            compacted_count=len(preparation.messages_to_compress),
            summary_text=full_summary,
            compressed_message_ids=[
                m.message_id for m in preparation.messages_to_compress
            ],
            summary_message_id=summary_msg.message_id,
        )

    def compact(
        self,
        *,
        protect_turns: int = 2,
        recent_token_budget: int = 40_000,
        min_tail_messages: int = 2,
    ) -> "CompactResult":
        """同步 fallback compact：简单截断摘要，无 LLM。

        当 LLM 压缩失败或不可用时调用。摘要质量较低（仅截取前 120 字符），
        优先使用 prepare_compact() + LLM + apply_compact() 路径。
        """
        preparation = self.prepare_compact(
            protect_turns=protect_turns,
            recent_token_budget=recent_token_budget,
            min_tail_messages=min_tail_messages,
        )
        if preparation.is_empty:
            return CompactResult()

        summary_lines: list[str] = []
        for msg in preparation.messages_to_compress:
            text = msg.get_text()
            if text and not (
                msg.role == "system" and text.strip().startswith("[历史压缩]")
            ):
                summary_lines.append(f"[{msg.role}] {text[:120]}")

        summary_text = (
            f"合并 {len(preparation.messages_to_compress)} 条消息，保留关键信息：\n- "
            + "\n- ".join(summary_lines[:6])
        )
        return self.apply_compact(summary_text, preparation)

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
    def _real_user_turn_starts(
        messages: Sequence[Message], *, start: int = 0
    ) -> list[int]:
        """返回真实用户轮次的起点索引。

        工具结果与命令结果虽然以 user message 形式写入 session，但它们属于
        内部续上下文消息，不能被当作新的"用户轮次"边界，否则 compact 会把
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


# ─── 数据类 ───────────────────────────────────────────────────────────────────

@dataclass
class CompactPreparation:
    """compact 边界计算结果（prepare_compact() 的返回值）。

    三段划分：
      stable_prefix        — 不参与压缩的稳定头部
      messages_to_compress — 待送入 LLM 摘要的中间消息
      messages_to_keep     — 最近保留的轮次（不压缩）
    """
    stable_prefix: list[Message]
    messages_to_compress: list[Message]
    messages_to_keep: list[Message]
    has_prior_summary: bool  # True 表示 stable_prefix 中含有历史摘要，使用增量压缩

    @property
    def is_empty(self) -> bool:
        """没有可压缩内容时为 True"""
        return len(self.messages_to_compress) == 0

    def build_llm_input(self) -> list[Message]:
        """为 LLM 调用构建输入消息列表。

        增量压缩时：将 stable_prefix 中的历史摘要消息前置作为上下文，
        再拼接 messages_to_compress，让 LLM 能感知已有摘要并做增量更新。
        首次压缩时：仅返回 messages_to_compress。
        """
        if not self.has_prior_summary:
            return list(self.messages_to_compress)

        # 只取 stable_prefix 中标记为 [历史压缩] 的摘要消息作为上下文
        prior_summaries = [
            msg
            for msg in self.stable_prefix
            if msg.role == "system"
            and msg.get_text().strip().startswith("[历史压缩]")
        ]
        return prior_summaries + list(self.messages_to_compress)


@dataclass
class CompactResult:
    compacted_count: int = 0
    summary_text: str = ""
    compressed_message_ids: list[str] = field(default_factory=list)
    summary_message_id: str | None = None
