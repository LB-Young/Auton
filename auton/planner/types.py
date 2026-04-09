"""Planner — 数据结构定义

Plan / PlanStep / Risk / Alternative 等核心类型。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


# ─── 风险 ────────────────────────────────────────────────────────────────────

RiskLevel = Literal["low", "medium", "high"]


@dataclass
class Risk:
    """风险项"""
    level: RiskLevel
    description: str
    mitigation: str | None = None

    def emoji(self) -> str:
        return {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(self.level, "⚪")

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "description": self.description,
            "mitigation": self.mitigation,
        }


# ─── 步骤 ──────────────────────────────────────────────────────────────────────

StepStatus = Literal["pending", "running", "completed", "failed", "skipped"]


@dataclass
class PlanStep:
    """计划中的单个步骤"""
    index: int
    description: str
    tool: str | None = None
    params: dict = field(default_factory=dict)
    risk: Risk | None = None
    depends_on: list[int] = field(default_factory=list)
    confidence: float = 0.8
    status: StepStatus = "pending"
    result: str | None = None
    alternatives: list[str] = field(default_factory=list)  # 备选实现方式

    def is_atomic(self) -> bool:
        """是否原子步骤（无需进一步分解）"""
        return self.tool is not None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "description": self.description,
            "tool": self.tool,
            "params": self.params,
            "risk": self.risk.to_dict() if self.risk else None,
            "depends_on": self.depends_on,
            "confidence": self.confidence,
            "status": self.status,
            "result": self.result,
        }


# ─── 方案 ──────────────────────────────────────────────────────────────────────

PlanConfidence = Literal["high", "medium", "low"]


@dataclass
class Alternative:
    """替代方案"""
    name: str
    description: str
    changes: list[str] = field(default_factory=list)  # 与默认方案的具体差异
    confidence: PlanConfidence = "medium"
    tradeoffs: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "changes": self.changes,
            "confidence": self.confidence,
            "tradeoffs": self.tradeoffs,
        }


# ─── 计划 ──────────────────────────────────────────────────────────────────────

PlanStatus = Literal["draft", "proposed", "confirmed", "in_progress", "completed", "cancelled", "failed"]


@dataclass
class Plan:
    """完整执行计划"""
    task: str
    goal: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    alternatives: list[Alternative] = field(default_factory=list)
    estimated_steps: int = 0
    estimated_risk: RiskLevel = "medium"
    confidence: float = 0.7
    status: PlanStatus = "draft"
    id: str = field(default_factory=lambda: f"plan_{int(time.time())}")
    created_at: datetime = field(default_factory=datetime.now)
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None
    owner_session: str | None = None  # 所属 session_id
    parent_plan_id: str | None = None  # 父计划 ID（修改重生成时）

    def step_count(self) -> int:
        return len(self.steps)

    def total_risk(self) -> RiskLevel:
        """计算整体风险等级"""
        if any(r.level == "high" for r in self.risks):
            return "high"
        if any(r.level == "medium" for r in self.risks):
            return "medium"
        return "low"

    def dependency_graph(self) -> dict[int, list[int]]:
        """构建依赖图：step_index → [依赖的 step_indices]"""
        graph: dict[int, list[int]] = {}
        for step in self.steps:
            graph[step.index] = step.depends_on
        return graph

    def topologically_sorted(self) -> list[PlanStep]:
        """返回拓扑排序后的步骤（依赖优先）"""
        sorted_steps: list[PlanStep] = []
        remaining = {s.index: s for s in self.steps}
        added: set[int] = set()

        while remaining:
            for idx, step in list(remaining.items()):
                if all(d in added for d in step.depends_on):
                    sorted_steps.append(step)
                    added.add(idx)
                    del remaining[idx]
                    break
            else:
                # 循环依赖：按索引顺序
                for idx, step in remaining.items():
                    sorted_steps.append(step)
                    added.add(idx)
                break

        return sorted_steps

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task": self.task,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "risks": [r.to_dict() for r in self.risks],
            "alternatives": [a.to_dict() for a in self.alternatives],
            "estimated_steps": self.estimated_steps,
            "estimated_risk": self.estimated_risk,
            "confidence": self.confidence,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "owner_session": self.owner_session,
        }
