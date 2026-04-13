"""Subagents TDD — TDD 工作流执行器

RED-GREEN-REFACTOR 循环：
  1. Write failing test (RED)
  2. Run test → FAIL
  3. Write minimal implementation (GREEN)
  4. Run test → PASS
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
            "Write test before any implementation code",
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

## RED Phase

### Test 1: Basic functionality
```python
def test_{feature.replace(" ", "_").lower()}_basic():
    # Arrange
    # Act
    # Assert
    assert False, "Not implemented"
```
Run: `pytest {test_dir}/test_{feature.replace(" ", "_").lower()}.py -v` → FAIL

## GREEN Phase

### Implement minimal code
```python
def {feature.replace(" ", "_").lower().replace("-", "_")}():
    return True  # minimal pass
```
Run: `pytest {test_dir}/test_{feature.replace(" ", "_").lower()}.py -v` → PASS

## REFACTOR Phase

- [ ] Remove duplication
- [ ] Improve naming
- [ ] Extract helper functions

## Coverage Check
Run: `pytest --cov={src_dir} --cov-report=term-missing`
Target: >= 80%

## Commit Strategy
After each passing test cycle:
```bash
git add .
git commit -m "test: add {feature} basic test"
```
"""
