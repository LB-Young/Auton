"""Write Tool — 创建或覆盖文件"""

from __future__ import annotations

from pathlib import Path

from ..base import Tool, ToolResult


class WriteTool(Tool):
    name = "write"
    description = "Write content to a file (creates or overwrites)"

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        }

    async def execute(self, file_path: str, content: str) -> ToolResult:
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolResult(content=f"Written {len(content)} bytes to {file_path}")
        except Exception as exc:
            return ToolResult(content=str(exc), success=False, error=str(exc))
