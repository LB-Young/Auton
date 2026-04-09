"""Auton Core — 结构化事件类型定义

所有事件继承 BaseEvent，包含：
  - type: 事件类型字符串
  - session_id: 所属会话
  - timestamp: 事件时间戳
  - step_id: 所属步骤（可选）
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass(kw_only=True)
class BaseEvent:
    """所有事件的基类"""
    type: str
    session_id: str
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    step_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "step_id": self.step_id,
        }


# ─── Text 事件 ────────────────────────────────────────────────────────────────

@dataclass
class TextStartEvent(BaseEvent):
    """助手开始输出文本"""
    type: str = "text-start"
    message_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {**super().to_dict(), "type": self.type, "message_id": self.message_id}


@dataclass
class TextDeltaEvent(BaseEvent):
    """文本增量（streaming）"""
    type: str = "text-delta"
    delta: str = ""

    def to_dict(self) -> dict:
        return {**super().to_dict(), "delta": self.delta}


@dataclass
class TextFinishEvent(BaseEvent):
    """文本输出完成"""
    type: str = "text-finish"
    content: str = ""
    message_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {**super().to_dict(), "content": self.content, "message_id": self.message_id}


# ─── Reasoning 事件 ───────────────────────────────────────────────────────────

@dataclass
class ReasoningStartEvent(BaseEvent):
    type: str = "reasoning-start"
    message_id: Optional[str] = None


@dataclass
class ReasoningDeltaEvent(BaseEvent):
    type: str = "reasoning-delta"
    delta: str = ""

    def to_dict(self) -> dict:
        return {**super().to_dict(), "delta": self.delta}


@dataclass
class ReasoningFinishEvent(BaseEvent):
    type: str = "reasoning-finish"
    content: str = ""
    message_id: Optional[str] = None


# ─── Tool 事件 ────────────────────────────────────────────────────────────────

@dataclass
class ToolCallEvent(BaseEvent):
    """工具被调用"""
    type: str = "tool-call"
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    tool_call_id: str = ""

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_call_id": self.tool_call_id,
        }


@dataclass
class ToolResultEvent(BaseEvent):
    """工具执行结果"""
    type: str = "tool-result"
    tool_name: str = ""
    tool_call_id: str = ""
    output: str = ""

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "output": self.output,
        }


@dataclass
class ToolErrorEvent(BaseEvent):
    """工具执行出错"""
    type: str = "tool-error"
    tool_name: str = ""
    tool_call_id: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "error": self.error,
        }


# ─── Step 事件 ───────────────────────────────────────────────────────────────

@dataclass
class StepStartEvent(BaseEvent):
    """步骤开始"""
    type: str = "step-start"
    step_id: str = ""
    step_index: int = 0

    def to_dict(self) -> dict:
        return {**super().to_dict(), "step_id": self.step_id, "step_index": self.step_index}


@dataclass
class StepFinishEvent(BaseEvent):
    """步骤完成"""
    type: str = "step-finish"
    step_id: str = ""
    step_index: int = 0
    summary: str = ""
    files_changed: list[str] = field(default_factory=list)
    token_used: int = 0

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "step_id": self.step_id,
            "step_index": self.step_index,
            "summary": self.summary,
            "files_changed": self.files_changed,
            "token_used": self.token_used,
        }


# ─── System 事件 ────────────────────────────────────────────────────────────

@dataclass
class SessionCompactEvent(BaseEvent):
    """会话上下文压缩"""
    type: str = "session-compact"
    before_token_count: int = 0
    after_token_count: int = 0

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "before_token_count": self.before_token_count,
            "after_token_count": self.after_token_count,
        }


@dataclass
class SessionStatusChangeEvent(BaseEvent):
    """会话状态变化"""
    type: str = "session-status-change"
    status: Literal["idle", "running", "compact", "waiting"] = "idle"
    reason: str = ""

    def to_dict(self) -> dict:
        return {**super().to_dict(), "status": self.status, "reason": self.reason}


@dataclass
class AuditEvent(BaseEvent):
    """审计日志事件"""
    type: str = "audit"
    action: str = ""
    tool_name: Optional[str] = None
    params: dict = field(default_factory=dict)
    result: str = ""
    approved: bool = True

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "action": self.action,
            "tool_name": self.tool_name,
            "params": self.params,
            "result": self.result,
            "approved": self.approved,
        }


# ─── Plan 事件 ────────────────────────────────────────────────────────────────

@dataclass
class PlanStartEvent(BaseEvent):
    """规划开始"""
    type: str = "plan-start"
    plan_id: str = ""
    task: str = ""

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "plan_id": self.plan_id,
            "task": self.task,
        }


@dataclass
class PlanConfirmEvent(BaseEvent):
    """用户确认计划"""
    type: str = "plan-confirm"
    plan_id: str = ""
    step_count: int = 0

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "plan_id": self.plan_id,
            "step_count": self.step_count,
        }


@dataclass
class PlanStepExecuteEvent(BaseEvent):
    """计划步骤执行"""
    type: str = "plan-step"
    plan_id: str = ""
    step_index: int = 0
    step_description: str = ""

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "plan_id": self.plan_id,
            "step_index": self.step_index,
            "step_description": self.step_description,
        }


@dataclass
class PlanCancelEvent(BaseEvent):
    """用户取消计划"""
    type: str = "plan-cancel"
    plan_id: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "plan_id": self.plan_id,
            "reason": self.reason,
        }


# ─── Workflow 事件 ────────────────────────────────────────────────────────────

@dataclass
class WorkflowRunStartEvent(BaseEvent):
    """工作流执行开始"""
    type: str = "workflow-run-start"
    run_id: str = ""
    workflow_id: str = ""

    def to_dict(self) -> dict:
        return {**super().to_dict(), "run_id": self.run_id, "workflow_id": self.workflow_id}


@dataclass
class WorkflowRunCompleteEvent(BaseEvent):
    """工作流执行完成"""
    type: str = "workflow-run-complete"
    run_id: str = ""
    workflow_id: str = ""
    status: str = ""  # completed / failed / cancelled
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class WorkflowBreakpointEvent(BaseEvent):
    """工作流触发断点"""
    type: str = "workflow-breakpoint"
    run_id: str = ""
    workflow_id: str = ""
    step_id: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "step_id": self.step_id,
            "reason": self.reason,
        }


# ─── Task 事件 ────────────────────────────────────────────────────────────────

@dataclass
class TaskCreateEvent(BaseEvent):
    """任务创建"""
    type: str = "task-create"
    task_id: str = ""
    title: str = ""

    def to_dict(self) -> dict:
        return {**super().to_dict(), "task_id": self.task_id, "title": self.title}


@dataclass
class TaskStatusChangeEvent(BaseEvent):
    """任务状态变化"""
    type: str = "task-status-change"
    task_id: str = ""
    from_status: str = ""
    to_status: str = ""

    def to_dict(self) -> dict:
        return {
            **super().to_dict(),
            "task_id": self.task_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
        }


# ─── 类型别名 ────────────────────────────────────────────────────────────────

AutonEvent = (
    TextStartEvent | TextDeltaEvent | TextFinishEvent
    | ReasoningStartEvent | ReasoningDeltaEvent | ReasoningFinishEvent
    | ToolCallEvent | ToolResultEvent | ToolErrorEvent
    | StepStartEvent | StepFinishEvent
    | SessionCompactEvent | SessionStatusChangeEvent | AuditEvent
    | PlanStartEvent | PlanConfirmEvent | PlanStepExecuteEvent | PlanCancelEvent
    | TaskCreateEvent | TaskStatusChangeEvent
    | WorkflowRunStartEvent | WorkflowRunCompleteEvent | WorkflowBreakpointEvent
)
