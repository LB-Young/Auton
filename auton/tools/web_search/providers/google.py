"""Google Custom Search Provider

环境变量:
  GOOGLE_API_KEY   — Google API Key
  GOOGLE_CSE_ID    — Custom Search Engine ID (cx)

文档: https://developers.google.com/custom-search/v1/overview
"""

from __future__ import annotations

import os

import httpx

from .base import SearchProvider, SearchResult

_API_URL = "https://www.googleapis.com/customsearch/v1"


class GoogleCSEProvider(SearchProvider):
    NAME = "google"
    ENV_KEYS = ["GOOGLE_API_KEY", "GOOGLE_CSE_ID"]

    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        api_key = os.environ["GOOGLE_API_KEY"]
        cse_id = os.environ["GOOGLE_CSE_ID"]
        # Google CSE 单次最多返回 10 条，num 超过 10 需分页
        num = min(num_results, 10)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _API_URL,
                params={"key": api_key, "cx": cse_id, "q": query, "num": num},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("items", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", "").replace("\n", " "),
                source=self.NAME,
            ))
        return results
