"""You.com Search Provider

环境变量: YDC_API_KEY
文档: https://documentation.you.com/api-reference
"""

from __future__ import annotations

import os

import httpx

from .base import SearchProvider, SearchResult

_API_URL = "https://api.ydc-index.io/search"


class YouProvider(SearchProvider):
    NAME = "you"
    ENV_KEYS = ["YDC_API_KEY"]

    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        api_key = os.environ["YDC_API_KEY"]
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _API_URL,
                headers={"X-API-Key": api_key},
                params={"query": query, "num_web_results": num_results},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("hits", []):
            snippets: list[str] = item.get("snippets", [])
            snippet = " ".join(snippets)[:500] if snippets else ""
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=snippet,
                source=self.NAME,
            ))
        return results
