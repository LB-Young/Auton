"""通义千问 (Qwen) Provider — 阿里云百炼 OpenAI 兼容接口"""

from __future__ import annotations

from .openai_compat import OpenAICompatProvider


class QwenProvider(OpenAICompatProvider):
    """阿里云通义千问系列 Provider。

    支持模型：qwen-max / qwen-plus / qwen-turbo /
              qwen3-235b-a22b / qwen2.5-72b-instruct 等。

    环境变量: DASHSCOPE_API_KEY（或 QWEN_API_KEY）
    文档: https://help.aliyun.com/zh/model-studio/developer-reference/use-qwen-by-calling-api
    """

    ENV_API_KEY = "DASHSCOPE_API_KEY"
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DEFAULT_MODEL = "qwen-max"
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
        # 支持 QWEN_API_KEY 作为别名
        if api_key is None:
            api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")
        super().__init__(
            model=model or self.DEFAULT_MODEL,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
