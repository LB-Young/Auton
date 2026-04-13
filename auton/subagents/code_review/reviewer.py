"""Subagents Code Review — 代码审查器

检查维度：
  - 代码质量（可读性、命名、函数大小）
  - 模式遵循（DRY、KISS、YAGNI）
  - 错误处理
  - 测试覆盖
  - 性能考虑
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..base import BaseSubagent


class CodeReviewSubagent(BaseSubagent):
    """代码审查 Subagent"""

    name = "code-review"
    description = (
        "Use after writing or modifying code. Reviews code for quality, "
        "security, patterns, and maintainability."
    )

    @classmethod
    def system_prompt(cls) -> str:
        return """\
You are a code reviewer. Review code for quality, security, and maintainability.

## Review Checklist

### Code Quality
- [ ] Functions are small (<50 lines)
- [ ] Files are focused (<800 lines)
- [ ] No deep nesting (>4 levels)
- [ ] Good naming (descriptive, consistent)

### Error Handling
- [ ] All errors are handled explicitly
- [ ] No silent error swallowing
- [ ] User-friendly error messages in UI code

### Testing
- [ ] Tests exist for new functionality
- [ ] Test coverage >= 80%
- [ ] Tests are isolated

### Performance
- [ ] No N+1 queries
- [ ] Proper pagination
- [ ] No unnecessary allocations

## Severity Levels
- CRITICAL: Security vulnerability → BLOCK
- HIGH: Bug or significant quality issue → WARN
- MEDIUM: Maintainability concern → INFO
- LOW: Style or minor suggestion → NOTE
"""

    async def _execute(
        self,
        context: dict[str, Any],
    ) -> tuple[str, list[str], list[str]]:
        files = context.get("files", [])
        diff = context.get("diff", "")
        language = context.get("language", "python")

        if not files and not diff:
            return "No code provided for review.", [], []

        logger.info("reviewing {n} files", n=len(files))

        findings = []
        recommendations = []

        # Analyze patterns
        if diff:
            findings.extend(self._analyze_patterns(diff, language))

        findings.append(f"Files reviewed: {len(files)}")
        recommendations.extend([
            "Fix CRITICAL issues before merge",
            "Address HIGH issues when possible",
            "Ensure >= 80% test coverage",
            "Run linter after fixes",
        ])

        output = self._format_review(files, findings, recommendations)

        return output, findings, recommendations

    def _analyze_patterns(self, diff: str, language: str) -> list[str]:
        findings = []
        if "TODO" in diff or "FIXME" in diff:
            findings.append("[LOW] TODO/FIXME comments found")
        if "except:" in diff:
            findings.append("[MEDIUM] Bare except clause - specify exception type")
        if "print(" in diff:
            findings.append("[LOW] print() found - use logging instead")
        if "os.system" in diff:
            findings.append("[HIGH] os.system() - command injection risk")
        return findings

    def _format_review(
        self,
        files: list[str],
        findings: list[str],
        recommendations: list[str],
    ) -> str:
        lines = [
            f"# Code Review\n\n",
            f"**Files reviewed:** {len(files)}\n\n",
            f"## Summary\n\n",
            f"- Files reviewed: {len(files)}\n",
            f"- Findings: {len(findings)}\n\n",
            f"## Findings\n\n",
        ]
        for i, f_ in enumerate(findings, 1):
            lines.append(f"{i}. {f_}\n")

        lines.append(f"\n## Recommendations\n\n")
        for r in recommendations:
            lines.append(f"- {r}\n")

        return "".join(lines)
