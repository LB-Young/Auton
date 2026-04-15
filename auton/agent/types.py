"""Agent Types — Agent 相关数据类型"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    from .message import Message


# ─── Sub-Agent 状态 ─────────────────────────────────────────────────────────

AgentStatus = Literal["pending", "running", "completed", "failed", "aborted"]


@dataclass(frozen=True)
class AgentDefinition:
    """Agent 定义（从 ~/.auton/agents/*.md 或项目 .auton/agents/*.md 加载）"""
    name: str                                    # 唯一标识
    description: str                             # 何时使用（供主 Agent 决策）
    system_prompt: str                           # 系统提示词
    model: str | None = None                     # 模型（None = 继承主 Agent）
    provider: str | None = None                  # LLM 平台（None = 继承主 Agent）
    tools: list[str] | None = None               # 允许的工具（None = 全部）
    disallowed_tools: list[str] = field(default_factory=list)  # 禁止的工具
    permission_mode: str = "default"             # 权限模式
    max_turns: int | None = None                # 最大轮次限制
    skills: list[str] = field(default_factory=list)  # 预加载的 skill
    mcp_servers: list[str] = field(default_factory=list)  # 需要的 MCP server 名称
    background: bool = False                     # 是否后台运行
    isolation: str | None = None                 # worktree 隔离模式
    source: str = "builtin"                      # builtin / user / project / plugin


@dataclass
class AgentRun:
    """Sub-Agent 运行实例"""
    run_id: str
    agent_name: str
    parent_session_id: str
    status: AgentStatus = "pending"
    prompt: str = ""
    result: str = ""
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None


# ─── 会话状态 ────────────────────────────────────────────────────────────────

SessionStatus = Literal["idle", "running", "compact", "waiting"]


@dataclass
class SessionMeta:
    """会话元信息"""
    session_id: str
    created_at: datetime
    updated_at: datetime
    project_path: str | None = None  # 所属项目路径，None = 无项目模式
    compaction_count: int = 0
    step_count: int = 0


# ─── 会话结果 ────────────────────────────────────────────────────────────────

@dataclass
class ProcessResult:
    """SessionProcessor.process() 返回值"""
    status: Literal["continue", "compact", "stop"]
    reason: str = ""


# ─── 工具调用状态 ────────────────────────────────────────────────────────────

ToolStatus = Literal["pending", "running", "completed", "error"]


# ─── LLM 请求上下文 ───────────────────────────────────────────────────────────

@dataclass
class LLMContext:
    """构建 LLM 请求时所需的上下文信息"""
    session_id: str
    messages: list[Message]
    tools: list[dict]
    system_prompt: str = ""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 8192
    temperature: float = 0.0
