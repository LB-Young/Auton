"""Gateway — 统一会话上下文类型

各接入端（CLI、Web、Slack、Feishu 等）拿到 SessionContext 后，
只需关心自己的 I/O 层，不再重复构建会话基础设施。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent.agent import SessionProcessor
    from ..agent.session import Session
    from ..agent.session_store import SessionStore
    from ..core.events import EventBus
    from ..llm.base import LLMProvider
    from ..skills.injector import SkillInjector


@dataclass
class SessionContext:
    """一次会话所需的全部运行时对象。

    由 SessionFactory.build() 构建后传给各接入端使用。
    接入端只需：
        1. 调用 ctx.processor.run_stream() 驱动主循环
        2. 处理自己的 I/O（终端打印 / HTTP SSE / Slack 消息推送 ...）
    """

    processor: "SessionProcessor"
    session: "Session"
    session_store: "SessionStore"
    llm: "LLMProvider"
    event_bus: "EventBus"
    skill_injector: "SkillInjector | None"
    system_prompt: str

    # 便捷属性
    @property
    def session_id(self) -> str:
        return self.session.meta.session_id

    @property
    def mode(self) -> str:
        """'project' 或 'date'"""
        return self.session_store.mode

    @property
    def project_root(self) -> "Path | None":
        return self.session_store.project_root
