"""Subagents — core types"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class SubagentPhase(enum.Enum):
    """Subagent 执行阶段"""
    PLANNING = "planning"
    INVESTIGATION = "investigation"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"
    COMPLETED = "completed"


@dataclass
class SubagentConfig:
    """Subagent 配置"""
    name: str
    description: str
    model: str | None = None          # None = 继承主 Agent
    max_turns: int | None = None      # None = 无限制
    timeout_seconds: int = 300          # 默认 5 分钟超时
    tools: list[str] | None = None    # None = 全部工具
    temperature: float = 0.0


@dataclass
class SubagentResult:
    """Subagent 执行结果"""
    name: str
    success: bool
    phase: SubagentPhase
    output: str = ""                   # 最终输出文本
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        if self.completed_at is None:
            return 0.0
        return (self.completed_at - self.started_at).total_seconds()
