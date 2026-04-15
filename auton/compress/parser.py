"""compress/parser.py — 压缩摘要输出解析"""

from __future__ import annotations

import re


def parse_compact_summary(raw: str) -> str:
    """从 LLM 原始输出中解析摘要。

    - 去除 <analysis> 思考草稿（仅用于提升质量，无信息价值）
    - 提取 <summary> 内容，格式化为可读文本
    - 若无 <summary> 标签，直接返回清理后的全文（降级处理）
    """
    text = raw

    # 去除 <analysis> 块
    text = re.sub(r"<analysis>[\s\S]*?</analysis>", "", text, flags=re.DOTALL)

    # 提取 <summary> 内容
    summary_match = re.search(r"<summary>([\s\S]*?)</summary>", text, re.DOTALL)
    if summary_match:
        content = summary_match.group(1).strip()
        text = f"对话摘要：\n{content}"

    # 清理多余空白行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
