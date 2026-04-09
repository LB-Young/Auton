"""Tools Base — 工具抽象"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


@dataclass
class ToolResult:
    """工具执行结果"""
    content: str
    success: bool = True
    error: str | None = None


class Tool(ABC):
    """Tool 抽象基类，子类通过 class 属性定义 name/description"""

    name: str
    description: str

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行工具，返回结果"""
        ...

    def schema(self) -> dict:
        """返回此工具的 JSON Schema（供 LLM 使用）"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema(),
        }

    def input_schema(self) -> dict:
        """返回 input_schema 子对象，子类可覆盖"""
        return {"type": "object", "properties": {}, "required": []}
