"""Tools Registry — 工具注册表

统一管理所有工具（内置 + MCP + 插件）。
SessionProcessor 通过注册表获取工具，无须感知工具来源差异。

设计要点：
  - 内置工具：自动注册
  - MCP 工具：通过 MCP client 动态注册
  - 插件工具：通过 plugin loader 动态注册
  - 支持同名工具覆盖（高优先级覆盖低优先级）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from .base import Tool

if TYPE_CHECKING:
    from ..llm.base import LLMProvider


@dataclass
class ToolMetadata:
    """工具元数据"""
    source: str  # "builtin" | "mcp:<server>" | "plugin:<name>"
    enabled: bool = True
    blocked: bool = False  # 用户可禁用特定工具


class ToolRegistry:
    """工具注册表 — 统一管理所有工具

    用法：
        registry = ToolRegistry()
        registry.register_builtin(ReadTool())
        registry.register_mcp_tools("github", [tool1, tool2])
        tools = registry.get_tools()
        tool = registry.get("read")
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._metadata: dict[str, ToolMetadata] = {}
        self._mcp_clients: dict[str, Any] = {}  # server_name -> MCP client
        self._logger = logger.bind(name="ToolRegistry")

    # ─── 注册 ───────────────────────────────────────────────────────────────

    def register(self, tool: Tool, *, source: str = "builtin") -> None:
        """注册单个工具"""
        if tool.name in self._tools:
            old_meta = self._metadata.get(tool.name)
            self._logger.warning(
                "tool {name} already registered (source={old}), replacing with source={new}",
                name=tool.name,
                old=old_meta.source if old_meta else "?",
                new=source,
            )
        self._tools[tool.name] = tool
        self._metadata[tool.name] = ToolMetadata(source=source)
        self._logger.debug("registered tool {name} from {source}", name=tool.name, source=source)

    def register_builtin(self, tool: Tool) -> None:
        """注册内置工具"""
        self.register(tool, source="builtin")

    def register_mcp_tools(self, server: str, tools: list[Tool]) -> None:
        """注册 MCP server 提供的工具"""
        for tool in tools:
            self.register(tool, source=f"mcp:{server}")

    def register_plugin_tools(self, plugin_name: str, tools: list[Tool]) -> None:
        """注册插件提供的工具"""
        for tool in tools:
            self.register(tool, source=f"plugin:{plugin_name}")

    def register_batch(self, tools: list[Tool], *, source: str = "builtin") -> None:
        """批量注册工具"""
        for tool in tools:
            self.register(tool, source=source)

    # ─── 查询 ───────────────────────────────────────────────────────────────

    def get(self, name: str) -> Tool | None:
        """根据名称查找工具"""
        return self._tools.get(name)

    def get_metadata(self, name: str) -> ToolMetadata | None:
        """获取工具元数据"""
        return self._metadata.get(name)

    def get_tools(self, *, enabled_only: bool = True) -> list[Tool]:
        """获取所有已注册工具"""
        if enabled_only:
            return [
                tool
                for tool in self._tools.values()
                if self._metadata.get(tool.name, ToolMetadata(source="?")).enabled
                and not self._metadata.get(tool.name, ToolMetadata(source="?")).blocked
            ]
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        """列出所有已注册工具名称"""
        return list(self._tools.keys())

    def list_by_source(self, source_prefix: str) -> list[Tool]:
        """按来源筛选工具"""
        return [
            self._tools[name]
            for name, meta in self._metadata.items()
            if meta.source.startswith(source_prefix)
        ]

    def schemas(self) -> list[dict[str, Any]]:
        """获取所有工具的 schema（供 LLM 使用）"""
        return [tool.schema() for tool in self.get_tools()]

    # ─── 状态管理 ───────────────────────────────────────────────────────────

    def enable(self, name: str) -> bool:
        """启用工具"""
        if name not in self._tools:
            return False
        self._metadata[name].enabled = True
        self._logger.info("enabled tool {name}", name=name)
        return True

    def disable(self, name: str) -> bool:
        """禁用工具"""
        if name not in self._tools:
            return False
        self._metadata[name].enabled = False
        self._logger.info("disabled tool {name}", name=name)
        return True

    def block(self, name: str) -> bool:
        """阻止工具（用户级别禁用）"""
        if name not in self._tools:
            return False
        self._metadata[name].blocked = True
        self._logger.info("blocked tool {name}", name=name)
        return True

    def unblock(self, name: str) -> bool:
        """解除阻止"""
        if name not in self._tools:
            return False
        self._metadata[name].blocked = False
        self._logger.info("unblocked tool {name}", name=name)
        return True

    # ─── MCP 客户端管理 ─────────────────────────────────────────────────────

    def set_mcp_client(self, server: str, client: Any) -> None:
        """设置 MCP server 客户端（供 MCP tool execute 时调用）"""
        self._mcp_clients[server] = client

    def get_mcp_client(self, server: str) -> Any | None:
        """获取 MCP server 客户端"""
        return self._mcp_clients.get(server)

    # ─── 内省 ───────────────────────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        """返回注册表摘要"""
        by_source: dict[str, int] = {}
        for meta in self._metadata.values():
            by_source[meta.source] = by_source.get(meta.source, 0) + 1
        return {
            "total": len(self._tools),
            "by_source": by_source,
            "tools": {name: meta.source for name, meta in self._metadata.items()},
        }

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# ─── 全局注册表 ──────────────────────────────────────────────────────────────

_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """获取全局工具注册表（懒加载单例）"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _load_builtin_tools(_registry)
    return _registry


def _load_builtin_tools(registry: ToolRegistry) -> None:
    """加载所有内置工具"""
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

    builtins = [
        ReadTool(),
        WriteTool(),
        EditTool(),
        GlobTool(),
        GrepTool(),
        BashTool(),
        WebSearchTool(),
        WebFetchTool(),
        TaskCreateTool(),
        TaskGetTool(),
        TaskListTool(),
        TaskStopTool(),
        MCPTool(),
        AgentCreateTool(),
        AgentListTool(),
    ]
    registry.register_batch(builtins, source="builtin")
    logger.info("loaded {n} builtin tools", n=len(builtins))


def reset_registry() -> None:
    """重置注册表（主要用于测试）"""
    global _registry
    _registry = None
