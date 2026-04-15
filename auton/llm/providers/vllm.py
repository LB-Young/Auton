"""vLLM Provider — 本地 / 私有部署的 vLLM 推理服务"""

from __future__ import annotations

from .openai_compat import OpenAICompatProvider


class VLLMProvider(OpenAICompatProvider):
    """vLLM 推理服务 Provider。

    vLLM 默认监听 http://localhost:8000，提供 OpenAI 兼容接口。

    启动示例：
        vllm serve Qwen/Qwen3-8B --port 8000

    model 需与 vllm serve 时指定的模型名称完全一致，例如：
      - Qwen/Qwen3-8B
      - deepseek-ai/DeepSeek-R1-Distill-Qwen-7B
      - meta-llama/Llama-3.3-70B-Instruct

    环境变量: VLLM_API_KEY（若服务端启动时指定了 --api-key 则需填写）
    文档: https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
    """

    ENV_API_KEY = "VLLM_API_KEY"
    DEFAULT_BASE_URL = "http://localhost:8000/v1"
    DEFAULT_MODEL = "Qwen/Qwen3-8B"
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
        import os
        if api_key is None:
            api_key = os.environ.get("VLLM_API_KEY") or "vllm"
        super().__init__(
            model=model or self.DEFAULT_MODEL,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
