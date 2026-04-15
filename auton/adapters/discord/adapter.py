"""Discord Adapter — 将 Auton 接入 Discord 平台

使用 discord.py 与 Discord Bot API 对接，支持：
  - 频道消息处理
  - 斜线命令（Slash Commands）
  - 线程（Threads）支持
  - 流式响应（使用 Discord 打字状态）

启动方式：

    python -m auton.adapters.discord.adapter

    # 或使用 discord.py 的内置方式
    python -m auton.adapters.discord.adapter --token YOUR_BOT_TOKEN

配置项（环境变量）：

    DISCORD_BOT_TOKEN=xxx              # Bot Token
    AUTON_SESSION_MODE=project|chat     # Auton 会话模式
    AUTON_YES_ALL=true                  # 自动确认所有工具调用
    DISCORD_PREFIX=!                    # 传统命令前缀（可选）
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from typing import Any, TYPE_CHECKING

import discord
from discord import app_commands

if TYPE_CHECKING:
    from ...gateway.types import SessionContext

# ─── 常量 ────────────────────────────────────────────────────────────────────

MAX_MESSAGE_LENGTH = 2000  # Discord 消息长度限制
STREAM_CHUNK_SIZE = 1500   # 流式发送时的分块大小


# ─── Session Context Manager ──────────────────────────────────────────────────


class DiscordSessionManager:
    """管理 Discord 频道/线程与 Auton SessionContext 的映射。"""

    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def get_lock(self, channel_id: str) -> asyncio.Lock:
        if channel_id not in self._locks:
            self._locks[channel_id] = asyncio.Lock()
        return self._locks[channel_id]

    def set_context(self, key: str, ctx: "SessionContext") -> None:
        self._sessions[key] = ctx

    def get_context(self, key: str) -> "SessionContext | None":
        return self._sessions.get(key)

    def remove_context(self, key: str) -> None:
        self._sessions.pop(key, None)
        self._locks.pop(key, None)


# ─── Response Collector ──────────────────────────────────────────────────────


class ResponseCollector:
    """收集 Auton 流式事件，组装为 Discord 可发送的消息。"""

    def __init__(self) -> None:
        self._text_parts: list[str] = []
        self._tool_calls: list[str] = []
        self._buffer = ""
        self._thinking_parts: list[str] = []

    def handle_event(self, event: Any) -> str | None:
        """处理事件，返回要发送的消息（如果有）。"""
        event_type = getattr(event, "type", "")

        if event_type == "reasoning_delta":
            self._thinking_parts.append(getattr(event, "delta", ""))
            return None

        elif event_type == "reasoning_finish":
            self._thinking_parts.clear()
            return None

        elif event_type == "text_delta":
            self._buffer += getattr(event, "delta", "")
            self._text_parts.append(getattr(event, "delta", ""))

            # 缓冲区足够大时返回
            if len(self._buffer) >= STREAM_CHUNK_SIZE:
                result = self._buffer
                self._buffer = ""
                return result
            return None

        elif event_type == "tool_use":
            tool_name = getattr(event, "name", "?")
            self._tool_calls.append(tool_name)
            prefix = f"🔧 调用 `{tool_name}`...\n"
            return prefix

        elif event_type == "text_finish":
            self._buffer += getattr(event, "full_text", "") or getattr(event, "content", "")
            self._text_parts.append(self._buffer)
            result = "".join(self._text_parts)
            return result

        elif event_type == "error":
            return f"❌ 错误: {getattr(event, 'error', 'Unknown error')}"

        return None

    def get_full_text(self) -> str:
        return "".join(self._text_parts)

    def reset(self) -> None:
        self._text_parts.clear()
        self._tool_calls.clear()
        self._buffer = ""
        self._thinking_parts.clear()


# ─── Discord Adapter ──────────────────────────────────────────────────────────


class DiscordAdapter(discord.Client):
    """Discord 平台适配器。

    使用 discord.py 处理 Discord 事件，包括：
      - 频道消息
      - 斜线命令
      - 线程管理

    使用方式：

        import os
        from auton.adapters.discord import DiscordAdapter

        adapter = DiscordAdapter(
            session_mode="chat",
            yes_all=True,
        )
        adapter.run(os.environ["DISCORD_BOT_TOKEN"])
    """

    def __init__(
        self,
        *,
        session_mode: str = "chat",
        yes_all: bool = True,
        prefix: str = "!auton",
        **kwargs: Any,
    ) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # 必须开启消息内容意图

        super().__init__(intents=intents, **kwargs)

        self._session_mode = session_mode or os.environ.get("AUTON_SESSION_MODE", "chat")
        self._yes_all = yes_all or os.environ.get("AUTON_YES_ALL", "true").lower() == "true"
        self._prefix = prefix

        self._tree = app_commands.CommandTree(self)
        self._session_mgr = DiscordSessionManager()

        self._setup_commands()

    def _setup_commands(self) -> None:
        """设置斜线命令。"""

        @self._tree.command(
            name="auton",
            description="与 Auton AI 助手对话",
        )
        @app_commands.describe(prompt="你想让 Auton 做什么？")
        async def auton_command(interaction: discord.Interaction, prompt: str) -> None:
            await interaction.response.defer(thinking=True)
            await self._process_message(
                content=prompt,
                channel=interaction.channel,
                interaction=interaction,
                user=interaction.user,
            )

    async def setup_hook(self) -> None:
        """在启动时同步斜线命令。"""
        await self._tree.sync()

    async def on_message(self, message: discord.Message) -> None:
        """处理频道消息。"""
        # 忽略机器人自己的消息
        if message.author.bot:
            return

        # 检查前缀
        content = message.content.strip()
        if not content.startswith(self._prefix):
            return

        # 提取命令内容
        cmd_content = content[len(self._prefix):].strip()
        if not cmd_content:
            await message.channel.send("请输入问题，例如：`!auton 帮我写一个 Hello World`")
            return

        await self._process_message(
            content=cmd_content,
            channel=message.channel,
            original_message=message,
            user=message.author,
        )

    async def _process_message(
        self,
        content: str,
        channel: discord.abc.Messageable,
        user: discord.abc.User,
        original_message: discord.Message | None = None,
        interaction: discord.Interaction | None = None,
    ) -> None:
        """处理消息并生成流式响应。"""
        from ...gateway import SessionFactory

        # 清理消息
        clean_content = self._clean_content(content)
        if not clean_content:
            msg = "请输入问题或任务。"
            if interaction:
                await interaction.followup.send(msg)
            else:
                await channel.send(msg)
            return

        # 区分频道和线程
        key = f"{channel.id}"
        if isinstance(channel, discord.Thread):
            key = f"thread:{channel.id}"

        async with self._session_mgr.get_lock(key):
            try:
                # 构建会话上下文
                ctx = await SessionFactory().build(
                    session_mode=self._session_mode,
                    yes_all=self._yes_all,
                    enable_mcp=False,
                )

                self._session_mgr.set_context(key, ctx)
                ctx.session.add_user_message(clean_content)

                # 收集响应
                collector = ResponseCollector()
                response_msg: discord.Message | None = None
                buffer = ""

                async for event in ctx.processor.run_stream():
                    chunk = collector.handle_event(event)

                    if chunk is None:
                        continue

                    # 发送或更新消息
                    if not response_msg:
                        # 首次发送
                        try:
                            response_msg = await channel.send(f"🤖 {buffer}{chunk[:MAX_MESSAGE_LENGTH-5]}")
                            buffer = chunk[MAX_MESSAGE_LENGTH-5:]
                        except discord.HTTPException:
                            buffer = chunk
                    else:
                        buffer += chunk
                        if len(buffer) >= STREAM_CHUNK_SIZE:
                            try:
                                # 编辑现有消息追加
                                new_content = response_msg.content + buffer[:MAX_MESSAGE_LENGTH-5]
                                if len(new_content) <= MAX_MESSAGE_LENGTH:
                                    await response_msg.edit(content=new_content)
                                else:
                                    response_msg = await channel.send(buffer[:MAX_MESSAGE_LENGTH-5])
                                buffer = buffer[MAX_MESSAGE_LENGTH-5:]
                            except discord.HTTPException:
                                buffer = ""

                # 发送最终消息
                final_text = collector.get_full_text() + buffer
                if final_text:
                    await self._send_long_message(channel, final_text, response_msg)
                elif buffer:
                    await self._send_long_message(channel, buffer, response_msg)

            except Exception as exc:
                import traceback
                traceback.print_exc()
                error_msg = f"处理消息时出错: {exc}"
                if interaction:
                    await interaction.followup.send(error_msg)
                else:
                    await channel.send(error_msg)

    async def _send_long_message(
        self,
        channel: discord.abc.Messageable,
        text: str,
        existing: discord.Message | None = None,
    ) -> None:
        """分片发送长消息。"""
        if not text:
            return

        if len(text) <= MAX_MESSAGE_LENGTH:
            if existing:
                await existing.edit(content=text)
            else:
                await channel.send(text)
            return

        # 分片发送
        for i in range(0, len(text), MAX_MESSAGE_LENGTH):
            chunk = text[i:i + MAX_MESSAGE_LENGTH]
            if i == 0 and existing:
                await existing.edit(content=chunk)
            else:
                await channel.send(chunk)

    def _clean_content(self, content: str) -> str:
        """清理消息内容，移除 @mention 和频道引用等。"""
        # 移除 <@!USER_ID> 格式的 mention
        content = re.sub(r"<@!?\d+>", "", content)
        # 移除 <#CHANNEL_ID> 格式的频道引用
        content = re.sub(r"<#\d+>", "", content)
        # 移除 <:emoji:ID> 格式的表情
        content = re.sub(r"<a?:[a-zA-Z0-9_]+:\d+>", "", content)
        # 移除 HTML 标签
        content = re.sub(r"<[^>]+>", "", content)
        return content.strip()


def run_discord_adapter(
    *,
    token: str | None = None,
    session_mode: str = "chat",
    yes_all: bool = True,
    prefix: str = "!auton",
) -> None:
    """快捷启动函数。"""
    token = token or os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise ValueError(
            "DISCORD_BOT_TOKEN is required. "
            "Pass token parameter or set DISCORD_BOT_TOKEN env var."
        )

    adapter = DiscordAdapter(
        session_mode=session_mode,
        yes_all=yes_all,
        prefix=prefix,
    )
    adapter.run(token)


if __name__ == "__main__":
    import sys

    token = None
    for i, arg in enumerate(sys.argv):
        if arg == "--token" and i + 1 < len(sys.argv):
            token = sys.argv[i + 1]
            break

    run_discord_adapter(token=token)
