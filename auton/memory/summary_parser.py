"""memory/summary_parser.py — 解析 SUMMARY.md 中的 msg_id 引用

提供两个公共接口：
  parse_summary_for_analytics  — 解析 SUMMARY.md 为 SummaryEntry 列表
  extract_msg_ids_from_text    — 从任意文本中提取 msg_id 引用
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# 兼容完整 UUID（含连字符）和短 8 位 ID
_MSG_ID_PATTERN = re.compile(r"\(msg_id-([a-zA-Z0-9\-]+)\)", re.IGNORECASE)
_OUTER_RANGE_PATTERN = re.compile(
    r"([a-zA-Z0-9\-]+)~([a-zA-Z0-9\-]+)", re.ASCII
)


@dataclass
class SummaryEntry:
    """SUMMARY.md 中一条 `- [msg_id: ...]` 要点的结构化表示"""

    topic: str                          # 所属 ## 标题
    msg_range: str                      # 外层 msg_id 范围，如 "a1b2c3d4~c3d4e5f6"
    content: str                        # 要点内容（含内层引用）
    inner_msg_ids: list[str] = field(default_factory=list)  # 内层 (msg_id-XXX)

    @property
    def all_msg_ids(self) -> list[str]:
        """外层端点 + 内层引用，合并去重"""
        outer = self._parse_range(self.msg_range)
        return list(dict.fromkeys(outer + self.inner_msg_ids))

    def _parse_range(self, msg_range: str) -> list[str]:
        m = _OUTER_RANGE_PATTERN.match(msg_range.strip())
        if m:
            return [m.group(1).lower(), m.group(2).lower()]
        return [msg_range.strip().lower()]


def parse_summary_for_analytics(summary: str) -> list[SummaryEntry]:
    """解析 SUMMARY.md 内容，提取所有 SummaryEntry。

    格式：
      ## <主题>
      - [msg_id: a1b2c3d4~c3d4e5f6] 子论点1（msg_id-a1b2），子论点2（msg_id-b2c3）

    内层 msg_id 提取为 best-effort：格式不完整时跳过，不影响整体解析。

    Args:
        summary: SUMMARY.md 完整文本

    Returns:
        按文件顺序排列的 SummaryEntry 列表
    """
    entries: list[SummaryEntry] = []
    topic: str = ""

    for line in summary.splitlines():
        # ## 标题行 → 更新当前主题
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            topic = m.group(1).strip()
            continue

        # - [msg_id: ...] 要点行
        m = re.match(r"^-\s+\[msg_id:\s*([^\]]+)\]\s*(.+)$", line)
        if m:
            outer_range = m.group(1).strip()
            content = m.group(2).strip()
            inner_ids = [x.lower() for x in _MSG_ID_PATTERN.findall(content)]
            entries.append(
                SummaryEntry(
                    topic=topic,
                    msg_range=outer_range,
                    content=content,
                    inner_msg_ids=inner_ids,
                )
            )

    return entries


def extract_msg_ids_from_text(text: str) -> list[str]:
    """从任意文本中提取所有 msg_id 引用（用于 analytics 记录）。

    兼容两种格式：
      (msg_id-xxxxxxxx)       — 内层引用
      [msg_id: xxx~yyy]       — 外层范围引用
    """
    ids: list[str] = []
    # 内层格式
    ids.extend(_MSG_ID_PATTERN.findall(text))
    # 外层范围格式
    for m in re.finditer(r"\[msg_id:\s*([^\]]+)\]", text, re.IGNORECASE):
        part = m.group(1).strip()
        r = _OUTER_RANGE_PATTERN.match(part)
        if r:
            ids.extend([r.group(1), r.group(2)])
        else:
            ids.append(part)
    return [x.lower() for x in dict.fromkeys(ids)]
