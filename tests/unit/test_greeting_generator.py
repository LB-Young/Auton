"""Tests for CLI greeting generation fallback behaviour."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import AsyncIterator

from auton.cli.greeting_context import GreetingContext
from auton.cli.greeting_generator import DEFAULT_GREETING, generate_greeting
from auton.llm.base import LLMProvider, LLMStreamEvent


class FailingLLM(LLMProvider):
    """LLM provider stub that always raises to simulate network errors."""

    def __init__(self) -> None:
        super().__init__(model="mock")

    async def stream(self, ctx) -> AsyncIterator[LLMStreamEvent]:  # type: ignore[override]
        raise RuntimeError("network unreachable")
        if False:  # pragma: no cover
            yield  # ensure this is treated as async generator


def _build_ctx() -> GreetingContext:
    today = date(2026, 4, 8)
    return GreetingContext(
        cwd=Path("/tmp"),
        today=today,
        yesterday=today,
        has_project_history=False,
        should_ask_project_mode=True,
        date_memory_snippets=[],
        project_memory_snippets=[],
    )


async def _run_generate() -> str:
    llm = FailingLLM()
    ctx = _build_ctx()
    return await generate_greeting(llm=llm, ctx=ctx, session_id="test-session")


def test_generate_greeting_returns_fallback_when_llm_fails():
    """When the provider raises, we still show a default greeting."""
    greeting = asyncio.run(_run_generate())
    assert greeting == DEFAULT_GREETING
