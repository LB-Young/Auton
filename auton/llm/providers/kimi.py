"""Kimi Provider — Moonshot AI"""

from __future__ import annotations

from .openai_compat import OpenAICompatProvider


class KimiProvider(OpenAICompatProvider):
    """Moonshot AI Kimi 系列 Provider。

    支持模型：
      - moonshot-v1-8k
      - moonshot-v1-32k
      - moonshot-v1-128k
      - kimi-latest（始终指向最新 Kimi 模型）

    环境变量: MOONSHOT_API_KEY（或 KIMI_API_KEY）
    文档: https://platform.moonshot.cn/docs/api/chat
    """

    ENV_API_KEY = "MOONSHOT_API_KEY"
    DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
    DEFAULT_MODEL = "moonshot-v1-32k"
    DEFAULT_CONTEXT_WINDOW = 128_000

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        timeout: float = 60.0,
    ) -> None:
        import os
        if api_key is None:
            api_key = os.environ.get("MOONSHOT_API_KEY") or os.environ.get("KIMI_API_KEY")
        super().__init__(
            model=model or self.DEFAULT_MODEL,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
