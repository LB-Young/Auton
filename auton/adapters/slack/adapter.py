"""Slack Adapter — 将 Auton 接入 Slack 平台

支持两种模式：
  - Socket Mode（推荐）：无需公网 Webhook，使用 WebSocket 长连接
  - HTTP Mode：需要公网 Webhook URL，参考 Slack Events API

启动方式：

    # Socket Mode（推荐）
    slack-bot run auton.adapters.slack.adapter --socket-mode

    # 或直接运行
    python -m auton.adapters.slack.adapter

配置项（环境变量）：

    SLACK_BOT_TOKEN=xapp-xxx        # Bot Token (xoxb-xxx)
    SLACK_APP_TOKEN=xapp-xxx        # App-Level Token (用于 Socket Mode)
    AUTON_SESSION_MODE=project|chat  # Auton 会话模式
    AUTON_YES_ALL=true               # 自动确认所有工具调用
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import TYPE_CHECKING, Any

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_bolt.oauth import OAuthFlow

if TYPE_CHECKING:
    from ...gateway.types import SessionContext

# ─── 事件映射器 ──────────────────────────────────────────────────────────────


def _map_event_to_slack(event: Any) -> dict[str, Any] | None:
    """将 Auton 事件映射为 Slack 消息格式。"""
    event_type = getattr(event, "type", "")

    if event_type == "text_delta":
        return {"type": "delta", "text": getattr(event, "delta", "")}
    elif event_type == "text_finish":
        return {
            "type": "message",
            "text": getattr(event, "full_text", "") or getattr(event, "content", ""),
        }
    elif event_type == "tool_use":
        return {"type": "tool_call", "name": getattr(event, "name", "")}
    elif event_type == "tool_result":
        return {"type": "result", "output": getattr(event, "output", "")}
    elif event_type == "tool_error":
        return {"type": "error", "error": getattr(event, "error", "")}
    elif hasattr(event, "status"):
        return {"type": "status", "status": getattr(event, "status", "")}

    return None


# ─── Session Context Manager ──────────────────────────────────────────────────


class SlackSessionManager:
    """管理 Slack 会话与 Auton SessionContext 的映射。

    每个 Slack 频道/线程对应一个 Auton 会话。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}  # channel_id -> context
        self._locks: dict[str, asyncio.Lock] = {}

    def get_lock(self, channel_id: str) -> asyncio.Lock:
        if channel_id not in self._locks:
            self._locks[channel_id] = asyncio.Lock()
        return self._locks[channel_id]

    def set_context(self, channel_id: str, ctx: "SessionContext") -> None:
        self._sessions[channel_id] = ctx

    def get_context(self, channel_id: str) -> "SessionContext | None":
        return self._sessions.get(channel_id)

    def remove_context(self, channel_id: str) -> None:
        self._sessions.pop(channel_id, None)
        self._locks.pop(channel_id, None)


# ─── Slack Adapter ────────────────────────────────────────────────────────────


class SlackAdapter:
    """Slack 平台适配器。

    使用 Slack Bolt 框架处理 Slack 事件，并通过 Socket Mode 或 HTTP Webhook
    与 Auton 会话引擎对接。

    使用方式：

        adapter = SlackAdapter()
        adapter.start()  # Socket Mode
        # 或
        adapter.start_http()  # HTTP Mode
    """

    def __init__(
        self,
        *,
        bot_token: str | None = None,
        app_token: str | None = None,
        session_mode: str = "chat",
        yes_all: bool = True,
        event_loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self._bot_token = bot_token or os.environ.get("SLACK_BOT_TOKEN", "")
        self._app_token = app_token or os.environ.get("SLACK_APP_TOKEN", "")
        self._session_mode = session_mode or os.environ.get("AUTON_SESSION_MODE", "chat")
        self._yes_all = yes_all or os.environ.get("AUTON_YES_ALL", "true").lower() == "true"
        self._loop = event_loop

        self._app: App | None = None
        self._handler: SocketModeHandler | None = None
        self._session_mgr = SlackSessionManager()

        # 用于在 Bolt 的同步上下文中调用 async 代码
        self._sync_to_async: asyncio.AbstractEventLoop | None = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None:
            return self._loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop

    def _ensure_app(self) -> App:
        if self._app is None:
            if not self._bot_token:
                raise ValueError(
                    "SLACK_BOT_TOKEN is required. "
                    "Set it via parameter or environment variable."
                )

            self._app = App(token=self._bot_token)
            self._setup_handlers()
        return self._app

    def _setup_handlers(self) -> None:
        """注册 Slack 事件处理器。"""
        app = self._app
        assert app is not None

        # ── 消息事件 ────────────────────────────────────────────────────────────
        @app.message()
        def handle_message(
            message: dict[str, Any],
            say: Any,
            context: dict[str, Any],
        ) -> None:
            """处理频道消息。"""
            # 忽略机器人自己的消息
            if context.get("bot_id"):
                return

            text = message.get("text", "") if isinstance(message, dict) else str(message)
            channel = context.get("channel_id", "")
            thread_ts = context.get("thread_ts")

            self._loop.call_soon_threadsafe(
                lambda: self._handle_message_async(text, say, channel, thread_ts)
            )

        # ── App Mention ─────────────────────────────────────────────────────────
        @app.event("app_mention")
        def handle_app_mention(
            event: dict[str, Any],
            say: Any,
            context: dict[str, Any],
        ) -> None:
            text = event.get("text", "")
            channel = context.get("channel_id", "")
            thread_ts = event.get("ts")

            self._loop.call_soon_threadsafe(
                lambda: self._handle_message_async(text, say, channel, thread_ts)
            )

        # ── 斜线命令 ────────────────────────────────────────────────────────────
        @app.command("/auton")
        def handle_auton_command(
            ack: Any,
            respond: Any,
            command: dict[str, Any],
        ) -> None:
            ack()  # 立即响应，延迟回复
            text = command.get("text", "")
            channel = command.get("channel_id", "")

            self._loop.call_soon_threadsafe(
                lambda: self._handle_message_async(text, respond, channel, None)
            )

    def _handle_message_async(
        self,
        text: str,
        say_or_respond: Any,
        channel: str,
        thread_ts: str | None,
    ) -> None:
        """异步处理消息（在事件循环中执行）。"""
        loop = self._get_loop()
        try:
            asyncio.ensure_future(
                self._process_message(text, say_or_respond, channel, thread_ts),
                loop=loop,
            )
        except RuntimeError:
            # 如果没有正在运行的事件循环，直接创建新循环
            asyncio.run(self._process_message(text, say_or_respond, channel, thread_ts))

    async def _process_message(
        self,
        text: str,
        say_or_respond: Any,
        channel: str,
        thread_ts: str | None,
    ) -> None:
        """处理消息并生成流式响应。"""
        from ...gateway import SessionFactory

        # 清理 @mention 文本
        import re
        clean_text = re.sub(r"<@[U0-9A-Z]+>", "", text).strip()
        if not clean_text:
            await self._send_ephemeral(say_or_respond, channel, thread_ts, "请输入问题或任务。")
            return

        # 构建会话上下文
        ctx = await SessionFactory().build(
            session_mode=self._session_mode,
            yes_all=self._yes_all,
            enable_mcp=False,
        )

        session_key = channel + (f":{thread_ts}" if thread_ts else "")
        self._session_mgr.set_context(session_key, ctx)
        ctx.session.add_user_message(clean_text)

        # 收集完整响应（流式发送到 Slack）
        full_text_parts: list[str] = []
        tool_calls: list[str] = []
        buffer = ""

        try:
            async for event in ctx.processor.run_stream():
                mapped = _map_event_to_slack(event)
                if not mapped:
                    continue

                evt_type = mapped["type"]

                if evt_type == "delta":
                    buffer += mapped["text"]
                    full_text_parts.append(mapped["text"])

                    # 每 100 字符或遇到换行时发送更新
                    if len(buffer) >= 100 or "\n" in buffer:
                        await self._update_message(say_or_respond, channel, thread_ts, buffer)
                        buffer = ""

                elif evt_type == "tool_call":
                    tool_calls.append(mapped["name"])
                    buffer += f"\n[正在调用: {mapped['name']}]...\n"
                    await self._update_message(say_or_respond, channel, thread_ts, buffer)
                    buffer = ""

                elif evt_type == "message":
                    # 最终消息
                    if buffer:
                        full_text_parts.append(buffer)
                    full_text = "".join(full_text_parts)
                    await self._send_final(say_or_respond, channel, thread_ts, full_text)

                elif evt_type == "error":
                    buffer += f"\n❌ 错误: {mapped['error']}\n"

        except Exception as exc:
            import traceback
            traceback.print_exc()
            await self._send_ephemeral(
                say_or_respond,
                channel,
                thread_ts,
                f"处理消息时出错: {exc}",
            )

    async def _send_ephemeral(
        self,
        say_or_respond: Any,
        channel: str,
        thread_ts: str | None,
        text: str,
    ) -> None:
        """发送临时消息（仅用户可见）。"""
        try:
            if hasattr(say_or_respond, "__call__"):
                await asyncio.to_thread(say_or_respond, text)
            elif hasattr(say_or_respond, "send_ephemeral"):
                await asyncio.to_thread(
                    say_or_respond.send_ephemeral,
                    text,
                    channel=channel,
                    thread_ts=thread_ts,
                )
        except Exception:
            pass

    async def _update_message(
        self,
        say_or_respond: Any,
        channel: str,
        thread_ts: str | None,
        text: str,
    ) -> None:
        """更新消息（流式打字效果）。"""
        try:
            # Slack 流式使用 thread reply
            if thread_ts and hasattr(say_or_respond, "say"):
                await asyncio.to_thread(
                    say_or_respond.say,
                    text=f"```\n{text}\n```",
                    thread_ts=thread_ts,
                )
        except Exception:
            pass

    async def _send_final(
        self,
        say_or_respond: Any,
        channel: str,
        thread_ts: str | None,
        text: str,
    ) -> None:
        """发送最终响应。"""
        try:
            if thread_ts and hasattr(say_or_respond, "say"):
                await asyncio.to_thread(
                    say_or_respond.say,
                    text=text,
                    thread_ts=thread_ts,
                )
            elif hasattr(say_or_respond, "__call__"):
                await asyncio.to_thread(say_or_respond, text)
        except Exception:
            pass

    def start(self) -> None:
        """启动 Socket Mode（推荐，无需公网 Webhook）。"""
        if not self._app_token:
            raise ValueError(
                "SLACK_APP_TOKEN is required for Socket Mode. "
                "Set it via parameter or SLACK_APP_TOKEN env var."
            )

        app = self._ensure_app()
        self._handler = SocketModeHandler(app, self._app_token)
        print("Starting Slack Socket Mode...")
        self._handler.start()

    def start_http(
        self,
        host: str = "0.0.0.0",
        port: int = 3000,
    ) -> None:
        """启动 HTTP Mode（需要公网 Webhook URL）。"""
        import uvicorn

        app = self._ensure_app()
        print(f"Starting Slack HTTP Mode on {host}:{port}...")
        uvicorn.run(app, host=host, port=port, log_level="info")


def run_slack_adapter(
    *,
    session_mode: str = "chat",
    yes_all: bool = True,
) -> None:
    """快捷启动函数。"""
    adapter = SlackAdapter(session_mode=session_mode, yes_all=yes_all)
    adapter.start()


if __name__ == "__main__":
    run_slack_adapter()
