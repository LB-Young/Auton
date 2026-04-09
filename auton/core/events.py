"""Auton Core — 事件总线

全系统模块间通过事件总线通信，UI / 记录器 / 快照订阅事件流。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Coroutine, Awaitable
from dataclasses import dataclass, field
from typing import Any, Literal

from loguru import logger

from .event_types import BaseEvent, AutonEvent


# 事件订阅者签名：可以是普通函数、async 函数、或带 filter 的 callable
EventHandler = Callable[[BaseEvent], Awaitable[None] | None]
EventFilter = Callable[[BaseEvent], bool]


@dataclass
class Subscription:
    """单个订阅"""
    handler: EventHandler
    filter_fn: EventFilter | None = None
    event_types: set[str] | None = None  # None = 全部类型

    def matches(self, event: BaseEvent) -> bool:
        if self.event_types and event.type not in self.event_types:
            return False
        if self.filter_fn and not self.filter_fn(event):
            return False
        return True


class EventBus:
    """事件总线

    支持：
      - 同步/异步 handler
      - 事件类型过滤
      - 按 session_id 过滤
      - 流式消费（async generator）
    """

    def __init__(self) -> None:
        self._subscriptions: list[Subscription] = []
        self._lock = asyncio.Lock()
        self._logger = logger.bind(name="EventBus")

    # ─── 订阅管理 ────────────────────────────────────────────────────────────

    def subscribe(
        self,
        handler: EventHandler,
        *,
        event_types: str | list[str] | None = None,
        filter_fn: EventFilter | None = None,
    ) -> None:
        """订阅事件

        Args:
            handler: 事件处理函数（同步或 async）
            event_types: 要监听的事件类型（None = 全部）
            filter_fn: 额外的过滤函数

        Returns:
            取消订阅的函数
        """
        if isinstance(event_types, str):
            event_types = {event_types}
        elif event_types:
            event_types = set(event_types)

        sub = Subscription(
            handler=handler,
            filter_fn=filter_fn,
            event_types=event_types,
        )
        self._subscriptions.append(sub)
        self._logger.debug("订阅事件: types={types}", types=event_types)

    def unsubscribe(self, handler: EventHandler) -> None:
        """取消订阅"""
        self._subscriptions = [s for s in self._subscriptions if s.handler != handler]

    # ─── 事件发布 ──────────────────────────────────────────────────────────

    async def emit(self, event: AutonEvent) -> None:
        """发布一个事件，异步调用所有匹配的订阅者"""
        async with self._lock:
            # 先复制一份，避免 handler 中订阅/取消订阅导致问题
            subs = list(self._subscriptions)

        tasks: list[Awaitable[None]] = []
        for sub in subs:
            if sub.matches(event):
                try:
                    result = sub.handler(event)
                    if asyncio.iscoroutine(result):
                        tasks.append(result)
                except Exception as exc:
                    self._logger.warning("事件处理异常 handler={handler} event={event}: {exc}",
                                        handler=sub.handler, event=event.type, exc=exc)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def emit_sync(self, event: AutonEvent) -> None:
        """同步发布（用于非 async 上下文，危险）"""
        for sub in self._subscriptions:
            if sub.matches(event):
                try:
                    result = sub.handler(event)
                    if asyncio.iscoroutine(result):
                        raise RuntimeError("emit_sync 不能处理 async handler")
                except Exception as exc:
                    self._logger.warning("事件处理异常: {exc}", exc=exc)

    # ─── 流式消费 ──────────────────────────────────────────────────────────

    async def stream(self, session_id: str) -> AsyncIterator[AutonEvent]:
        """生成器：只消费指定 session_id 的事件流"""
        queue: asyncio.Queue[AutonEvent] = asyncio.Queue()
        running = True

        async def _handler(event: BaseEvent) -> None:
            if running:
                await queue.put(event)  # type: ignore[arg-type]

        self.subscribe(
            _handler,
            filter_fn=lambda e: e.session_id == session_id,
        )
        try:
            while running:
                event = await queue.get()
                yield event
                if isinstance(event, str) and event == "_STOP_":
                    running = False
        finally:
            self.unsubscribe(_handler)

    # ─── 工具 ──────────────────────────────────────────────────────────────

    def count_subscribers(self, event_type: str | None = None) -> int:
        """统计订阅者数量"""
        if event_type:
            return sum(1 for s in self._subscriptions if s.event_types is None or event_type in s.event_types)
        return len(self._subscriptions)


# ─── 全局单例 ──────────────────────────────────────────────────────────────

_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """获取全局事件总线单例"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
