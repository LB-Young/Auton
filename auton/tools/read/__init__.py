"""Read Tool — 读取文件内容"""

from __future__ import annotations

from pathlib import Path

from ..base import Tool, ToolResult
from ..file_filter import should_skip_for_read, binary_sniff


class ReadTool(Tool):
    name = "read"
    description = (
        "Read the content of a text file. "
        "Binary files (.pyc, .so, images, etc.) are automatically rejected."
    )

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

            # 扩展名过滤：拒绝二进制 / 编译产物
            skip, reason = should_skip_for_read(path)
            if skip:
                return ToolResult(content=reason, success=False)

            # 无扩展名或扩展名不在黑名单时，做二进制嗅探（检查 NULL 字节）
            if not path.suffix and binary_sniff(path):
                return ToolResult(
                    content=(
                        f"拒绝读取 `{path.name}`：文件头部含有二进制字节，"
                        "可能是编译产物或非文本文件。"
                    ),
                    success=False,
                )

            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            snippet = lines[offset : offset + limit] if limit else lines[offset:]
            content = "\n".join(snippet)
            prefix = f"[lines {offset}:{offset + len(snippet)}]\n"
            return ToolResult(content=prefix + content)
        except Exception as exc:
            return ToolResult(content=str(exc), success=False, error=str(exc))
