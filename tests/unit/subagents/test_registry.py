"""Tests — SubagentRegistry 集成测试"""

import pytest

from auton.subagents import SubagentRegistry, BaseSubagent


@pytest.mark.unit
class TestSubagentRegistry:
    def test_singleton(self):
        """单例模式：多次 get_instance 返回同一实例"""
        # Reset singleton for test isolation
        SubagentRegistry.reset()
        r1 = SubagentRegistry.get_instance()
        r2 = SubagentRegistry.get_instance()
        assert r1 is r2
        SubagentRegistry.reset()

    def test_reset_clears_instance(self):
        """reset() 清除单例"""
        r1 = SubagentRegistry.get_instance()
        SubagentRegistry.reset()
        r2 = SubagentRegistry.get_instance()
        assert r1 is not r2

    def test_list_all_returns_8_subagents(self):
        """所有 8 个内置 subagent 都已注册"""
        SubagentRegistry.reset()
        registry = SubagentRegistry.get_instance()
        names = [s.name for s in registry.list_all()]
        expected = [
            "planner", "debugging", "tdd", "code-review",
            "security-review", "refactor", "architect", "delegator",
        ]
        for name in expected:
            assert name in names, f"{name} not in registry"

    def test_get_returns_correct_subagent(self):
        """get() 返回正确的 subagent"""
        registry = SubagentRegistry.get_instance()
        planner = registry.get("planner")
        assert planner is not None
        assert planner.name == "planner"
        assert planner.description

    def test_get_returns_none_for_unknown(self):
        """get() 对未知名称返回 None"""
        registry = SubagentRegistry.get_instance()
        unknown = registry.get("nonexistent")
        assert unknown is None

    def test_list_configs_returns_all_configs(self):
        """list_configs() 返回所有配置"""
        registry = SubagentRegistry.get_instance()
        configs = registry.list_configs()
        assert len(configs) == 8
        assert all(c.name for c in configs)

    def test_get_system_prompt_returns_prompt(self):
        """get_system_prompt() 返回非空字符串"""
        registry = SubagentRegistry.get_instance()
        prompt = registry.get_system_prompt("planner")
        assert prompt is not None
        assert len(prompt) > 100
