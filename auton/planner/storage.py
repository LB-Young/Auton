"""Planner — 计划持久化

将 Plan 保存到磁盘（~/.auton/plans/）。
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from .types import Alternative, Plan, PlanStep, Risk, RiskLevel, PlanStatus


class PlanStorage:
    """计划存储（持久化到 ~/.auton/plans/）"""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = storage_dir or Path("~/.auton/plans").expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logger.bind(name="PlanStorage")

    def save(self, plan: Plan) -> None:
        """保存计划到磁盘"""
        path = self._plan_path(plan.id)
        data = self._serialize(plan)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._logger.debug("saved plan {id} to {p}", id=plan.id, p=path)

    def load(self, plan_id: str) -> Plan | None:
        """从磁盘加载计划"""
        path = self._plan_path(plan_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return self._deserialize(data)
        except Exception as exc:
            self._logger.warning("failed to load plan {id}: {e}", id=plan_id, e=exc)
            return None

    def delete(self, plan_id: str) -> bool:
        """删除计划"""
        path = self._plan_path(plan_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_all(self, status: str | None = None) -> list[Plan]:
        """列出所有计划"""
        plans: list[Plan] = []
        for path in self.storage_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                plan = self._deserialize(data)
                if plan and (status is None or plan.status == status):
                    plans.append(plan)
            except Exception:
                continue
        plans.sort(key=lambda p: p.created_at, reverse=True)
        return plans

    def list_active(self) -> list[Plan]:
        """列出活跃计划（draft/proposed/confirmed/in_progress）"""
        active_statuses: set[str] = {"draft", "proposed", "confirmed", "in_progress"}
        all_plans = self.list_all()
        return [p for p in all_plans if p.status in active_statuses]

    def _plan_path(self, plan_id: str) -> Path:
        return self.storage_dir / f"{plan_id}.json"

    def _serialize(self, plan: Plan) -> dict:
        return plan.to_dict()

    def _deserialize(self, data: dict) -> Plan | None:
        try:
            # 重建 steps
            steps: list[PlanStep] = []
            for s in data.get("steps", []):
                risk = None
                if s.get("risk"):
                    r = s["risk"]
                    risk = Risk(level=r["level"], description=r["description"], mitigation=r.get("mitigation"))
                steps.append(PlanStep(
                    index=s["index"],
                    description=s["description"],
                    tool=s.get("tool"),
                    params=s.get("params", {}),
                    risk=risk,
                    depends_on=s.get("depends_on", []),
                    confidence=s.get("confidence", 0.8),
                    status=s.get("status", "pending"),
                    result=s.get("result"),
                ))

            # 重建 risks
            risks: list[Risk] = []
            for r in data.get("risks", []):
                risks.append(Risk(
                    level=r["level"],
                    description=r["description"],
                    mitigation=r.get("mitigation"),
                ))

            # 重建 alternatives
            alternatives: list[Alternative] = []
            for a in data.get("alternatives", []):
                alternatives.append(Alternative(
                    name=a["name"],
                    description=a["description"],
                    changes=a.get("changes", []),
                    confidence=a.get("confidence", "medium"),
                    tradeoffs=a.get("tradeoffs"),
                ))

            # 解析时间
            from datetime import datetime
            created_at = data.get("created_at")
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            else:
                created_at = datetime.now()

            confirmed_at = data.get("confirmed_at")
            if isinstance(confirmed_at, str):
                confirmed_at = datetime.fromisoformat(confirmed_at)

            completed_at = data.get("completed_at")
            if isinstance(completed_at, str):
                completed_at = datetime.fromisoformat(completed_at)

            return Plan(
                id=data["id"],
                task=data["task"],
                goal=data.get("goal", ""),
                steps=steps,
                risks=risks,
                alternatives=alternatives,
                estimated_steps=data.get("estimated_steps", 0),
                estimated_risk=data.get("estimated_risk", "medium"),
                confidence=data.get("confidence", 0.7),
                status=data.get("status", "draft"),
                created_at=created_at,
                confirmed_at=confirmed_at,
                completed_at=completed_at,
                owner_session=data.get("owner_session"),
                parent_plan_id=data.get("parent_plan_id"),
            )
        except Exception as exc:
            self._logger.warning("failed to deserialize plan: {e}", e=exc)
            return None
