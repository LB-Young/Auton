"""兼容层 — 系统提示词内容已迁移至 auton.agent.system_prompt

新代码请直接使用：
    from auton.agent.system_prompt import SystemPromptBuilder, build_system_prompt
"""

from ..agent.system_prompt import (  # noqa: F401
    SystemPromptBuilder,
    PromptSection,
    build_system_prompt,
    _IDENTITY_PROJECT,
    _IDENTITY_CHAT,
)

__all__ = [
    "build_system_prompt",
    "SystemPromptBuilder",
    "PromptSection",
]
