"""WhatsApp Adapter — 将 Auton 接入 WhatsApp Business Cloud API

使用 WhatsApp Business Cloud API 与 Meta WhatsApp 对接：
  - Webhook 接收用户消息
  - REST API 发送回复

启动方式：

    python -m auton.adapters.whatsapp.adapter

    # 或使用 FastAPI ASGI 服务器
    uvicorn auton.adapters.whatsapp.adapter:app --host 0.0.0.0 --port 8000

配置项（环境变量）：

    WHATSAPP_PHONE_NUMBER_ID=xxx       # WhatsApp Business Phone Number ID
    WHATSAPP_WEBHOOK_SECRET=xxx        # Webhook 验证密钥
    WHATSAPP_ACCESS_TOKEN=xxx          # Meta App Access Token
    WHATSAPP_VERIFY_TOKEN=xxx          # Webhook 验证 Token（自定义）
    AUTON_SESSION_MODE=project|chat    # Auton 会话模式
    AUTON_YES_ALL=true                 # 自动确认所有工具调用
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from ...gateway.types import SessionContext

# ─── 配置 ────────────────────────────────────────────────────────────────────


@dataclass
class WhatsAppConfig:
    """WhatsApp Business API 配置。"""

    phone_number_id: str = field(default_factory=lambda: os.environ.get("WHATSAPP_PHONE_NUMBER_ID", ""))
    webhook_secret: str = field(default_factory=lambda: os.environ.get("WHATSAPP_WEBHOOK_SECRET", ""))
    access_token: str = field(default_factory=lambda: os.environ.get("WHATSAPP_ACCESS_TOKEN", ""))
    verify_token: str = field(default_factory=lambda: os.environ.get("WHATSAPP_VERIFY_TOKEN", ""))
    api_version: str = "v18.0"
    base_url: str = "https://graph.facebook.com"

    def validate(self) -> None:
        """验证配置完整性。"""
        if not self.phone_number_id:
            raise ValueError("WHATSAPP_PHONE_NUMBER_ID is required")
        if not self.access_token:
            raise ValueError("WHATSAPP_ACCESS_TOKEN is required")

    @property
    def api_url(self) -> str:
        return f"{self.base_url}/{self.api_version}/{self.phone_number_id}/messages"


# ─── Session Manager ─────────────────────────────────────────────────────────


class WhatsAppSessionManager:
    """管理 WhatsApp 用户会话与 Auton SessionContext 的映射。

    每个 WhatsApp 用户（通过 WA ID 标识）对应一个独立的 Auton 会话。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def get_lock(self, wa_id: str) -> asyncio.Lock:
        if wa_id not in self._locks:
            self._locks[wa_id] = asyncio.Lock()
        return self._locks[wa_id]

    def set_context(self, wa_id: str, ctx: "SessionContext") -> None:
        self._sessions[wa_id] = ctx

    def get_context(self, wa_id: str) -> "SessionContext | None":
        return self._sessions.get(wa_id)

    def remove_context(self, wa_id: str) -> None:
        self._sessions.pop(wa_id, None)
        self._locks.pop(wa_id, None)


# ─── WhatsApp API Client ─────────────────────────────────────────────────────


class WhatsAppClient:
    """WhatsApp Business Cloud API 客户端。"""

    def __init__(self, config: WhatsAppConfig) -> None:
        self._config = config
        self._http = httpx.AsyncClient(timeout=30.0)

    async def send_text_message(self, to: str, text: str) -> dict[str, Any]:
        """发送文本消息。"""
        headers = {
            "Authorization": f"Bearer {self._config.access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }

        response = await self._http.post(
            self._config.api_url,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def send_reaction(self, to: str, message_id: str, emoji: str = "✅") -> dict[str, Any]:
        """发送消息反应（已读回执）。"""
        headers = {
            "Authorization": f"Bearer {self._config.access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "reaction",
            "reaction": {
                "message_id": message_id,
                "emoji": emoji,
            },
        }

        response = await self._http.post(
            self._config.api_url,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def mark_as_read(self, to: str, message_id: str) -> dict[str, Any]:
        """标记消息为已读。"""
        headers = {
            "Authorization": f"Bearer {self._config.access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "mark_seen",
        }

        response = await self._http.post(
            self._config.api_url,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def send_typing_on(self, to: str) -> None:
        """发送打字中状态。"""
        await self._mark_typing(to, True)

    async def send_typing_off(self, to: str) -> None:
        """停止打字状态。"""
        await self._mark_typing(to, False)

    async def _mark_typing(self, to: str, typing: bool) -> None:
        headers = {
            "Authorization": f"Bearer {self._config.access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "typing",
            "typing": typing,
        }

        try:
            await self._http.post(
                self._config.api_url,
                headers=headers,
                json=payload,
            )
        except Exception:
            pass

    async def close(self) -> None:
        await self._http.aclose()


# ─── Response Collector ───────────────────────────────────────────────────────


class WhatsAppResponseCollector:
    """收集 Auton 流式事件，组装为 WhatsApp 可发送的消息。"""

    def __init__(self, max_length: int = 4096) -> None:
        self._max_length = max_length
        self._text_parts: list[str] = []
        self._tool_calls: list[str] = []
        self._buffer = ""

    def handle_event(self, event: Any) -> str | None:
        """处理事件，返回要发送的消息（如果有）。"""
        event_type = getattr(event, "type", "")

        if event_type == "text_delta":
            self._buffer += getattr(event, "delta", "")
            self._text_parts.append(getattr(event, "delta", ""))

            if len(self._buffer) >= self._max_length:
                result = self._buffer
                self._buffer = ""
                return result
            return None

        elif event_type == "tool_use":
            tool_name = getattr(event, "name", "?")
            self._tool_calls.append(tool_name)
            return f"🔧 正在调用 `{tool_name}`...\n"

        elif event_type == "text_finish":
            self._buffer += getattr(event, "full_text", "") or getattr(event, "content", "")
            self._text_parts.append(self._buffer)
            return "".join(self._text_parts)

        elif event_type == "error":
            return f"❌ 错误: {getattr(event, 'error', 'Unknown error')}"

        return None

    def get_full_text(self) -> str:
        return "".join(self._text_parts)

    def reset(self) -> None:
        self._text_parts.clear()
        self._tool_calls.clear()
        self._buffer = ""


# ─── WhatsApp Adapter ─────────────────────────────────────────────────────────


class WhatsAppAdapter:
    """WhatsApp Business Cloud API 适配器。

    提供 FastAPI 应用处理 WhatsApp Webhook 事件。

    使用方式：

        import os
        from auton.adapters.whatsapp import WhatsAppAdapter, WhatsAppConfig

        config = WhatsAppConfig(
            phone_number_id=os.environ["WHATSAPP_PHONE_NUMBER_ID"],
            access_token=os.environ["WHATSAPP_ACCESS_TOKEN"],
            webhook_secret=os.environ["WHATSAPP_WEBHOOK_SECRET"],
            verify_token=os.environ["WHATSAPP_VERIFY_TOKEN"],
        )
        adapter = WhatsAppAdapter(config)
        adapter.run()
    """

    def __init__(
        self,
        config: WhatsAppConfig | None = None,
        *,
        session_mode: str = "chat",
        yes_all: bool = True,
    ) -> None:
        self._config = config or WhatsAppConfig()
        self._session_mode = session_mode
        self._yes_all = yes_all

        self._session_mgr = WhatsAppSessionManager()
        self._client: WhatsAppClient | None = None
        self._app = self._create_app()

    def _create_app(self) -> FastAPI:
        """创建 FastAPI 应用。"""
        app = FastAPI(title="Auton WhatsApp Adapter")

        @app.get("/webhook")
        async def verify_webhook(request: Request) -> Response:
            """Webhook 验证（Meta 调用此端点进行验证）。"""
            mode = request.query_params.get("hub.mode")
            token = request.query_params.get("hub.verify_token")
            challenge = request.query_params.get("hub.challenge")

            if mode == "subscribe" and token == self._config.verify_token:
                return Response(content=challenge, media_type="text/plain")
            raise HTTPException(status_code=403, detail="Verification failed")

        @app.post("/webhook")
        async def handle_webhook(request: Request) -> JSONResponse:
            """处理 WhatsApp 消息事件。"""
            body = await request.json()
            await self._handle_webhook_event(body)
            return JSONResponse({"status": "ok"})

        @app.get("/health")
        async def health() -> dict[str, str]:
            return {"status": "ok"}

        return app

    def _get_client(self) -> WhatsAppClient:
        if self._client is None:
            self._client = WhatsAppClient(self._config)
        return self._client

    async def _handle_webhook_event(self, body: dict[str, Any]) -> None:
        """处理 Webhook 事件。"""
        try:
            entry = body.get("entry", [])
            for e in entry:
                changes = e.get("changes", [])
                for change in changes:
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    for msg in messages:
                        await self._process_message(msg, value)
        except Exception as exc:
            import traceback
            traceback.print_exc()

    async def _process_message(self, msg: dict[str, Any], value: dict[str, Any]) -> None:
        """处理单条 WhatsApp 消息。"""
        from ...gateway import SessionFactory

        msg_id = msg.get("id", "")
        from_ = msg.get("from", "")
        msg_type = msg.get("type", "")
        text = msg.get("text", {}).get("body", "") if msg_type == "text" else ""

        # 忽略空消息
        if not text and msg_type == "text":
            return

        # 对于非文本消息，暂时只回复提示
        if msg_type != "text":
            client = self._get_client()
            await client.send_text_message(
                from_,
                "目前只支持文本消息，请发送文字问题。",
            )
            return

        client = self._get_client()

        # 标记已读
        try:
            await client.mark_as_read(from_, msg_id)
        except Exception:
            pass

        # 发送打字状态
        await client.send_typing_on(from_)

        async with self._session_mgr.get_lock(from_):
            try:
                # 构建会话上下文
                ctx = await SessionFactory().build(
                    session_mode=self._session_mode,
                    yes_all=self._yes_all,
                    enable_mcp=False,
                )

                self._session_mgr.set_context(from_, ctx)
                ctx.session.add_user_message(text)

                # 收集响应
                collector = WhatsAppResponseCollector()
                full_response = ""

                async for event in ctx.processor.run_stream():
                    chunk = collector.handle_event(event)
                    if chunk:
                        # 分段发送
                        for part in self._chunk_text(chunk):
                            await client.send_text_message(from_, part)
                            full_response += part
                            await asyncio.sleep(0.5)  # 避免限流

                # 发送最终响应（如果有未发送的部分）
                final_text = collector.get_full_text()
                if final_response and len(final_response) > len(full_response):
                    remaining = final_response[len(full_response):]
                    for part in self._chunk_text(remaining):
                        await client.send_text_message(from_, part)
                        await asyncio.sleep(0.5)

            except Exception as exc:
                import traceback
                traceback.print_exc()
                await client.send_text_message(from_, f"处理消息时出错: {exc}")
            finally:
                await client.send_typing_off(from_)

    def _chunk_text(self, text: str, max_length: int = 4096) -> list[str]:
        """分块长文本。"""
        if len(text) <= max_length:
            return [text]

        chunks = []
        for i in range(0, len(text), max_length):
            chunks.append(text[i:i + max_length])
        return chunks

    @property
    def app(self) -> FastAPI:
        """获取 FastAPI 应用。"""
        return self._app

    def run(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
    ) -> None:
        """启动 FastAPI 服务器。"""
        import uvicorn
        uvicorn.run(self._app, host=host, port=port, log_level="info")


def run_whatsapp_adapter(
    *,
    phone_number_id: str | None = None,
    access_token: str | None = None,
    webhook_secret: str | None = None,
    verify_token: str | None = None,
    session_mode: str = "chat",
    yes_all: bool = True,
    host: str = "0.0.0.0",
    port: int = 8000,
) -> None:
    """快捷启动函数。"""
    config = WhatsAppConfig(
        phone_number_id=phone_number_id or os.environ.get("WHATSAPP_PHONE_NUMBER_ID", ""),
        access_token=access_token or os.environ.get("WHATSAPP_ACCESS_TOKEN", ""),
        webhook_secret=webhook_secret or os.environ.get("WHATSAPP_WEBHOOK_SECRET", ""),
        verify_token=verify_token or os.environ.get("WHATSAPP_VERIFY_TOKEN", ""),
    )
    config.validate()

    adapter = WhatsAppAdapter(
        config=config,
        session_mode=session_mode,
        yes_all=yes_all,
    )
    adapter.run(host=host, port=port)


# ASGI 应用入口
app: FastAPI | None = None


def get_app() -> FastAPI:
    """获取 ASGI 应用实例（用于 gunicorn 等）。"""
    global app
    if app is None:
        config = WhatsAppConfig()
        adapter = WhatsAppAdapter(config)
        app = adapter.app
    return app


if __name__ == "__main__":
    run_whatsapp_adapter()
