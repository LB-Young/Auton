"""LLM Prompt Templates"""

from __future__ import annotations

SYSTEM_DEFAULT = """你是一个智能编程助手，帮助用户完成软件开发任务。
你可以使用工具读取、编辑、创建文件，以及执行命令。
始终遵循安全最佳实践，不要执行危险操作。
"""


def build_system_prompt(
    project_context: str = "",
    memory_context: str = "",
    active_skill: str = "",
) -> str:
    """构建完整 system prompt"""
    parts = [SYSTEM_DEFAULT.strip()]

    if project_context:
        parts.append(f"\n## 项目上下文\n{project_context}")

    if memory_context:
        parts.append(f"\n## 个人记忆\n{memory_context}")

    if active_skill:
        parts.append(f"\n## 当前技能\n{active_skill}")

    return "\n\n".join(parts)
