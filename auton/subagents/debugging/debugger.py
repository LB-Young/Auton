"""Subagents Debugging — 系统化调试器

4 阶段根因分析：
  Phase 1: 错误信息分析
  Phase 2: 可复现性验证
  Phase 3: 根因定位
  Phase 4: 修复方案
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..base import BaseSubagent


class DebuggingSubagent(BaseSubagent):
    """系统化调试 Subagent"""

    name = "debugging"
    description = (
        "Use when encountering any bug, test failure, or unexpected behavior. "
        "4-phase root cause investigation — NO fixes without understanding the problem first."
    )

    @classmethod
    def system_prompt(cls) -> str:
        return """\
You are a systematic debugger. Find root causes before proposing fixes.

## The Iron Law
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST

## The Four Phases

### Phase 1: Error Analysis
- Read error messages carefully (don't skip warnings)
- Note line numbers, file paths, error codes
- Search for error strings in the codebase

### Phase 2: Reproducibility
- Can you trigger it reliably?
- Exact steps to reproduce?
- Does it happen every time?
- If not reproducible → gather more data, don't guess

### Phase 3: Root Cause
- Narrow down the failing component
- Check recent changes
- Examine data flow
- Use logging to trace execution

### Phase 4: Fix Proposal
- Propose fix with file paths and line numbers
- Explain WHY this fixes the root cause
- List verification steps
"""

    async def _execute(
        self,
        context: dict[str, Any],
    ) -> tuple[str, list[str], list[str]]:
        bug_description = context.get("bug_description", "")
        error_message = context.get("error_message", "")
        stack_trace = context.get("stack_trace", "")
        reproduction_steps = context.get("reproduction_steps", "")

        if not bug_description and not error_message:
            return "No bug information provided.", [], []

        logger.info("debugging: {b}", b=bug_description[:80])

        findings = []
        recommendations = []

        # Phase 1: Error Analysis
        if error_message:
            findings.append(f"Error: {error_message[:200]}")
        if stack_trace:
            findings.append(f"Stack trace: {len(stack_trace)} chars")
        if bug_description:
            findings.append(f"Bug: {bug_description[:200]}")

        # Phase 2: Reproducibility
        if reproduction_steps:
            findings.append(f"Reproduction steps provided: {reproduction_steps[:100]}")
        else:
            findings.append("Reproduction steps: NOT PROVIDED - must gather")

        # Phase 3 & 4: Based on available info
        if stack_trace or error_message:
            recommendations.extend([
                "Parse error message for root cause",
                "Add targeted logging at failure point",
                "Verify fix doesn't break other functionality",
            ])
        else:
            recommendations.append("Gather: error message, stack trace, reproduction steps")

        output = self._format_output(bug_description, error_message, stack_trace, findings, recommendations)

        return output, findings, recommendations

    def _format_output(
        self,
        bug_description: str,
        error_message: str,
        stack_trace: str,
        findings: list[str],
        recommendations: list[str],
    ) -> str:
        lines = [
            f"# Debugging Report\n\n",
            f"**Bug:** {bug_description or 'Not specified'}\n",
            f"\n## Phase 1: Error Analysis\n\n",
        ]
        for f_ in findings[:5]:
            lines.append(f"- {f_}\n")

        lines.extend([
            f"\n## Phase 2: Reproducibility\n\n",
            "- [ ] Identify exact reproduction steps\n",
            "- [ ] Verify bug occurs reliably\n",
            f"\n## Phase 3: Root Cause\n\n",
            "- TBD after investigation\n",
            f"\n## Phase 4: Fix Proposal\n\n",
        ])
        for r in recommendations:
            lines.append(f"- {r}\n")

        return "".join(lines)
