"""Brave Search Provider

环境变量: BRAVE_SEARCH_API_KEY
文档: https://api.search.brave.com/app/documentation/web-search/get-started
"""

from __future__ import annotations

import os

import httpx

from .base import SearchProvider, SearchResult

_API_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveProvider(SearchProvider):
    NAME = "brave"
    ENV_KEYS = ["BRAVE_SEARCH_API_KEY"]

    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        api_key = os.environ["BRAVE_SEARCH_API_KEY"]
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _API_URL,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
                params={"q": query, "count": num_results},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("web", {}).get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
                source=self.NAME,
            ))
        return results
