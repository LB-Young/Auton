"""memory/memory_read_hook.py — 工具层文件读取拦截

在 Read 工具执行后根据文件路径自动分类记录到 RetrievalAnalytics，
无需 LLM 主动汇报读取行为。

接入方式（在 SessionProcessor._execute_tools 的工具执行后调用）：
    hook.on_tool_result(tool_name, tool_input, result_text, session_id)
    hook.set_current_query(query_text)   # 每轮对话开始时调用
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .retrieval_analytics import RetrievalAnalytics


# 可识别为"文件读取"的工具名（兼容不同工具注册名）
_READ_TOOL_NAMES = frozenset({"Read", "read_file", "read", "ReadFile"})


class MemoryReadHook:
    """在 Read 工具执行后，根据文件路径分类记录到 RetrievalAnalytics。

    路径分类规则（大小写不敏感）：
      *.../SUMMARY.md  → hit_source="summary"
      *.../MEMORY.md   → hit_source="memory"（暂不主动记录，避免重复）
      *.jsonl          → hit_source="jsonl"

    Args:
        analytics: RetrievalAnalytics 实例（持久化存储）
    """

    def __init__(self, analytics: "RetrievalAnalytics") -> None:
        self.analytics = analytics
        self._current_query: str = ""

    def set_current_query(self, query: str) -> None:
        """每轮新用户消息到来时调用，记录当前 query 文本。

        由 SessionProcessor 在主循环每次获取 user query 后调用。
        """
        self._current_query = query.strip()

    def on_tool_result(
        self,
        tool_name: str,
        tool_input: dict,
        result: str,
        session_id: str,
    ) -> None:
        """Read 工具执行完成后调用，根据文件路径分类记录。

        如果工具不是文件读取类工具，或路径不属于记忆文件，则静默忽略。

        Args:
            tool_name:  执行的工具名
            tool_input: 工具输入参数（含 path 字段）
            result:     工具返回的文本内容
            session_id: 当前 session ID
        """
        if tool_name not in _READ_TOOL_NAMES:
            return

        path = str(tool_input.get("path", "")).strip()
        if not path:
            return

        path_lower = path.lower()

        if "summary.md" in path_lower:
            # agent 读取了 SUMMARY.md
            msg_ids = _extract_msg_ids_from_text(result)
            self.analytics.record(
                query_text=self._current_query,
                hit_source="summary",
                hit_msg_ids=msg_ids or None,
                hit_content=result[:500],
                session_id=session_id,
            )

        elif path_lower.endswith(".jsonl"):
            # agent 降级读取了原始 session.jsonl
            msg_ids = _extract_msg_ids_from_jsonl(result)
            self.analytics.record(
                query_text=self._current_query,
                hit_source="jsonl",
                hit_msg_ids=msg_ids or None,
                hit_content=result[:500],
                session_id=session_id,
            )

        # MEMORY.md 读取暂不单独记录：
        # agent 读 MEMORY.md 后若不再读 summary/jsonl，表示 memory 已足够；
        # 但此时 query 已经过了，无法确认是否需要后续读取。
        # 建议通过 on_turn_end(hit_source="memory") 在轮次结束时补充记录。


# ─── 辅助函数 ──────────────────────────────────────────────────────────────────

def _extract_msg_ids_from_text(text: str) -> list[str]:
    """从任意文本中提取 msg_id 引用（内层和外层格式均兼容）"""
    ids = re.findall(r"msg_id[-:]([a-zA-Z0-9\-]+)", text, re.IGNORECASE)
    return list(dict.fromkeys(x.lower() for x in ids))


def _extract_msg_ids_from_jsonl(content: str) -> list[str]:
    """从 jsonl 内容中提取 msg_id 字段（每行一个 JSON 对象）"""
    ids: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            mid = obj.get("msg_id") or obj.get("message_id", "")
            if mid:
                ids.append(str(mid).lower())
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue
    return list(dict.fromkeys(ids))
