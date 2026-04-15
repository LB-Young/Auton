"""Exa (formerly Metaphor) Search Provider

环境变量: EXA_API_KEY
文档: https://docs.exa.ai/reference/search
"""

from __future__ import annotations

import os

import httpx

from .base import SearchProvider, SearchResult

_API_URL = "https://api.exa.ai/search"


class ExaProvider(SearchProvider):
    NAME = "exa"
    ENV_KEYS = ["EXA_API_KEY"]

    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        api_key = os.environ["EXA_API_KEY"]
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _API_URL,
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json={
                    "query": query,
                    "numResults": num_results,
                    "contents": {"text": {"maxCharacters": 500}},
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("results", []):
            snippet = ""
            if isinstance(item.get("text"), str):
                snippet = item["text"][:500]
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=snippet,
                source=self.NAME,
                score=item.get("score", 0.0),
            ))
        return results
