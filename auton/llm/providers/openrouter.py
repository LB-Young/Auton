"""OpenRouter Provider — 聚合多家 LLM 的统一代理"""

from __future__ import annotations

import os
from typing import Any

from .openai_compat import OpenAICompatProvider


class OpenRouterProvider(OpenAICompatProvider):
    """OpenRouter Provider。

    OpenRouter 聚合了数百个模型（Anthropic、OpenAI、Google、Meta 等），
    使用统一的 OpenAI 兼容接口。模型名称格式为 "提供方/模型名"，例如：
      - openai/gpt-4o
      - anthropic/claude-3.5-sonnet
      - google/gemini-2.0-flash
      - meta-llama/llama-3.3-70b-instruct
      - deepseek/deepseek-chat
      - qwen/qwen-2.5-72b-instruct

    可通过 HTTP Referer / X-Title 头标识应用（可选）。

    环境变量: OPENROUTER_API_KEY
    文档: https://openrouter.ai/docs
    """

    ENV_API_KEY = "OPENROUTER_API_KEY"
    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL = "openai/gpt-4o"
    DEFAULT_CONTEXT_WINDOW = 128_000

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        timeout: float = 60.0,
        # OpenRouter 推荐填写，用于排行榜显示和费率追踪（可选）
        app_name: str | None = None,
        app_url: str | None = None,
    ) -> None:
        super().__init__(
            model=model or self.DEFAULT_MODEL,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
        self._app_name = app_name or os.environ.get("OPENROUTER_APP_NAME", "Auton")
        self._app_url = app_url or os.environ.get("OPENROUTER_APP_URL", "")

    async def _raw_stream(
        self,
        ctx: Any,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        """注入 OpenRouter 专属请求头后调用父类流式接口。"""
        # 在 AsyncOpenAI 客户端的 default_headers 中注入标识头
        if self._app_name:
            self._client.default_headers["X-Title"] = self._app_name
        if self._app_url:
            self._client.default_headers["HTTP-Referer"] = self._app_url

        async for event in super()._raw_stream(ctx, messages, tools):
            yield event
