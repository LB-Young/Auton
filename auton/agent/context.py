"""Agent Context — LLM 请求上下文构建"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from .message import Message
from .session import Session
from .types import LLMContext

if TYPE_CHECKING:
    from ..llm.base import LLMProvider


class ContextBuilder:
    """从 Session 构建 LLM 请求上下文"""

    def __init__(self, provider: "LLMProvider", tools: list[dict] | None = None) -> None:
        self.provider = provider
        self.tools = tools or []
        self._logger = logger.bind(name="ContextBuilder")
        self._system_stored = False

    @property
    def system_stored(self) -> bool:
        """系统提示词是否已持久化到 session store（只读）。"""
        return self._system_stored

    def mark_system_stored(self) -> None:
        """标记系统提示词已持久化（由 SessionProcessor 在存储后调用）。"""
        self._system_stored = True

    def reset(self) -> None:
        """重置 Builder 状态，用于新会话开始时清理历史标记。"""
        self._system_stored = False

    def build(self, session: Session, system_prompt: str = "") -> LLMContext:
        """从 Session 构建 LLMContext"""
        return LLMContext(
            session_id=session.meta.session_id,
            messages=self._build_messages(session),
            tools=self.tools,
            system_prompt=system_prompt,
            model=self.provider.model_name,
            max_tokens=self.provider.max_tokens,
            temperature=self.provider.temperature,
        )

    def _build_messages(self, session: Session) -> list[Message]:
        """将 Session.messages 转换为 provider 格式"""
        return session.messages

    # ─── System Prompt 片段 ──────────────────────────────────────────────

    @staticmethod
    def system_prompt_from_files(
        project_path: Path | None,
        memory_md: str = "",
        skill_md: str = "",
    ) -> str:
        """拼装 system prompt 片段"""
        parts = []

        if project_path:
            parts.append(f"[Project: {project_path}]")

        if memory_md:
            parts.append(f"\n## Personal Context\n{memory_md}")

        if skill_md:
            parts.append(f"\n## Active Skill\n{skill_md}")

        return "\n".join(parts)
