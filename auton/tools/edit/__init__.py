"""Edit Tool — 原地编辑文件（替换字符串）"""

from __future__ import annotations

from pathlib import Path

from ..base import Tool, ToolResult


class EditTool(Tool):
    name = "edit"
    description = "Replace a string in an existing file (old_string → new_string)"

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact string to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement string",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    async def execute(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
    ) -> ToolResult:
        try:
            path = Path(file_path)
            if not path.exists():
                return ToolResult(content=f"File not found: {file_path}", success=False)

            original = path.read_text(encoding="utf-8")
            if old_string not in original:
                return ToolResult(
                    content=f"old_string not found in {file_path}",
                    success=False,
                    error="old_string not found",
                )

            new_content = original.replace(old_string, new_string, 1)
            path.write_text(new_content, encoding="utf-8")
            return ToolResult(content=f"Edited {file_path}")
        except Exception as exc:
            return ToolResult(content=str(exc), success=False, error=str(exc))
