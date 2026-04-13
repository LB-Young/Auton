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

## SOLID Principles
- Single Responsibility (one reason to change)
- Open/Closed (open for extension, closed for modification)
- Liskov Substitution (subtypes substitutable for base)
- Interface Segregation (many specific interfaces > one general)
- Dependency Inversion (depend on abstractions)

## Design Patterns by Category
**Creational:** Factory, Builder, Singleton, Prototype
**Structural:** Adapter, Bridge, Composite, Decorator, Facade, Proxy
**Behavioral:** Strategy, Observer, Command, State, Template Method

## Decision Framework
1. Problem: What are we solving?
2. Options: What are the alternatives?
3. Trade-offs: Pros/Cons of each option
4. Decision: Which approach and why?
5. Consequences: What are the implications?
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

        findings = [f"Feature: {feature}"]
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
            f"# Architecture Decision: {feature}\n\n",
            f"## Context\n\n",
            f"**Feature:** {feature}\n\n",
        ]

        if existing_architecture:
            lines.append(f"**Existing architecture:**\n{existing_architecture}\n\n")

        if constraints:
            lines.append(f"**Constraints:**\n")
            for c in constraints:
                lines.append(f"- {c}\n")
            lines.append("\n")

        lines.extend([
            f"## Decision\n\n",
            f"TBD after options analysis\n\n",
            f"## Options Considered\n\n",
            f"### Option A: [Name]\n\n",
            f"**Pros:**\n- ...\n\n",
            f"**Cons:**\n- ...\n\n",
            f"### Option B: [Name]\n\n",
            f"**Pros:**\n- ...\n\n",
            f"**Cons:**\n- ...\n\n",
            f"## Consequences\n\n",
            f"### Positive\n\n",
            f"- ...\n\n",
            f"### Negative\n\n",
            f"- ...\n\n",
            f"## Recommendation\n\n",
            f"Proceed with Option [A/B] because [rationale]\n",
        ])

        return "".join(lines)
