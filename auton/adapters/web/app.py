"""FastAPI application serving the Auton Web UI.

Web 层职责（单一入口）：
  1. 接收 HTTP 请求，解析用户输入和 session 上下文
  2. 定位或创建 session，恢复历史消息
  3. 委托 SessionFactory 构建会话运行时（LLM / Tools / SystemPrompt）
  4. 驱动 SessionProcessor.run_stream() 主循环
  5. 将流式事件转换为 JSONL 响应推送给前端

设计原则：
  - Web 层只做编排，不包含任何业务逻辑
  - 所有业务逻辑（compact、工具调用、LLM 调用）都在 SessionProcessor 中
  - session_store 由 Web 层创建并传入，SessionFactory 不重复创建（通过 base_override）
"""

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
    """POST /api/chat/stream 的请求体

    设计意图：
      - message: 必填，用户输入文本
      - session_id: 可选，指定恢复哪个历史 session（为空则创建新 session）
      - project_path: 可选，指定项目目录（影响 session_store 的 mode 和 system prompt 内容）
      - session_date: 可选，辅助定位 session（date 模式下需要）

    为什么需要 session_date？
      session 目录结构为 ~/.auton/sessions/{date}/{session_id}/，
      给定 session_id 但不指定 date 时，resolve_session_path 会向前回溯最多 14 天搜索。
    """
    message: str
    session_id: str | None = None
    project_path: str | None = None
    session_date: str | None = None


def _ensure_project_path(path_str: str | None, *, strict: bool = True) -> Path | None:
    """将字符串路径转换为 Path 并验证其有效性。

    strict=True 时：如果路径不存在或不是目录，抛出 400 HTTPException
    strict=False 时：如果路径无效，静默返回 None（用于可选路径的宽松检查）

    为什么需要 strict 参数？
      - /api/sidebar 和 /api/greeting 允许 project_path 为空（用户未选择项目）
      - /api/sessions 和 /api/chat/stream 要求 project_path 必须有效
    """
    if not path_str:
        return None
    path = Path(path_str).expanduser()
    if not path.exists() or not path.is_dir():
        if strict:
            raise HTTPException(status_code=400, detail=f"项目路径不存在：{path}")
        return None
    return path


def _create_llm() -> LLMProvider:
    """根据配置创建 LLM Provider，支持全部 provider。

    为什么委托给 SessionFactory.create_llm？
      Web 层不应该维护独立的 provider 创建逻辑，否则：
        1. 与 CLI 的创建逻辑容易产生分歧
        2. 新增 provider 时需要在多处修改
      统一通过 SessionFactory.create_llm() 确保所有入口行为一致。
    """
    from ...gateway import SessionFactory
    return SessionFactory.create_llm()


def _jsonl(payload: dict[str, Any]) -> bytes:
    """将 dict 序列化为带换行的 JSONL 字节串。

    为什么用 JSONL 而非 SSE？
      前端需要区分事件类型（delta/command/tool_call/error/complete），
      JSONL 每行一个完整 JSON 对象，解析简单且天然支持多类型多事件流。
    """
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


async def _stream_processor(processor: SessionProcessor) -> AsyncIterator[Any]:
    """将 SessionProcessor.run_stream() 的事件透传给调用方。

    为什么需要这个包装函数？
      run_stream() 是 async generator，不能直接作为 StreamingResponse 的 yield 来源。
      这层包装确保类型正确（AsyncIterator[Any]）且事件能正确流向 HTTP 响应。
    """
    async for event in processor.run_stream():
        yield event


def _build_project_context_message(project_path: Path) -> str:
    """为新 session 构建项目上下文 system 消息。

    包含内容：
      1. [Project workspace] 标识 + 路径
      2. 工具使用提示（使用绝对路径）
      3. README 文件预览（最多 2000 字符）

    为什么需要 README 预览？
      如果项目有 README.md，LLM 需要知道项目的基本介绍、目录结构和使用方式，
      这样即使没有用户指令，LLM 也能理解当前项目的上下文。

    为什么限制 2000 字符？
      README 可能很大，全部塞入 system 消息会浪费 token 预算。
      2000 字符足以传达项目概览，又不会显著影响上下文成本。
    """
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
    """将项目上下文注入为 system 消息。

    为什么只在 is_new_session=True 时注入？
      - 历史 session 已经有完整的消息历史和 system 消息，不需要重复注入
      - 新 session 才需要通过这条消息告知 LLM 当前工作目录和项目信息

    为什么插入到 messages[0]（头部）？
      system 消息在 messages 列表中的位置影响 LLM 对上下文的感知权重。
      放在最前面是最规范的做法，LLM 会将系统指令视为最高优先级。

    为什么同时调用 session_store.append_system_message()？
      session.messages 是内存中的消息列表，session_store 是持久化层。
      两者需要保持同步，否则 session 重启后恢复消息时会丢失这条 system 消息。
    """
    if not is_new_session:
        return
    text = _build_project_context_message(project_path)
    system_msg = Message(role="system")
    system_msg.add_text(text)
    session.messages.insert(0, system_msg)
    session_store.append_system_message(session.meta.session_id, text)


@asynccontextmanager
async def _lifespan(app: FastAPI):  # type: ignore[misc]
    """FastAPI 应用生命周期管理：启动和停止后台服务。

    为什么需要 lifespan 管理？
      - MemoryWatcher 是一个长期运行的后台进程（定时扫描 session 做摘要）
      - 不使用 lifespan 的话，后台进程会在请求间被垃圾回收
      - 通过 lifespan 确保应用启动时启动、退出时优雅关闭

    为什么先 flush() 再 stop()？
      flush() 将内存中的记忆数据写入磁盘（避免丢失）
      stop() 关闭后台定时器和资源
      顺序不能颠倒，否则未 flush 的数据会丢失。
    """
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
    """创建并配置 FastAPI 应用实例。

    为什么叫 create_app 而非直接创建 app？
      为了支持通过 import 引用并在测试时替换（pytest fixture 常用模式）。

    为什么用 lifespan 而非 on_event？
      FastAPI 0.100+ 推荐 lifespan 替代 on_event("startup"/"shutdown")，
      lifespan 更简洁且支持 async 上下文管理器。
    """
    setup_logging()
    app = FastAPI(title="Auton Web UI", lifespan=_lifespan)

    # 挂载静态文件目录（如果有的话）
    # 为什么需要这个检查？
    #   开发时可能没有构建前端，静态目录不存在不应该导致启动失败
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        """返回前端 HTML 页面。

        为什么用 HTMLResponse 而非直接返回文件？
          FastAPI 的 StaticFiles 更适合服务 JS/CSS 等静态资源，
          HTML 作为入口文件直接读取内容返回更简单直接。
        """
        html_path = STATIC_DIR / "index.html"
        if not html_path.exists():
            raise HTTPException(status_code=404, detail="frontend missing")
        return html_path.read_text(encoding="utf-8")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """健康检查端点，供负载均衡器和前端轮询使用。

        为什么返回 dict 而不是字符串？
          便于扩展（如加入 version、database 状态等），
          前端可以通过 response.ok 判断，不需要解析 body。
        """
        return {"status": "ok"}

    @app.get("/api/greeting")
    async def greeting(project_path: str | None = Query(None)) -> dict[str, str]:
        """生成启动问候语，复用 CLI 的收集和生成逻辑。

        为什么需要问候语？
          - 新用户首次使用时，LLM 根据项目上下文生成个性化欢迎语
          - 包含项目简介、最近活动、推荐操作等

        为什么复用 CLI 的逻辑？
          - 避免重复实现相同逻辑（collect_greeting_context + generate_greeting）
          - Web 和 CLI 的问候语行为保持一致

        为什么 should_ask_project_mode = False？
          Web 端用户在发起请求时已通过 project_path 参数指定了项目，
          不需要再次询问是否进入项目模式。
        """
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
        """返回侧边栏会话列表。

        为什么有两种模式（project / date）？
          - project 模式：列出指定项目下的所有 session（按项目组织）
          - date 模式：列出最近所有 session（按日期分组）

        为什么 project_path 为空时用 date 模式？
          用户未选择项目时，无法按项目过滤，只能按日期显示最近的 session。
        """
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
        """加载指定 session 的完整消息历史，用于恢复会话页面。

        为什么需要 project_path 和 session_date？
          session 目录结构为 ~/.auton/sessions/{date}/{session_id}/，
          给定 session_id 时需要这两个参数辅助定位具体目录。

        为什么返回 messages 而不是 events？
          前端只需要消息内容，不需要底层的压缩事件等内部数据结构。
          build_session_from_events 已经过滤和转换好了，serialize_messages 进一步格式化。
        """
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
        """核心聊天端点：接收用户消息，流式返回 LLM 响应事件。

        执行流程：
          1. 校验输入
          2. 定位或创建 session
          3. 恢复历史消息（构建 Session 对象）
          4. 注入项目上下文（新 session + 有 project_path）
          5. 通过 SessionFactory 构建运行时（LLM / Tools / SystemPrompt）
          6. 驱动 SessionProcessor.run_stream() 流式主循环
          7. 将事件转换为 JSONL 推送给前端

        为什么返回 StreamingResponse？
          LLM 响应通过流式方式逐步返回，避免用户等待完整生成。
          前端可以通过 fetch + ReadableStream 实时显示打字效果。
        """
        msg = payload.message.strip()
        if not msg:
            raise HTTPException(status_code=400, detail="消息不能为空")

        config = get_config()
        storage_dir = Path(config.memory.storage_dir).expanduser()

        # ── 1. 解析 project_path（必填，session 模式依赖此参数）────────────
        project_path = _ensure_project_path(payload.project_path)

        # ── 2. 定位 session 目录（基于 session_id 和 date）─────────────────
        # 为什么需要 session_date？
        #   session 目录结构: ~/.auton/sessions/{date}/{session_id}/
        #   如果只给 session_id 不给 date，resolve_session_path 会回溯搜索最多 14 天
        session_path = None
        if payload.session_id:
            session_path = resolve_session_path(
                storage_dir,
                payload.session_id,
                project_path=project_path,
                session_date=payload.session_date,
                search_days=14,
            )

        # ── 3. 确定 session_id（新 session 用 uuid，恢复 session 用请求中的）─
        session_id = payload.session_id or str(uuid.uuid4())

        # ── 4. 从 JSONL 文件恢复历史消息，构建 Session 对象 ──────────────
        # 如果 session_path 不存在（新建 session），events 为空列表
        events = load_session_events(session_path) if session_path else []
        session = build_session_from_events(
            session_id,
            events,
            project_path=project_path,
        )

        # ── 5. 创建 SessionStore（持久化层）────────────────────────────────
        # 为什么需要 base_override？
        #   如果是恢复的 session，session_store 应该写入该 session 原本的目录，
        #   而不是基于当前 project_path 重新创建目录。
        #   base_override = session_path.parent.parent 就是原来 session 所在的日期目录。
        processor_store_base = session_path.parent.parent if session_path else None
        session_store = create_session_store(
            storage_dir,
            project_path,
            base_override=processor_store_base,
        )

        # ── 6. 注入项目上下文（新 session 且有 project_path 时）─────────────
        # 为什么只在 "没有历史事件" 时注入？
        #   有历史事件的 session 已经有完整的消息和 system 消息，
        #   不需要也不应该重复注入（会导致重复 system 消息）。
        if project_path and not events:
            _inject_project_context_message(
                session,
                session_store,
                project_path,
                is_new_session=not events,
            )

        # ── 7. 通过 SessionFactory 统一构建运行时上下文 ────────────────────
        # 为什么传入已有的 session？
        #   我们已经从 JSONL 恢复了 session，不需要 SessionFactory 再创建新的。
        #   这样保证恢复的 session 和新创建的 session 行为一致。
        from ...gateway import SessionFactory
        _mode = "project" if project_path else "chat"
        _gw_ctx = await SessionFactory().build(
            session_mode=_mode,
            project_root=project_path,
            yes_all=True,          # Web 端跳过所有工具确认（yes-all 模式）
            session=session,       # 复用已恢复的 session
            event_bus=EventBus(),
        )

        # ── 8. 构造 SessionProcessor（复用 SessionFactory 的 LLM 和 tools，
        #       但 session_store 用 Web 层创建的）──────────────────────────
        # 为什么 session_store 不从 _gw_ctx 拿？
        #   因为 _gw_ctx.session_store 是基于当前 project_root 创建的，
        #   对于恢复的历史 session，我们需要写入它原本的目录（base_override 指定）。
        #   所以保留 Web 层创建的 session_store，只复用 _gw_ctx 的 llm/tools/system_prompt。
        processor = SessionProcessor(
            session=session,
            llm=_gw_ctx.llm,
            tools=_gw_ctx.processor.tools.values(),  # type: ignore[arg-type]
            session_store=session_store,
            event_bus=_gw_ctx.event_bus,
            system_prompt=_gw_ctx.system_prompt,
        )

        # ── 9. 初始化流式会话状态 ──────────────────────────────────────────
        # 为什么需要 prepare_streaming_session？
        #   新请求到来时，_last_stored_msg_index 需要指向当前已有消息的末尾，
        #   这样新消息才会被正确持久化。
        processor.prepare_streaming_session(session)

        # ── 10. 添加用户消息到 session（在 run_stream 之前）───────────────
        # 注意：这条消息的持久化由 prepare_streaming_session + run_stream 内部处理
        session.add_user_message(msg)

        async def event_stream() -> AsyncIterator[bytes]:
            """异步生成器：逐事件 yield JSONL 格式的响应。

            为什么用内部函数而不是直接 yield？
              需要在 StreamingResponse 创建前完成所有初始化，
              而 yield 只能在 async generator 中使用。
              这个内部函数延迟执行，确保初始化逻辑先运行。

            为什么每个事件类型对应不同的 JSON 结构？
              前端需要区分事件类型来渲染不同的 UI（打字效果 / 工具调用提示 / 错误提示）。
            """
            # 首先发送 session 元数据，让前端知道当前 session 的基本信息
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
                    # 命令结果（/compact 等命令的输出）直接透传
                    if isinstance(event, CommandResult):
                        yield _jsonl({"type": "command", "content": event.content})
                        continue

                    event_type = getattr(event, "type", "")
                    # 文本增量：逐 token 推送，前端拼接显示打字效果
                    if event_type == "text_delta":
                        yield _jsonl({"type": "delta", "text": getattr(event, "delta", "")})
                    # 文本完成：全文已生成完毕，用于最终渲染
                    elif event_type == "text_finish":
                        yield _jsonl({"type": "message", "text": getattr(event, "full_text", "") or getattr(event, "content", "")})
                    # 工具调用：告诉前端即将执行某个工具
                    elif event_type == "tool_use":
                        yield _jsonl({"type": "tool_call", "name": getattr(event, "name", "")})
                    else:
                        # 其他事件（ProcessResult 等）：包含 status 字段
                        status = getattr(event, "status", None)
                        if status:
                            yield _jsonl({
                                "type": "result",
                                "status": status,
                                "reason": getattr(event, "reason", ""),
                            })
            except Exception as exc:  # pragma: no cover - streamed to client
                # 异常通过事件流传递，不抛到外层（StreamingResponse 不能处理外层异常）
                log.exception("stream error: {exc}", exc=exc)
                yield _jsonl({"type": "error", "message": str(exc)})
            finally:
                # 发送 session 结束标记，前端收到后可以清理状态
                yield _jsonl({
                    "type": "complete",
                    "session_id": session.meta.session_id,
                })

        return StreamingResponse(event_stream(), media_type="application/jsonl; charset=utf-8")

    return app


app = create_app()
