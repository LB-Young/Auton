"""LM Studio Provider — 本地 LM Studio 服务"""

from __future__ import annotations

from .openai_compat import OpenAICompatProvider


class LMStudioProvider(OpenAICompatProvider):
    """本地 LM Studio Provider。

    LM Studio 默认监听 http://localhost:1234，提供 OpenAI 兼容接口。
    无需 API Key。

    model 填写 LM Studio 中加载的模型标识符，例如：
      - qwen2.5-7b-instruct
      - deepseek-r1-distill-qwen-7b
      - llama-3.2-3b-instruct
    
    也可直接填 "local-model"（LM Studio 始终指向当前加载的模型）。

    文档: https://lmstudio.ai/docs/local-server
    """

    ENV_API_KEY = "LM_STUDIO_API_KEY"
    DEFAULT_BASE_URL = "http://localhost:1234/v1"
    DEFAULT_MODEL = "local-model"
    DEFAULT_CONTEXT_WINDOW = 32_000

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(
            model=model or self.DEFAULT_MODEL,
            api_key=api_key or "lm-studio",
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
