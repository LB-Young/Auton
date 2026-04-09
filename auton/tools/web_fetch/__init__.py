"""WebFetch Tool — 抓取网页内容"""

from __future__ import annotations

from ..base import Tool, ToolResult


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch the content of a web page"

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum characters to return",
                },
            },
            "required": ["url"],
        }

    async def execute(self, url: str, max_length: int = 5000) -> ToolResult:
        return ToolResult(
            content=(
                "Fetching raw HTML is disabled to save tokens. "
                "Use the browser tool's snapshot action to inspect page content."
            ),
            success=False,
            error="html_fetch_blocked",
        )
