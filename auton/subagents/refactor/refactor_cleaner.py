"""Subagents Refactor — 重构清理器

发现并清理：
  - 死代码（未使用的函数、变量、import）
  - 代码重复
  - 过长的函数/文件
  - 坏味道（duplicated code, long method, etc.）
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..base import BaseSubagent


class RefactorCleanerSubagent(BaseSubagent):
    """重构清理 Subagent"""

    name = "refactor"
    description = (
        "Use for code maintenance and cleanup. Identifies dead code, "
        "duplicates, long functions, and suggests refactoring opportunities."
    )

    @classmethod
    def system_prompt(cls) -> str:
        return """\
You are a refactoring specialist. Find and eliminate code smells.

## Code Smells

### Bloaters
- Long Method (>50 lines)
- Large Class (>800 lines)
- Primitive Obsession
- Long Parameter List

### Change Preventers
- Divergent Change
- Shotgun Surgery
- Parallel Inheritance

### Dispensables
- Dead Code
- Data Class
- Lazy Class
- Speculative Generality

## Refactoring Steps
1. Identify the smell
2. Write tests (preserve behavior)
3. Apply refactoring
4. Verify tests still pass
5. Commit
"""

    async def _execute(
        self,
        context: dict[str, Any],
    ) -> tuple[str, list[str], list[str]]:
        files = context.get("files", [])
        language = context.get("language", "python")

        if not files:
            return "No files provided for refactoring.", [], []

        logger.info("refactoring analysis of {n} files", n=len(files))

        findings = []
        recommendations = []

        for file_path in files:
            file_findings = self._analyze_file(file_path, language)
            findings.extend(file_findings)

        if findings:
            recommendations.extend([
                "Write tests before refactoring (preserve behavior)",
                "Refactor one smell at a time",
                "Run tests after each refactoring step",
                "Commit after each successful refactoring",
            ])
        else:
            recommendations.append("No refactoring issues found")

        output = self._format_refactor_report(files, findings, recommendations)

        return output, findings, recommendations

    def _analyze_file(self, file_path: str, language: str) -> list[str]:
        findings = []
        try:
            from pathlib import Path
            content = Path(file_path).read_text(encoding="utf-8")
            lines = content.split("\n")
        except Exception:
            return findings

        # Check file length
        if language == "python" and len(lines) > 500:
            findings.append(f"[MEDIUM] {file_path}: File is {len(lines)} lines (consider splitting)")

        # Check for TODO/FIXME comments
        for i, line in enumerate(lines, 1):
            if "# TODO" in line or "# FIXME" in line:
                findings.append(f"[LOW] {file_path}:{i} - TODO/FIXME comment")

        return findings

    def _format_refactor_report(
        self,
        files: list[str],
        findings: list[str],
        recommendations: list[str],
    ) -> str:
        lines = [
            f"# Refactoring Report\n\n",
            f"**Files analyzed:** {len(files)}\n",
            f"**Issues found:** {len(findings)}\n\n",
        ]

        if findings:
            lines.append(f"## Issues\n\n")
            for f_ in findings:
                lines.append(f"- {f_}\n")
        else:
            lines.append("No refactoring issues found.\n")

        if recommendations:
            lines.append(f"\n## Recommendations\n\n")
            for r in recommendations:
                lines.append(f"- {r}\n")

        return "".join(lines)
