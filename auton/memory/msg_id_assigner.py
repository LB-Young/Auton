"""memory/msg_id_assigner.py — 消息分块与 msg_id 范围分配

将 session.jsonl 的消息列表划分为语义连续的交互块（MsgBlock），
每块对应 SUMMARY.md 中的一条或多条要点。

切块触发条件（满足任一即切）：
  1. 相邻消息时间间隔 > time_gap_threshold 秒
  2. 当前块消息数 >= max_block_size
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MsgBlock:
    """一个连续消息块，对应 SUMMARY.md 中的若干要点"""

    msg_ids: list[str]                   # 块内所有消息的 msg_id
    msg_range: str                       # "first_id~last_id"（单条时仅写一个 id）
    messages: list[dict] = field(default_factory=list)  # 原始消息内容

    @property
    def start_id(self) -> str:
        return self.msg_ids[0] if self.msg_ids else ""

    @property
    def end_id(self) -> str:
        return self.msg_ids[-1] if self.msg_ids else ""

    @property
    def size(self) -> int:
        return len(self.msg_ids)


class MsgIdAssigner:
    """将消息列表划分为交互块，并为每块分配 msg_id 范围。

    Args:
        time_gap_threshold: 相邻消息时间间隔超过此秒数则切块（默认 300s）
        max_block_size:     单块最大消息数（默认 20）
    """

    def __init__(
        self,
        time_gap_threshold: int = 300,
        max_block_size: int = 20,
    ) -> None:
        self.time_gap_threshold = time_gap_threshold
        self.max_block_size = max_block_size

    def assign(self, messages: list[dict]) -> list[MsgBlock]:
        """将消息列表划分为交互块。

        Args:
            messages: session.jsonl 的消息列表（每条含 msg_id、role、content、timestamp）

        Returns:
            MsgBlock 列表，保持原始顺序
        """
        blocks: list[MsgBlock] = []
        current: list[dict] = []
        last_ts: float = 0.0

        for msg in messages:
            ts = float(msg.get("timestamp", 0))
            time_gap = ts - last_ts if last_ts else 0.0

            should_cut = bool(current) and (
                time_gap > self.time_gap_threshold
                or len(current) >= self.max_block_size
            )
            if should_cut:
                blocks.append(self._finalize_block(current))
                current = []

            current.append(msg)
            last_ts = ts

        if current:
            blocks.append(self._finalize_block(current))

        return blocks

    def _finalize_block(self, messages: list[dict]) -> MsgBlock:
        ids = [m["msg_id"] for m in messages if m.get("msg_id")]
        first_id = ids[0] if ids else ""
        last_id = ids[-1] if ids else ""
        # 单条消息时不写冗余的 "aaa~aaa"
        msg_range = first_id if first_id == last_id else f"{first_id}~{last_id}"
        return MsgBlock(msg_ids=ids, msg_range=msg_range, messages=list(messages))
