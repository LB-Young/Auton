"""memory/retrieval_analytics.py — 检索命中分析

记录每次检索的来源（memory / summary / jsonl / none），
用于反向驱动 SUMMARY.md 质量改进。

检索来源定义：
  memory  — agent 从 MEMORY.md 直接回答，无需读 summary
  summary — agent 读取了 SUMMARY.md 并从中获得足够信息
  jsonl   — agent 降级读取了原始 session.jsonl（summary 不足）
  none    — 无任何记忆命中
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


HitSource = Literal["memory", "summary", "jsonl", "none"]


@dataclass
class RetrievalRecord:
    """单次检索记录"""

    query_id: str
    query_text: str
    hit_source: HitSource
    hit_msg_ids: list[str] | None         # 命中的 msg_id 列表
    hit_content: str | None               # 命中的具体内容片段（前 500 字符）
    session_id: str
    timestamp: float


class RetrievalAnalytics:
    """记录检索命中情况，提供统计接口。

    数据持久化为 JSON 文件，供跨进程恢复使用。
    """

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self.records: list[RetrievalRecord] = []
        self._load()

    # ─── 记录 ──────────────────────────────────────────────────────────────

    def record(
        self,
        query_text: str,
        hit_source: HitSource,
        *,
        hit_msg_ids: list[str] | None = None,
        hit_content: str | None = None,
        session_id: str = "",
    ) -> None:
        """记录一次检索事件"""
        rec = RetrievalRecord(
            query_id=str(uuid.uuid4())[:8],
            query_text=query_text,
            hit_source=hit_source,
            hit_msg_ids=hit_msg_ids,
            hit_content=hit_content[:500] if hit_content else None,
            session_id=session_id,
            timestamp=time.time(),
        )
        self.records.append(rec)
        self._persist()

    # ─── 统计接口 ──────────────────────────────────────────────────────────

    def get_summary_hit_rate(self, session_id: str) -> float:
        """从 summary 回答的命中率（不含从 memory 回答的情况）"""
        recs = self._for_session(session_id)
        if not recs:
            return 0.0
        return sum(1 for r in recs if r.hit_source == "summary") / len(recs)

    def get_no_jsonl_hit_rate(self, session_id: str) -> float:
        """不降级到 jsonl 的命中率（memory + summary），即 98% 目标指标"""
        recs = self._for_session(session_id)
        if not recs:
            return 0.0
        no_jsonl = sum(1 for r in recs if r.hit_source in ("memory", "summary"))
        return no_jsonl / len(recs)

    def get_failed_queries(self, session_id: str) -> list[RetrievalRecord]:
        """获取真正降级到 jsonl 的 query（不含 memory 命中的成功记录）"""
        return [
            r for r in self.records
            if r.session_id == session_id and r.hit_source == "jsonl"
        ]

    def get_msg_id_stats(self) -> dict[str, dict[str, int]]:
        """统计各 msg_id 的命中 / 未命中次数

        Returns:
            {msg_id: {"hit": n, "miss": n}}
        """
        stats: dict[str, dict[str, int]] = {}
        for r in self.records:
            if not r.hit_msg_ids:
                continue
            for mid in r.hit_msg_ids:
                if mid not in stats:
                    stats[mid] = {"hit": 0, "miss": 0}
                if r.hit_source == "summary":
                    stats[mid]["hit"] += 1
                else:
                    stats[mid]["miss"] += 1
        return stats

    def get_keyword_frequency(self, session_id: str) -> list[tuple[str, int]]:
        """提取降级到 jsonl 的 query 中的高频关键词（summary 覆盖不足的信号）"""
        words: Counter[str] = Counter()
        stop_words = {"the", "and", "for", "with", "this", "that", "what", "how", "why"}
        for r in self.records:
            if r.session_id == session_id and r.hit_source == "jsonl":
                tokens = re.findall(r"\w{3,}", r.query_text.lower())
                words.update(w for w in tokens if w not in stop_words)
        return words.most_common(30)

    def total_count(self, session_id: str) -> int:
        return len(self._for_session(session_id))

    def failed_count(self, session_id: str) -> int:
        return len(self.get_failed_queries(session_id))

    # ─── 持久化 ────────────────────────────────────────────────────────────

    def _for_session(self, session_id: str) -> list[RetrievalRecord]:
        return [r for r in self.records if r.session_id == session_id]

    def _persist(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "query_id": r.query_id,
                "query_text": r.query_text,
                "hit_source": r.hit_source,
                "hit_msg_ids": r.hit_msg_ids,
                "hit_content": r.hit_content,
                "session_id": r.session_id,
                "timestamp": r.timestamp,
            }
            for r in self.records
        ]
        self.storage_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
            for item in raw:
                self.records.append(
                    RetrievalRecord(
                        query_id=item.get("query_id", ""),
                        query_text=item.get("query_text", ""),
                        hit_source=item.get("hit_source", "none"),
                        hit_msg_ids=item.get("hit_msg_ids"),
                        hit_content=item.get("hit_content"),
                        session_id=item.get("session_id", ""),
                        timestamp=item.get("timestamp", 0.0),
                    )
                )
        except (json.JSONDecodeError, KeyError):
            self.records = []
