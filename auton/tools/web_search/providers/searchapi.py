"""SearchAPI.io Search Provider

环境变量: SEARCHAPI_API_KEY
文档: https://www.searchapi.io/docs/google
"""

from __future__ import annotations

import os

import httpx

from .base import SearchProvider, SearchResult

_API_URL = "https://www.searchapi.io/api/v1/search"


class SearchApiProvider(SearchProvider):
    NAME = "searchapi"
    ENV_KEYS = ["SEARCHAPI_API_KEY"]

    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        api_key = os.environ["SEARCHAPI_API_KEY"]
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                _API_URL,
                params={
                    "engine": "google",
                    "q": query,
                    "api_key": api_key,
                    "num": num_results,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("organic_results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                source=self.NAME,
            ))
        return results
