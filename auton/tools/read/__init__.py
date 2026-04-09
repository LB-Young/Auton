"""Read Tool — 读取文件内容"""

from __future__ import annotations

from pathlib import Path

from ..base import Tool, ToolResult


class ReadTool(Tool):
    name = "read"
    description = "Read the full content of a file"

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (0-indexed)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read",
                },
            },
            "required": ["file_path"],
        }

    async def execute(
        self,
        file_path: str,
        offset: int = 0,
        limit: int | None = None,
    ) -> ToolResult:
        try:
            path = Path(file_path)
            if not path.exists():
                return ToolResult(content=f"File not found: {file_path}", success=False)
            if not path.is_file():
                return ToolResult(content=f"Not a file: {file_path}", success=False)

            lines = path.read_text(encoding="utf-8").splitlines()
            snippet = lines[offset : offset + limit] if limit else lines[offset:]
            content = "\n".join(snippet)
            prefix = f"[lines {offset}:{offset + len(snippet)}]\n"
            return ToolResult(content=prefix + content)
        except Exception as exc:
            return ToolResult(content=str(exc), success=False, error=str(exc))
