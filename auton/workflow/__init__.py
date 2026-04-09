"""Auton Workflow — 工作流引擎

工作流 DSL、条件分支、断点续执。
"""

from .types import (
    RunStatus,
    StepStatus,
    StepType,
    StepResult,
    TaskRef,
    WorkflowCondition,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStep,
    is_terminal,
)
from .dsl import DSLParser, DSLParseError, TemplateRenderer
from .store import WorkflowStore, RunStore
from .runner import WorkflowRunner

__all__ = [
    # 类型
    "StepType",
    "StepStatus",
    "RunStatus",
    "StepResult",
    "TaskRef",
    "WorkflowCondition",
    "WorkflowDefinition",
    "WorkflowRun",
    "WorkflowStep",
    # 工具
    "is_terminal",
    "DSLParser",
    "DSLParseError",
    "TemplateRenderer",
    # 存储
    "WorkflowStore",
    "RunStore",
    # 执行
    "WorkflowRunner",
]
