"""compress/config.py — 实时会话压缩配置"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompressConfig:
    """实时会话压缩配置"""

    # 触发阈值（双阈值，任一满足即触发）
    token_threshold: int = 150_000       # 绝对 token 数
    threshold_percent: float = 0.60      # 上下文窗口比例

    # 尾部保护
    protect_turns: int = 2               # 保留最近几轮用户对话
    tail_token_budget: int = 40_000      # 尾部 token 上限

    # 工具输出截断
    tool_output_threshold: int = 200     # 超过此字符数截断为占位符
    protect_tail_tool_results: int = 15  # 尾部保留的工具结果数量

    # 摘要生成
    max_summary_tokens: int = 8192       # 摘要最大 token 数
    summary_temperature: float = 0.0    # 摘要生成温度

    # 防抖
    compression_cooldown_seconds: int = 60   # 压缩后冷却时间（秒）
    max_compressions_per_session: int = 10   # 单会话最大压缩次数
