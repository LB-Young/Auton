"""Google Gemini Provider — 通过 OpenAI 兼容端点接入"""

from __future__ import annotations

from .openai_compat import OpenAICompatProvider


class GeminiProvider(OpenAICompatProvider):
    """Google Gemini 系列 Provider。

    使用 Google 官方提供的 OpenAI 兼容端点，无需安装 google-genai SDK，
    直接复用 openai 包即可。

    支持模型：
      - gemini-2.0-flash          （快速，默认）
      - gemini-2.0-flash-thinking  （含思维链）
      - gemini-2.5-pro-preview     （最强推理）
      - gemini-1.5-pro
      - gemini-1.5-flash

    环境变量: GEMINI_API_KEY（或 GOOGLE_API_KEY）
    文档: https://ai.google.dev/gemini-api/docs/openai
    """

    ENV_API_KEY = "GEMINI_API_KEY"
    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
    DEFAULT_MODEL = "gemini-2.0-flash"
    DEFAULT_CONTEXT_WINDOW = 1_000_000

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
            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        super().__init__(
            model=model or self.DEFAULT_MODEL,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
