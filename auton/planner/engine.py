"""Planner — 主引擎

协调任务分解、风险分析、替代方案生成，提供统一规划接口。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from .decomposer import TaskDecomposer
from .formatter import PlanFormatter
from .risks import RiskAnalyzer, RiskAnalysis
from .types import Alternative, Plan, PlanStep, Risk, RiskLevel
from .storage import PlanStorage

if TYPE_CHECKING:
    from ..llm.base import LLMProvider


class Planner:
    """规划引擎主类

    使用示例：
      planner = Planner(llm=llm_provider)
      plan = planner.plan("重构 auth 模块")
      print(plan.format())
    """

    def __init__(
        self,
        llm: "LLMProvider | None" = None,
        storage: PlanStorage | None = None,
    ) -> None:
        self.llm = llm
        self.decomposer = TaskDecomposer(llm=llm)
        self.risk_analyzer = RiskAnalyzer()
        self.formatter = PlanFormatter()
        self.storage = storage or PlanStorage()
        self._logger = logger.bind(name="Planner")
        self._current_plan: Plan | None = None

    def plan(
        self,
        task: str,
        context: str = "",
        goal: str = "",
    ) -> Plan:
        """生成完整执行计划

        Args:
            task: 用户描述的任务
            context: 项目上下文（技术栈、目录结构等）
            goal: 明确的目标描述

        Returns:
            Plan 对象
        """
        self._logger.info("planning task: {t}", t=task[:80])

        # 1. 任务分解
        decomposition = self.decomposer.decompose(task, context)
        step_dicts = decomposition.steps

        # 2. 转换为 PlanStep
        steps = self._build_steps(step_dicts)

        # 3. 风险分析
        analysis = self.risk_analyzer.analyze(step_dicts)

        # 4. 填充步骤级风险
        for step in steps:
            if step.index in analysis.step_risks:
                step.risk = analysis.step_risks[step.index]

        # 5. 生成替代方案
        alternatives = self._generate_alternatives(task, steps)

        # 6. 构建 Plan
        plan = Plan(
            task=task,
            goal=goal or self._infer_goal(task),
            steps=steps,
            risks=analysis.global_risks,
            alternatives=alternatives,
            estimated_steps=len(steps),
            estimated_risk=analysis.overall_level,
            confidence=decomposition.confidence,
            status="proposed",
        )

        self._current_plan = plan
        self.storage.save(plan)
        self._logger.info(
            "plan created: {id}, {n} steps, risk={risk}",
            id=plan.id,
            n=len(steps),
            risk=analysis.overall_level,
        )
        return plan

    def modify_step(
        self,
        plan_id: str,
        step_index: int,
        new_description: str,
    ) -> Plan | None:
        """修改计划中的某个步骤，重新生成后续步骤"""
        plan = self.storage.load(plan_id)
        if not plan:
            self._logger.warning("plan not found: {id}", id=plan_id)
            return None

        if step_index < 1 or step_index > len(plan.steps):
            return None

        # 更新该步骤
        plan.steps[step_index - 1].description = new_description

        # 重新分析风险
        step_dicts = [s.to_dict() for s in plan.steps]
        analysis = self.risk_analyzer.analyze(step_dicts)

        for i, step in enumerate(plan.steps, start=1):
            step.risk = analysis.step_risks.get(i)

        plan.status = "proposed"
        plan.parent_plan_id = plan.id
        plan.id = f"plan_{int(plan.created_at.timestamp())}_v2"

        self.storage.save(plan)
        self._current_plan = plan
        return plan

    def confirm(self, plan_id: str) -> Plan | None:
        """确认计划"""
        plan = self.storage.load(plan_id)
        if not plan:
            return None
        plan.status = "confirmed"
        from datetime import datetime
        plan.confirmed_at = datetime.now()
        self.storage.save(plan)
        return plan

    def cancel(self, plan_id: str) -> Plan | None:
        """取消计划"""
        plan = self.storage.load(plan_id)
        if not plan:
            return None
        plan.status = "cancelled"
        self.storage.save(plan)
        return plan

    def complete(self, plan_id: str) -> Plan | None:
        """标记计划完成"""
        plan = self.storage.load(plan_id)
        if not plan:
            return None
        plan.status = "completed"
        from datetime import datetime
        plan.completed_at = datetime.now()
        self.storage.save(plan)
        return plan

    def format(self, plan: Plan, analysis: RiskAnalysis | None = None) -> str:
        """格式化计划为 Markdown"""
        return self.formatter.format(plan, analysis)

    def get_plan(self, plan_id: str) -> Plan | None:
        """获取计划"""
        return self.storage.load(plan_id)

    def list_plans(self, status: str | None = None) -> list[Plan]:
        """列出所有计划"""
        return self.storage.list_all(status=status)

    def get_current(self) -> Plan | None:
        """获取当前正在操作的计划"""
        return self._current_plan

    # ─── 内部 ─────────────────────────────────────────────────────────

    def _build_steps(self, step_dicts: list[dict]) -> list[PlanStep]:
        """将字典列表转换为 PlanStep 列表"""
        steps: list[PlanStep] = []

        for item in step_dicts:
            idx = item.get("index", len(steps) + 1)
            desc = item.get("description", "")
            tool = item.get("tool")
            params = item.get("params", {})
            depends_on = item.get("depends_on", [])
            confidence = item.get("confidence", 0.8)

            # 自动推断工具
            if tool is None:
                tool, params = TaskDecomposer.suggest_tool_for_step(desc)

            # 自动估计置信度
            if confidence == 0.8:
                confidence = TaskDecomposer.estimate_confidence(desc, tool)

            step = PlanStep(
                index=idx,
                description=desc,
                tool=tool,
                params=params,
                depends_on=depends_on,
                confidence=confidence,
            )
            steps.append(step)

        # 按 index 排序
        steps.sort(key=lambda s: s.index)
        return steps

    def _generate_alternatives(
        self,
        task: str,
        steps: list[PlanStep],
    ) -> list[Alternative]:
        """生成替代方案"""
        alternatives: list[Alternative] = []
        task_lower = task.lower()

        # 方案B: 渐进式重构
        if any(k in task_lower for k in ["重构", "修改", "重写", "refactor", "rewrite"]):
            alternatives.append(Alternative(
                name="渐进式重构（推荐）",
                description=(
                    "保留现有接口，逐步迁移到新实现。"
                    "每次只改一小部分，降低风险。"
                ),
                changes=[
                    "新增抽象层，不改动现有调用",
                    "逐模块迁移，而非一次性重写",
                    "每次迁移后运行测试验证",
                ],
                confidence="high",
                tradeoffs="耗时更长，但更安全",
            ))

        # 方案C: 完整重构
        if any(k in task_lower for k in ["重构", "refactor"]) and len(steps) > 3:
            alternatives.append(Alternative(
                name="完整重构",
                description="一步到位重新实现，删除旧代码。",
                changes=[
                    "先完整备份现有代码",
                    "在新分支实现全部功能",
                    "测试通过后替换",
                ],
                confidence="low",
                tradeoffs="速度快，但风险高，测试覆盖要求高",
            ))

        return alternatives

    def _infer_goal(self, task: str) -> str:
        """从任务描述推断目标"""
        # 简单启发式
        task_lower = task.lower()
        if "重构" in task or "refactor" in task_lower:
            return "在不改变外部行为的前提下改善代码质量"
        if "优化" in task or "optimize" in task_lower:
            return "提升性能或资源利用率"
        if "新增" in task or "add" in task_lower or "实现" in task:
            return "新增功能"
        if "修复" in task or "fix" in task_lower:
            return "修复问题"
        return ""
