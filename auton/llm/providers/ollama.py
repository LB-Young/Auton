"""Ollama Provider — 本地 Ollama 服务"""

from __future__ import annotations

from .openai_compat import OpenAICompatProvider


class OllamaProvider(OpenAICompatProvider):
    """本地 Ollama Provider。

    Ollama 默认监听 http://localhost:11434，提供 OpenAI 兼容接口。
    无需 API Key。

    常用模型（需提前 ollama pull <model>）：
      - qwen3:8b / qwen3:30b / qwen3:235b
      - deepseek-r1:7b / deepseek-r1:32b
      - llama3.3:70b / llama3.2:3b
      - gemma3:27b
      - mistral:7b
      - phi4:14b

    查看已下载模型: ollama list
    文档: https://ollama.com/blog/openai-compatibility
    """

    ENV_API_KEY = "OLLAMA_API_KEY"          # 本地服务通常不需要，留作扩展
    DEFAULT_BASE_URL = "http://localhost:11434/v1"
    DEFAULT_MODEL = "qwen3:8b"
    DEFAULT_CONTEXT_WINDOW = 32_000

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        timeout: float = 120.0,             # 本地推理较慢，适当放宽超时
    ) -> None:
        super().__init__(
            model=model or self.DEFAULT_MODEL,
            api_key=api_key or "ollama",    # OpenAI SDK 要求非空，填占位符即可
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
