"""Grep Tool — 文件内容搜索"""

from __future__ import annotations

import re
from pathlib import Path

from ..base import Tool, ToolResult
from ..file_filter import should_skip_for_search


class GrepTool(Tool):
    name = "grep"
    description = (
        "Search for a pattern in files. "
        "Automatically skips binary files, compiled caches (__pycache__, .pyc), "
        "version control dirs (.git), session logs, and other noise."
    )

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in",
                },
                "glob": {
                    "type": "string",
                    "description": "Only match files matching this glob (e.g. '*.py')",
                },
                "context": {
                    "type": "integer",
                    "description": "Number of context lines before/after each match",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        glob: str | None = None,
        context: int = 2,
    ) -> ToolResult:
        try:
            results: list[str] = []
            base = Path(path)
            for f in base.rglob(glob or "*"):
                if not f.is_file():
                    continue
                # 跳过二进制文件、编译缓存目录、session 日志等噪声
                if should_skip_for_search(f):
                    continue
                try:
                    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                except Exception:
                    continue
                for i, line in enumerate(lines):
                    if re.search(pattern, line):
                        ctx_before = max(0, i - context)
                        ctx_after = min(len(lines) - 1, i + context)
                        snippet = "\n".join(
                            f"{j+1}: {lines[j]}" for j in range(ctx_before, ctx_after + 1)
                        )
                        results.append(f"{f}:{i+1}\n{snippet}\n")
            output = "\n".join(results) or "(no matches)"
            return ToolResult(content=output)
        except Exception as exc:
            return ToolResult(content=str(exc), success=False, error=str(exc))
