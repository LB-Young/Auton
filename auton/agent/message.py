"""Agent Message — Part 化消息模型

一个 Message 由多个 Part 组成，每种 Part 独立更新：
  - TextPart:     助手回复正文（streaming 增量）
  - ReasoningPart: 思考过程（不暴露给用户，保留在 context）
  - ToolPart:     工具调用状态机
  - StepPart:     单步边界（files_changed 信息）
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional, Any

if TYPE_CHECKING:
    from .types import ToolStatus


# ─── Part 基类 ────────────────────────────────────────────────────────────────

class Part:
    """Part 基类，所有 Part 继承此类"""
    type: str

    def to_dict(self) -> dict:
        raise NotImplementedError


# ─── TextPart ────────────────────────────────────────────────────────────────

@dataclass
class TextPart(Part):
    """文本回复 Part（支持 streaming 增量）"""
    type: Literal["text"] = "text"
    content: str = ""

    def append(self, delta: str) -> None:
        """增量追加文本"""
        self.content += delta

    def to_dict(self) -> dict:
        return {"type": self.type, "content": self.content}


# ─── ReasoningPart ───────────────────────────────────────────────────────────

@dataclass
class ReasoningPart(Part):
    """思考过程 Part（不暴露给用户）"""
    type: Literal["reasoning"] = "reasoning"
    content: str = ""

    def append(self, delta: str) -> None:
        self.content += delta

    def to_dict(self) -> dict:
        return {"type": self.type, "content": self.content}


# ─── ToolPart ────────────────────────────────────────────────────────────────

@dataclass
class ToolPart(Part):
    """工具调用状态机"""
    type: Literal["tool"] = "tool"
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    status: Literal["pending", "running", "completed", "error"] = "pending"
    tool_output: Optional[str] = None
    tool_call_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "status": self.status,
            "tool_output": self.tool_output,
            "tool_call_id": self.tool_call_id,
        }


# ─── StepPart ───────────────────────────────────────────────────────────────

@dataclass
class StepPart(Part):
    """单步边界 Part（标记 step 起始/结束）"""
    type: Literal["step"] = "step"
    step_id: str = ""
    step_index: int = 0
    summary: str = ""
    files_changed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "step_id": self.step_id,
            "step_index": self.step_index,
            "summary": self.summary,
            "files_changed": self.files_changed,
        }


# ─── Message ────────────────────────────────────────────────────────────────

@dataclass
class Message:
    """消息：一个 role 下的多个 Part"""
    role: Literal["user", "assistant", "system"]
    parts: list[Part] = field(default_factory=list)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "parts": [p.to_dict() for p in self.parts],
            "message_id": self.message_id,
            "created_at": self.created_at,
        }

    # ─── Part 快捷操作 ────────────────────────────────────────────────────

    def add_text(self, content: str = "") -> TextPart:
        part = TextPart(content=content)
        self.parts.append(part)
        return part

    def add_reasoning(self, content: str = "") -> ReasoningPart:
        part = ReasoningPart(content=content)
        self.parts.append(part)
        return part

    def add_tool(
        self,
        tool_name: str,
        tool_input: dict,
        *,
        tool_call_id: str | None = None,
    ) -> ToolPart:
        part = ToolPart(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_call_id=tool_call_id or str(uuid.uuid4()),
        )
        self.parts.append(part)
        return part

    def add_step(
        self,
        step_id: str,
        step_index: int,
        *,
        summary: str = "",
        files_changed: list[str] | None = None,
    ) -> StepPart:
        part = StepPart(
            step_id=step_id,
            step_index=step_index,
            summary=summary,
            files_changed=files_changed or [],
        )
        self.parts.append(part)
        return part

    def get_text(self) -> str:
        """合并所有 TextPart 内容"""
        return "".join(p.content for p in self.parts if isinstance(p, TextPart))

    def get_tools(self) -> list[ToolPart]:
        return [p for p in self.parts if isinstance(p, ToolPart)]

    def is_empty(self) -> bool:
        return all(
            (isinstance(p, TextPart) and not p.content)
            for p in self.parts
        )

    # ─── 反序列化 ────────────────────────────────────────────────────────

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Message | None":
        """重建消息对象（用于 session 回放）"""
        if not record:
            return None

        # 兼容 append_user_message / append_system_message 的事件格式
        event_type = record.get("type")
        if event_type in {"user-message", "system"}:
            msg = cls(
                role="user" if event_type == "user-message" else "system",
                message_id=str(record.get("message_id") or str(uuid.uuid4())),
                created_at=float(record.get("timestamp") or time.time()),
            )
            msg.add_text(record.get("content", ""))
            return msg

        role = record.get("role")
        parts = record.get("parts")
        if not role or not isinstance(parts, list):
            return None

        msg = cls(
            role=role,
            message_id=str(record.get("message_id") or str(uuid.uuid4())),
            created_at=float(record.get("created_at") or time.time()),
        )

        for part in parts:
            p_type = part.get("type")
            if p_type == "text":
                msg.add_text(part.get("content", ""))
            elif p_type == "reasoning":
                msg.add_reasoning(part.get("content", ""))
            elif p_type == "tool":
                tool_part = msg.add_tool(
                    tool_name=part.get("tool_name", ""),
                    tool_input=part.get("tool_input") or {},
                    tool_call_id=part.get("tool_call_id"),
                )
                tool_part.status = part.get("status", "pending")  # type: ignore[assignment]
                tool_part.tool_output = part.get("tool_output")
            elif p_type == "step":
                msg.add_step(
                    step_id=part.get("step_id", ""),
                    step_index=int(part.get("step_index") or 0),
                    summary=part.get("summary", ""),
                    files_changed=part.get("files_changed") or [],
                )
        return msg
