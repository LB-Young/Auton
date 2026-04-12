"""Memory Watcher — 后台定期扫描，自动生成摘要与长期记忆

设计原则：
  - 职责分离：agent 只管对话，watcher 只管记忆写入，彼此不耦合
  - 触发条件（OR 关系）：
      1. 某 session 有 ≥50k 原始对话字符尚未被摘要
      2. 某 session 最后一次写入距今 > INACTIVITY_SECONDS（视为 "session 已结束"）
         且存在任何未被摘要的内容
  - 每 SCAN_INTERVAL_SECONDS 秒扫描一次所有 session JSONL 文件
  - 并发安全：用 session_id 集合避免同一 session 被并发摘要两次

目录结构：
  storage_dir/
    projects/<sanitized>/sessions/<session_id>.jsonl
    projects/<sanitized>/memory/SUMMARY.md
    projects/<sanitized>/memory/MEMORY.md
    dates/YYYY-MM-DD/sessions/<session_id>.jsonl
    dates/YYYY-MM-DD/memory/SUMMARY.md
    dates/YYYY-MM-DD/memory/memory.md
"""

from __future__ import annotations

import asyncio
import glob
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from ..llm.base import LLMProvider


# ─── 常量 ─────────────────────────────────────────────────────────────────────

SCAN_INTERVAL_SECONDS: int = 600         # 每 10 分钟扫描一次
UNSUMMARIZED_CHARS_THRESHOLD: int = 200_000  # ≈50k token；超过则中途触发摘要
INACTIVITY_SECONDS: int = 600            # 超过 10 分钟未写入视为 session 已结束


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def _read_events(jsonl_path: Path) -> list[dict]:
    """读取 session JSONL，返回所有事件列表。"""
    events: list[dict] = []
    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass
    return events


def _count_raw_chars(events: list[dict], start_idx: int = 0) -> int:
    """统计从 start_idx 开始的原始对话字符数（用户消息 + 助手文本，不含 compact）。"""
    total = 0
    for ev in events[start_idx:]:
        ev_type = ev.get("type", "")
        if ev_type == "user-message":
            total += len(ev.get("content", ""))
        elif ev.get("role") == "assistant":
            for block in ev.get("parts", []):
                if block.get("type") == "text":
                    total += len(block.get("content", ""))
                    break
    return total


def _detect_scope(jsonl_path: Path, storage_dir: Path) -> tuple[str, Path]:
    """从 JSONL 路径推断 mode 和对应的 memory 目录。

    Returns:
        (mode, memory_dir)  mode 为 "project" 或 "date"
    """
    try:
        rel = jsonl_path.relative_to(storage_dir)
        parts = rel.parts
        # parts[0] = "projects" | "dates"
        # parts[1] = "<sanitized>" | "YYYY-MM-DD"
        # parts[2] = "sessions"
        # parts[3] = "<session_id>.jsonl"
        if len(parts) >= 4:
            scope_dir = storage_dir / parts[0] / parts[1]
            memory_dir = scope_dir / "memory"
            mode = "project" if parts[0] == "projects" else "date"
            return mode, memory_dir
    except ValueError:
        pass
    # fallback
    return "date", jsonl_path.parent.parent / "memory"


# ─── MemoryWatcher ────────────────────────────────────────────────────────────

class MemoryWatcher:
    """后台 watcher：定期扫描所有 session 文件，按需生成摘要与长期记忆。

    用法::

        watcher = MemoryWatcher(storage_dir="/path/to/.auton/memory", llm=llm)
        await watcher.start()
        # ... 应用运行中 ...
        await watcher.stop()        # 优雅关闭，等待当前扫描完成
    """

    def __init__(
        self,
        storage_dir: str | Path,
        llm: "LLMProvider",
        *,
        scan_interval: int = SCAN_INTERVAL_SECONDS,
        unsummarized_threshold: int = UNSUMMARIZED_CHARS_THRESHOLD,
        inactivity_seconds: int = INACTIVITY_SECONDS,
    ) -> None:
        self.storage_dir = Path(storage_dir).expanduser()
        self.llm = llm
        self.scan_interval = scan_interval
        self.unsummarized_threshold = unsummarized_threshold
        self.inactivity_seconds = inactivity_seconds

        self._task: asyncio.Task | None = None
        self._processing: set[str] = set()  # 正在处理的 session_id，防并发重入
        self._logger = logger.bind(name="MemoryWatcher")

    # ─── 生命周期 ──────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动后台扫描循环。"""
        if self._task and not self._task.done():
            return  # 已启动
        self._task = asyncio.create_task(self._loop(), name="memory-watcher")
        self._logger.info(
            "started (interval={s}s threshold={t}chars inactivity={i}s)",
            s=self.scan_interval,
            t=self.unsummarized_threshold,
            i=self.inactivity_seconds,
        )

    async def stop(self) -> None:
        """停止后台循环，等待当前正在进行的扫描完成。"""
        if not self._task or self._task.done():
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._logger.info("stopped")

    async def flush(self) -> None:
        """立即执行一次完整扫描（用于应用关闭前的最终 flush）。"""
        self._logger.info("flush: running final scan before shutdown")
        await self.scan_once()

    # ─── 扫描循环 ─────────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while True:
            # 先等待，再扫描（应用启动时不必立即扫描）
            await asyncio.sleep(self.scan_interval)
            try:
                await self.scan_once()
            except Exception as exc:
                self._logger.warning("scan error: {exc}", exc=exc)

    async def scan_once(self) -> None:
        """执行一次完整扫描，处理所有符合条件的 session 文件。"""
        all_jsonl = self._find_all_sessions()
        if not all_jsonl:
            return

        self._logger.debug("scanning {n} session files", n=len(all_jsonl))
        tasks = [self._maybe_process(p) for p in all_jsonl]
        await asyncio.gather(*tasks, return_exceptions=True)

    def _find_all_sessions(self) -> list[Path]:
        """返回 storage_dir 下所有 session JSONL 文件路径。"""
        patterns = [
            str(self.storage_dir / "projects" / "*" / "sessions" / "*.jsonl"),
            str(self.storage_dir / "dates" / "*" / "sessions" / "*.jsonl"),
        ]
        paths: list[Path] = []
        for pattern in patterns:
            paths.extend(Path(p) for p in glob.glob(pattern))
        return paths

    # ─── 单个 session 处理 ────────────────────────────────────────────────────

    async def _maybe_process(self, jsonl_path: Path) -> None:
        """检查单个 session 文件，决定是否触发摘要+记忆生成。"""
        session_id = jsonl_path.stem

        # 防止并发重入同一个 session
        if session_id in self._processing:
            return
        self._processing.add(session_id)
        try:
            await self._process_session(jsonl_path, session_id)
        except Exception as exc:
            self._logger.warning(
                "error processing session={id}: {exc}", id=session_id, exc=exc
            )
        finally:
            self._processing.discard(session_id)

    async def _process_session(self, jsonl_path: Path, session_id: str) -> None:
        """核心逻辑：读取 session，按条件生成摘要和记忆。"""
        from .summary_generator import generate_and_append_summary, get_last_summarized_idx
        from .memory_generator import update_project_memory, append_date_memory_entry

        # 1. 读取基本信息
        try:
            stat = jsonl_path.stat()
        except FileNotFoundError:
            return

        now = time.time()
        last_write = stat.st_mtime
        is_inactive = (now - last_write) > self.inactivity_seconds

        # 2. 读取事件
        events = _read_events(jsonl_path)
        if not events:
            return

        # 3. 确定 memory 目录 & 摘要路径
        mode, memory_dir = _detect_scope(jsonl_path, self.storage_dir)
        summary_path = memory_dir / "SUMMARY.md"

        # 4. 计算未摘要内容量
        last_idx = get_last_summarized_idx(summary_path, session_id)
        start_idx = last_idx + 1

        if start_idx > len(events) - 1:
            return  # 全部已摘要

        unsummarized_chars = _count_raw_chars(events, start_idx)

        # 5. 决策：是否触发？
        trigger_mid = unsummarized_chars >= self.unsummarized_threshold
        trigger_end = is_inactive and unsummarized_chars > 0

        if not trigger_mid and not trigger_end:
            return

        trigger_reason = (
            f"mid-session ({unsummarized_chars // 1000}k chars)"
            if trigger_mid and not trigger_end
            else (
                f"session-end (inactive {int(now - last_write)}s, {unsummarized_chars} chars)"
                if trigger_end
                else f"both mid+end"
            )
        )
        self._logger.info(
            "trigger={reason} session={id}",
            reason=trigger_reason,
            id=session_id[:8],
        )

        # 6. 生成摘要（SUMMARY.md）
        scope = (
            f"项目：{jsonl_path.parent.parent.name}"
            if mode == "project"
            else f"日期：{jsonl_path.parent.parent.name}"
        )
        new_last_idx = await generate_and_append_summary(
            self.llm,
            session_id=session_id,
            events=events,
            start_idx=start_idx,
            summary_path=summary_path,
            scope=scope,
        )

        if new_last_idx < start_idx:
            return  # 摘要生成失败或无内容

        self._logger.info(
            "SUMMARY.md updated events={s}-{e} session={id}",
            s=start_idx,
            e=new_last_idx,
            id=session_id[:8],
        )

        # 7. session 结束时才更新长期记忆（project MEMORY.md / date memory.md）
        if not trigger_end:
            return

        memory_dir.mkdir(parents=True, exist_ok=True)

        if mode == "project":
            memory_path = memory_dir / "MEMORY.md"
            project_name = jsonl_path.parent.parent.name
            ok = await update_project_memory(
                self.llm,
                session_id=session_id,
                events=events,
                memory_path=memory_path,
                project_name=project_name,
            )
            if ok:
                self._logger.info(
                    "MEMORY.md updated session={id}", id=session_id[:8]
                )
        else:
            memory_path = memory_dir / "memory.md"
            started_at = events[0].get("timestamp") or events[0].get("created_at")
            if isinstance(started_at, str):
                import datetime
                try:
                    started_at = datetime.datetime.fromisoformat(started_at).timestamp()
                except ValueError:
                    started_at = None
            await append_date_memory_entry(
                session_id=session_id,
                events=events,
                memory_path=memory_path,
                llm=self.llm,
                started_at=started_at,
            )
            self._logger.info(
                "memory.md updated session={id}", id=session_id[:8]
            )
