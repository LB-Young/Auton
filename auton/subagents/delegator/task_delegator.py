"""Subagents Delegator — 任务委托器

编排多 Subagent 工作流：
  1. 分析任务，拆分为子任务
  2. 选择合适的 Subagent
  3. 顺序或并行执行
  4. 汇总结果
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..base import BaseSubagent


class TaskDelegatorSubagent(BaseSubagent):
    """任务委托 Subagent"""

    name = "delegator"
    description = (
        "Use when a complex task needs to be broken down and delegated "
        "to specialized subagents. Orchestrates multi-subagent workflows."
    )

    @classmethod
    def system_prompt(cls) -> str:
        return """\
You are a task delegator. Break down complex tasks and delegate to specialists.

## Available Subagents

| Name | When to Use |
|------|------------|
| planner | Task needs decomposition |
| debugging | Bug investigation needed |
| tdd | New feature implementation |
| code-review | Code quality check |
| security-review | Security audit needed |
| refactor | Code cleanup needed |
| architect | Design decisions needed |

## Delegation Process

### 1. Analyze Task
- What are the components?
- Which subagents are needed?
- What are the dependencies?

### 2. Create Sub-agent Plan
```markdown
## Sub-agent 1: [Name]
- Responsibility: ...
- Input: ...
- Expected output: ...
```

### 3. Execute
- Run independent subagents in parallel
- Run dependent subagents in sequence

### 4. Finalize
- Synthesize sub-agent outputs
- Create final deliverable
"""

    async def _execute(
        self,
        context: dict[str, Any],
    ) -> tuple[str, list[str], list[str]]:
        task = context.get("task", "")
        available_subagents = context.get("available_subagents", [])

        if not task:
            return "No task specified for delegation.", [], []

        logger.info("delegating task: {t}", t=task[:80])

        findings = []
        recommendations = []

        if len(task) > 500 or "and" in task.lower() or "then" in task.lower():
            findings.append("Complex task - delegation recommended")
        else:
            findings.append("Simple task - consider direct implementation")

        recommendations.extend([
            "Use planner for task decomposition",
            "Run independent subagents in parallel",
            "Run dependent subagents in sequence",
            "Aggregate results for final output",
        ])

        output = self._generate_delegation_plan(task, available_subagents)

        return output, findings, recommendations

    def _generate_delegation_plan(
        self,
        task: str,
        available_subagents: list[str],
    ) -> str:
        subagent_list = ", ".join(available_subagents) if available_subagents else "planner, debugging, tdd, code-review, security-review, refactor, architect"

        return f"""\
# Delegation Plan: {task[:80]}

## Available Subagents
{subagent_list}

## Recommended Workflow

### Phase 1: Planning
1. Use **planner** to decompose the task
2. Identify dependencies between subtasks

### Phase 2: Execution
- Run independent subtasks in parallel using appropriate subagents
- Run dependent subtasks in sequence

### Phase 3: Integration
- Aggregate results from all subagents
- Create final deliverable

## Sub-agent Assignment Template

```markdown
### Sub-agent: [Name]
- Task: [specific subtask]
- Depends on: [none or other sub-agent name]
- Parallel with: [none or list of sub-agents]
```

## Execution Tracking
- [ ] Phase 1 complete
- [ ] Phase 2 complete
- [ ] Phase 3 complete
"""
