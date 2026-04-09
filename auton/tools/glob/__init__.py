"""Glob Tool — 文件名模式匹配"""

from __future__ import annotations

from pathlib import Path

from ..base import Tool, ToolResult


class GlobTool(Tool):
    name = "glob"
    description = "List files matching a glob pattern"

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. '**/*.py')",
                },
                "path": {
                    "type": "string",
                    "description": "Root directory to search from",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, pattern: str, path: str = ".") -> ToolResult:
        try:
            matches = sorted(Path(path).glob(pattern))
            listing = "\n".join(str(m) for m in matches)
            return ToolResult(content=listing or "(no matches)")
        except Exception as exc:
            return ToolResult(content=str(exc), success=False, error=str(exc))
