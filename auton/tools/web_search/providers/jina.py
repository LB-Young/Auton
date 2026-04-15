"""Jina AI Search Provider

环境变量: JINA_API_KEY
文档: https://jina.ai/reader/#apiform  (s.jina.ai endpoint)
"""

from __future__ import annotations

import os
from urllib.parse import quote

import httpx

from .base import SearchProvider, SearchResult

_BASE_URL = "https://s.jina.ai/"


class JinaProvider(SearchProvider):
    NAME = "jina"
    ENV_KEYS = ["JINA_API_KEY"]

    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        api_key = os.environ["JINA_API_KEY"]
        url = _BASE_URL + quote(query)
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                    "X-Retain-Images": "none",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("data", [])[:num_results]:
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", item.get("content", ""))[:500],
                source=self.NAME,
            ))
        return results
