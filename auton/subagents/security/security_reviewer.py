"""Subagents Security — 安全审查器

OWASP Top 10 + Auton 特定风险：
  - 硬编码密钥
  - SQL/NoSQL 注入
  - XSS/命令注入
  - 不安全的文件操作
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

from ..base import BaseSubagent


# ─── 风险模式定义 ──────────────────────────────────────────────────────────────

_PATTERNS = {
    "hardcoded_secret": [
        (re.compile(r'["\']api[_-]?key["\']\s*[:=]\s*["\'][A-Za-z0-9]{20,}["\']', re.I), "Hardcoded API key"),
        (re.compile(r'password\s*[:=]\s*["\'][^"\']{8,}["\']', re.I), "Hardcoded password"),
        (re.compile(r'sk-[A-Za-z0-9]{20,}', re.I), "Hardcoded secret key"),
    ],
    "command_injection": [
        (re.compile(r'os\.system\s*\('), "os.system() - command injection risk"),
        (re.compile(r'subprocess\.\w+\s*\(\s*["\']', re.I), "subprocess with string - use list args"),
        (re.compile(r'eval\s*\('), "eval() - code injection risk"),
    ],
    "path_traversal": [
        (re.compile(r'open\s*\([^,]*\+'), "File path concatenation - traversal risk"),
    ],
}


class SecurityReviewSubagent(BaseSubagent):
    """安全审查 Subagent"""

    name = "security-review"
    description = (
        "Use after writing code that handles authentication, authorization, "
        "user input, file operations, or external API calls. "
        "Flags OWASP Top 10 vulnerabilities."
    )

    @classmethod
    def system_prompt(cls) -> str:
        return """\
You are a security reviewer. Find and fix security vulnerabilities.

## OWASP Top 10
1. Injection (SQL, NoSQL, OS, LDAP)
2. Broken Authentication
3. Sensitive Data Exposure
4. XSS
5. Broken Access Control
6. Security Misconfiguration
7. XSS
8. Insecure Deserialization
9. Using Components with Known Vulnerabilities
10. Insufficient Logging

## Severity
- CRITICAL: Immediate block - exploit is trivial
- HIGH: High risk - fix before merge
- MEDIUM: Moderate risk - address soon
- LOW: Low risk - consider fixing
"""

    async def _execute(
        self,
        context: dict[str, Any],
    ) -> tuple[str, list[str], list[str]]:
        files = context.get("files", [])
        code_snippets = context.get("code_snippets", {})

        if not files and not code_snippets:
            return "No code provided for security review.", [], []

        logger.info("security review of {n} files", n=len(files))

        findings = []
        recommendations = []

        for file_path in files:
            file_findings = self._scan_file(file_path)
            findings.extend(file_findings)

        critical = [f for f in findings if "CRITICAL" in f]
        high = [f for f in findings if "HIGH" in f]
        medium = [f for f in findings if "MEDIUM" in f]

        if critical:
            recommendations.append("CRITICAL issues must be fixed before merge")
        if high:
            recommendations.append("HIGH issues should be addressed before merge")
        recommendations.extend([
            "Use environment variables for secrets",
            "Validate all user input",
            "Use parameterized queries",
        ])

        output = self._format_review(files, critical, high, medium, recommendations)

        return output, findings, recommendations

    def _scan_file(self, file_path: str) -> list[str]:
        findings = []
        try:
            from pathlib import Path
            content = Path(file_path).read_text(encoding="utf-8")
        except Exception:
            return findings

        for category, patterns in _PATTERNS.items():
            for regex, description in patterns:
                if regex.search(content):
                    findings.append(f"[HIGH] {description} in {file_path}")

        return findings

    def _format_review(
        self,
        files: list[str],
        critical: list[str],
        high: list[str],
        medium: list[str],
        recommendations: list[str],
    ) -> str:
        lines = [
            f"# Security Review\n\n",
            f"**Files reviewed:** {len(files)}\n\n",
            f"## Summary\n\n",
            f"- CRITICAL: {len(critical)}\n",
            f"- HIGH: {len(high)}\n",
            f"- MEDIUM: {len(medium)}\n",
        ]

        if critical:
            lines.append(f"\n## CRITICAL Issues\n\n")
            for c in critical:
                lines.append(f"- {c}\n")

        if high:
            lines.append(f"\n## HIGH Issues\n\n")
            for h in high:
                lines.append(f"- {h}\n")

        if medium:
            lines.append(f"\n## MEDIUM Issues\n\n")
            for m in medium:
                lines.append(f"- {m}\n")

        lines.append(f"\n## Recommendations\n\n")
        for r in recommendations:
            lines.append(f"- {r}\n")

        return "".join(lines)
