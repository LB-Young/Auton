"""Subagents Planner — 任务规划器

将复杂任务分解为小的、具体的步骤。
参考 hermes-agent writing-plans skill。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..base import BaseSubagent


class PlannerSubagent(BaseSubagent):
    """任务规划器 Subagent"""

    name = "planner"
    description = (
        "Use when you have a spec or requirements for a multi-step task. "
        "Creates comprehensive implementation plans with bite-sized tasks, "
        "exact file paths, and complete code examples."
    )

    @classmethod
    def system_prompt(cls) -> str:
        return """\
You are a task planner. Break down complex tasks into bite-sized steps.

## Core Principle
A good plan makes implementation obvious. If someone has to guess, the plan is incomplete.

## Bite-Sized Task Granularity
Each step is one action (2-5 minutes):
- "Write the failing test" — step
- "Run it to make sure it fails" — step
- "Implement the minimal code to make the test pass" — step
- "Run the tests and make sure they pass" — step
- "Commit" — step

## Output Format

Generate a markdown plan with this header:
# [Feature Name] Implementation Plan

**Goal:** [One sentence]

**Architecture:** [2-3 sentences]

---

Then for each task:

### Task N: [Descriptive Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:45-67`

- [ ] **Step 1: [Action]**
- [ ] **Step 2: [Action]**
- [ ] **Step 3: [Action]**

## Rules
- Exact file paths always
- Complete code in every step
- DRY, YAGNI, TDD
- Frequent commits
"""

    async def _execute(
        self,
        context: dict[str, Any],
    ) -> tuple[str, list[str], list[str]]:
        task = context.get("task", "")
        cwd = context.get("cwd", ".")
        relevant_files = context.get("relevant_files", [])

        if not task:
            return "No task provided.", [], []

        logger.info("planning task: {t}", t=task[:80])

        # Generate plan
        plan = self._generate_plan(task, cwd, relevant_files)

        findings = [
            f"Task decomposed: {task[:80]}",
            f"Working directory: {cwd}",
            f"Relevant files: {len(relevant_files)}",
        ]
        recommendations = [
            "Use TDD for each implementation task",
            "Commit after each task",
            "Run tests after each task",
        ]

        return plan, findings, recommendations

    def _generate_plan(
        self,
        task: str,
        cwd: str,
        relevant_files: list[str],
    ) -> str:
        """Generate task plan from template."""
        files_section = ""
        if relevant_files:
            files_section = "\n".join(f"- `{f}`" for f in relevant_files[:10])

        return f"""# Implementation Plan

**Goal:** {task}

**Working Directory:** `{cwd}`

**Relevant Files:**
{files_section if files_section else "- (none provided)"}

---

## Task 1: Understand Requirements

- [ ] **Step 1: Analyze the task requirements**
- [ ] **Step 2: Explore relevant source files**
- [ ] **Step 3: Identify affected files and boundaries**

## Task 2: Implement Core Logic

- [ ] **Step 1: Write the failing test (RED)**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write minimal implementation (GREEN)**
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Refactor (IMPROVE)**

## Task 3: Add Edge Cases

- [ ] **Step 1: Identify edge cases**
- [ ] **Step 2: Add tests for edge cases**
- [ ] **Step 3: Handle edge cases in implementation**

## Task 4: Integration & Verify

- [ ] **Step 1: Run all tests**
- [ ] **Step 2: Verify functionality manually**
- [ ] **Step 3: Commit changes**

## Recommendations
- Use TDD approach for each task
- Keep commits small and focused
- Test edge cases early
- Verify >= 80% coverage
"""
