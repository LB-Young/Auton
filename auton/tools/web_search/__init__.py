"""WebSearch Tool — 网络搜索"""

from __future__ import annotations

from ..base import Tool, ToolResult


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web for information"

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return",
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        num_results: int = 5,
    ) -> ToolResult:
        # TODO: integrate with exa-search or similar
        return ToolResult(
            content=f"[web_search stub] query={query!r} num_results={num_results}\n"
            "Web search not yet configured. Set EXA_API_KEY or implement search provider."
        )
