"""agent_list Tool — 列出所有已配置的 Agent（M12 Multi-Agent）"""

from __future__ import annotations

from ..base import Tool, ToolResult


class AgentListTool(Tool):
    """agent_list 工具 — 列出所有已注册的 agent"""
    name = "agent_list"
    description = "List all configured agents"

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "Filter by tools, e.g. 'read,grep'",
                },
            },
        }

    async def execute(self, filter: str | None = None) -> ToolResult:
        from auton.agent import AgentManager

        manager = AgentManager()
        if filter:
            tool_names = [t.strip() for t in filter.split(",")]
            agents = manager.list_by_tools(tool_names)
            header = f"Agents supporting tools: {filter}"
        else:
            agents = manager.list()
            header = "All Agents"

        if not agents:
            return ToolResult(content="No agents found.", success=False)

        source_icon = {
            "builtin": "🔧",
            "user": "👤",
            "project": "📁",
            "plugin": "🔌",
        }

        lines = [f"## {header}\n"]
        for agent in agents:
            icon = source_icon.get(agent.source, "?")
            tools_str = ", ".join(agent.tools) if agent.tools else "(all tools)"
            lines.append(f"**{icon} `{agent.name}`**  [{agent.source}]")
            lines.append(f"  {agent.description}")
            lines.append(f"  tools: {tools_str}")
            if agent.model:
                lines.append(f"  model: {agent.model}")
            lines.append("")

        return ToolResult(content="\n".join(lines))
