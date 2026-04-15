"""memory/config.py — 会话后摘要配置"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SummaryConfig:
    """会话后摘要配置"""

    # Block 触发
    block_size_threshold: int = 10         # 超过此数量事件则使用 LLM 摘要

    # 摘要生成
    max_conversation_tokens: int = 32_000  # 单次 LLM 摘要的最大对话 token
    summary_max_tokens: int = 4096         # 摘要输出最大 token

    # 输出路径（相对于 base 目录）
    summary_md_name: str = "SUMMARY.md"   # 分段摘要文件名
    memory_md_name: str = "MEMORY.md"     # 索引文件名
