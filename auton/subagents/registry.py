"""Subagents — SubagentRegistry: 全局单例注册表"""

from __future__ import annotations

from loguru import logger

from .base import BaseSubagent
from .types import SubagentConfig


class SubagentRegistry:
    """全局 Subagent 注册表（单例）"""

    _instance: "SubagentRegistry | None" = None

    def __init__(self) -> None:
        self._by_name: dict[str, BaseSubagent] = {}
        self._logger = logger.bind(name="SubagentRegistry")

    @classmethod
    def get_instance(cls) -> "SubagentRegistry":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._load_built_ins()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（测试用）"""
        cls._instance = None

    def _load_built_ins(self) -> None:
        """延迟导入并注册所有内置 Subagent"""
        subagent_map = [
            ("planner", ".planner", "PlannerSubagent"),
            ("debugging", ".debugging", "DebuggingSubagent"),
            ("tdd", ".tdd", "TDDRunnerSubagent"),
            ("code_review", ".code_review", "CodeReviewSubagent"),
            ("security", ".security", "SecurityReviewSubagent"),
            ("refactor", ".refactor", "RefactorCleanerSubagent"),
            ("architect", ".architect", "ArchitectureAdvisorSubagent"),
            ("delegator", ".delegator", "TaskDelegatorSubagent"),
        ]

        for name, module_path, cls_name in subagent_map:
            try:
                import importlib
                module = importlib.import_module(module_path, package=__package__)
                subagent_cls = getattr(module, cls_name)
                self.register_single(subagent_cls())
            except ImportError:
                self._logger.debug("subagent {n} not available yet", n=name)

        self._logger.info("loaded {n} built-in subagents", n=len(self._by_name))

    def register_single(self, instance: BaseSubagent) -> None:
        self._by_name[instance.name] = instance

    def get(self, name: str) -> BaseSubagent | None:
        return self._by_name.get(name)

    def list_all(self) -> list[BaseSubagent]:
        return list(self._by_name.values())

    def list_configs(self) -> list[SubagentConfig]:
        return [sub.config() for sub in self.list_all()]

    def get_system_prompt(self, name: str) -> str | None:
        sub = self.get(name)
        return sub.system_prompt() if sub else None
