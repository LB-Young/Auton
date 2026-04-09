"""CLI — Auton 命令行入口"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from ..agent.agent import SessionProcessor
from ..agent.session import Session
from ..agent.session_store import SessionStore
from ..core.config import get_config
from ..core.event_types import (
    AutonEvent,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
    ToolErrorEvent,
)
from ..core.events import EventBus
from ..core.logging import get_logger, setup_logging
from ..llm.anthropic_provider import AnthropicProvider
from ..llm.base import LLMProvider
from ..tools import get_default_tools, get_registry
from ..tools.mcp import load_mcp_servers, stop_mcp_servers
from .greeting_context import collect_greeting_context
from .greeting_generator import generate_greeting
from .project_mode_intent import parse_project_mode_reply

app = typer.Typer(help="Auton — Personal AI Agent", no_args_is_help=True)
console = Console()


class CLIRenderer:
    """CLI 流式渲染器

    支持两类事件：
    - LLMStreamEvent  (llm/base.py): run_stream() yield 的 LLM 原始事件
    - AutonEvent      (core/event_types.py): EventBus 分发的结构化事件
    """

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._tool_outputs: list[str] = []
        self._reasoning_chunks: list[str] = []
        self._done = False
        self._thinking = False

    def render(self) -> str:
        parts = []
        if self._thinking and self._reasoning_chunks:
            thinking_text = "".join(self._reasoning_chunks)
            if len(thinking_text) > 200:
                thinking_text = thinking_text[-200:] + "..."
            parts.append(f"[dim][思考中...][/dim]\n\n")
        if self._lines:
            parts.append("".join(self._lines))
        if self._tool_outputs:
            tools_str = "\n".join(self._tool_outputs)
            parts.append(f"\n[Tool outputs]\n{tools_str}")
        return "".join(parts)

    def handle(self, event) -> None:
        # ── LLMStreamEvent (run_stream 直接 yield 的) ─────────────────────────
        event_type = getattr(event, "type", None)
        if event_type == "text_delta":
            self._thinking = False
            self._lines.append(getattr(event, "delta", ""))
        elif event_type == "reasoning_start":
            self._thinking = True
        elif event_type == "reasoning_delta":
            self._reasoning_chunks.append(getattr(event, "delta", ""))
        elif event_type == "reasoning_finish":
            self._thinking = False
        elif event_type == "tool_use":
            self._tool_outputs.append(f"\n[{getattr(event, 'name', '?')}] ...")
        # ── AutonEvent (EventBus 分发的结构化事件) ────────────────────────────
        elif isinstance(event, AutonEvent):
            if isinstance(event, TextDeltaEvent):
                self._thinking = False
                self._lines.append(event.delta)
            elif isinstance(event, ToolCallEvent):
                self._tool_outputs.append(f"\n[{event.tool_name}] ...")
            elif isinstance(event, ToolResultEvent):
                if self._tool_outputs:
                    self._tool_outputs[-1] = f"\n[{event.tool_name}]\n{event.output[:500]}"
            elif isinstance(event, ToolErrorEvent):
                if self._tool_outputs:
                    self._tool_outputs[-1] = f"\n[{event.tool_name}] ERROR: {event.error}"


async def _start_session(
    message: str | None,
    project: Path | None,
    model: str | None,
    provider: str | None,
    permission: str | None,
    no_stream: bool,
    yes_all: bool,
) -> None:
    setup_logging()
    log = get_logger("cli")
    config = get_config()

    session_store = SessionStore(
        storage_dir=config.memory.storage_dir,
        project_root=project,
    )
    session = Session.create(project_path=str(project) if project else None)

    log.info("session_id={id}", id=session.meta.session_id)

    # LLM Provider
    llm_cfg = config.llm
    selected_provider = provider or llm_cfg.provider

    llm: LLMProvider
    if selected_provider == "minimax":
        from auton.llm import MiniMaxProvider
        llm = MiniMaxProvider(
            model=model or llm_cfg.model,
            api_key=llm_cfg.api_key,
            base_url=llm_cfg.base_url,
            max_tokens=llm_cfg.max_tokens,
            temperature=llm_cfg.temperature,
            timeout=llm_cfg.timeout,
        )
    else:
        llm = AnthropicProvider(
            model=model or llm_cfg.model,
            api_key=llm_cfg.api_key,
            base_url=llm_cfg.base_url,
            max_tokens=llm_cfg.max_tokens,
            temperature=llm_cfg.temperature,
            timeout=llm_cfg.timeout,
        )

    # Tools — BashTool gets permission_mode from config/cli flag
    permission_mode = permission or config.security.permission_mode
    tools = get_default_tools(permission_mode=permission_mode, yes_all=yes_all)

    # MCP servers — 启动时初始化，退出时关闭
    registry = get_registry()
    if config.mcp.auto_start and config.mcp.servers:
        try:
            mcp_clients = await load_mcp_servers(
                {"mcp": config.mcp.model_dump()}
            )
            for name, client in mcp_clients.items():
                registry.set_mcp_client(name, client)
            log.info("MCP servers started: {servers}", servers=list(mcp_clients.keys()))
        except Exception as exc:
            log.warning("failed to load MCP servers: {exc}", exc=exc)

    # Event bus
    event_bus = EventBus()

    # SessionProcessor
    processor = SessionProcessor(
        session=session,
        llm=llm,
        tools=tools,
        session_store=session_store,
        event_bus=event_bus,
    )

    # 添加用户消息
    if message:
        session.add_user_message(message)

    # Interactive input loop
    if no_stream:
        await _run_sync(processor, session)
    elif message:
        # 有初始消息：单次运行，流式渲染
        await _run_stream_once(processor)
    else:
        # 无初始消息：交互式 REPL 循环
        await _run_repl(processor)


@app.command()
def main(
    message: str | None = typer.Option(None, "--msg", "-m", help="Initial message"),
    project: Path | None = typer.Option(None, "--project", "-p", help="Project path"),
    model: str | None = typer.Option(None, "--model", help="Override model"),
    provider: str | None = typer.Option(None, "--provider", help="LLM provider: anthropic/minimax"),
    permission: str | None = typer.Option(None, "--permission", help="Permission mode: default/auto/bypass/yolo"),
    no_stream: bool = typer.Option(False, "--no-stream", help="Disable streaming"),
    yes_all: bool = typer.Option(False, "--yes", "-y", help="Auto-confirm all permission prompts"),
) -> None:
    """启动 Auton 会话"""
    import anyio
    anyio.run(_start_session, message, project, model, provider, permission, no_stream, yes_all)


@app.command(help="启动 Auton Web 界面")
def web(
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
    port: int = typer.Option(8000, "--port", "-p", help="监听端口"),
) -> None:
    import uvicorn
    from ..web.app import app as web_app

    console.print(f"[green]Starting Auton Web UI at http://{host}:{port}[/green]")
    uvicorn.run(web_app, host=host, port=port, log_level="info")


async def _run_sync(processor: SessionProcessor, session: Session) -> None:
    try:
        result = await processor.run()
        console.print(f"\n[dim]Session ended: {result.status} — {result.reason}[/dim]")
    finally:
        await stop_mcp_servers()


async def _render_stream(processor: SessionProcessor, live) -> None:
    """流式渲染事件（供单次/REPL 共用）"""
    renderer = CLIRenderer()
    try:
        async for event in processor.run_stream():
            if not hasattr(event, "type"):
                continue
            from auton.commands import CommandResult
            if isinstance(event, CommandResult):
                live.update(Panel(
                    Markdown(event.content),
                    title="[command result]",
                    border_style="green",
                ))
                continue
            renderer.handle(event)
            live.update(Panel(
                Markdown(renderer.render()),
                title="Auton",
                border_style="blue",
            ))
    except Exception as exc:
        live.update(Panel(
            f"[red]Error:[/red] {exc}",
            title="[error]",
            border_style="red",
        ))


async def _run_stream_once(processor: SessionProcessor) -> None:
    """单次运行（用于有初始消息的场景）"""
    try:
        with Live(console=console, refresh_per_second=10) as live:
            await _render_stream(processor, live)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
    finally:
        await stop_mcp_servers()


async def _run_repl(processor: SessionProcessor) -> None:
    """交互式 REPL 循环：问候 → 添加消息 → 流式响应 → 循环"""
    from auton.commands import CommandResult

    store = processor.session_store
    cwd = Path.cwd()

    # ── 问候 ─────────────────────────────────────────────────────────────
    console.print("\n[bold green]你好！我是 Auton，你的 AI 助手。[/bold green]")
    console.print(f"[dim]当前目录：{cwd}[/dim]")

    # 只按已有项目历史判定是否直接进入项目模式
    has_project_history = store.has_existing_project_history(cwd)
    if has_project_history:
        if store.mode != "project" or store.project_root != cwd:
            store.set_project_root(cwd)
        console.print(f"[green]✓ 检测到历史项目记录：{cwd.name}（项目模式）[/green]\n")
    else:
        console.print("[dim]当前目录暂无历史项目记录，默认日期模式[/dim]\n")

    # 本地收集上下文，再让模型生成问候
    greeting_ctx = collect_greeting_context(
        storage_dir=store.storage_dir,
        cwd=cwd,
        has_project_history=has_project_history,
    )
    greeting_text = await generate_greeting(
        llm=processor.llm,
        ctx=greeting_ctx,
        session_id=processor.session.meta.session_id,
    )

    # 将问候作为助手消息加入 session
    greeting_msg = processor.session.add_assistant_message()
    greeting_msg.add_text(greeting_text)

    # 渲染问候语
    console.print(Panel(
        Markdown(greeting_text),
        title="Auton",
        border_style="blue",
    ))

    # 项目模式询问：独立显示，不依赖 LLM 问候是否包含该问题
    if not has_project_history:
        console.print(
            "[dim]是否按[bold]项目模式[/bold]开启？(y/N，直接回车或输入任务则跳过)[/dim]"
        )
        try:
            mode_input = await asyncio.to_thread(console.input, "[bold blue]>[/bold blue] ")
        except (KeyboardInterrupt, EOFError):
            mode_input = ""

        decision = parse_project_mode_reply(mode_input)
        if decision is True:
            store.set_project_root(cwd)
            console.print(f"[green]✓ 已切换为项目模式：{cwd.name}[/green]\n")
        else:
            console.print("[dim]已保持日期模式。[/dim]\n")

        # 无论用户怎么回答，问候都立刻持久化
        processor.session_store.append_assistant_message(
            processor.session.meta.session_id,
            greeting_msg,
        )

        # 如果用户输入的不是 yes/no 而是一条真实任务，直接执行
        if decision is None and mode_input.strip():
            processor.session.add_user_message(mode_input)
            renderer = CLIRenderer()
            try:
                with Live(console=console, refresh_per_second=10, transient=False) as live:
                    try:
                        async for event in processor.run_stream():
                            if not hasattr(event, "type"):
                                continue
                            if isinstance(event, CommandResult):
                                live.update(Panel(
                                    Markdown(event.content),
                                    title="[command result]",
                                    border_style="green",
                                ))
                                continue
                            renderer.handle(event)
                            live.update(Panel(
                                Markdown(renderer.render()),
                                title="Auton",
                                border_style="blue",
                            ))
                    except Exception as exc:
                        live.update(Panel(
                            f"[red]Error:[/red] {exc}",
                            title="[error]",
                            border_style="red",
                        ))
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted[/yellow]")
    else:
        processor.session_store.append_assistant_message(
            processor.session.meta.session_id,
            greeting_msg,
        )

    try:
        while True:
            try:
                user_input = await asyncio.to_thread(console.input, "\n[bold blue]>[/bold blue] ")
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]再见！[/yellow]")
                break

            if not user_input.strip():
                continue

            # 添加用户消息，开始一轮
            processor.session.add_user_message(user_input)
            renderer = CLIRenderer()

            try:
                with Live(console=console, refresh_per_second=10, transient=False) as live:
                    try:
                        async for event in processor.run_stream():
                            if not hasattr(event, "type"):
                                continue
                            if isinstance(event, CommandResult):
                                live.update(Panel(
                                    Markdown(event.content),
                                    title="[command result]",
                                    border_style="green",
                                ))
                                continue
                            renderer.handle(event)
                            live.update(Panel(
                                Markdown(renderer.render()),
                                title="Auton",
                                border_style="blue",
                            ))
                    except Exception as exc:
                        live.update(Panel(
                            f"[red]Error:[/red] {exc}",
                            title="[error]",
                            border_style="red",
                        ))
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted[/yellow]")
                break
    finally:
        await stop_mcp_servers()


@app.command()
def replay(
    session_id: str = typer.Argument(..., help="Session ID to replay"),
) -> None:
    """回放历史会话"""
    setup_logging()
    config = get_config()
    store = SessionStore(config.memory.storage_dir)
    events = store.read_session_by_id(session_id)

    console.print(f"[dim]Replay session {session_id} ({len(events)} events)[/dim]\n")
    for ev in events:
        role = ev.get("role", ev.get("type", "?"))
        if role == "user":
            console.print(Panel(
                ev.get("content", ""),
                title=f"[{role}]",
                border_style="green",
            ))
        elif role == "assistant":
            text = ""
            for part in ev.get("parts", []):
                if part.get("type") == "text":
                    text += part.get("content", "")
            if text:
                console.print(Panel(
                    Markdown(text),
                    title="[assistant]",
                    border_style="blue",
                ))
        else:
            console.print(f"[dim]{role}: {ev}[/dim]")
        console.print()


if __name__ == "__main__":
    app()
