#!/usr/bin/env python3
"""Auton 多轮对话测试脚本

测试路径：
  用户 → add_user_message → run_stream() → LLM回复
       → add_user_message → run_stream() → LLM回复（续上下文）
       → ...

注意：
  - run_stream() 是单次执行（不是 while 循环）
  - 多轮对话需要多次调用 run_stream()，每次都在 session.messages 中续上下文
  - run_stream() 结束时 yield ProcessResult(continue)，调用方决定是否继续

目的：
  - 理解多轮对话的调用方式
  - 验证 session.messages 在多次 run_stream 调用间的累积
  - 可以在以下位置打断点：
      - debug_query.py:76     (async for event in run_stream)
      - auton/agent/agent.py:193 (run_stream)
      - auton/agent/agent.py:248 (_decide)

用法：
  python scripts/debug_multiturn.py
  python scripts/debug_multiturn.py --queries "你好" "帮我读一下 README" "总结一下"
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from auton.agent import Session, SessionProcessor
from auton.agent.session_store import SessionStore
from auton.core.config import get_config
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
    return AnthropicProvider(
        model=model or cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        timeout=cfg.timeout,
    )


async def run_single_turn(processor: SessionProcessor, query: str, turn: int) -> str:
    """单轮对话：添加用户消息 → run_stream → 收集回复"""
    session = processor.session

    # 添加用户消息（续到 session.messages）
    session.add_user_message(query)

    print(f"\n{'─'*60}")
    print(f"[Turn {turn}] User: {query}")
    print(f"{'─'*60}")

    buffer = ""
    async for event in processor.run_stream():
        if not hasattr(event, "type"):
            # ProcessResult
            continue
        if event.type == "text_delta":
            delta = getattr(event, "delta", "")
            print(delta, end="", flush=True)
            buffer += delta
        elif event.type == "tool_use":
            print(f"\n[tool: {event.name}]")

    print()
    return buffer


async def run_multiturn(queries: list[str], provider: str = "anthropic", model: str | None = None):
    setup_logging()
    log = get_logger("debug_multiturn")
    config = get_config()

    session_store = SessionStore(config.memory.storage_dir)
    session = Session.create()

    llm = create_llm(provider, model)

    from auton.tools import get_default_tools
    tools = get_default_tools()

    processor = SessionProcessor(
        session=session,
        llm=llm,
        tools=tools,
        session_store=session_store,
    )

    log.info("session_id={}", session.meta.session_id)
    log.info("provider={} model={}", provider, model or config.llm.model)
    log.info("turns={}", len(queries))

    total_text: list[str] = []

    for i, query in enumerate(queries, 1):
        reply = await run_single_turn(processor, query, i)
        total_text.append(reply)

        # 打印当前 session 状态（验证上下文累积）
        msg_count = len(session.messages)
        log.debug(
            "turn={n} session.messages={count} last_role={role}",
            n=i, count=msg_count,
            role=session.messages[-1].role if session.messages else "none",
        )

    print(f"\n{'='*60}")
    print(f"多轮对话结束")
    print(f"  session_id : {session.meta.session_id}")
    print(f"  总轮次      : {len(queries)}")
    print(f"  总消息数    : {len(session.messages)}")
    print(f"  各轮回复长度: {[len(t) for t in total_text]}")

    return total_text


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Auton 多轮对话测试")
    parser.add_argument(
        "--queries", "-q", nargs="+",
        default=["你好，介绍一下你自己", "你能做什么？", "再见"],
        help="多轮对话的问题列表",
    )
    parser.add_argument("--provider", "-p", default="anthropic",
                        choices=["anthropic", "minimax"], help="LLM Provider")
    parser.add_argument("--model", "-m", default=None, help="模型名称")
    args = parser.parse_args()

    asyncio.run(run_multiturn(args.queries, args.provider, args.model))


if __name__ == "__main__":
    main()
