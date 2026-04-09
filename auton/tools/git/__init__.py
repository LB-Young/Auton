"""Git Tool — Git 操作代理（通过 bash 调用 git）"""

from __future__ import annotations

from ..base import Tool, ToolResult


class GitTool(Tool):
    name = "git"
    description = "Run a git command"

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "args": {
                    "type": "string",
                    "description": "git subcommand and arguments (e.g. 'status', 'log --oneline -5')",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory",
                },
            },
            "required": ["args"],
        }

    async def execute(self, args: str, cwd: str = ".") -> ToolResult:
        from ..bash import BashTool

        bash = BashTool()
        return await bash.execute(f"git {args}", cwd=cwd)
