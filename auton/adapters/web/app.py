"""FastAPI application serving the Auton Web UI."""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ...agent.agent import SessionProcessor
from ...agent.message import Message
from ...agent.session import Session
from ...agent.session_store import SessionStore
from ..cli.greeting_context import collect_greeting_context
from ..cli.greeting_generator import generate_greeting
from ...commands.base import CommandResult
from ...core.config import get_config
from ...core.events import EventBus
from ...core.logging import setup_logging, get_logger
from ...llm import AnthropicProvider, MiniMaxProvider
from ...llm.base import LLMProvider
from ...tools import get_default_tools
from .session_utils import (
    build_session_from_events,
    create_session_store,
    list_project_sessions,
    list_recent_date_sessions,
    load_session_events,
    resolve_session_path,
    serialize_messages,
)

log = get_logger("web")
STATIC_DIR = Path(__file__).parent / "static"
README_CANDIDATES = ("README.md", "Readme.md", "readme.md")
README_MAX_CHARS = 2000


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    project_path: str | None = None
    session_date: str | None = None


def _ensure_project_path(path_str: str | None, *, strict: bool = True) -> Path | None:
    if not path_str:
        return None
    path = Path(path_str).expanduser()
    if not path.exists() or not path.is_dir():
        if strict:
            raise HTTPException(status_code=400, detail=f"项目路径不存在：{path}")
        return None
    return path


def _create_llm() -> LLMProvider:
    config = get_config()
    llm_cfg = config.llm
    provider = llm_cfg.provider
    if provider == "minimax":
        return MiniMaxProvider(
            model=llm_cfg.model,
            api_key=llm_cfg.api_key,
            base_url=llm_cfg.base_url,
            max_tokens=llm_cfg.max_tokens,
            temperature=llm_cfg.temperature,
            timeout=llm_cfg.timeout,
        )
    return AnthropicProvider(
        model=llm_cfg.model,
        api_key=llm_cfg.api_key,
        base_url=llm_cfg.base_url,
        max_tokens=llm_cfg.max_tokens,
        temperature=llm_cfg.temperature,
        timeout=llm_cfg.timeout,
    )


def _jsonl(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


async def _stream_processor(processor: SessionProcessor) -> AsyncIterator[Any]:
    async for event in processor.run_stream():
        yield event


def _build_project_context_message(project_path: Path) -> str:
    parts = [
        f"[Project workspace]\n{project_path}",
        "在此目录内执行所有文件读写与命令；bash/glob/read 等工具请使用绝对路径。",
    ]
    for candidate in README_CANDIDATES:
        readme = project_path / candidate
        if readme.exists() and readme.is_file():
            try:
                content = readme.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            snippet = content[:README_MAX_CHARS]
            parts.append(f"\n## README 预览（{candidate}）\n{snippet}")
            break
    return "\n".join(parts)


def _inject_project_context_message(
    session: Session,
    session_store: SessionStore,
    project_path: Path,
    *,
    is_new_session: bool,
) -> None:
    if not is_new_session:
        return
    text = _build_project_context_message(project_path)
    system_msg = Message(role="system")
    system_msg.add_text(text)
    session.messages.insert(0, system_msg)
    session_store.append_system_message(session.meta.session_id, text)


@asynccontextmanager
async def _lifespan(app: FastAPI):  # type: ignore[misc]
    """应用生命周期：启动 MemoryWatcher，关闭时先 flush 再停止。"""
    from ...memory.memory_watcher import MemoryWatcher

    config = get_config()
    llm = _create_llm()
    watcher = MemoryWatcher(
        storage_dir=config.memory.storage_dir,
        llm=llm,
    )
    await watcher.start()
    try:
        yield
    finally:
        await watcher.flush()
        await watcher.stop()


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="Auton Web UI", lifespan=_lifespan)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        html_path = STATIC_DIR / "index.html"
        if not html_path.exists():
            raise HTTPException(status_code=404, detail="frontend missing")
        return html_path.read_text(encoding="utf-8")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/greeting")
    async def greeting(project_path: str | None = Query(None)) -> dict[str, str]:
        """启动问候语：复用 CLI 的 collect_greeting_context + generate_greeting 逻辑。"""
        config = get_config()
        storage_dir = Path(config.memory.storage_dir).expanduser()
        path = _ensure_project_path(project_path, strict=False)

        ctx = collect_greeting_context(
            storage_dir=storage_dir,
            cwd=path if path else storage_dir,
            has_project_history=path is not None,
        )
        ctx.should_ask_project_mode = False

        llm = _create_llm()
        text = await generate_greeting(llm=llm, ctx=ctx, session_id=str(uuid.uuid4()))
        return {"greeting": text}

    @app.get("/api/sidebar")
    async def sidebar(project_path: str | None = Query(None)) -> dict[str, Any]:
        config = get_config()
        storage_dir = Path(config.memory.storage_dir).expanduser()
        path = _ensure_project_path(project_path, strict=False)
        if path:
            sessions = list_project_sessions(storage_dir, path)
            mode = "project"
        else:
            sessions = list_recent_date_sessions(storage_dir)
            mode = "date"
        return {"mode": mode, "sessions": sessions, "project_path": path.as_posix() if path else None}

    @app.get("/api/sessions/{session_id}")
    async def session_messages(
        session_id: str,
        project_path: str | None = Query(None),
        session_date: str | None = Query(None),
    ) -> dict[str, Any]:
        config = get_config()
        storage_dir = Path(config.memory.storage_dir).expanduser()
        path = _ensure_project_path(project_path)
        session_path = resolve_session_path(
            storage_dir,
            session_id,
            project_path=path,
            session_date=session_date,
        )
        if not session_path:
            raise HTTPException(status_code=404, detail="Session not found")
        events = load_session_events(session_path)
        session = build_session_from_events(
            session_id,
            events,
            project_path=path,
        )
        return {
            "session_id": session_id,
            "messages": serialize_messages([msg.to_dict() for msg in session.messages]),
            "session_date": session_path.parent.parent.name,
        }

    @app.post("/api/chat/stream")
    async def chat_stream(payload: ChatRequest):
        msg = payload.message.strip()
        if not msg:
            raise HTTPException(status_code=400, detail="消息不能为空")

        config = get_config()
        storage_dir = Path(config.memory.storage_dir).expanduser()
        project_path = _ensure_project_path(payload.project_path)
        session_path = None

        if payload.session_id:
            session_path = resolve_session_path(
                storage_dir,
                payload.session_id,
                project_path=project_path,
                session_date=payload.session_date,
                search_days=14,
            )

        session_id = payload.session_id or str(uuid.uuid4())
        events = load_session_events(session_path) if session_path else []
        session = build_session_from_events(
            session_id,
            events,
            project_path=project_path,
        )
        processor_store_base = session_path.parent.parent if session_path else None

        session_store = create_session_store(
            storage_dir,
            project_path,
            base_override=processor_store_base,
        )

        if project_path and not events:
            _inject_project_context_message(
                session,
                session_store,
                project_path,
                is_new_session=not events,
            )

        # 通过统一工厂构建会话上下文（注入已有 session 和 session_store）
        from ...gateway import SessionFactory
        _mode = "project" if project_path else "chat"
        _gw_ctx = await SessionFactory().build(
            session_mode=_mode,
            project_root=project_path,
            yes_all=True,
            session=session,
            event_bus=EventBus(),
        )
        # Web 端 session_store 由上方 create_session_store 创建（含 base_override），
        # 保留不替换；只取 processor / llm
        processor = SessionProcessor(
            session=session,
            llm=_gw_ctx.llm,
            tools=_gw_ctx.processor.tools.values(),  # type: ignore[arg-type]
            session_store=session_store,
            event_bus=_gw_ctx.event_bus,
            system_prompt=_gw_ctx.system_prompt,
        )
        processor.prepare_streaming_session(session)
        session.add_user_message(msg)

        async def event_stream() -> AsyncIterator[bytes]:
            yield _jsonl({
                "type": "session",
                "session_id": session.meta.session_id,
                "project_path": project_path.as_posix() if project_path else None,
                "mode": session_store.mode,
                "session_date": (
                    session_store.base.name
                    if session_store.mode == "date"
                    else None
                ),
            })
            try:
                async for event in _stream_processor(processor):
                    if isinstance(event, CommandResult):
                        yield _jsonl({"type": "command", "content": event.content})
                        continue

                    event_type = getattr(event, "type", "")
                    if event_type == "text_delta":
                        yield _jsonl({"type": "delta", "text": getattr(event, "delta", "")})
                    elif event_type == "text_finish":
                        yield _jsonl({"type": "message", "text": getattr(event, "full_text", "") or getattr(event, "content", "")})
                    elif event_type == "tool_use":
                        yield _jsonl({"type": "tool_call", "name": getattr(event, "name", "")})
                    else:
                        status = getattr(event, "status", None)
                        if status:
                            yield _jsonl({
                                "type": "result",
                                "status": status,
                                "reason": getattr(event, "reason", ""),
                            })
            except Exception as exc:  # pragma: no cover - streamed to client
                log.error("stream error: {exc}", exc=exc)
                yield _jsonl({"type": "error", "message": str(exc)})
            finally:
                yield _jsonl({
                    "type": "complete",
                    "session_id": session.meta.session_id,
                })

        return StreamingResponse(event_stream(), media_type="application/jsonl; charset=utf-8")

    return app


app = create_app()
