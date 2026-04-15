"""Bing Search Provider (Azure Cognitive Services)

环境变量: BING_SEARCH_API_KEY
文档: https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/overview
"""

from __future__ import annotations

import os

import httpx

from .base import SearchProvider, SearchResult

_API_URL = "https://api.bing.microsoft.com/v7.0/search"


class BingProvider(SearchProvider):
    NAME = "bing"
    ENV_KEYS = ["BING_SEARCH_API_KEY"]

    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        api_key = os.environ["BING_SEARCH_API_KEY"]
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _API_URL,
                headers={"Ocp-Apim-Subscription-Key": api_key},
                params={"q": query, "count": num_results, "mkt": "zh-CN"},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("webPages", {}).get("value", []):
            results.append(SearchResult(
                title=item.get("name", ""),
                url=item.get("url", ""),
                snippet=item.get("snippet", ""),
                source=self.NAME,
            ))
        return results
