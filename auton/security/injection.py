"""Security — Prompt Injection 防护

在工具结果返回 LLM 之前，对其进行清洗，防止：
  - Markdown 代码块（``` 未闭合，或在内容中间时危险）
  - 水平线（--- 打断 system prompt）
  - 指令注入（# 单独成行）

清洗原则：保守（宁可多洗，不可漏洗）。
"""

from __future__ import annotations

import re
import unicodedata


# 需要清洗的危险标记（使用非 raw string，\n = 实际换行符 chr(10)）
_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Markdown 未闭合代码块 / 危险反引号
    # 匹配 ``` 不接换行也不接 ```（说明在内容中间或末尾）
    # (?<!\n) = 前一字符不是换行（排除独立行的 ``` 开头）
    # `{3,} = 3+ 个反引号
    # (?![\n`]) = 下一字符不是换行也不是反引号
    (
        re.compile(r"(?<!\n)`{3,}(?![\n`])"),
        "\n── code delimiter ──\n",
    ),
    # 水平线：--- 前后都有换行（独立的 --- 行）
    (
        re.compile(r"(?<=\n)-{3,}(?=\n)"),
        "\n── divider ──\n",
    ),
    # 单行水平线（整行只有 ---）
    (
        re.compile(r"^-{3,}$", re.MULTILINE),
        "───",
    ),
    # 指令注入（# 单独成行，在换行之后）
    (
        re.compile(r"(?<=\n)^#{1,6}\s", re.MULTILINE),
        "\n## ",
    ),
]

# 最大连续空行数
_MAX_BLANK_LINES = 3


def escape_injection(text: str) -> str:
    """清洗文本中的 prompt injection 模式

    Args:
        text: 原始工具输出

    Returns:
        清洗后的安全文本
    """
    if not text:
        return text

    # 1. Unicode 规范化（防止同形字符欺骗）
    text = unicodedata.normalize("NFKC", text)

    # 2. 应用危险模式替换
    for pattern, replacement in _INJECTION_PATTERNS:
        text = pattern.sub(replacement, text)

    # 3. 折叠连续空行（防止填充攻击）
    text = re.sub(r"\n{4,}", "\n" * _MAX_BLANK_LINES, text)

    # 4. 去除首尾空白（防止前导空格注入）
    text = text.strip()

    return text


def is_injection_suspect(text: str) -> bool:
    """快速判断文本是否包含注入特征（不清洗，仅检测）"""
    if not text:
        return False

    for pattern, _ in _INJECTION_PATTERNS:
        if pattern.search(text):
            return True

    return False


class InjectionGuard:
    """工具输出清洗器"""

    def __init__(self) -> None:
        self.sanitized_count = 0

    def sanitize(self, tool_name: str, raw_output: str) -> str:
        """清洗工具输出"""
        cleaned = escape_injection(raw_output)
        if is_injection_suspect(raw_output):
            self.sanitized_count += 1
        return cleaned

    def report(self) -> str:
        """生成可疑活动报告"""
        if self.sanitized_count == 0:
            return ""
        return f"[security] {self.sanitized_count} suspicious output(s) sanitized"
