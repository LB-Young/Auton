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

import base64
import json
import re
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

# ─── Base64 媒体落盘工具 ────────────────────────────────────────────────────

_DATA_URI_RE = re.compile(
    r'data:(image/[a-zA-Z0-9.+-]+|application/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=]+)'
)

_MIME_TO_EXT: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "application/pdf": "pdf",
}

_BASE64_MIN_LEN = 256  # 短于此长度的 base64 不落盘，避免误处理小图标


def _save_base64_uri(data_uri: str, tmp_dir: Path, prefix: str = "media") -> str | None:
    """将 base64 数据 URI 落盘，返回文件路径字符串；失败返回 None。"""
    m = _DATA_URI_RE.match(data_uri)
    if not m:
        return None
    mime, b64data = m.group(1), m.group(2)
    if len(b64data) < _BASE64_MIN_LEN:
        return None
    ext = _MIME_TO_EXT.get(mime, mime.split("/")[-1])
    tmp_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex[:12]}.{ext}"
    filepath = tmp_dir / filename
    try:
        filepath.write_bytes(base64.b64decode(b64data, validate=True))
    except Exception:
        return None
    return str(filepath)


def _replace_base64_in_str(value: str, tmp_dir: Path, tool_name: str = "tool") -> str:
    """将字符串中所有 base64 数据 URI 替换为落盘路径引用。"""
    def replacer(m: re.Match) -> str:
        saved = _save_base64_uri(m.group(0), tmp_dir, prefix=tool_name)
        if saved:
            return f"[media saved: {saved}]"
        return m.group(0)

    return _DATA_URI_RE.sub(replacer, value)


def _sanitize_event(event: dict, tmp_dir: Path) -> dict:
    """递归扫描 event dict，将 base64 数据 URI 落盘并替换为路径引用。

    只处理字符串值，不修改其他类型，也不修改 key。
    """
    if not isinstance(event, dict):
        return event

    result: dict = {}
    for k, v in event.items():
        if isinstance(v, str):
            # 推断工具名（用于文件名前缀）
            tool_name = event.get("tool_name") or (
                event.get("name") or k
            )
            result[k] = _replace_base64_in_str(v, tmp_dir, tool_name=str(tool_name))
        elif isinstance(v, dict):
            result[k] = _sanitize_event(v, tmp_dir)
        elif isinstance(v, list):
            result[k] = [
                _sanitize_event(item, tmp_dir) if isinstance(item, dict)
                else (_replace_base64_in_str(item, tmp_dir) if isinstance(item, str) else item)
                for item in v
            ]
        else:
            result[k] = v
    return result


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
        self.storage_dir = Path(storage_dir).expanduser()
        # base64 媒体文件统一落盘到 ~/.auton/tmp/
        self.tmp_dir: Path = self.storage_dir.parent / "tmp"
        self._logger = logger.bind(name="SessionStore")
        # session_id → Path 的懒加载索引，用于 O(1) 全局查找
        self._session_index: dict[str, Path] | None = None

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

    def set_date_mode(self, target_date: date | None = None) -> None:
        """切换为闲聊（日期）模式，忽略自动项目检测。"""
        self.project_root = None
        self._mode = "date"
        target_date = target_date or date.today()
        self._base = self.storage_dir / "dates" / target_date.isoformat()
        self._logger.info("switched to date mode: base={base}", base=self._base)

    @property
    def mode(self) -> Literal["project", "date"]:
        """当前存储模式（project / date）"""
        return self._mode

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

    def session_memory_sources(self) -> list[Path]:
        """返回当前会话允许访问的 session 目录列表。"""

        def add_if_valid(path: Path) -> None:
            if not path.exists() or not path.is_dir():
                return
            resolved = str(path.resolve(strict=False))
            if resolved in seen:
                return
            seen.add(resolved)
            sources.append(path)

        sources: list[Path] = []
        seen: set[str] = set()

        if self._mode == "project":
            add_if_valid(self._sessions_dir())
            return sources

        add_if_valid(self._sessions_dir())

        dates_root = self.storage_dir / "dates"
        if dates_root.exists():
            for date_dir in sorted(dates_root.iterdir()):
                if not date_dir.is_dir():
                    continue
                add_if_valid(date_dir / self.SESSIONS_DIR)

        projects_root = self.storage_dir / "projects"
        if projects_root.exists():
            for proj_dir in sorted(projects_root.iterdir()):
                if not proj_dir.is_dir():
                    continue
                add_if_valid(proj_dir / self.SESSIONS_DIR)

        return sources

    @property
    def mode(self) -> Literal["project", "date"]:
        return self._mode

    @property
    def base(self) -> Path:
        return self._base

    # ─── Append-only 写入 ─────────────────────────────────────────────────

    def sanitize_tool_output(self, content: str, tool_name: str = "tool") -> str:
        """将工具输出中的 base64 数据 URI 落盘，返回已替换为路径引用的字符串。

        应在工具结果写入 ToolPart.tool_output **之前**调用，确保 base64
        不进入任何内存中的会话上下文，也不被带入 LLM 的 prompt。
        """
        return _replace_base64_in_str(content, self.tmp_dir, tool_name=tool_name)

    def append_event(self, session_id: str, event: dict) -> None:
        """追加单个事件到 jsonl

        兜底安全层：写入前再次扫描 event，防止未经 sanitize_tool_output 处理的
        base64 数据意外进入 jsonl 文件。正常路径下 base64 应已在工具执行时被替换。
        """
        event = _sanitize_event(event, self.tmp_dir)
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
        message_id: str | None = None,
    ) -> None:
        """追加用户消息事件。

        message_id 用于后续在 SUMMARY.md 中为每条摘要要点附加来源引用，
        建议调用方传入 Message.message_id，保证与内存对象一致。
        """
        self.append_event(
            session_id,
            {
                "type": "user-message",
                "session_id": session_id,
                "content": content,
                "timestamp": time.time(),
                "message_id": message_id or str(uuid.uuid4()),
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
        meta: dict | None = None,
    ) -> None:
        """追加 compact 摘要事件（compact 时调用，不删除原始行）"""
        payload = {
            "type": "compact",
            "session_id": session_id,
            "timestamp": time.time(),
            "before_count": before_count,
            "summary": summary,
        }
        if meta:
            payload.update(meta)
        self.append_event(
            session_id,
            payload,
        )

    # ─── Skill 调用事件 ──────────────────────────────────────────────────

    def append_skill_invoke_start(
        self,
        session_id: str,
        skill_name: str,
        fragment_id: str,
        trigger: str,
        query: str,
        turn_index: int,
        skill_path: str = "",
        msg_id_start: str = "",
    ) -> None:
        """记录 skill 被注入 context 的时刻（每轮 LLM 调用开始前）。

        对应 OPTIMIZATION.md 7.2.2 中的 skill_invoke_start 事件。
        msg_id_start 为此时刻最后一条会话消息的 message_id，用于在 session.jsonl 中定位片段起点。
        """
        self.append_event(
            session_id,
            {
                "type": "skill_invoke_start",
                "session_id": session_id,
                "skill_name": skill_name,
                "fragment_id": fragment_id,
                "skill_path": skill_path,
                "trigger": trigger,
                "query": query,
                "turn_index": turn_index,
                "msg_id_start": msg_id_start,
                "timestamp": time.time(),
            },
        )

    def append_skill_invoke_end(
        self,
        session_id: str,
        skill_name: str,
        fragment_id: str,
        success: bool,
        tool_calls_count: int,
        llm_turns: int,
        duration_ms: float,
        error_message: str | None = None,
        msg_id_end: str = "",
    ) -> None:
        """记录一轮 skill 调用结束（工具链执行完毕后）。

        对应 OPTIMIZATION.md 7.2.2 中的 skill_invoke_end 事件。
        msg_id_end 为此时刻最后一条会话消息的 message_id，用于在 session.jsonl 中定位片段终点。
        """
        self.append_event(
            session_id,
            {
                "type": "skill_invoke_end",
                "session_id": session_id,
                "skill_name": skill_name,
                "fragment_id": fragment_id,
                "success": success,
                "tool_calls_count": tool_calls_count,
                "llm_turns": llm_turns,
                "duration_ms": duration_ms,
                "error_message": error_message,
                "msg_id_end": msg_id_end,
                "timestamp": time.time(),
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
        """将会话路径追加到 index.jsonl，并更新当前 scope 的 SUMMARY.md / MEMORY.md。

        两种 scope 下都会在对应目录生成/追加摘要文件：
          - 项目模式 → ~/.auton/memory/projects/<path>/memory/{SUMMARY,MEMORY}.md
          - 日期模式 → ~/.auton/memory/dates/YYYY-MM-DD/memory/{SUMMARY,MEMORY}.md
        """
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

        # 生成 / 更新当前 scope 的 SUMMARY.md 和 MEMORY.md
        self._update_memory_files(session_id)

        self._logger.info("archive session={id}", id=session_id)

    def _update_memory_files(self, session_id: str) -> None:
        """占位：SUMMARY.md 和 MEMORY.md 现由 SessionProcessor._generate_summary_and_memory() 异步生成。

        此方法保留以防外部调用，但不再执行实质操作。
        """

    # ─── 读取（供 memory_manager.py 调用）──────────────────────────────────

    @staticmethod
    def _read_session_file(path: Path) -> list[dict]:
        events: list[dict] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("invalid json line ignored: path={path}", path=path)
        return events

    def read_session(self, session_id: str) -> list[dict]:
        """读取整个 jsonl（供检索模块调用）"""
        path = self.session_path(session_id)
        if not path.exists():
            return []
        return self._read_session_file(path)

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

    def build_index(self) -> dict[str, Path]:
        """建立 session_id → Path 的内存索引（全量扫描，供首次调用时构建）。

        遍历 storage_dir 下所有 dates/ 和 projects/ 目录，
        将每个 .jsonl 文件的 stem 作为 session_id 加入索引。
        索引仅在 scope="all" 的查找路径中使用，构建后缓存于 _session_index。
        """
        index: dict[str, Path] = {}

        dates_dir = self.storage_dir / "dates"
        if dates_dir.exists():
            for date_dir in dates_dir.iterdir():
                if not date_dir.is_dir():
                    continue
                sessions_dir = date_dir / "sessions"
                if sessions_dir.is_dir():
                    for p in sessions_dir.glob("*.jsonl"):
                        index[p.stem] = p

        projects_dir = self.storage_dir / "projects"
        if projects_dir.exists():
            for proj_dir in projects_dir.iterdir():
                if not proj_dir.is_dir():
                    continue
                sessions_dir = proj_dir / "sessions"
                if sessions_dir.is_dir():
                    for p in sessions_dir.glob("*.jsonl"):
                        index[p.stem] = p

        self._logger.debug("session index built: {n} entries", n=len(index))
        return index

    def _invalidate_index(self) -> None:
        """新 session 创建后使缓存失效，下次查找时重建。"""
        self._session_index = None

    def read_session_by_id(
        self,
        session_id: str,
        *,
        scope: Literal["session", "all"] = "session",
    ) -> list[dict]:
        """读取指定 session_id 的 jsonl。

        Args:
            session_id: 目标 session ID
            scope: ``"session"`` 仅在当前会话允许的记忆源中搜索；
                ``"all"`` 搜索整个 storage_dir（用于 CLI replay 等全局操作）
        """
        if scope == "session":
            for sessions_dir in self.session_memory_sources():
                path = sessions_dir / f"{session_id}.jsonl"
                if path.exists():
                    return self._read_session_file(path)
            return []

        # scope="all": 使用内存索引实现 O(1) 查找，首次调用时构建
        if self._session_index is None:
            self._session_index = self.build_index()

        path = self._session_index.get(session_id)
        if path and path.exists():
            return self._read_session_file(path)

        # 索引未命中时降级为全量搜索（session 可能是新建的）
        found = self.find_session_path(self.storage_dir, session_id)
        if found and found.exists():
            # 补充到索引，避免下次再次全量搜索
            self._session_index[session_id] = found
            return self._read_session_file(found)
        return []
