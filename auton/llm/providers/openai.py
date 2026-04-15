"""OpenAI GPT Provider"""

from __future__ import annotations

from .openai_compat import OpenAICompatProvider


class OpenAIProvider(OpenAICompatProvider):
    """OpenAI GPT 系列 Provider（gpt-4o / gpt-4-turbo / o1 等）。

    环境变量: OPENAI_API_KEY
    文档: https://platform.openai.com/docs/api-reference
    """

    ENV_API_KEY = "OPENAI_API_KEY"
    DEFAULT_MODEL = "gpt-4o"
    DEFAULT_CONTEXT_WINDOW = 128_000
    DEFAULT_BASE_URL = None  # 使用 openai SDK 默认地址

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(
            model=model or self.DEFAULT_MODEL,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
