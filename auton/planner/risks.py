"""Planner — 风险分析器

分析计划步骤和整体任务的风险。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger

from .types import PlanStep, Risk, RiskLevel


@dataclass
class RiskAnalysis:
    step_risks: dict[int, Risk]       # index → Risk
    global_risks: list[Risk]           # 整体风险
    overall_level: RiskLevel           # 整体风险等级
    warnings: list[str]               # 警告信息


# ─── 风险模式 ─────────────────────────────────────────────────────────────────

# 工具级风险模式
RISKY_BASH_PATTERNS = [
    (r"\brm?\s+", "rm/rm -rf 慎用，可能删除文件"),
    (r"\bsudo\s+", "sudo 提权操作"),
    (r"\bdrop\s+database", "DROP DATABASE 不可逆操作"),
    (r"\bdelete\s+from\s+\w+", "DELETE FROM 无 WHERE 条件可能清空表"),
    (r"\|\s*sh\b", "管道到 shell 存在注入风险"),
    (r"\bcurl\b.*\b-w\b", "curl 可能发起网络请求"),
]

RISKY_TOOLS = {
    "bash": "shell 命令，存在执行风险",
    "write": "写文件，可能覆盖现有内容",
    "edit": "修改文件，可能引入错误",
}

# 语义风险关键词
RISK_KEYWORDS: dict[str, tuple[RiskLevel, str]] = {
    "重构": ("medium", "重构有破坏现有功能的风险"),
    "迁移": ("medium", "数据迁移存在丢失风险，建议备份"),
    "部署": ("high", "部署操作可能影响线上服务"),
    "数据库": ("high", "数据库操作不可逆"),
    "密码": ("high", "密码/密钥处理需格外小心"),
    "认证": ("high", "认证逻辑修改可能阻止用户登录"),
    "支付": ("critical", "支付相关操作风险极高"),
    "删除": ("high", "删除操作不可逆"),
    "修改": ("medium", "修改现有代码可能引入 bug"),
    "depoly": ("high", "部署操作可能影响线上服务"),
    "migration": ("medium", "数据迁移存在丢失风险"),
    "refactor": ("medium", "重构有破坏现有功能的风险"),
    "delete": ("high", "删除操作不可逆"),
    "auth": ("high", "认证逻辑修改可能阻止用户登录"),
    "payment": ("critical", "支付相关操作风险极高"),
}

# 高风险文件路径
RISKY_PATHS = [
    r"\.env$",
    r"config.*\.yaml$",
    r"config.*\.json$",
    r"\.key$",
    r"\.pem$",
    r"credentials",
    r"password",
]


class RiskAnalyzer:
    """风险分析器"""

    def __init__(self) -> None:
        self._logger = logger.bind(name="RiskAnalyzer")

    def analyze(self, steps: list[dict]) -> RiskAnalysis:
        """分析步骤列表的风险"""
        step_risks: dict[int, Risk] = {}
        global_risks: list[Risk] = []
        warnings: list[str] = []
        overall_highest: RiskLevel = "low"

        for step_dict in steps:
            idx = step_dict.get("index", 0)
            desc = step_dict.get("description", "")
            tool = step_dict.get("tool")
            params = step_dict.get("params", {})

            risk = self._analyze_step(desc, tool, params)
            if risk:
                step_risks[idx] = risk
                if risk.level == "high":
                    overall_highest = "high"
                elif risk.level == "medium" and overall_highest != "high":
                    overall_highest = "medium"

        # 全局风险
        task_text = " ".join(s.get("description", "") for s in steps)
        for keyword, (level, desc) in RISK_KEYWORDS.items():
            if keyword.lower() in task_text.lower():
                existing = any(r.description == desc for r in global_risks)
                if not existing:
                    global_risks.append(Risk(level=level, description=desc))
                    if level == "high":
                        overall_highest = "high"
                    elif level == "medium" and overall_highest != "high":
                        overall_highest = "medium"

        # 警告
        if len(steps) > 10:
            warnings.append(f"计划包含 {len(steps)} 个步骤，建议拆分为子计划")

        if not step_risks and not global_risks:
            global_risks.append(Risk(
                level="low",
                description="无明显风险，步骤可安全执行",
            ))

        return RiskAnalysis(
            step_risks=step_risks,
            global_risks=global_risks,
            overall_level=overall_highest,
            warnings=warnings,
        )

    def _analyze_step(
        self,
        description: str,
        tool: str | None,
        params: dict,
    ) -> Risk | None:
        """分析单个步骤的风险"""
        desc_lower = description.lower()

        # 1. 检查工具风险
        if tool in RISKY_TOOLS:
            level = "medium" if tool in {"write", "edit"} else "high"
            return Risk(
                level=level,
                description=RISKY_TOOLS[tool],
                mitigation=f"执行前确认目标路径和内容",
            )

        # 2. 检查 bash 命令风险
        if tool == "bash":
            cmd = params.get("command", "")
            for pattern, reason in RISKY_BASH_PATTERNS:
                if re.search(pattern, cmd, re.IGNORECASE):
                    return Risk(
                        level="high",
                        description=reason,
                        mitigation="确认命令无误后再执行，考虑先 dry-run",
                    )

        # 3. 检查参数中的敏感路径
        param_str = str(params)
        for risky in RISKY_PATHS:
            if re.search(risky, param_str, re.IGNORECASE):
                return Risk(
                    level="high",
                    description=f"涉及敏感路径：{risky}",
                    mitigation="确认文件路径正确，避免误删",
                )

        # 4. 检查语义关键词
        for keyword, (level, reason) in RISK_KEYWORDS.items():
            if keyword.lower() in desc_lower:
                return Risk(
                    level=level,
                    description=reason,
                    mitigation=self._get_mitigation(keyword),
                )

        return None

    def _get_mitigation(self, keyword: str) -> str:
        """获取缓解措施"""
        mitigations: dict[str, str] = {
            "重构": "在独立分支执行，确保测试覆盖",
            "迁移": "执行前备份数据，在低峰期操作",
            "部署": "使用蓝绿部署，保留回滚能力",
            "数据库": "使用事务，备份数据",
            "删除": "确认无误后执行，考虑软删除",
            "修改": "先在测试环境验证",
            "refactor": "在独立分支执行，确保测试覆盖",
            "migration": "执行前备份数据，在低峰期操作",
            "depoly": "使用蓝绿部署，保留回滚能力",
            "delete": "确认无误后执行，考虑软删除",
        }
        return mitigations.get(keyword, "谨慎操作，执行前确认")

    @staticmethod
    def risk_level_score(level: RiskLevel) -> int:
        """风险等级转分数（用于排序）"""
        return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(level, 0)
