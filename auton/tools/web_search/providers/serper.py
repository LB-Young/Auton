"""Serper.dev Google Search Provider

环境变量: SERPER_API_KEY
文档: https://serper.dev/api-reference
"""

from __future__ import annotations

import os

import httpx

from .base import SearchProvider, SearchResult

_API_URL = "https://google.serper.dev/search"


class SerperProvider(SearchProvider):
    NAME = "serper"
    ENV_KEYS = ["SERPER_API_KEY"]

    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        api_key = os.environ["SERPER_API_KEY"]
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _API_URL,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": num_results},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("organic", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                source=self.NAME,
            ))
        return results
