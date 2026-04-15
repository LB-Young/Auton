"""WebSearch Tool — 网络搜索工具主类"""

from __future__ import annotations

import os

from loguru import logger

from ..base import Tool, ToolResult
from .providers import SearchResult, auto_detect_provider, list_providers


class WebSearchTool(Tool):
    """网络搜索工具

    自动检测可用的搜索 provider（按优先级），无需手动配置。
    配置任意一个平台的 API Key 即可使用：

      TAVILY_API_KEY        Tavily（推荐，AI Agent 优化）
      EXA_API_KEY           Exa 神经语义搜索
      SERPER_API_KEY        Google（via Serper）
      SERPAPI_API_KEY       Google/Bing（via SerpAPI）
      BRAVE_SEARCH_API_KEY  Brave 独立索引
      BING_SEARCH_API_KEY   Bing（Azure）
      YDC_API_KEY           You.com
      GOOGLE_API_KEY +      Google Custom Search
        GOOGLE_CSE_ID
      JINA_API_KEY          Jina AI Search
      SEARCHAPI_API_KEY     SearchAPI.io
    """

    name = "web_search"
    description = (
        "Search the web for up-to-date information. "
        "Supports Tavily, Exa, Serper, SerpAPI, Brave, Bing, You.com, "
        "Google CSE, Jina, and SearchAPI — whichever key is configured."
    )

    def __init__(self, prefer_provider: str | None = None) -> None:
        """
        Args:
            prefer_provider: 可选，强制指定 provider name（如 "tavily"），
                             未配置时自动回退到其他可用 provider。
        """
        self._prefer = prefer_provider or os.environ.get("WEB_SEARCH_PROVIDER")
        self._logger = logger.bind(name="WebSearchTool")

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5, max: 10)",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        num_results: int = 5,
    ) -> ToolResult:
        num_results = max(1, min(num_results, 10))
        provider = auto_detect_provider(prefer=self._prefer)

        if provider is None:
            tips = self._no_provider_tips()
            return ToolResult(
                content=tips,
                success=False,
                error="no_search_provider_configured",
            )

        self._logger.debug("using provider={p} query={q!r}", p=provider.NAME, q=query)
        try:
            results = await provider.search(query, num_results=num_results)
        except Exception as exc:
            self._logger.warning("search failed provider={p} err={e}", p=provider.NAME, e=exc)
            return ToolResult(
                content=f"Search failed ({provider.NAME}): {exc}",
                success=False,
                error=str(exc),
            )

        if not results:
            return ToolResult(
                content=f"No results found for: {query!r}",
                success=True,
            )

        return ToolResult(
            content=self._format_results(query, results, provider.NAME),
            success=True,
        )

    # ─── 私有 ────────────────────────────────────────────────────────────────

    @staticmethod
    def _format_results(query: str, results: list[SearchResult], provider_name: str) -> str:
        lines = [f"Search results for: **{query}** (via {provider_name})\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.to_text()}")
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def _no_provider_tips() -> str:
        statuses = list_providers()
        lines = [
            "No web search provider configured.",
            "Set one of the following environment variables:\n",
        ]
        for s in statuses:
            keys = ", ".join(s["env_keys"])
            lines.append(f"  {s['name']:12s}  →  {keys}")
        lines.append(
            "\nOptionally set WEB_SEARCH_PROVIDER=<name> to force a specific provider."
        )
        return "\n".join(lines)
