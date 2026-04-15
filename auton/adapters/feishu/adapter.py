"""Feishu (飞书) Adapter — 将 Auton 接入飞书平台

使用飞书开放平台与飞书机器人对接：
  - 接收并处理私聊 / 群聊消息
  - 支持 @机器人 触发
  - 使用流式响应

启动方式：

    python -m auton.adapters.feishu.adapter

    # 或使用 FastAPI ASGI 服务器
    uvicorn auton.adapters.feishu.adapter:app --host 0.0.0.0 --port 8000

配置项（环境变量）：

    FEISHU_APP_ID=xxx                    # 飞书应用 App ID
    FEISHU_APP_SECRET=xxx                 # 飞书应用 App Secret
    FEISHU_BOT_NAME=Auton                 # 机器人名称（用于识别 @ 消息）
    AUTON_SESSION_MODE=project|chat        # Auton 会话模式
    AUTON_YES_ALL=true                    # 自动确认所有工具调用
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

if TYPE_CHECKING:
    from ...gateway.types import SessionContext

# ─── 配置 ────────────────────────────────────────────────────────────────────


@dataclass
class FeishuConfig:
    """飞书开放平台配置。"""

    app_id: str = field(default_factory=lambda: os.environ.get("FEISHU_APP_ID", ""))
    app_secret: str = field(default_factory=lambda: os.environ.get("FEISHU_APP_SECRET", ""))
    bot_name: str = field(default_factory=lambda: os.environ.get("FEISHU_BOT_NAME", "Auton"))
    api_base: str = "https://open.feishu.cn/open-apis"

    def validate(self) -> None:
        """验证配置完整性。"""
        if not self.app_id:
            raise ValueError("FEISHU_APP_ID is required")
        if not self.app_secret:
            raise ValueError("FEISHU_APP_SECRET is required")

    def api_url(self, path: str) -> str:
        return f"{self.api_base}/{path.lstrip('/')}"


# ─── Request/Response Models ─────────────────────────────────────────────────


class FeishuWebhookEvent(BaseModel):
    """飞书 Webhook 事件模型。"""
    schema: str = ""
    header: dict[str, Any] = {}
    event: dict[str, Any] = {}


# ─── Token Manager ───────────────────────────────────────────────────────────


class FeishuTokenManager:
    """飞书 Tenant Access Token 管理器（自动刷新）。"""

    def __init__(self, config: FeishuConfig) -> None:
        self._config = config
        self._token: str | None = None
        self._expires_at: float = 0

    async def get_token(self) -> str:
        """获取有效的 Tenant Access Token。"""
        if self._token and time.time() < self._expires_at - 60:
            return self._token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._config.api_url("/auth/v3/tenant_access_token/internal"),
                json={
                    "app_id": self._config.app_id,
                    "app_secret": self._config.app_secret,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0:
                raise RuntimeError(f"Failed to get Feishu token: {data}")

            self._token = data["tenant_access_token"]
            self._expires_at = time.time() + data.get("expire", 7200)

        return self._token


# ─── Feishu API Client ────────────────────────────────────────────────────────


class FeishuClient:
    """飞书开放平台 API 客户端。"""

    def __init__(self, config: FeishuConfig, token_manager: FeishuTokenManager) -> None:
        self._config = config
        self._token_manager = token_manager
        self._http = httpx.AsyncClient(timeout=30.0)

    async def _headers(self) -> dict[str, str]:
        token = await self._token_manager.get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def send_message(
        self,
        receive_id: str,
        msg_type: str,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        """发送消息。"""
        response = await self._http.post(
            self._config.api_url("/im/v1/messages"),
            headers=await self._headers(),
            params={"receive_id_type": "open_id"},
            json={
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": content,
            },
        )
        response.raise_for_status()
        return response.json()

    async def send_text(self, receive_id: str, text: str) -> dict[str, Any]:
        """发送文本消息。"""
        return await self.send_message(
            receive_id,
            "text",
            {"text": text},
        )

    async def reply_message(self, message_id: str, msg_type: str, content: dict[str, Any]) -> dict[str, Any]:
        """回复消息。"""
        response = await self._http.post(
            self._config.api_url(f"/im/v1/messages/{message_id}/reply"),
            headers=await self._headers(),
            json={
                "msg_type": msg_type,
                "content": content,
            },
        )
        response.raise_for_status()
        return response.json()

    async def reply_text(self, message_id: str, text: str) -> dict[str, Any]:
        """回复文本消息。"""
        return await self.reply_message(
            message_id,
            "text",
            {"text": text},
        )

    async def get_message(self, message_id: str) -> dict[str, Any]:
        """获取消息详情。"""
        response = await self._http.get(
            self._config.api_url(f"/im/v1/messages/{message_id}"),
            headers=await self._headers(),
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self._http.aclose()


# ─── Session Manager ─────────────────────────────────────────────────────────


class FeishuSessionManager:
    """管理飞书会话与 Auton SessionContext 的映射。

    每个飞书用户（通过 open_id 标识）对应一个独立的 Auton 会话。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def get_lock(self, open_id: str) -> asyncio.Lock:
        if open_id not in self._locks:
            self._locks[open_id] = asyncio.Lock()
        return self._locks[open_id]

    def set_context(self, open_id: str, ctx: "SessionContext") -> None:
        self._sessions[open_id] = ctx

    def get_context(self, open_id: str) -> "SessionContext | None":
        return self._sessions.get(open_id)

    def remove_context(self, open_id: str) -> None:
        self._sessions.pop(open_id, None)
        self._locks.pop(open_id, None)


# ─── Response Collector ─────────────────────────────────────────────────────


class FeishuResponseCollector:
    """收集 Auton 流式事件，组装为飞书可发送的消息。"""

    def __init__(self, max_length: int = 4000) -> None:
        self._max_length = max_length
        self._text_parts: list[str] = []
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
        self._buffer = ""


# ─── Feishu Adapter ──────────────────────────────────────────────────────────


class FeishuAdapter:
    """飞书平台适配器。

    提供 FastAPI 应用处理飞书 Webhook 事件。

    使用方式：

        import os
        from auton.adapters.feishu import FeishuAdapter, FeishuConfig

        config = FeishuConfig(
            app_id=os.environ["FEISHU_APP_ID"],
            app_secret=os.environ["FEISHU_APP_SECRET"],
        )
        adapter = FeishuAdapter(config)
        adapter.run()
    """

    def __init__(
        self,
        config: FeishuConfig | None = None,
        *,
        session_mode: str = "chat",
        yes_all: bool = True,
    ) -> None:
        self._config = config or FeishuConfig()
        self._session_mode = session_mode
        self._yes_all = yes_all

        self._token_manager = FeishuTokenManager(self._config)
        self._client: FeishuClient | None = None
        self._session_mgr = FeishuSessionManager()
        self._app = self._create_app()

    def _create_app(self) -> FastAPI:
        """创建 FastAPI 应用。"""
        app = FastAPI(title="Auton Feishu Adapter")

        @app.get("/webhook")
        async def verify_webhook(request: Request) -> Response:
            """Webhook 验证（飞书调用此端点进行验证）。"""
            challenge = request.query_params.get("challenge")
            if challenge:
                return JSONResponse({"challenge": challenge})

            verification = request.query_params.get("verification")
            if verification and verification == os.environ.get("FEISHU_VERIFICATION_TOKEN", ""):
                return JSONResponse({"challenge": challenge})
            raise HTTPException(status_code=403, detail="Verification failed")

        @app.post("/webhook")
        async def handle_webhook(request: Request) -> JSONResponse:
            """处理飞书消息事件。"""
            body = await request.json()
            await self._handle_webhook_event(body)
            return JSONResponse({"code": 0, "msg": "success"})

        @app.get("/health")
        async def health() -> dict[str, str]:
            return {"status": "ok"}

        return app

    def _get_client(self) -> FeishuClient:
        if self._client is None:
            self._client = FeishuClient(self._config, self._token_manager)
        return self._client

    async def _handle_webhook_event(self, body: dict[str, Any]) -> None:
        """处理 Webhook 事件。"""
        try:
            header = body.get("header", {})
            event_type = header.get("event_type", "")

            if event_type == "im.message.receive_v1":
                event = body.get("event", {})
                await self._process_message(event)
        except Exception as exc:
            import traceback
            traceback.print_exc()

    async def _process_message(self, event: dict[str, Any]) -> None:
        """处理单条飞书消息。"""
        from ...gateway import SessionFactory

        message = event.get("message", {})
        msg_id = message.get("message_id", "")
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {}).get("open_id", "")
        chat_type = event.get("chat_type", "p2p")
        msg_type = message.get("msg_type", "")
        content_str = message.get("content", "{}")

        # 解析消息内容
        import json
        try:
            content = json.loads(content_str)
        except (json.JSONDecodeError, TypeError):
            content = {}

        # 提取文本
        if msg_type == "text":
            text = content.get("text", "").strip()
        elif msg_type == "post":
            # 富文本消息，只取文本部分
            text = self._extract_text_from_post(content)
        else:
            text = ""

        # 忽略空消息或非文本消息
        if not text:
            return

        # 私聊直接处理，群聊需要 @机器人
        if chat_type == "group" and f"@{self._config.bot_name}" not in text:
            return

        # 清理 @ 机器人文本
        clean_text = self._clean_mention(text, self._config.bot_name)
        if not clean_text:
            return

        client = self._get_client()

        async with self._session_mgr.get_lock(sender_id):
            try:
                # 构建会话上下文
                ctx = await SessionFactory().build(
                    session_mode=self._session_mode,
                    yes_all=self._yes_all,
                    enable_mcp=False,
                )

                self._session_mgr.set_context(sender_id, ctx)
                ctx.session.add_user_message(clean_text)

                # 收集响应
                collector = FeishuResponseCollector()

                async for ev in ctx.processor.run_stream():
                    chunk = collector.handle_event(ev)
                    if chunk:
                        # 分段发送
                        for part in self._chunk_text(chunk):
                            await client.reply_text(msg_id, part)
                            await asyncio.sleep(0.3)  # 避免限流

            except Exception as exc:
                import traceback
                traceback.print_exc()
                await client.reply_text(msg_id, f"处理消息时出错: {exc}")

    def _extract_text_from_post(self, content: dict[str, Any]) -> str:
        """从富文本消息中提取文本。"""
        texts = []
        for section in content.get("content", []):
            if isinstance(section, dict):
                for item in section.get("content", []):
                    if item.get("tag") == "text":
                        texts.append(item.get("text", ""))
        return "".join(texts)

    def _clean_mention(self, text: str, bot_name: str) -> str:
        """清理 @机器人 文本。"""
        import re
        # 移除 <at user_id="xxx">名字</at> 格式
        text = re.sub(r"<at[^>]*>.*?</at>", "", text)
        # 移除 @名字 格式
        text = re.sub(rf"@{re.escape(bot_name)}", "", text)
        return text.strip()

    def _chunk_text(self, text: str, max_length: int = 4000) -> list[str]:
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
        self._config.validate()
        uvicorn.run(self._app, host=host, port=port, log_level="info")


def run_feishu_adapter(
    *,
    app_id: str | None = None,
    app_secret: str | None = None,
    bot_name: str = "Auton",
    session_mode: str = "chat",
    yes_all: bool = True,
    host: str = "0.0.0.0",
    port: int = 8000,
) -> None:
    """快捷启动函数。"""
    config = FeishuConfig(
        app_id=app_id or os.environ.get("FEISHU_APP_ID", ""),
        app_secret=app_secret or os.environ.get("FEISHU_APP_SECRET", ""),
        bot_name=bot_name,
    )
    config.validate()

    adapter = FeishuAdapter(
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
        config = FeishuConfig()
        adapter = FeishuAdapter(config)
        app = adapter.app
    return app


if __name__ == "__main__":
    run_feishu_adapter()
