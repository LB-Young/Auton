"""Subagents — 内置 Subagent 集合

用法::

    registry = SubagentRegistry.get_instance()
    planner = registry.get("planner")
    result = await planner.run(context={"task": "实现登录功能"})
"""

from .base import BaseSubagent
from .registry import SubagentRegistry
from .types import SubagentConfig, SubagentPhase, SubagentResult

__all__ = [
    "BaseSubagent",
    "SubagentRegistry",
    "SubagentConfig",
    "SubagentPhase",
    "SubagentResult",
]
