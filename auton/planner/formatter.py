"""Planner — 计划格式化器

将 Plan 渲染为 Markdown（带 Mermaid 流程图）。
"""

from __future__ import annotations

from loguru import logger

from .types import Alternative, Plan, PlanStep, Risk, RiskLevel
from .risks import RiskAnalysis


class PlanFormatter:
    """将 Plan 结构化渲染为 Markdown"""

    RISK_EMOJI: dict[RiskLevel, str] = {
        "low": "🟢 low",
        "medium": "🟡 medium",
        "high": "🔴 high",
        "critical": "🔴🔴 critical",
    }

    def __init__(self) -> None:
        self._logger = logger.bind(name="PlanFormatter")

    def format(self, plan: Plan, analysis: RiskAnalysis | None = None) -> str:
        """将 Plan 渲染为完整的 Markdown 文档"""
        parts: list[str] = []

        # Header
        parts.append(self._header(plan))
        parts.append("")

        # 概览
        parts.append(self._overview(plan))
        parts.append("")

        # 流程图
        if plan.steps:
            parts.append(self._flowchart(plan))
            parts.append("")

        # 详细步骤
        if plan.steps:
            parts.append(self._steps(plan))
            parts.append("")

        # 风险分析
        if plan.risks or (analysis and analysis.global_risks):
            parts.append(self._risks(plan, analysis))
            parts.append("")

        # 替代方案
        if plan.alternatives:
            parts.append(self._alternatives(plan))
            parts.append("")

        # 操作指引
        parts.append(self._action_guide(plan))

        return "\n".join(parts)

    def _header(self, plan: Plan) -> str:
        """计划头部"""
        status_icon = {
            "draft": "📝",
            "proposed": "📋",
            "confirmed": "✅",
            "in_progress": "🔄",
            "completed": "🎉",
            "cancelled": "❌",
            "failed": "❌",
        }.get(plan.status, "📋")

        risk_emoji = self.RISK_EMOJI.get(plan.estimated_risk, "⚪")

        return (
            f"## {status_icon} 计划: {plan.id}\n\n"
            f"**任务**: {plan.task}\n"
            f"**目标**: {plan.goal or '（见任务描述）'}\n"
            f"**步骤数**: {len(plan.steps)}\n"
            f"**整体风险**: {risk_emoji}\n"
            f"**置信度**: {plan.confidence:.0%}\n"
            f"**创建时间**: {plan.created_at.strftime('%Y-%m-%d %H:%M')}"
        )

    def _overview(self, plan: Plan) -> str:
        """概览表格"""
        lines = ["### 📊 概览\n"]
        lines.append("| 维度 | 值 |")
        lines.append("|------|------|")
        lines.append(f"| 任务 | {plan.task[:60]}{'...' if len(plan.task) > 60 else ''} |")
        lines.append(f"| 步骤数 | {len(plan.steps)} |")
        lines.append(f"| 风险等级 | {self.RISK_EMOJI.get(plan.estimated_risk, '⚪')} |")
        lines.append(f"| 置信度 | {plan.confidence:.0%} |")
        if plan.estimated_steps:
            lines.append(f"| 预计完成步骤 | {plan.estimated_steps} |")
        return "\n".join(lines)

    def _flowchart(self, plan: Plan) -> str:
        """Mermaid 流程图"""
        if not plan.steps:
            return ""

        lines = ["### 🔀 执行流程\n"]
        lines.append("```mermaid")
        lines.append("graph LR")
        lines.append("    %% 执行流程图")

        # 为每个步骤生成节点
        node_ids: dict[int, str] = {}
        for step in plan.steps:
            node_id = f"S{step.index}"
            node_ids[step.index] = node_id
            # 截断描述用于显示
            desc_short = step.description[:30].replace('"', "'")
            lines.append(f'    {node_id}["{desc_short}"]')

        # 生成依赖边
        for step in plan.steps:
            node_id = node_ids[step.index]
            for dep_idx in step.depends_on:
                dep_id = node_ids.get(dep_idx, f"S{dep_idx}")
                lines.append(f"    {dep_id} --> {node_id}")

        # 如果没有依赖关系，添加顺序连接
        if not any(step.depends_on for step in plan.steps):
            for i in range(len(plan.steps) - 1):
                lines.append(f"    S{i+1} --> S{i+2}")

        lines.append("```")
        return "\n".join(lines)

    def _steps(self, plan: Plan) -> str:
        """详细步骤列表"""
        lines = ["### 📋 详细步骤\n"]

        for step in plan.steps:
            risk_str = ""
            if step.risk:
                risk_str = f" **{step.risk.emoji()} {step.risk.level}**"

            lines.append(f"**{step.index}. {step.description}**{risk_str}")

            if step.tool:
                lines.append(f"   - 工具: `{step.tool}`")
                if step.params:
                    param_str = ", ".join(
                        f"`{k}={v!r}"[:50] + ("..." if len(str(v)) > 50 else "")
                        for k, v in list(step.params.items())[:3]
                    )
                    lines.append(f"   - 参数: {param_str}")

            if step.depends_on:
                dep_str = ", ".join(f"步骤 {d}" for d in step.depends_on)
                lines.append(f"   - 依赖: {dep_str}")

            lines.append(f"   - 置信度: {step.confidence:.0%}")

            if step.alternatives:
                lines.append(f"   - 备选: {', '.join(step.alternatives[:2])}")

            lines.append("")

        return "\n".join(lines)

    def _risks(self, plan: Plan, analysis: RiskAnalysis | None) -> str:
        """风险分析表格"""
        lines = ["### ⚠️ 风险分析\n"]

        # 整体风险
        if analysis and analysis.warnings:
            lines.append("**⚡ 警告:**")
            for w in analysis.warnings:
                lines.append(f"- {w}")
            lines.append("")

        # 全局风险表
        all_risks = list(plan.risks)
        if analysis:
            all_risks.extend(analysis.global_risks)

        if all_risks:
            lines.append("| 风险 | 等级 | 缓解措施 |")
            lines.append("|------|------|----------|")
            seen: set[str] = set()
            for risk in all_risks:
                key = risk.description
                if key in seen:
                    continue
                seen.add(key)
                mitigation = risk.mitigation or "—"
                lines.append(
                    f"| {risk.description} | "
                    f"{self.RISK_EMOJI.get(risk.level, '⚪')} | "
                    f"{mitigation} |"
                )
            lines.append("")

        # 步骤级风险
        if analysis and analysis.step_risks:
            lines.append("**步骤级风险:**")
            for idx, risk in sorted(analysis.step_risks.items()):
                lines.append(
                    f"- 步骤 {idx}: {risk.emoji()} {risk.description}"
                    + (f" → {risk.mitigation}" if risk.mitigation else "")
                )

        return "\n".join(lines)

    def _alternatives(self, plan: Plan) -> str:
        """替代方案"""
        lines = ["### 🔄 替代方案\n"]

        for i, alt in enumerate(plan.alternatives, start=1):
            confidence_icon = {
                "high": "🟢",
                "medium": "🟡",
                "low": "🟠",
            }.get(alt.confidence, "⚪")

            lines.append(f"**方案 {i}: {alt.name}** {confidence_icon}\n")
            lines.append(f"{alt.description}")

            if alt.tradeoffs:
                lines.append(f"\n权衡: {alt.tradeoffs}")

            if alt.changes:
                lines.append("\n具体差异:")
                for change in alt.changes[:3]:
                    lines.append(f"- {change}")

            lines.append("")

        return "\n".join(lines)

    def _action_guide(self, plan: Plan) -> str:
        """操作指引"""
        return (
            "---\n\n"
            "## 📌 确认执行\n\n"
            "请回复以下选项之一：\n\n"
            "| 回复 | 含义 |\n"
            "|------|------|\n"
            "| `ok` / `执行` / `好的` | 确认计划，开始执行 |\n"
            "| `跳过` | 跳过计划，直接用自然语言继续 |\n"
            "| `修改步骤 N: <描述>` | 修改第 N 步后继续执行 |\n"
            "| `取消` | 取消计划 |\n\n"
            "**Tip**: 可以直接用自然语言要求修改某一步骤。"
        )

    def format_step_confirm(
        self,
        plan: Plan,
        step_idx: int,
        confirmed: bool = True,
    ) -> str:
        """格式化单个步骤确认消息"""
        if step_idx > len(plan.steps):
            return f"❌ 计划只有 {len(plan.steps)} 个步骤，不存在步骤 {step_idx}"

        step = plan.steps[step_idx - 1]
        emoji = "✅" if confirmed else "⏭️"

        return (
            f"{emoji} **步骤 {step_idx}**: {step.description}\n\n"
            f"工具: `{step.tool or '（无需工具）'}`\n"
            f"置信度: {step.confidence:.0%}\n"
        )

    def format_completion(self, plan: Plan) -> str:
        """格式化计划完成消息"""
        duration = ""
        if plan.completed_at:
            delta = plan.completed_at - plan.created_at
            mins = int(delta.total_seconds() / 60)
            duration = f"（用时约 {mins} 分钟）"

        return (
            f"🎉 **计划执行完成**: {plan.id} {duration}\n\n"
            f"完成了 {len(plan.steps)} 个步骤。\n"
            f"如需查看详情，可使用 `/memory search {plan.task[:20]}` 保存本次经验。"
        )
