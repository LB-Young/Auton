"""LLM 重试工具 — Jittered Exponential Backoff

防止并发重试风暴（thundering herd），在 429 / 5xx / 网络错误时
使用带抖动的指数退避策略自动重试 LLM API 调用。
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator, Callable
from functools import wraps
from typing import Any, TypeVar

from loguru import logger

from ..core.errors import LLMError

# 默认可重试的 HTTP 状态码
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

# 默认重试参数
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 5.0   # 秒
DEFAULT_MAX_DELAY = 120.0  # 秒
DEFAULT_JITTER_RATIO = 0.5


def jittered_backoff(
    attempt: int,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter_ratio: float = DEFAULT_JITTER_RATIO,
) -> float:
    """计算带抖动的指数退避等待时间。

    使用 decorrelated jitter 策略，有效防止并发重试的雷鸣羊群效应：
    多个进程同时重试时，随机抖动确保它们的重试时间分散开来。

    Args:
        attempt: 当前重试次数（从 1 开始）
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟上限（秒）
        jitter_ratio: 抖动比例（0~1），0.5 表示最多额外增加 50% 的抖动

    Returns:
        本次应等待的秒数
    """
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    # 使用时间戳 XOR 混合产生不依赖共享随机种子的抖动
    seed = (time.time_ns() ^ (attempt * 0x9E3779B9)) & 0xFFFFFFFF
    rng = random.Random(seed)
    jitter = rng.uniform(0, jitter_ratio * delay)
    return delay + jitter


def is_retryable_error(exc: BaseException) -> bool:
    """判断异常是否可重试。

    可重试条件：
    - LLMError 且 status_code 在 RETRYABLE_STATUS_CODES 中
    - 网络相关异常（ConnectionError、TimeoutError 等）
    """
    if isinstance(exc, LLMError):
        if exc.status_code is not None:
            return exc.status_code in RETRYABLE_STATUS_CODES
        # status_code 为 None 时视为网络错误，可重试
        return True

    retryable_types = (
        ConnectionError,
        TimeoutError,
        OSError,
    )
    return isinstance(exc, retryable_types)


async def retry_async(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    **kwargs: Any,
) -> Any:
    """通用异步重试包装器。

    对可重试错误执行带 jittered backoff 的自动重试。

    Args:
        func: 要重试的异步函数
        *args: 传递给 func 的位置参数
        max_retries: 最大重试次数（不含首次调用）
        base_delay: 基础退避延迟（秒）
        max_delay: 最大退避延迟上限（秒）
        **kwargs: 传递给 func 的关键字参数

    Raises:
        最后一次失败的异常（若所有重试均失败）
    """
    last_exc: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except BaseException as exc:
            if not is_retryable_error(exc) or attempt >= max_retries:
                raise
            last_exc = exc
            wait = jittered_backoff(attempt + 1, base_delay=base_delay, max_delay=max_delay)
            logger.warning(
                "LLM API 调用失败（尝试 {attempt}/{max_retries}），{wait:.1f}s 后重试: {exc}",
                attempt=attempt + 1,
                max_retries=max_retries,
                wait=wait,
                exc=exc,
            )
            await asyncio.sleep(wait)

    raise last_exc  # type: ignore[misc]


T = TypeVar("T")


async def retry_stream(
    stream_factory: Callable[[], AsyncIterator[T]],
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
) -> AsyncIterator[T]:
    """带重试的流式生成器包装器。

    流式调用的特殊性：一旦开始 yield，中途失败无法回溯，
    因此仅在流开始前（第一次 __anext__ 前）捕获并重试。

    Args:
        stream_factory: 返回 AsyncIterator 的无参函数（每次调用产生新流）
        max_retries: 最大重试次数
        base_delay: 基础退避延迟（秒）
        max_delay: 最大退避延迟上限（秒）

    Yields:
        流中的每个事件对象
    """
    for attempt in range(max_retries + 1):
        try:
            async for item in stream_factory():
                yield item
            return
        except BaseException as exc:
            if not is_retryable_error(exc) or attempt >= max_retries:
                raise
            wait = jittered_backoff(attempt + 1, base_delay=base_delay, max_delay=max_delay)
            logger.warning(
                "LLM 流式调用失败（尝试 {attempt}/{max_retries}），{wait:.1f}s 后重试: {exc}",
                attempt=attempt + 1,
                max_retries=max_retries,
                wait=wait,
                exc=exc,
            )
            await asyncio.sleep(wait)
