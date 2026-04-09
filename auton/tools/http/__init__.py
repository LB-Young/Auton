"""HTTP Tool — 发送 HTTP 请求"""

from __future__ import annotations

from ..base import Tool, ToolResult


class HTTPClientTool(Tool):
    name = "http"
    description = "Send an HTTP request"

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET, POST, PUT, DELETE, etc.)",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                },
                "url": {"type": "string", "description": "URL to request"},
                "headers": {"type": "object", "description": "HTTP headers"},
                "body": {"type": "string", "description": "Request body"},
            },
            "required": ["method", "url"],
        }

    async def execute(
        self,
        method: str = "GET",
        url: str = "",
        headers: dict | None = None,
        body: str | None = None,
    ) -> ToolResult:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                meth = getattr(client, method.lower())
                resp = await meth(url, headers=headers or {}, content=body)
                return ToolResult(
                    content=f"[{resp.status_code}] {resp.text[:2000]}"
                )
        except Exception as exc:
            return ToolResult(content=str(exc), success=False, error=str(exc))
