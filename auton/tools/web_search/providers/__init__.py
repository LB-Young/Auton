"""WebSearch Providers — 注册表与自动检测

优先级顺序（越靠前越优先）：
  1. Tavily    — AI Agent 优化，响应质量高
  2. Exa       — 神经语义搜索
  3. Serper    — Google 结果，低延迟
  4. SerpAPI   — Google/Bing 多引擎
  5. Brave     — 独立索引，隐私友好
  6. Bing      — 微软 Azure，覆盖广
  7. You.com   — AI 增强搜索
  8. Google    — Google Custom Search Engine
  9. Jina      — AI 阅读器搜索
 10. SearchAPI — Google 结果备选

环境变量配置任意一个即可激活对应 provider。
"""

from __future__ import annotations

import os

from .base import SearchProvider, SearchResult
from .bing import BingProvider
from .brave import BraveProvider
from .exa import ExaProvider
from .google import GoogleCSEProvider
from .jina import JinaProvider
from .searchapi import SearchApiProvider
from .serpapi import SerpApiProvider
from .serper import SerperProvider
from .tavily import TavilyProvider
from .you import YouProvider

# 优先级注册表（顺序即优先级）
_REGISTRY: list[SearchProvider] = [
    TavilyProvider(),
    ExaProvider(),
    SerperProvider(),
    SerpApiProvider(),
    BraveProvider(),
    BingProvider(),
    YouProvider(),
    GoogleCSEProvider(),
    JinaProvider(),
    SearchApiProvider(),
]


def auto_detect_provider(prefer: str | None = None) -> SearchProvider | None:
    """按优先级检测可用的搜索 provider。

    Args:
        prefer: 可选，强制指定 provider name（如 "tavily"），
                若该 provider 不可用则回退到自动检测。

    Returns:
        第一个可用的 SearchProvider，全部不可用时返回 None。
    """
    if prefer:
        for p in _REGISTRY:
            if p.NAME == prefer:
                if p.is_available():
                    return p
                # 指定的 provider key 未配置，fallthrough 自动检测

    for p in _REGISTRY:
        if p.is_available():
            return p
    return None


def list_providers() -> list[dict]:
    """返回所有 provider 的状态列表（用于诊断/debug）"""
    return [
        {
            "name": p.NAME,
            "available": p.is_available(),
            "env_keys": p.ENV_KEYS,
        }
        for p in _REGISTRY
    ]


__all__ = [
    "SearchProvider",
    "SearchResult",
    "auto_detect_provider",
    "list_providers",
    # 各 provider 类（供直接实例化使用）
    "TavilyProvider",
    "ExaProvider",
    "SerperProvider",
    "SerpApiProvider",
    "BraveProvider",
    "BingProvider",
    "YouProvider",
    "GoogleCSEProvider",
    "JinaProvider",
    "SearchApiProvider",
]
