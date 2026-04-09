"""Agent Session Store — Append-only 会话日志存储

核心原则：存储（Store）和检索（Use）完全分离。
session_store.py 只管 append jsonl，不管检索。

设计要点：
  - 项目模式（project_root 已知）：存到 ~/.auton/memory/projects/<绝对路径字符串>/sessions/
  - 无项目模式（date 模式）：存到 ~/.auton/memory/dates/YYYY-MM-DD/sessions/
  - append-only：每个事件一行 jsonl，永不修改已有行
  - compact 时：原始消息行 + compact 摘要行同时 append，不删除原行
  - 会话结束后：将会话路径追加到 index.jsonl
  - 支持完整回放：从 jsonl 重建会话历史
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TextIO

from loguru import logger

from .message import Message
from ..memory.global_memory import GlobalMemory
from ..memory.storage_utils import project_storage_base

if TYPE_CHECKING:
    pass


class SessionStore:
    """Append-only 会话存储

    自动根据 project_root 判断存储位置：
      - project_root 已知 → 项目模式
        ~/.auton/memory/projects/<绝对路径字符串>/
          sessions/<session_id>.jsonl
          memory/MEMORY.md
          memory/SUMMARY.md
          index.jsonl

      - project_root 为 None → 日期模式
        ~/.auton/memory/dates/YYYY-MM-DD/
          sessions/<session_id>.jsonl
          memory/MEMORY.md
          memory/SUMMARY.md
          index.jsonl
    """

    SESSIONS_DIR = "sessions"
    MEMORY_DIR = "memory"
    INDEX_FILE = "index.jsonl"

    def __init__(
        self,
        storage_dir: Path,
        project_root: Path | None = None,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self._logger = logger.bind(name="SessionStore")

        # 自动检测模式：优先用显式传入的 project_root
        # 未传入时，从当前目录往上遍历找 .auton/ 作为项目根
        if project_root:
            self.project_root = Path(project_root)
        else:
            self.project_root = self._find_project_root()

        if self.project_root:
            self._mode: Literal["project", "date"] = "project"
            # 项目模式：统一存到 ~/.auton/memory/projects/<绝对路径字符串>/
            self._base = project_storage_base(self.storage_dir, self.project_root)
        else:
            self._mode = "date"
            self._base = self.storage_dir / "dates" / date.today().isoformat()

    def set_project_root(self, project_root: Path) -> None:
        """切换为项目模式（运行时调用）"""
        self.project_root = Path(project_root)
        self._mode = "project"
        # 项目模式：统一存到 ~/.auton/memory/projects/<绝对路径字符串>/
        self._base = project_storage_base(self.storage_dir, self.project_root)
        self._logger.info("switched to project mode: base={base}", base=self._base)

    def has_existing_project_history(self, cwd: Path) -> bool:
        """当前目录是否已有项目历史记录（projects/<绝对路径字符串>/）"""
        project_root = self._find_project_root(cwd) or cwd
        project_base = project_storage_base(self.storage_dir, project_root)
        return project_base.exists() and project_base.is_dir()

    # ─── 项目根自动检测 ─────────────────────────────────────────────────

    @staticmethod
    def _find_project_root(cwd: Path | None = None) -> Path | None:
        """从当前目录往上遍历，找 .git/ 目录作为项目根

        注意：
          - ~/.auton/ 是全局根目录，不算项目，跳过
          - 只有包含 .git/ 的目录才算项目
          - 找到项目根后，后续 session/memory 存储到 {项目}/.auton/memory/
        """
        if cwd is None:
            cwd = Path.cwd()
        home = Path.home()
        for dir_path in [cwd] + list(cwd.parents):
            # 跳过 home 目录
            if dir_path == home or dir_path == home.parent:
                continue
            # 有 .git/ 目录的就是项目
            if (dir_path / ".git").exists():
                return dir_path
        return None

    # ─── 路径计算 ───────────────────────────────────────────────────────

    def _sessions_dir(self) -> Path:
        d = self._base / self.SESSIONS_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _memory_dir(self) -> Path:
        d = self._base / self.MEMORY_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d

    def session_path(self, session_id: str) -> Path:
        """获取会话 jsonl 路径"""
        return self._sessions_dir() / f"{session_id}.jsonl"

    def index_path(self) -> Path:
        return self._base / self.INDEX_FILE

    def memory_dir(self) -> Path:
        """记忆目录（供 MemoryManager 调用）"""
        return self._memory_dir()

    def sessions_dir(self) -> Path:
        """sessions 目录"""
        return self._sessions_dir()

    def memory_path(self) -> Path:
        """MEMORY.md 路径"""
        return self._memory_dir() / "MEMORY.md"

    def summary_path(self) -> Path:
        """SUMMARY.md 路径"""
        return self._memory_dir() / "SUMMARY.md"

    @property
    def mode(self) -> Literal["project", "date"]:
        return self._mode

    @property
    def base(self) -> Path:
        return self._base

    # ─── Append-only 写入 ─────────────────────────────────────────────────

    def append_event(self, session_id: str, event: dict) -> None:
        """追加单个事件到 jsonl"""
        path = self.session_path(session_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def append_message(self, message: Message) -> None:
        """将会话消息写入 jsonl"""
        self.append_event(message.meta.session_id, message.to_dict())

    def append_system_message(
        self,
        session_id: str,
        content: str,
    ) -> None:
        """追加系统提示词事件"""
        self.append_event(
            session_id,
            {
                "type": "system",
                "content": content,
                "timestamp": time.time(),
            },
        )

    def append_user_message(
        self,
        session_id: str,
        content: str,
    ) -> None:
        """追加用户消息事件"""
        self.append_event(
            session_id,
            {
                "type": "user-message",
                "session_id": session_id,
                "content": content,
                "timestamp": time.time(),
            },
        )

    def append_assistant_message(
        self,
        session_id: str,
        message: Message,
    ) -> None:
        """追加助手消息事件"""
        self.append_event(session_id, message.to_dict())

    def append_compact_event(
        self,
        session_id: str,
        before_count: int,
        summary: str,
    ) -> None:
        """追加 compact 摘要事件（compact 时调用，不删除原始行）"""
        self.append_event(
            session_id,
            {
                "type": "compact",
                "session_id": session_id,
                "timestamp": time.time(),
                "before_count": before_count,
                "summary": summary,
            },
        )

    # ─── 会话结束归档 ────────────────────────────────────────────────────

    def archive_session(
        self,
        session_id: str,
        started_at: str,
        ended_at: str,
        compaction_count: int,
    ) -> None:
        """将会话路径追加到 index.jsonl"""
        index_path = self.index_path()
        entry = {
            "session_id": session_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "compaction_count": compaction_count,
            "path": f"{self.SESSIONS_DIR}/{session_id}.jsonl",
        }
        # 确保 index 所在目录存在
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(index_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # 项目模式下，增量维护 project_modify.md（仅记录 session 路径）
        if self._mode == "project":
            gm = GlobalMemory(self.storage_dir)
            gm.record_project_session_path(
                date.today(),
                str(self.session_path(session_id)),
            )
        self._logger.info("archive session={id}", id=session_id)

    # ─── 读取（供 memory_manager.py 调用）──────────────────────────────────

    def read_session(self, session_id: str) -> list[dict]:
        """读取整个 jsonl（供检索模块调用）"""
        path = self.session_path(session_id)
        if not path.exists():
            return []
        events = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        self._logger.warning("invalid json line ignored: path={path}", path=path)
        return events

    def read_session_lines(
        self,
        session_id: str,
        start_line: int = 0,
        end_line: int | None = None,
    ) -> list[dict]:
        """按行号范围读取 jsonl（用于三层检索 L3）"""
        path = self.session_path(session_id)
        if not path.exists():
            return []
        events = []
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                if i < start_line:
                    continue
                if end_line is not None and i >= end_line:
                    break
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    self._logger.warning("invalid json line ignored: path={path}, line={line_no}", path=path, line_no=i)
        return events

    def read_index(self) -> list[dict]:
        """读取 index.jsonl"""
        path = self.index_path()
        if not path.exists():
            return []
        entries = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    # ─── 静态方法 ─────────────────────────────────────────────────────

    @staticmethod
    def find_session_path(
        storage_dir: Path,
        session_id: str,
    ) -> Path | None:
        """在 projects/ 和 dates/ 中搜索 session jsonl，返回第一个匹配

        搜索顺序：dates/今日 → dates/昨日 → projects/*/
        """
        import os

        # dates/ 目录搜索（最近2天）
        from datetime import date, timedelta
        today = date.today()
        for d_offset in range(2):
            d = today - timedelta(days=d_offset)
            p = storage_dir / "dates" / d.isoformat() / "sessions" / f"{session_id}.jsonl"
            if p.exists():
                return p

        # projects/ 目录搜索
        projects_dir = storage_dir / "projects"
        if projects_dir.exists():
            for proj_dir in projects_dir.iterdir():
                if not proj_dir.is_dir():
                    continue
                p = proj_dir / "sessions" / f"{session_id}.jsonl"
                if p.exists():
                    return p

        return None

    def read_session_by_id(self, session_id: str) -> list[dict]:
        """读取指定 session_id 的 jsonl（自动搜索所有目录）"""
        # 先尝试当前 base 下
        path = self.session_path(session_id)
        if path.exists():
            events = []
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            self._logger.warning("invalid json line ignored: path={path}", path=path)
            return events

        # 搜索全部
        found = self.find_session_path(self.storage_dir, session_id)
        if found and found.exists():
            events = []
            with open(found, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            self._logger.warning("invalid json line ignored: path={path}", path=found)
            return events

        return []
