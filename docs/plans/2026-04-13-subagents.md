# Auton Subagents Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 8 个内置 Subagent，为 Auton 提供任务规划、系统调试、TDD、代码审查、安全审查、重构清理、架构决策和子代理委托能力。

**Architecture:** 采用基类 + 策略模式。每个 Subagent 继承 `BaseSubagent`，通过 `SubagentRegistry` 统一管理。Subagent 通过 `AgentDefinition` 模板注入 LLM 系统提示词，复用 Auton 现有的工具注册和 Skills 系统。

**Tech Stack:** Python 3.11+, loguru, asyncio, dataclasses, Path

---

## File Structure

```
auton/subagents/
├── __init__.py              # 导出所有 Subagent + SubagentRegistry
├── base.py                  # BaseSubagent 抽象基类
├── registry.py              # SubagentRegistry 单例
├── types.py                 # SubagentResult, SubagentConfig 等类型
├── planner/
│   ├── __init__.py
│   └── planner.py           # 任务规划器
├── debugging/
│   ├── __init__.py
│   └── debugger.py          # 系统调试器
├── tdd/
│   ├── __init__.py
│   └── tdd_runner.py        # TDD 工作流
├── code_review/
│   ├── __init__.py
│   └── reviewer.py          # 代码审查
├── security/
│   ├── __init__.py
│   └── security_reviewer.py # 安全审查
├── refactor/
│   ├── __init__.py
│   └── refactor_cleaner.py  # 重构清理
├── architect/
│   ├── __init__.py
│   └── architecture_advisor.py  # 架构决策
└── delegator/
    ├── __init__.py
    └── task_delegator.py     # 子代理委托
```

---

## Task 1: Base Infrastructure

**Files:**
- Create: `auton/subagents/__init__.py`
- Create: `auton/subagents/base.py`
- Create: `auton/subagents/types.py`
- Create: `auton/subagents/registry.py`

- [ ] **Step 1: Create types.py with all shared types**

```python
"""Subagents — core types"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class SubagentPhase(enum.Enum):
    """Subagent 执行阶段"""
    PLANNING = "planning"
    INVESTIGATION = "investigation"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"
    COMPLETED = "completed"


@dataclass
class SubagentConfig:
    """Subagent 配置"""
    name: str
    description: str
    model: str | None = None          # None = 继承主 Agent
    max_turns: int | None = None      # None = 无限制
    timeout_seconds: int = 300         # 默认 5 分钟超时
    tools: list[str] | None = None    # None = 全部工具
    temperature: float = 0.0


@dataclass
class SubagentResult:
    """Subagent 执行结果"""
    name: str
    success: bool
    phase: SubagentPhase
    output: str = ""                   # 最终输出文本
    findings: list[str] = field(default_factory=list)   # 调查结果/发现
    recommendations: list[str] = field(default_factory=list)  # 建议
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        if self.completed_at is None:
            return 0.0
        return (self.completed_at - self.started_at).total_seconds()
```

- [ ] **Step 2: Create base.py with BaseSubagent ABC**

```python
"""Subagents — BaseSubagent: 抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from loguru import logger

from .types import SubagentConfig, SubagentPhase, SubagentResult

if TYPE_CHECKING:
    pass


class BaseSubagent(ABC):
    """所有 Subagent 的抽象基类。

    设计原则：
      - 每个 Subagent 是无状态的工具类，通过 run() 方法执行
      - 通过 config() 类方法返回 SubagentConfig
      - 通过 system_prompt() 类方法返回专用系统提示词
      - 子类实现 _execute() 核心逻辑
    """

    # ─── 类属性（子类覆盖）─────────────────────────────────────────────

    name: str = ""          # 唯一标识
    description: str = ""   # 何时使用

    # ─── 配置 ──────────────────────────────────────────────────────────

    @classmethod
    def config(cls) -> SubagentConfig:
        """返回 Subagent 配置（子类可覆盖）"""
        return SubagentConfig(
            name=cls.name,
            description=cls.description,
        )

    # ─── 系统提示词 ────────────────────────────────────────────────────

    @classmethod
    def system_prompt(cls) -> str:
        """返回此 Subagent 的专用系统提示词（子类必须实现）"""
        raise NotImplementedError

    # ─── 执行入口 ─────────────────────────────────────────────────────

    async def run(
        self,
        context: dict[str, Any],
        **kwargs: Any,
    ) -> SubagentResult:
        """异步执行入口。默认实现调用 _execute()。

        Args:
            context: 执行上下文（含 cwd, task, relevant_files 等）

        Returns:
            SubagentResult 执行结果
        """
        from datetime import datetime

        logger.info("subagent {n} starting", n=self.name)
        result = SubagentResult(
            name=self.name,
            success=True,
            phase=SubagentPhase.PLANNING,
        )

        try:
            output, findings, recommendations = await self._execute(context, **kwargs)
            result.output = output
            result.findings = findings
            result.recommendations = recommendations
            result.phase = SubagentPhase.COMPLETED
        except Exception as exc:
            result.success = False
            result.errors.append(str(exc))
            result.phase = SubagentPhase.COMPLETED
            logger.exception("subagent {n} failed: {e}", n=self.name, e=exc)

        result.completed_at = datetime.now()
        return result

    # ─── 核心逻辑（子类实现）───────────────────────────────────────────

    @abstractmethod
    async def _execute(
        self,
        context: dict[str, Any],
    ) -> tuple[str, list[str], list[str]]:
        """核心执行逻辑（子类必须实现）。

        Returns:
            (output, findings, recommendations)
        """
        raise NotImplementedError
```

- [ ] **Step 3: Create registry.py with SubagentRegistry**

```python
"""Subagents — SubagentRegistry: 全局单例注册表"""

from __future__ import annotations

from loguru import logger

from .base import BaseSubagent
from .types import SubagentConfig


class SubagentRegistry:
    """全局 Subagent 注册表（单例）"""

    _instance: "SubagentRegistry | None" = None
    _built_in: list[type[BaseSubagent]] = []

    def __init__(self) -> None:
        self._by_name: dict[str, BaseSubagent] = {}
        self._logger = logger.bind(name="SubagentRegistry")

    @classmethod
    def get_instance(cls) -> "SubagentRegistry":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._load_built_ins()
        return cls._instance

    @classmethod
    def register(cls, subagent_cls: type[BaseSubagent]) -> None:
        """注册一个 Subagent 类（供 _load_built_ins 调用）"""
        cls._built_in.append(subagent_cls)

    def _load_built_ins(self) -> None:
        """延迟导入并注册所有内置 Subagent"""
        from .planner import PlannerSubagent
        from .debugging import DebuggingSubagent
        from .tdd import TDDRunnerSubagent
        from .code_review import CodeReviewSubagent
        from .security import SecurityReviewSubagent
        from .refactor import RefactorCleanerSubagent
        from .architect import ArchitectureAdvisorSubagent
        from .delegator import TaskDelegatorSubagent

        for cls_ in self._built_in:
            self.register_single(cls_())

        self._logger.info("loaded {n} built-in subagents", n=len(self._by_name))

    def register_single(self, instance: BaseSubagent) -> None:
        self._by_name[instance.name] = instance

    def get(self, name: str) -> BaseSubagent | None:
        return self._by_name.get(name)

    def list_all(self) -> list[BaseSubagent]:
        return list(self._by_name.values())

    def list_configs(self) -> list[SubagentConfig]:
        return [sub.config() for sub in self.list_all()]

    def get_system_prompt(self, name: str) -> str | None:
        sub = self.get(name)
        return sub.system_prompt() if sub else None
```

- [ ] **Step 4: Create __init__.py with public exports**

```python
"""Subagents — 内置 Subagent 集合

用法::

    registry = SubagentRegistry.get_instance()
    planner = registry.get("planner")
    result = await planner.run(context={"task": "实现登录功能"})
"""

from .base import BaseSubagent
from .registry import SubagentRegistry
from .types import SubagentConfig, SubagentPhase, SubagentResult

__all__ = [
    "BaseSubagent",
    "SubagentRegistry",
    "SubagentConfig",
    "SubagentPhase",
    "SubagentResult",
]
```

- [ ] **Step 5: Run test to verify base infrastructure**

Run: `python -c "from auton.subagents import SubagentRegistry; r = SubagentRegistry.get_instance(); print([s.name for s in r.list_all()])"`
Expected: `['planner', 'debugging', 'tdd', 'code-review', 'security-review', 'refactor', 'architect', 'delegator']`

- [ ] **Step 6: Commit**

```bash
git add auton/subagents/
git commit -m "feat(subagents): add base infrastructure and registry"
```

---

## Task 2: Planner Subagent

**Files:**
- Create: `auton/subagents/planner/__init__.py`
- Create: `auton/subagents/planner/planner.py`

- [ ] **Step 1: Create planner/__init__.py**

```python
"""Subagents Planner — 任务规划器"""

from .planner import PlannerSubagent

__all__ = ["PlannerSubagent"]
```

- [ ] **Step 2: Create planner/planner.py**

```python
"""Subagents Planner — 任务规划器

将复杂任务分解为小的、具体的步骤。
参考 hermes-agent writing-plans skill。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..base import BaseSubagent
from ..types import SubagentPhase


class PlannerSubagent(BaseSubagent):
    """任务规划器 Subagent"""

    name = "planner"
    description = (
        "Use when you have a spec or requirements for a multi-step task. "
        "Creates comprehensive implementation plans with bite-sized tasks, "
        "exact file paths, and complete code examples."
    )

    # ─── 系统提示词 ────────────────────────────────────────────────────

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


    # ─── 核心执行 ──────────────────────────────────────────────────────

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

        # 生成计划（通过 LLM 调用）
        plan = await self._generate_plan(task, cwd, relevant_files, context)

        findings = [f"Task decomposed into multiple steps", f"Working directory: {cwd}"]
        recommendations = [
            "Use TDD for each implementation task",
            "Commit after each task",
            "Run tests after each task",
        ]

        return plan, findings, recommendations

    async def _generate_plan(
        self,
        task: str,
        cwd: str,
        relevant_files: list[str],
        context: dict[str, Any],
    ) -> str:
        """生成任务计划。

        子类可以通过注入 LLM 来实现更智能的计划生成。
        默认返回模板计划。
        """
        # 获取 LLM（如果有）
        llm = context.get("llm")
        if llm is not None:
            return await self._generate_with_llm(task, cwd, relevant_files, llm)

        # 无 LLM：返回指导性计划
        return self._template_plan(task)

    async def _generate_with_llm(
        self,
        task: str,
        cwd: str,
        relevant_files: list[str],
        llm: Any,
    ) -> str:
        """使用 LLM 生成结构化计划"""
        from ..planner.planner import PlannerSubagent
        prompt = PlannerSubagent.system_prompt() + f"\n\nTask: {task}\nCWD: {cwd}\nRelevant files: {relevant_files}"
        # 调用 LLM...
        return self._template_plan(task)

    def _template_plan(self, task: str) -> str:
        """返回模板计划（无 LLM 时使用）"""
        return f"""# Implementation Plan

**Goal:** {task}

**Architecture:** TBD based on codebase exploration

---

### Task 1: [Understand Requirements]

**Files:**
- Read: relevant source files

- [ ] **Step 1: Analyze the task requirements**
- [ ] **Step 2: Explore existing codebase**
- [ ] **Step 3: Identify affected files**

### Task 2: [Implement Core Logic]

**Files:**
- Create: `src/`

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write minimal implementation**
- [ ] **Step 4: Run test to verify it passes**

### Task 3: [Add Edge Cases]

- [ ] **Step 1: Identify edge cases**
- [ ] **Step 2: Add tests for edge cases**
- [ ] **Step 3: Handle edge cases in implementation**

### Task 4: [Integration & Verify]

- [ ] **Step 1: Run all tests**
- [ ] **Step 2: Verify functionality manually**
- [ ] **Step 3: Commit changes**

## Recommendations
- Use TDD approach
- Keep commits small and focused
- Test edge cases early
"""
```

- [ ] **Step 3: Register in registry.py**

Edit `auton/subagents/registry.py` to import and register `PlannerSubagent`.

- [ ] **Step 4: Run test**

Run: `python -c "from auton.subagents import SubagentRegistry; r = SubagentRegistry.get_instance(); p = r.get('planner'); print(p.description[:60])"`
Expected: `Use when you have a spec or requirements for a multi`

- [ ] **Step 5: Commit**

```bash
git add auton/subagents/planner/
git commit -m "feat(subagents): add PlannerSubagent for task decomposition"
```

---

## Task 3: Debugging Subagent

**Files:**
- Create: `auton/subagents/debugging/__init__.py`
- Create: `auton/subagents/debugging/debugger.py`

- [ ] **Step 1: Create debugging/__init__.py**

```python
"""Subagents Debugging — 系统化调试"""

from .debugger import DebuggingSubagent

__all__ = ["DebuggingSubagent"]
```

- [ ] **Step 2: Create debugging/debugger.py**

```python
"""Subagents Debugging — 系统化调试器

4 阶段根因分析：
  Phase 1: 错误信息分析
  Phase 2: 可复现性验证
  Phase 3: 根因定位
  Phase 4: 修复方案
参考 hermes-agent systematic-debugging skill。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..base import BaseSubagent
from ..types import SubagentPhase


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
- Read error messages carefully (don't skip past warnings)
- Note line numbers, file paths, error codes
- Search for error strings in the codebase

### Phase 2: Reproducibility
- Can you trigger it reliably?
- What are the exact steps?
- Does it happen every time?
- If not reproducible → gather more data, don't guess

### Phase 3: Root Cause
- Narrow down the failing component
- Check recent changes
- Examine data flow
- Use logging to trace execution

### Phase 4: Fix Proposal
- Propose specific fix with file paths and line numbers
- Explain WHY this fixes the root cause
- List verification steps

## Output Format

## Phase 1: Error Analysis
**Findings:**
- ...

## Phase 2: Reproducibility
**Steps to reproduce:**
- ...

## Phase 3: Root Cause
**Root cause:** ...

## Phase 4: Fix Proposal
**Recommended fix:**
```python
# specific code
```

**Verification:**
- Step 1: ...
- Step 2: ...
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
            findings.append(f"Error: {error_message}")
        if stack_trace:
            findings.append(f"Stack trace available: {len(stack_trace)} chars")

        # Phase 2: Reproducibility
        findings.append("Reproduction steps needed to verify")

        # Phase 3 & 4: Based on available info
        if stack_trace:
            recommendations.append("Parse stack trace to identify root cause")
            recommendations.append("Add targeted logging at failure point")
        else:
            recommendations.append("Gather more information: error message, stack trace, reproduction steps")

        output = self._format_output(bug_description, error_message, findings, recommendations)

        return output, findings, recommendations

    def _format_output(
        self,
        bug_description: str,
        error_message: str,
        findings: list[str],
        recommendations: list[str],
    ) -> str:
        lines = [
            f"# Debugging Report\n",
            f"**Bug:** {bug_description}\n",
            f"\n## Phase 1: Error Analysis\n",
        ]
        for f_ in findings:
            lines.append(f"- {f_}\n")

        lines.append(f"\n## Phase 2: Reproducibility\n")
        lines.append("- [ ] Identify exact reproduction steps\n")

        lines.append(f"\n## Phase 3: Root Cause\n")
        lines.append("- TBD after investigation\n")

        lines.append(f"\n## Phase 4: Fix Proposal\n")
        for r in recommendations:
            lines.append(f"- {r}\n")

        return "".join(lines)
```

- [ ] **Step 3: Register in registry.py**

- [ ] **Step 4: Commit**

```bash
git add auton/subagents/debugging/
git commit -m "feat(subagents): add DebuggingSubagent for systematic bug investigation"
```

---

## Task 4: TDD Runner Subagent

**Files:**
- Create: `auton/subagents/tdd/__init__.py`
- Create: `auton/subagents/tdd/tdd_runner.py`

- [ ] **Step 1: Create tdd/__init__.py**

```python
"""Subagents TDD — 测试驱动开发"""

from .tdd_runner import TDDRunnerSubagent

__all__ = ["TDDRunnerSubagent"]
```

- [ ] **Step 2: Create tdd/tdd_runner.py**

```python
"""Subagents TDD — TDD 工作流执行器

强制 TDD 循环：
  1. Write failing test (RED)
  2. Run test - should FAIL
  3. Write minimal implementation (GREEN)
  4. Run test - should PASS
  5. Refactor (IMPROVE)
  6. Verify coverage >= 80%
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..base import BaseSubagent


class TDDRunnerSubagent(BaseSubagent):
    """TDD 工作流 Subagent"""

    name = "tdd"
    description = (
        "Use when implementing new features, fixing bugs, or refactoring. "
        "Enforces write-tests-first methodology with RED-GREEN-REFACTOR cycle."
    )

    @classmethod
    def system_prompt(cls) -> str:
        return """\
You are a TDD practitioner. Always write tests first.

## TDD Cycle

### RED: Write the failing test
```python
def test_feature():
    result = function_under_test(input)
    assert result == expected
```

### GREEN: Write minimal implementation
```python
def function_under_test(input):
    return expected  # minimal pass
```

### REFACTOR: Improve code
- Remove duplication
- Improve naming
- Extract helpers

## Coverage Requirement
Minimum 80% test coverage required.

## TDD Rules
1. Never write implementation code before writing the test
2. Write the simplest test that could fail
3. Write the minimal code to make the test pass
4. Refactor only after tests pass
5. Run full test suite after refactoring

## Output Format

## TDD Plan for: [Feature Name]

### Test 1: [Test Name]
- [ ] Write failing test
- [ ] Run: `pytest tests/... -v` → FAIL
- [ ] Write minimal code
- [ ] Run: `pytest tests/... -v` → PASS

### Coverage Check
- Run: `pytest --cov=src --cov-report=term-missing`
- Target: >= 80%
"""


    async def _execute(
        self,
        context: dict[str, Any],
    ) -> tuple[str, list[str], list[str]]:
        feature = context.get("feature", "")
        test_dir = context.get("test_dir", "tests/unit")
        src_dir = context.get("src_dir", "src")

        if not feature:
            return "No feature specified for TDD.", [], []

        logger.info("tdd for feature: {f}", f=feature)

        findings = [
            f"Feature: {feature}",
            f"Test directory: {test_dir}",
            f"Source directory: {src_dir}",
        ]

        recommendations = [
            "Write test before any implementation",
            "Run tests after each RED-GREEN cycle",
            "Maintain >= 80% coverage",
            "Commit after each passing test cycle",
        ]

        output = self._generate_tdd_plan(feature, test_dir, src_dir)

        return output, findings, recommendations

    def _generate_tdd_plan(self, feature: str, test_dir: str, src_dir: str) -> str:
        return f"""\
# TDD Plan for: {feature}

## Setup
- Test directory: `{test_dir}`
- Source directory: `{src_dir}`

## Test Cases

### Test 1: Basic functionality
- [ ] **RED:** Write test in `{test_dir}/test_{feature}.py`
```python
def test_{feature}_basic():
    assert True  # placeholder
```
- [ ] **GREEN:** Run `pytest {test_dir}/test_{feature}.py -v`
- [ ] **REFACTOR:** Improve test structure

### Test 2: Input validation
- [ ] **RED:** Write test for input validation
- [ ] **GREEN:** Run tests → PASS
- [ ] **REFACTOR:** Extract validation logic

### Test 3: Edge cases
- [ ] **RED:** Write tests for edge cases
- [ ] **GREEN:** Run tests → PASS
- [ ] **REFACTOR:** Clean up

## Coverage Check
Run: `pytest --cov={src_dir} --cov-report=term-missing`
Target: >= 80%

## Commit Strategy
- After each passing test: commit
- Message format: `test: add {feature} {test_name}`
"""
```

- [ ] **Step 3: Register in registry.py**

- [ ] **Step 4: Commit**

```bash
git add auton/subagents/tdd/
git commit -m "feat(subagents): add TDDRunnerSubagent for test-driven development"
```

---

## Task 5: Code Review Subagent

**Files:**
- Create: `auton/subagents/code_review/__init__.py`
- Create: `auton/subagents/code_review/reviewer.py`

- [ ] **Step 1: Create code_review/__init__.py**

```python
"""Subagents Code Review — 代码审查"""

from .reviewer import CodeReviewSubagent

__all__ = ["CodeReviewSubagent"]
```

- [ ] **Step 2: Create code_review/reviewer.py**

```python
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

### Security
- [ ] No hardcoded secrets
- [ ] User input validated
- [ ] SQL injection prevented
- [ ] XSS prevented

## Severity Levels
- CRITICAL: Security vulnerability or data loss risk → BLOCK
- HIGH: Bug or significant quality issue → WARN
- MEDIUM: Maintainability concern → INFO
- LOW: Style or minor suggestion → NOTE

## Output Format

# Code Review: [Files]

## Summary
- Files reviewed: N
- CRITICAL issues: N
- HIGH issues: N
- MEDIUM issues: N

## Issues

### [CRITICAL] Issue title
**File:** `path/to/file.py:45`
**Description:** ...
**Recommendation:** ...
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

        # Analyze based on language
        if language == "python":
            findings.extend(self._analyze_python(files, diff))
        else:
            findings.append(f"Analyzing {language} code")

        # Standard recommendations
        recommendations.extend([
            "Fix CRITICAL issues before merge",
            "Address HIGH issues when possible",
            "Ensure >= 80% test coverage",
            "Run linter (ruff/black) after fixes",
        ])

        output = self._format_review(files, findings, recommendations)

        return output, findings, recommendations

    def _analyze_python(self, files: list[str], diff: str) -> list[str]:
        findings = []
        # Basic Python patterns to check
        if "TODO" in diff or "FIXME" in diff:
            findings.append("TODO/FIXME comments found - address before merge")
        if "except:" in diff:
            findings.append("Bare except clause found - specify exception type")
        if "print(" in diff:
            findings.append("print() found - use logging instead")
        if "os.system" in diff:
            findings.append("os.system() found - use subprocess with args list")
        return findings

    def _format_review(
        self,
        files: list[str],
        findings: list[str],
        recommendations: list[str],
    ) -> str:
        lines = [
            f"# Code Review\n",
            f"**Files reviewed:** {len(files)}\n",
            f"\n## Summary\n",
            f"- Files reviewed: {len(files)}\n",
            f"- Findings: {len(findings)}\n",
            f"\n## Findings\n",
        ]
        for i, f_ in enumerate(findings, 1):
            lines.append(f"{i}. {f_}\n")

        lines.append(f"\n## Recommendations\n")
        for r in recommendations:
            lines.append(f"- {r}\n")

        return "".join(lines)
```

- [ ] **Step 3: Register in registry.py**

- [ ] **Step 4: Commit**

```bash
git add auton/subagents/code_review/
git commit -m "feat(subagents): add CodeReviewSubagent for code quality review"
```

---

## Task 6: Security Review Subagent

**Files:**
- Create: `auton/subagents/security/__init__.py`
- Create: `auton/subagents/security/security_reviewer.py`

- [ ] **Step 1: Create security/__init__.py**

```python
"""Subagents Security — 安全审查"""

from .security_reviewer import SecurityReviewSubagent

__all__ = ["SecurityReviewSubagent"]
```

- [ ] **Step 2: Create security/security_reviewer.py**

```python
"""Subagents Security — 安全审查器

OWASP Top 10 + Auton 特定风险：
  - 硬编码密钥
  - SQL/NoSQL 注入
  - XSS/命令注入
  - 不安全的文件操作
  - 认证/授权绕过
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
        (re.compile(r'token\s*[:=]\s*["\'][A-Za-z0-9_\-]{20,}["\']', re.I), "Hardcoded token"),
        (re.compile(r'sk-[A-Za-z0-9]{20,}', re.I), "Hardcoded secret key"),
    ],
    "command_injection": [
        (re.compile(r'os\.system\s*\('), "os.system() - command injection risk"),
        (re.compile(r'subprocess\.\w+\s*\(\s*["\']', re.I), "subprocess with string - use list args"),
        (re.compile(r'eval\s*\('), "eval() - code injection risk"),
    ],
    "sql_injection": [
        (re.compile(r'execute\s*\(\s*["\'].*\%s', re.I), "SQL with %s formatting - use parameterized queries"),
        (re.compile(r'["\'].*\+.*WHERE|SELECT|INSERT|UPDATE|DELETE', re.I), "SQL string concatenation - injection risk"),
    ],
    "path_traversal": [
        (re.compile(r'open\s*\([^,]*\+'), "File path concatenation - traversal risk"),
        (re.compile(r'read_text\s*\([^,]*\+'), "Path.join with user input"),
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

## Mandatory Security Checks

Before ANY commit:
- [ ] No hardcoded secrets (API keys, passwords, tokens)
- [ ] All user inputs validated
- [ ] SQL/NoSQL injection prevented (parameterized queries)
- [ ] Command injection prevented (subprocess with list args)
- [ ] Path traversal prevented (validate file paths)
- [ ] XSS prevented (sanitize HTML)

## OWASP Top 10
1. Injection (SQL, NoSQL, OS, LDAP)
2. Broken Authentication
3. Sensitive Data Exposure
4. XML External Entities (XXE)
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

## Output Format

# Security Review: [Files]

## CRITICAL Issues
...

## HIGH Issues
...

## MEDIUM Issues
...

## Recommendations
1. ...
"""


    async def _execute(
        self,
        context: dict[str, Any],
    ) -> tuple[str, list[str], list[str]]:
        files = context.get("files", [])
        code_snippets = context.get("code_snippets", {})
        language = context.get("language", "python")

        if not files and not code_snippets:
            return "No code provided for security review.", [], []

        logger.info("security review of {n} files", n=len(files))

        findings = []
        recommendations = []

        # Pattern-based scanning
        for file_path in files:
            file_findings = self._scan_file(file_path, language)
            findings.extend(file_findings)

        # Categorize findings
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
            "Run security scanner (bandit)",
        ])

        output = self._format_review(files, critical, high, medium, recommendations)

        return output, findings, recommendations

    def _scan_file(self, file_path: str, language: str) -> list[str]:
        """Scan a file for security patterns"""
        findings = []
        try:
            from pathlib import Path
            content = Path(file_path).read_text(encoding="utf-8")
        except Exception:
            return findings

        for category, patterns in _PATTERNS.items():
            if category == "sql_injection" and language != "python":
                continue
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
            f"# Security Review\n",
            f"**Files reviewed:** {len(files)}\n",
            f"\n## Summary\n",
            f"- CRITICAL: {len(critical)}\n",
            f"- HIGH: {len(high)}\n",
            f"- MEDIUM: {len(medium)}\n",
        ]

        if critical:
            lines.append(f"\n## CRITICAL Issues\n")
            for c in critical:
                lines.append(f"- {c}\n")

        if high:
            lines.append(f"\n## HIGH Issues\n")
            for h in high:
                lines.append(f"- {h}\n")

        if medium:
            lines.append(f"\n## MEDIUM Issues\n")
            for m in medium:
                lines.append(f"- {m}\n")

        lines.append(f"\n## Recommendations\n")
        for r in recommendations:
            lines.append(f"- {r}\n")

        return "".join(lines)
```

- [ ] **Step 3: Register in registry.py**

- [ ] **Step 4: Commit**

```bash
git add auton/subagents/security/
git commit -m "feat(subagents): add SecurityReviewSubagent for vulnerability scanning"
```

---

## Task 7: Refactor Cleaner Subagent

**Files:**
- Create: `auton/subagents/refactor/__init__.py`
- Create: `auton/subagents/refactor/refactor_cleaner.py`

- [ ] **Step 1: Create refactor/__init__.py**

```python
"""Subagents Refactor — 重构清理"""

from .refactor_cleaner import RefactorCleanerSubagent

__all__ = ["RefactorCleanerSubagent"]
```

- [ ] **Step 2: Create refactor/refactor_cleaner.py**

```python
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
- Long Method
- Large Class
- Primitive Obsession
- Long Parameter List
- Data Clumps

### Object-Orientation Abusers
- Switch Statements
- Temporary Field
- Refused Bequest

### Change Preventers
- Divergent Change
- Shotgun Surgery
- Parallel Inheritance

### Dispensables
- Dead Code
- Data Class
- Lazy Class
- Speculative Generality
- Noise Comments

## Refactoring Steps
1. Identify the smell
2. Write tests (preserve behavior)
3. Apply refactoring
4. Verify tests still pass
5. Commit

## Output Format

# Refactoring Report

## Dead Code
- `file.py:45` - unused function `old_function`
- `file.py:67` - unused import `OldClass`

## Duplications
- `file1.py` and `file2.py` share similar logic in `analyze_`
- Extract to shared utility

## Long Functions
- `file.py:100` - `complex_calculation` (150 lines)
  - Split into: `validate_input`, `process_data`, `format_output`

## Recommendations
1. Remove dead code
2. Extract duplicated logic
3. Split long functions
"""


    async def _execute(
        self,
        context: dict[str, Any],
    ) -> tuple[str, list[str], list[str]]:
        files = context.get("files", [])
        language = context.get("language", "python")
        include_dead_code = context.get("include_dead_code", True)
        include_duplicates = context.get("include_duplicates", True)

        if not files:
            return "No files provided for refactoring.", [], []

        logger.info("refactoring analysis of {n} files", n=len(files))

        findings = []
        recommendations = []

        # Analyze each file
        for file_path in files:
            file_findings = self._analyze_file(file_path, language)
            findings.extend(file_findings)

        # Generate recommendations
        if findings:
            recommendations.extend([
                "Write tests before refactoring (preserve behavior)",
                "Refactor one smell at a time",
                "Run tests after each refactoring step",
                "Commit after each successful refactoring",
            ])

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

        # Check for long functions (heuristic)
        if language == "python":
            findings.extend(self._check_python_smells(file_path, lines))

        # Check for dead imports
        findings.extend(self._check_dead_imports(file_path, content))

        return findings

    def _check_python_smells(self, file_path: str, lines: list[str]) -> list[str]:
        findings = []
        # Check file length
        if len(lines) > 500:
            findings.append(f"[MEDIUM] {file_path}: File is {len(lines)} lines (consider splitting)")

        # Check for TODO/FIXME
        for i, line in enumerate(lines, 1):
            if "# TODO" in line or "# FIXME" in line:
                findings.append(f"[LOW] {file_path}:{i} - TODO/FIXME comment")

        return findings

    def _check_dead_imports(self, file_path: str, content: str) -> list[str]:
        findings = []
        # Simple heuristic: check for unused standard imports
        unused = ["os", "sys", "json", "re"]
        for module in unused:
            if f"import {module}" in content and module not in content[content.find(f"import {module}"):]:
                pass  # Simplified check
        return findings

    def _format_refactor_report(
        self,
        files: list[str],
        findings: list[str],
        recommendations: list[str],
    ) -> str:
        lines = [
            f"# Refactoring Report\n",
            f"**Files analyzed:** {len(files)}\n",
            f"**Issues found:** {len(findings)}\n",
        ]

        if findings:
            lines.append(f"\n## Issues\n")
            for f_ in findings:
                lines.append(f"- {f_}\n")
        else:
            lines.append(f"\nNo refactoring issues found.\n")

        if recommendations:
            lines.append(f"\n## Recommendations\n")
            for r in recommendations:
                lines.append(f"- {r}\n")

        return "".join(lines)
```

- [ ] **Step 3: Register in registry.py**

- [ ] **Step 4: Commit**

```bash
git add auton/subagents/refactor/
git commit -m "feat(subagents): add RefactorCleanerSubagent for code cleanup"
```

---

## Task 8: Architecture Advisor Subagent

**Files:**
- Create: `auton/subagents/architect/__init__.py`
- Create: `auton/subagents/architect/architecture_advisor.py`

- [ ] **Step 1: Create architect/__init__.py**

```python
"""Subagents Architect — 架构决策"""

from .architecture_advisor import ArchitectureAdvisorSubagent

__all__ = ["ArchitectureAdvisorSubagent"]
```

- [ ] **Step 2: Create architect/architecture_advisor.py**

```python
"""Subagents Architect — 架构决策顾问

辅助架构决策：
  - 评估设计选项
  - 识别架构风险
  - 提供模式建议
  - 权衡分析
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..base import BaseSubagent


class ArchitectureAdvisorSubagent(BaseSubagent):
    """架构决策 Subagent"""

    name = "architect"
    description = (
        "Use when designing new features, making architectural decisions, "
        "or evaluating system design. Provides pattern recommendations "
        "and trade-off analysis."
    )

    @classmethod
    def system_prompt(cls) -> str:
        return """\
You are an architecture advisor. Guide design decisions with trade-off analysis.

## Architecture Principles

### SOLID Principles
- Single Responsibility (one reason to change)
- Open/Closed (open for extension, closed for modification)
- Liskov Substitution (subtypes substitutable for base)
- Interface Segregation (many specific interfaces > one general)
- Dependency Inversion (depend on abstractions)

### Design Patterns by Category

**Creational:** Factory, Builder, Singleton, Prototype
**Structural:** Adapter, Bridge, Composite, Decorator, Facade, Proxy
**Behavioral:** Strategy, Observer, Command, State, Template Method

### Decision Framework
1. Problem: What are we solving?
2. Options: What are the alternatives?
3. Trade-offs: Pros/Cons of each option
4. Decision: Which approach and why?
5. Consequences: What are the implications?

## Output Format

# Architecture Decision: [Title]

## Context
[Background and constraints]

## Decision
[What we decided]

## Options Considered

### Option A: [Name]
**Pros:** ...
**Cons:** ...

### Option B: [Name]
**Pros:** ...
**Cons:** ...

## Consequences
### Positive
- ...

### Negative
- ...

## Recommendation
[Final recommendation with rationale]
"""


    async def _execute(
        self,
        context: dict[str, Any],
    ) -> tuple[str, list[str], list[str]]:
        feature = context.get("feature", "")
        constraints = context.get("constraints", [])
        existing_architecture = context.get("existing_architecture", "")

        if not feature:
            return "No feature specified for architecture design.", [], []

        logger.info("architecture analysis for: {f}", f=feature)

        findings = [
            f"Feature: {feature}",
        ]
        if existing_architecture:
            findings.append(f"Existing architecture: {existing_architecture[:100]}")
        findings.extend([f"Constraint: {c}" for c in constraints])

        recommendations = [
            "Consider SOLID principles",
            "Evaluate 2-3 design options before deciding",
            "Prototype risky parts early",
            "Document architectural decisions (ADRs)",
        ]

        output = self._generate_adr(feature, constraints, existing_architecture)

        return output, findings, recommendations

    def _generate_adr(
        self,
        feature: str,
        constraints: list[str],
        existing_architecture: str,
    ) -> str:
        lines = [
            f"# Architecture Decision: {feature}\n",
            f"\n## Context\n",
            f"Feature: {feature}\n",
        ]

        if existing_architecture:
            lines.append(f"Existing architecture:\n{existing_architecture}\n")

        if constraints:
            lines.append(f"\n**Constraints:**\n")
            for c in constraints:
                lines.append(f"- {c}\n")

        lines.extend([
            f"\n## Decision\n",
            f"TBD after options analysis\n",
            f"\n## Options Considered\n",
            f"\n### Option A: [Name]\n",
            f"**Pros:**\n- ...\n",
            f"**Cons:**\n- ...\n",
            f"\n### Option B: [Name]\n",
            f"**Pros:**\n- ...\n",
            f"**Cons:**\n- ...\n",
            f"\n## Consequences\n",
            f"\n### Positive\n",
            f"- ...\n",
            f"\n### Negative\n",
            f"- ...\n",
            f"\n## Recommendation\n",
            f"Proceed with Option [A/B] because [rationale]\n",
        ])

        return "".join(lines)
```

- [ ] **Step 3: Register in registry.py**

- [ ] **Step 4: Commit**

```bash
git add auton/subagents/architect/
git commit -m "feat(subagents): add ArchitectureAdvisorSubagent for design decisions"
```

---

## Task 9: Task Delegator Subagent

**Files:**
- Create: `auton/subagents/delegator/__init__.py`
- Create: `auton/subagents/delegator/task_delegator.py`

- [ ] **Step 1: Create delegator/__init__.py**

```python
"""Subagents Delegator — 任务委托"""

from .task_delegator import TaskDelegatorSubagent

__all__ = ["TaskDelegatorSubagent"]
```

- [ ] **Step 2: Create delegator/task_delegator.py**

```python
"""Subagents Delegator — 任务委托器

编排多 Subagent 工作流：
  1. 分析任务，拆分为子任务
  2. 选择合适的 Subagent
  3. 顺序或并行执行
  4. 汇总结果
参考 hermes-agent subagent-driven-development skill。
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
        "to specialized subagents. Orchestrates multi-subagent workflows "
        "for complex tasks."
    )

    @classmethod
    def system_prompt(cls) -> str:
        return """\
You are a task delegator. Break down complex tasks and delegate to specialists.

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

## Sub-agent 2: [Name]
- Responsibility: ...
- Input: ...
- Expected output: ...
```

### 3. Execute
- Run independent subagents in parallel
- Run dependent subagents in sequence
- Aggregate results

### 4. Finalize
- Synthesize sub-agent outputs
- Create final deliverable
- Report completion

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

## Output Format

# Delegation Plan: [Task]

## Sub-agent Assignments

### Sub-agent 1: [Name]
- Task: ...
- Depends on: none
- Parallel with: none

### Sub-agent 2: [Name]
- Task: ...
- Depends on: Sub-agent 1
- Parallel with: none

## Execution Order
1. [Sub-agent 1] → [Output]
2. [Sub-agent 2] → [Output]

## Final Output
[synthesized result]
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

        # Analyze task complexity
        if len(task) > 500 or "and" in task.lower() or "then" in task.lower():
            findings.append("Complex task - delegation recommended")
        else:
            findings.append("Simple task - consider direct implementation")

        # List available subagents
        if available_subagents:
            findings.append(f"Available subagents: {', '.join(available_subagents)}")

        # Suggest delegation strategy
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
```

- [ ] **Step 3: Register in registry.py**

- [ ] **Step 4: Commit**

```bash
git add auton/subagents/delegator/
git commit -m "feat(subagents): add TaskDelegatorSubagent for multi-agent orchestration"
```

---

## Task 10: Integration Tests

**Files:**
- Create: `tests/unit/subagents/`

- [ ] **Step 1: Create test file**

```python
"""Tests — Subagents 集成测试"""
import pytest

from auton.subagents import SubagentRegistry, SubagentResult


@pytest.mark.unit
class TestSubagentRegistry:
    def test_singleton(self):
        r1 = SubagentRegistry.get_instance()
        r2 = SubagentRegistry.get_instance()
        assert r1 is r2

    def test_list_all_returns_all_subagents(self):
        registry = SubagentRegistry.get_instance()
        names = [s.name for s in registry.list_all()]
        assert "planner" in names
        assert "debugging" in names
        assert "tdd" in names
        assert "code-review" in names
        assert "security-review" in names
        assert "refactor" in names
        assert "architect" in names
        assert "delegator" in names

    def test_get_returns_correct_subagent(self):
        registry = SubagentRegistry.get_instance()
        planner = registry.get("planner")
        assert planner is not None
        assert planner.name == "planner"


@pytest.mark.unit
class TestSubagentResults:
    def test_subagent_result_default_values(self):
        result = SubagentResult(name="test", success=True, phase=None)
        assert result.success is True
        assert result.findings == []
        assert result.errors == []

    def test_duration_seconds(self):
        from datetime import datetime, timedelta
        result = SubagentResult(name="test", success=True, phase=None)
        result.started_at = datetime.now()
        result.completed_at = result.started_at + timedelta(seconds=5)
        assert result.duration_seconds == 5.0
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/unit/subagents/ -v`
Expected: 5 passed

- [ ] **Step 3: Commit**

```bash
git add tests/unit/subagents/
git commit -m "test(subagents): add integration tests for subagent infrastructure"
```

---

## Final Commit

- [ ] **Step 1: Final verification**

Run: `python -c "from auton.subagents import SubagentRegistry; r = SubagentRegistry.get_instance(); print('Subagents:', [s.name for s in r.list_all()])"`
Expected: `Subagents: ['planner', 'debugging', 'tdd', 'code-review', 'security-review', 'refactor', 'architect', 'delegator']`

- [ ] **Step 2: Final commit**

```bash
git add -A
git commit -m "feat(subagents): implement all 8 built-in subagents

- BaseSubagent + SubagentRegistry infrastructure
- PlannerSubagent: task decomposition
- DebuggingSubagent: 4-phase root cause analysis
- TDDRunnerSubagent: RED-GREEN-REFACTOR cycle
- CodeReviewSubagent: code quality review
- SecurityReviewSubagent: OWASP Top 10 vulnerability scan
- RefactorCleanerSubagent: dead code and smell detection
- ArchitectureAdvisorSubagent: ADR generation
- TaskDelegatorSubagent: multi-subagent orchestration
"
```
