"""LLM Factory — 统一创建 LLM Provider 实例的便捷入口"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import LLMProvider


def get_llm_provider(
    provider: str | None = None,
    model: str | None = None,
) -> "LLMProvider":
    """创建 LLM Provider 实例。

    provider / model 均为 None 时从全局配置读取（主 Agent 默认行为）。
    指定不同于全局配置的 provider 时，api_key / base_url 将从该 provider
    各自的环境变量中自动读取，不会错误传入主 Agent 的凭证。

    Args:
        provider: LLM 平台名称，如 "openai" / "deepseek" / "qwen"。
                  None = 继承全局配置中的 provider。
        model:    模型名称，如 "gpt-4o" / "deepseek-chat"。
                  None = 继承全局配置中的 model。

    Returns:
        已初始化的 LLMProvider 实例。
    """
    from ..gateway.session_factory import SessionFactory
    return SessionFactory()._create_llm(model=model, provider=provider)
