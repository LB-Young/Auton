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
from auton.llm import AnthropicProvider, MiniMaxProvider, MockProvider


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
    if provider == "mock":
        return MockProvider(
            model=model or "mock-echo",
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
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


async def run_query(
    query: str,
    provider: str = "anthropic",
    model: str | None = None,
    mode: str = "project",
):
    setup_logging()
    log = get_logger("debug")
    config = get_config()

    # 创建 session 和 store，按模式初始化
    session_store = SessionStore(config.memory.storage_dir)
    if mode == "chat":
        session_store.set_date_mode()
    else:
        session_store.set_project_root(Path(__file__).parent.parent)
    session = Session.create()

    log.info("session_id={} mode={}", session.meta.session_id, session_store.mode)
    log.info("provider={} model={}", provider, model or get_config().llm.model)

    # 构建系统提示词
    from auton.llm.prompt import build_system_prompt
    system_prompt = build_system_prompt(
        include_env=True,
        session_mode=session_store.mode,
    )

    # 创建 LLM 和 processor
    llm = create_llm(provider, model)

    from auton.tools import get_default_tools
    tools = get_default_tools()

    processor = SessionProcessor(
        session=session,
        llm=llm,
        tools=tools,
        session_store=session_store,
        system_prompt=system_prompt,
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
    parser.add_argument(
        "--provider",
        "-p",
        default="anthropic",
        choices=["anthropic", "minimax", "mock"],
        help="LLM Provider",
    )
    parser.add_argument("--model", "-m", default=None, help="模型名称")
    parser.add_argument("--mode", default="chat", choices=["project", "chat"], help="Session 模式（project=工程, chat=闲聊）")
    args = parser.parse_args()

    asyncio.run(run_query(args.query, args.provider, args.model, args.mode))


if __name__ == "__main__":
    main()
