"""Auton Core — 日志敏感信息过滤

防止 API Key、Token 等凭据意外写入日志文件。
"""

from __future__ import annotations

import re

# 需要过滤的敏感信息正则模式
# 每个 pattern 匹配成功后会被替换为 [REDACTED]
_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    # Anthropic / OpenAI API Keys
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}", re.ASCII),
    # Anthropic Session Keys
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}", re.ASCII),
    # Claude keys（claude- 前缀的临时令牌）
    re.compile(r"claude-[A-Za-z0-9_\-]{20,}", re.ASCII),
    # GitHub Personal Access Tokens
    re.compile(r"ghp_[A-Za-z0-9]{36}", re.ASCII),
    re.compile(r"github_pat_[A-Za-z0-9_]{10,}", re.ASCII),
    # Slack Tokens
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}", re.ASCII),
    # AWS Access Key ID / Secret
    re.compile(r"AKIA[0-9A-Z]{16}", re.ASCII),
    re.compile(r"(?i)aws[_\- ]?secret[_\- ]?access[_\- ]?key\s*[=:]\s*\S{20,}"),
    # Generic Bearer Token（Authorization 头）
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{20,}"),
    # Generic API Key 模式（key=xxxx / api_key: xxxx）
    re.compile(r"(?i)(?:api[_\- ]?key|apikey|access[_\- ]?token)\s*[=:]\s*['\"]?[A-Za-z0-9\-._~+/]{16,}['\"]?"),
    # MiniMax API Key
    re.compile(r"(?i)minimax[_\- ]?api[_\- ]?key\s*[=:]\s*\S{16,}"),
    # 通用 Base64 Secret（长度 ≥ 32 且包含 +/= 或全字母数字）在 secret/password 上下文中
    re.compile(r"(?i)(?:secret|password|passwd|pwd)\s*[=:]\s*['\"]?[A-Za-z0-9+/=]{16,}['\"]?"),
]

_REDACTED = "[REDACTED]"


def redact_sensitive_text(text: str) -> str:
    """过滤字符串中的敏感信息，替换为 [REDACTED]。

    设计为幂等且高性能：每次调用仅做正则替换，无 IO 操作。

    Args:
        text: 原始字符串（日志行、错误信息等）

    Returns:
        已过滤敏感信息的字符串
    """
    for pattern in _SENSITIVE_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


class RedactingFilter:
    """Loguru sink 过滤器：对日志消息进行敏感信息过滤。

    用法（与 Loguru 集成）：
        logger.add(sink, filter=RedactingFilter())

    由于 Loguru 的 filter 在 record 被序列化之前调用，
    此处直接修改 record["message"]，效率优于 Formatter 方案。
    """

    def __call__(self, record: dict) -> bool:
        """修改 record 中的敏感字段，始终返回 True（不丢弃日志）。"""
        record["message"] = redact_sensitive_text(record["message"])
        # 同时过滤 extra 字典中的字符串值
        for key, val in record.get("extra", {}).items():
            if isinstance(val, str):
                record["extra"][key] = redact_sensitive_text(val)
        return True
