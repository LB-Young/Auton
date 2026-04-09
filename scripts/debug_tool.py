#!/usr/bin/env python3
"""Auton 工具调用测试脚本

测试指定工具的执行流程：
  用户请求 → LLM决定调用工具 → _execute_tools() → Tool.execute()
  → 工具结果注入 session.messages → 第二轮 LLM 基于结果回复

核心链路（断点位置）：
  - auton/agent/agent.py:296     tool_use 事件处理（_handle_llm_event）
  - auton/agent/agent.py:314     _execute_tools（工具执行入口）
  - auton/agent/agent.py:337     tool.execute()（实际工具逻辑）
  - auton/agent/agent.py:348     工具结果注入 session.messages

用法：
  python scripts/debug_tool.py "帮我列出当前目录下的所有 .py 文件"
  python scripts/debug_tool.py --tool bash "echo hello world"
  python scripts/debug_tool.py --tool read "auton/__init__.py"
  python scripts/debug_tool.py --tool glob "**/*.py"
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


# ─── 可用工具列表（与 get_default_tools 顺序一致）──────────────────────────────
TOOL_MAP = {
    "bash":     "auton.tools.bash.BashTool",
    "read":     "auton.tools.read.ReadTool",
    "write":    "auton.tools.write.WriteTool",
    "edit":     "auton.tools.edit.EditTool",
    "glob":     "auton.tools.glob.GlobTool",
    "grep":     "auton.tools.grep.GrepTool",
    "web_search":  "auton.tools.web_search.WebSearchTool",
    "web_fetch":   "auton.tools.web_fetch.WebFetchTool",
    "task_create": "auton.tools.task_create.TaskCreateTool",
    "task_list":   "auton.tools.task_list.TaskListTool",
    "agent_create": "auton.tools.agent_create.AgentCreateTool",
}


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


def build_tools_query(selected_tool: str | None, query: str) -> str:
    """根据工具构建查询，强制触发特定工具"""
    if selected_tool == "bash":
        return query or "执行 bash 命令：echo hello world"
    elif selected_tool == "read":
        return query or "读取文件：scripts/debug_query.py"
    elif selected_tool == "glob":
        return query or "查找所有 .py 文件：glob **/*.py"
    elif selected_tool == "grep":
        return query or "搜索文件内容：grep 'class Session' auton/**/*.py"
    elif selected_tool == "web_search":
        return query or "搜索网页：web_search Python 3.12 新特性"
    else:
        return query or "列出当前目录下所有 Python 文件"


async def run_tool_query(
    query: str,
    provider: str = "anthropic",
    model: str | None = None,
    selected_tool: str | None = None,
    security_mode: str = "yolo",
):
    setup_logging()
    log = get_logger("debug_tool")
    config = get_config()

    session_store = SessionStore(config.memory.storage_dir)
    session = Session.create()

    llm = create_llm(provider, model)

    # 构造查询（强制触发指定工具）
    full_query = build_tools_query(selected_tool, query)

    # 导入并实例化工具（各工具在 auton/tools/<name>/__init__.py）
    from auton.tools.bash import BashTool
    from auton.tools.read import ReadTool
    from auton.tools.write import WriteTool
    from auton.tools.edit import EditTool
    from auton.tools.glob import GlobTool
    from auton.tools.grep import GrepTool
    from auton.tools.web_search import WebSearchTool
    from auton.tools.web_fetch import WebFetchTool
    from auton.tools.task_create import TaskCreateTool
    from auton.tools.task_list import TaskListTool
    from auton.tools.agent_create import AgentCreateTool

    all_tools = [
        BashTool(permission_mode=security_mode),
        ReadTool(),
        WriteTool(),
        EditTool(),
        GlobTool(),
        GrepTool(),
        WebSearchTool(),
        WebFetchTool(),
        TaskCreateTool(),
        TaskListTool(),
        AgentCreateTool(),
    ]

    processor = SessionProcessor(
        session=session,
        llm=llm,
        tools=all_tools,
        session_store=session_store,
    )

    session.add_user_message(full_query)

    log.info("session_id={}", session.meta.session_id)
    log.info("tool={} security_mode={}", selected_tool, security_mode)

    print(f"\n{'='*60}")
    print(f"Query     : {full_query}")
    print(f"Tool      : {selected_tool or 'auto'}")
    print(f"Security  : {security_mode}")
    print(f"{'='*60}\n")

    # ── 第一轮：收集工具调用事件 ───────────────────────────────────────────────
    tool_calls: list[dict] = []
    text_deltas: list[str] = []
    tool_results: list[str] = []
    turns = 0

    async for event in processor.run_stream():
        if not hasattr(event, "type"):
            # ProcessResult
            turns += 1
            if event.status == "continue":
                log.debug("turn={t} decision=continue (tools executed, going next round)", t=turns)
            elif event.status == "stop":
                log.debug("turn={t} decision=stop reason={r}", t=turns, r=event.reason)
            continue

        if event.type == "tool_use":
            print(f"\n[LLM 触发工具] {event.name}({event.input})")
            tool_calls.append({"name": event.name, "input": event.input})
        elif event.type == "text_delta":
            delta = getattr(event, "delta", "")
            print(delta, end="", flush=True)
            text_deltas.append(delta)

    # ── 打印总结 ──────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"工具调用总结")
    print(f"  session_id : {session.meta.session_id}")
    print(f"  总轮次      : {turns}")
    print(f"  工具调用    : {len(tool_calls)} 次")
    for tc in tool_calls:
        print(f"    - {tc['name']}: {tc['input']}")

    # 从 session.messages 中提取工具结果
    for msg in session.messages:
        if msg.role == "user" and "[tool:" in msg.get_text():
            tool_results.append(msg.get_text())

    if tool_results:
        print(f"  工具结果    : {len(tool_results)} 条")
        for tr in tool_results:
            preview = tr[:200].replace("\n", " ")
            print(f"    > {preview}...")

    full_reply = "".join(text_deltas)
    print(f"  最终回复长度: {len(full_reply)} chars")
    print(f"  总消息数    : {len(session.messages)}")

    return {
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "full_reply": full_reply,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Auton 工具调用测试")
    parser.add_argument("query", nargs="?", default=None,
                        help="要发送给 Auton 的请求（会自动匹配合适的工具）")
    parser.add_argument("--tool", "-t", choices=list(TOOL_MAP.keys()),
                        default=None, help="指定要测试的工具")
    parser.add_argument("--provider", "-p", default="anthropic",
                        choices=["anthropic", "minimax"], help="LLM Provider")
    parser.add_argument("--model", "-m", default=None, help="模型名称")
    parser.add_argument("--security", "-s", default="yolo",
                        choices=["default", "auto", "bypass", "yolo"],
                        help="BashTool 权限模式（yolo=无限制）")
    args = parser.parse_args()

    asyncio.run(run_tool_query(
        query=args.query,
        provider=args.provider,
        model=args.model,
        selected_tool=args.tool,
        security_mode=args.security,
    ))


if __name__ == "__main__":
    main()
