#!/usr/bin/env python3
"""Auton Debug Script — 快速发送 query 测试 agent"""

import asyncio
import sys
from pathlib import Path

# 确保从项目根目录可以 import auton
sys.path.insert(0, str(Path(__file__).parent.parent))

from auton.agent import Session, SessionProcessor
from auton.agent.session_store import SessionStore
from auton.core.config import get_config
from auton.core.events import EventBus
from auton.core.logging import setup_logging, get_logger
from auton.llm import AnthropicProvider, MiniMaxProvider


def create_llm(provider: str = "anthropic", model: str | None = None):
    config = get_config()
    cfg = config.llm

    if provider == "minimax":
        return MiniMaxProvider(
            model=model or cfg.model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            timeout=cfg.timeout,
        )
    else:
        return AnthropicProvider(
            model=model or cfg.model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            timeout=cfg.timeout,
        )


async def run_query(query: str, provider: str = "anthropic", model: str | None = None):
    setup_logging()
    log = get_logger("debug")
    config = get_config()

    # 创建 session 和 store
    session_store = SessionStore(config.memory.storage_dir)
    session = Session.create()

    log.info("session_id={}", session.meta.session_id)
    log.info("provider={} model={}", provider, model or get_config().llm.model)

    # 创建 LLM 和 processor
    llm = create_llm(provider, model)

    from auton.tools import get_default_tools
    tools = get_default_tools()

    processor = SessionProcessor(
        session=session,
        llm=llm,
        tools=tools,
        session_store=session_store,
    )

    # 添加用户消息
    session.add_user_message(query)

    # 流式打印响应
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}\n")

    buffer = ""
    async for event in processor.run_stream():
        # ProcessResult (decision) 没有 type 属性
        if not hasattr(event, "type"):
            if event.status == "stop":
                log.debug("stream ended: stop reason={}", event.reason)
            continue
        # LLMStreamEvent
        if event.type == "text_delta":
            delta = getattr(event, "delta", "")
            print(delta, end="", flush=True)
            buffer += delta
        elif event.type == "tool_use":
            print(f"\n[tool: {event.name}]")

    print(f"\n{'='*60}")
    print(f"Session ended. id={session.meta.session_id}")
    print(f"Messages: {len(session.messages)}")

    return buffer


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Auton Debug Query")
    parser.add_argument("query", nargs="?", default="你好，介绍一下你自己", help="要发送给 Auton 的问题")
    parser.add_argument("--provider", "-p", default="anthropic", choices=["anthropic", "minimax"], help="LLM Provider")
    parser.add_argument("--model", "-m", default=None, help="模型名称")
    args = parser.parse_args()

    asyncio.run(run_query(args.query, args.provider, args.model))


if __name__ == "__main__":
    main()
