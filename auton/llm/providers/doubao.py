"""豆包 (Doubao) Provider — 字节跳动火山引擎 ARK 平台"""

from __future__ import annotations

from .openai_compat import OpenAICompatProvider


class DoubaoProvider(OpenAICompatProvider):
    """字节跳动豆包 / 火山引擎 ARK Provider。

    模型名称为火山引擎侧的「接入点 ID」（endpoint ID），格式如：
      ep-20250101000000-xxxxx

    也可使用公开模型名称（需在控制台开通）：
      doubao-pro-4k / doubao-pro-32k / doubao-pro-128k /
      doubao-lite-4k / doubao-lite-32k 等。

    环境变量: ARK_API_KEY（或 DOUBAO_API_KEY）
    文档: https://www.volcengine.com/docs/82379/1263482
    """

    ENV_API_KEY = "ARK_API_KEY"
    DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
    DEFAULT_MODEL = "doubao-pro-32k"
    DEFAULT_CONTEXT_WINDOW = 32_000

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
            api_key = os.environ.get("ARK_API_KEY") or os.environ.get("DOUBAO_API_KEY")
        super().__init__(
            model=model or self.DEFAULT_MODEL,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
