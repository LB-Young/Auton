"""Glob Tool — 文件名模式匹配"""

from __future__ import annotations

from pathlib import Path

from ..base import Tool, ToolResult
from ..file_filter import should_skip_for_search


class GlobTool(Tool):
    name = "glob"
    description = (
        "List files matching a glob pattern. "
        "Automatically excludes binary files, __pycache__, .git, node_modules, "
        "session logs, and other irrelevant paths."
    )

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
            root = Path(path)
            matches = [
                m for m in sorted(root.glob(pattern))
                if m.is_file() and not should_skip_for_search(m)
                # 目录不过滤，只过滤文件（让 LLM 仍能看到目录结构）
                or m.is_dir()
            ]
            listing = "\n".join(str(m) for m in matches)
            return ToolResult(content=listing or "(no matches)")
        except Exception as exc:
            return ToolResult(content=str(exc), success=False, error=str(exc))
