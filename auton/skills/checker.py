"""Skills — dependency checker: verifies skill bins/permissions are available."""

from __future__ import annotations

import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from loguru import logger

from .registry import SkillRegistry


@dataclass
class CheckResult:
    """检查结果"""

    skill_name: str
    passed: bool
    errors: list[str] = None
    warnings: list[str] = None
    missing_bins: list[str] = None
    permission_issues: list[str] = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if self.missing_bins is None:
            self.missing_bins = []
        if self.permission_issues is None:
            self.permission_issues = []


class SkillChecker:
    """技能依赖检查器

    检查：
      - required_bins 是否在 PATH 中可执行
      - scripts/ 目录下的脚本是否有执行权限
    """

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self._registry = registry or SkillRegistry.get_instance()
        self._logger = logger.bind(name="SkillChecker")

    def check_all(self) -> list[CheckResult]:
        """检查所有已注册的 Skill"""
        self._registry.ensure_loaded()
        results = []
        for skill in self._registry:
            results.append(self.check_skill(skill.name))
        return results

    def check_skill(self, name: str) -> CheckResult:
        """检查单个 Skill"""
        skill = self._registry.get(name)
        if skill is None:
            return CheckResult(skill_name=name, passed=False, errors=[f"Skill '{name}' not found"])

        result = CheckResult(skill_name=name, passed=True)

        # 检查 required_bins
        for bin_name in skill.required_bins:
            if not self._is_executable(bin_name):
                result.missing_bins.append(bin_name)
                result.passed = False
                result.errors.append(f"Required binary '{bin_name}' not found in PATH")

        # 检查 scripts/ 权限
        for script in skill.list_scripts():
            if not self._is_executable(script):
                result.permission_issues.append(str(script))
                result.warnings.append(
                    f"Script '{script.name}' is not executable. Run: chmod +x {script}"
                )

        return result

    def _is_executable(self, bin_name: str) -> bool:
        """检查命令是否在 PATH 中可执行"""
        path = shutil.which(bin_name)
        return path is not None

    def check_all_and_report(self) -> str:
        """检查所有 Skill 并生成报告"""
        results = self.check_all()
        lines = ["## Skill Dependency Check\n"]

        all_passed = True
        for result in results:
            if not result.passed:
                all_passed = False

        if all_passed:
            lines.append("✅ All skills have their dependencies satisfied.\n")
        else:
            lines.append("❌ Some skills have missing dependencies:\n")

        for result in results:
            emoji = "✅" if result.passed else "❌"
            lines.append(f"\n### {emoji} {result.skill_name}")

            if result.missing_bins:
                for bin_name in result.missing_bins:
                    lines.append(f"  - Missing binary: `{bin_name}`")
            if result.permission_issues:
                for issue in result.permission_issues:
                    lines.append(f"  - Permission issue: `{issue}`")
            if result.warnings:
                for warning in result.warnings:
                    lines.append(f"  - Warning: {warning}")

        return "\n".join(lines)
