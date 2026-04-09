"""Tools — 内置工具集

工具注册表统一管理所有工具（内置 + MCP + 插件）。
推荐通过 `get_registry()` 获取工具，而非直接实例化：
    from auton.tools import get_registry
    registry = get_registry()
    tools = registry.get_tools()
    schema = registry.schemas()
"""

from __future__ import annotations

from .base import Tool, ToolResult
from .registry import get_registry, ToolRegistry, reset_registry

__all__ = [
    "Tool",
    "ToolResult",
    "get_registry",
    "ToolRegistry",
    "reset_registry",
]


def get_default_tools(permission_mode: str = "default", yes_all: bool = False) -> list[Tool]:
    """返回默认启用的工具列表（已注册到全局注册表）"""
    from .bash import BashTool
    from .edit import EditTool
    from .glob import GlobTool
    from .grep import GrepTool
    from .read import ReadTool
    from .write import WriteTool
    from .web_search import WebSearchTool
    from .web_fetch import WebFetchTool
    from .task_create import TaskCreateTool
    from .task_get import TaskGetTool
    from .task_list import TaskListTool
    from .task_stop import TaskStopTool
    from .mcp import MCPTool
    from .agent_create import AgentCreateTool
    from .agent_list import AgentListTool
    from .browser import BrowserTool

    return [
        ReadTool(),
        WriteTool(),
        EditTool(),
        GlobTool(),
        GrepTool(),
        BashTool(permission_mode=permission_mode, yes_all=yes_all),
        WebSearchTool(),
        WebFetchTool(),
        TaskCreateTool(),
        TaskGetTool(),
        TaskListTool(),
        TaskStopTool(),
        MCPTool(),
        AgentCreateTool(),
        AgentListTool(),
        BrowserTool(),
    ]
