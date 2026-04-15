"""DeepSeek Provider — 支持 DeepSeek-V3 / DeepSeek-R1 推理模型"""

from __future__ import annotations

from .openai_compat import OpenAICompatProvider


class DeepSeekProvider(OpenAICompatProvider):
    """DeepSeek 系列 Provider。

    支持模型：
      - deepseek-chat       （DeepSeek-V3，对话/代码）
      - deepseek-reasoner   （DeepSeek-R1，含思维链 reasoning_content）

    当使用 deepseek-reasoner 时，流中会额外产生 ReasoningStartEvent /
    ReasoningDeltaEvent / ReasoningFinishEvent 事件，可在 UI 层展示思考过程。

    环境变量: DEEPSEEK_API_KEY
    文档: https://platform.deepseek.com/api-docs/
    """

    ENV_API_KEY = "DEEPSEEK_API_KEY"
    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
    DEFAULT_MODEL = "deepseek-chat"
    DEFAULT_CONTEXT_WINDOW = 64_000
    # DeepSeek-R1 在 delta 中附带 reasoning_content 字段
    SUPPORT_REASONING_FIELD = True

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
