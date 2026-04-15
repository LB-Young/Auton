"""Tavily Search Provider

环境变量: TAVILY_API_KEY
文档: https://docs.tavily.com/docs/tavily-api/rest_api
"""

from __future__ import annotations

import os

import httpx

from .base import SearchProvider, SearchResult

_API_URL = "https://api.tavily.com/search"


class TavilyProvider(SearchProvider):
    NAME = "tavily"
    ENV_KEYS = ["TAVILY_API_KEY"]

    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        api_key = os.environ["TAVILY_API_KEY"]
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _API_URL,
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": num_results,
                    "search_depth": "basic",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                source=self.NAME,
                score=item.get("score", 0.0),
            ))
        return results
