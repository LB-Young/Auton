"""Tests — BaseSubagent 集成测试"""

import pytest

from auton.subagents.base import BaseSubagent
from auton.subagents.types import SubagentPhase, SubagentResult
from datetime import datetime, timedelta


@pytest.mark.unit
class TestSubagentResult:
    def test_default_values(self):
        """默认字段值正确"""
        result = SubagentResult(name="test", success=True, phase=SubagentPhase.PLANNING)
        assert result.findings == []
        assert result.recommendations == []
        assert result.errors == []
        assert result.output == ""

    def test_duration_seconds_no_completion(self):
        """未完成时 duration_seconds 返回 0"""
        result = SubagentResult(name="test", success=True, phase=SubagentPhase.PLANNING)
        assert result.duration_seconds == 0.0

    def test_duration_seconds_with_completion(self):
        """完成时 duration_seconds 返回正确值"""
        result = SubagentResult(name="test", success=True, phase=SubagentPhase.COMPLETED)
        result.started_at = datetime(2024, 1, 1, 12, 0, 0)
        result.completed_at = datetime(2024, 1, 1, 12, 0, 5)
        assert result.duration_seconds == 5.0


@pytest.mark.unit
class TestConcreteSubagent:
    """测试一个具体的 BaseSubagent 子类"""

    async def test_run_returns_result(self):
        """run() 返回包含正确字段的 SubagentResult"""
        class DummySubagent(BaseSubagent):
            name = "dummy"
            description = "Dummy for testing"

            @classmethod
            def system_prompt(cls) -> str:
                return "Dummy prompt"

            async def _execute(self, context):
                return "output", ["finding"], ["recommendation"]

        agent = DummySubagent()
        result = await agent.run({})
        assert result.name == "dummy"
        assert result.success is True
        assert result.phase == SubagentPhase.COMPLETED
        assert result.output == "output"
        assert result.findings == ["finding"]
        assert result.recommendations == ["recommendation"]
        assert result.completed_at is not None

    async def test_run_catches_exception(self):
        """run() 捕获异常并设置 success=False"""
        class FailingSubagent(BaseSubagent):
            name = "failing"
            description = "Fails for testing"

            @classmethod
            def system_prompt(cls) -> str:
                return "Failing prompt"

            async def _execute(self, context):
                raise ValueError("test error")

        agent = FailingSubagent()
        result = await agent.run({})
        assert result.success is False
        assert "test error" in result.errors[0]
        assert result.phase == SubagentPhase.COMPLETED
