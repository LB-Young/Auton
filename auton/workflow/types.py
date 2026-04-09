"""Workflow — 工作流数据类型与状态机"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

# ─── 步骤类型 ─────────────────────────────────────────────────────────────────

StepType = Literal["task", "condition", "input", "output", "checkpoint"]
RunStatus = Literal["idle", "running", "completed", "failed", "breakpoint", "cancelled"]
StepStatus = Literal["pending", "running", "completed", "failed", "skipped", "breakpoint"]


def is_terminal(status: str) -> bool:
    return status in {"completed", "failed", "cancelled"}


# ─── 条件 ─────────────────────────────────────────────────────────────────────

@dataclass
class WorkflowCondition:
    """条件分支"""
    expression: str = ""          # Jinja2 风格: "{{ env }} == 'prod'"
    then: list[str] = field(default_factory=list)   # 满足时执行的步骤 IDs
    else_: list[str] = field(default_factory=list)    # 不满足时执行的步骤 IDs
    result: bool | None = None   # 运行时计算结果

    def to_dict(self) -> dict:
        return {
            "expression": self.expression,
            "then": self.then,
            "else": self.else_,
            "result": self.result,
        }


# ─── 任务引用 ────────────────────────────────────────────────────────────────

@dataclass
class TaskRef:
    """引用 M9 Task"""
    title: str
    description: str = ""
    params: dict = field(default_factory=dict)


# ─── 工作流步骤 ────────────────────────────────────────────────────────────────

@dataclass
class WorkflowStep:
    """工作流中的单个步骤"""
    id: str
    type: StepType = "task"
    description: str = ""
    task: TaskRef | None = None
    condition: WorkflowCondition | None = None
    depends_on: list[str] = field(default_factory=list)   # 依赖的步骤 IDs
    breakpoints: bool = False          # 是否在执行后自动断点
    skip: bool = False               # 是否跳过
    max_retries: int = 0             # 失败重试次数
    on_failure: Literal["stop", "skip", "retry"] = "stop"
    # 运行时状态
    status: StepStatus = "pending"
    output: str = ""
    error: str = ""
    task_id: str | None = None       # 关联的 M9 Task ID
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def is_atomic(self) -> bool:
        return self.type in {"task", "input", "output", "checkpoint"}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "description": self.description,
            "task": {"title": self.task.title, "description": self.task.description}
            if self.task else None,
            "condition": self.condition.to_dict() if self.condition else None,
            "depends_on": self.depends_on,
            "breakpoints": self.breakpoints,
            "skip": self.skip,
            "max_retries": self.max_retries,
            "on_failure": self.on_failure,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "task_id": self.task_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# ─── 工作流定义 ──────────────────────────────────────────────────────────────

OnFailure = Literal["stop", "skip", "retry"]


@dataclass
class WorkflowDefinition:
    """工作流定义（从 DSL 解析而来）"""
    id: str
    name: str
    version: str = "1.0"
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    breakpoints: list[str] = field(default_factory=list)   # 断点步骤 IDs
    on_failure: OnFailure = "stop"
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def get_step(self, step_id: str) -> WorkflowStep | None:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def dependency_graph(self) -> dict[str, list[str]]:
        """构建依赖图: step_id → [依赖的 step_ids]"""
        return {s.id: s.depends_on for s in self.steps}

    def topological_order(self) -> list[WorkflowStep]:
        """返回拓扑排序后的步骤"""
        sorted_steps: list[WorkflowStep] = []
        remaining = {s.id: s for s in self.steps}
        added: set[str] = set()

        while remaining:
            for sid, step in list(remaining.items()):
                if all(d in added for d in step.depends_on):
                    sorted_steps.append(step)
                    added.add(sid)
                    del remaining[sid]
                    break
            else:
                for sid, step in remaining.items():
                    sorted_steps.append(step)
                    added.add(sid)
                break

        return sorted_steps

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "breakpoints": self.breakpoints,
            "on_failure": self.on_failure,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowDefinition":
        from datetime import datetime

        def parse_dt(val):
            if val is None:
                return datetime.now()
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(val)

        steps = []
        for s in data.get("steps", []):
            task = None
            if s.get("task"):
                task = TaskRef(
                    title=s["task"].get("title", ""),
                    description=s["task"].get("description", ""),
                    params=s["task"].get("params", {}),
                )
            cond = None
            if s.get("condition"):
                c = s["condition"]
                cond = WorkflowCondition(
                    expression=c.get("expression", ""),
                    then=c.get("then", []),
                    else_=c.get("else", []),
                    result=c.get("result"),
                )
            steps.append(WorkflowStep(
                id=s["id"],
                type=s.get("type", "task"),
                description=s.get("description", ""),
                task=task,
                condition=cond,
                depends_on=s.get("depends_on", []),
                breakpoints=s.get("breakpoints", False),
                skip=s.get("skip", False),
                max_retries=s.get("max_retries", 0),
                on_failure=s.get("on_failure", "stop"),
                status=s.get("status", "pending"),
                output=s.get("output", ""),
                error=s.get("error", ""),
                task_id=s.get("task_id"),
                started_at=parse_dt(s.get("started_at")) if s.get("started_at") else None,
                completed_at=parse_dt(s.get("completed_at")) if s.get("completed_at") else None,
            ))

        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
            steps=steps,
            breakpoints=data.get("breakpoints", []),
            on_failure=data.get("on_failure", "stop"),
            tags=data.get("tags", []),
            created_at=parse_dt(data.get("created_at")),
            updated_at=parse_dt(data.get("updated_at")),
        )


# ─── 执行实例 ─────────────────────────────────────────────────────────────────

@dataclass
class StepResult:
    """单步执行结果"""
    step_id: str
    status: StepStatus
    output: str = ""
    error: str = ""
    task_id: str | None = None
    duration_seconds: float | None = None


@dataclass
class WorkflowRun:
    """工作流执行实例"""
    id: str = field(default_factory=lambda: f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}")
    workflow_id: str = ""
    workflow_name: str = ""
    status: RunStatus = "idle"
    step_states: dict[str, StepStatus] = field(default_factory=dict)  # step_id → status
    params: dict = field(default_factory=dict)                          # 变量参数
    current_step: str | None = None              # 当前执行到的步骤
    breakpoint_step: str | None = None            # 断点步骤 ID
    breakpoint_reason: str = ""                   # 断点原因
    output: str = ""                             # 累积输出
    logs: list[dict] = field(default_factory=list)  # 执行日志
    error: str = ""                              # 整体错误
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    finished_step_id: str | None = None          # 最后完成的步骤

    def duration_seconds(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def add_log(self, event: str, step_id: str | None = None, detail: str = "") -> None:
        self.logs.append({
            "event": event,
            "step_id": step_id,
            "detail": detail,
            "at": datetime.now().isoformat(),
        })

    def is_terminal(self) -> bool:
        return is_terminal(self.status)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "status": self.status,
            "step_states": self.step_states,
            "params": self.params,
            "current_step": self.current_step,
            "breakpoint_step": self.breakpoint_step,
            "breakpoint_reason": self.breakpoint_reason,
            "output": self.output,
            "logs": self.logs,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "finished_step_id": self.finished_step_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowRun":
        from datetime import datetime

        def parse_dt(val):
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(val)

        return cls(
            id=data["id"],
            workflow_id=data.get("workflow_id", ""),
            workflow_name=data.get("workflow_name", ""),
            status=data.get("status", "idle"),
            step_states=data.get("step_states", {}),
            params=data.get("params", {}),
            current_step=data.get("current_step"),
            breakpoint_step=data.get("breakpoint_step"),
            breakpoint_reason=data.get("breakpoint_reason", ""),
            output=data.get("output", ""),
            logs=data.get("logs", []),
            error=data.get("error", ""),
            created_at=parse_dt(data.get("created_at")) or datetime.now(),
            started_at=parse_dt(data.get("started_at")),
            completed_at=parse_dt(data.get("completed_at")),
            finished_step_id=data.get("finished_step_id"),
        )
