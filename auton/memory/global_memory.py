"""Global Memory — 全局记忆管理（~/.auton/memory/dates/YYYY-MM-DD/）

无项目模式下使用，按日期组织：
  ~/.auton/memory/dates/YYYY-MM-DD/
    sessions/        # append-only jsonl
    memory/MEMORY.md  # 当日长期记忆索引（L1）
    memory/SUMMARY.md # 当日分段摘要（L2，详细）
    index.jsonl       # session 索引
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from loguru import logger

from ..core.paths import resolve_userspace_path


class GlobalMemory:
    """全局记忆管理器（按日期组织）

    存储结构：
      ~/.auton/memory/dates/YYYY-MM-DD/
        sessions/<session_id>.jsonl
        memory/MEMORY.md   # 当日长期记忆索引（L1）
        memory/SUMMARY.md  # 当日分段摘要（L2，详细）
        index.jsonl         # session 索引
    """

    SESSIONS_DIR = "sessions"
    MEMORY_DIR = "memory"
    INDEX_FILE = "index.jsonl"
    MEMORY_FILE = "MEMORY.md"
    SUMMARY_FILE = "SUMMARY.md"

    def __init__(self, storage_dir: Path | None = None) -> None:
        if storage_dir is None:
            storage_dir = resolve_userspace_path("memory")
        self.storage_dir = Path(storage_dir)
        self._logger = logger.bind(name="GlobalMemory")

    # ─── 路径 ───────────────────────────────────────────────────────────

    def _date_base(self, d: date) -> Path:
        return self.storage_dir / "dates" / d.isoformat()

    def sessions_dir(self, d: date) -> Path:
        p = self._date_base(d) / self.SESSIONS_DIR
        p.mkdir(parents=True, exist_ok=True)
        return p

    def memory_dir(self, d: date) -> Path:
        p = self._date_base(d) / self.MEMORY_DIR
        p.mkdir(parents=True, exist_ok=True)
        return p

    def index_path(self, d: date) -> Path:
        return self._date_base(d) / self.INDEX_FILE

    def memory_path(self, d: date) -> Path:
        """memory/MEMORY.md 路径"""
        return self.memory_dir(d) / self.MEMORY_FILE

    def summary_path(self, d: date) -> Path:
        """memory/SUMMARY.md 路径"""
        return self.memory_dir(d) / self.SUMMARY_FILE

    def session_path(self, d: date, session_id: str) -> Path:
        """sessions/<session_id>.jsonl 路径"""
        return self.sessions_dir(d) / f"{session_id}.jsonl"

    # ─── 读取 ───────────────────────────────────────────────────────────

    def read_memory(self, d: date) -> str:
        """读取指定日期的 MEMORY.md"""
        path = self.memory_path(d)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def read_summary(self, d: date) -> str:
        """读取指定日期的 SUMMARY.md"""
        path = self.summary_path(d)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    # ─── 写入 ───────────────────────────────────────────────────────────

    def append_memory_entry(self, d: date, line: str) -> None:
        """向指定日期的 MEMORY.md 追加一条"""
        path = self.memory_path(d)
        if not path.exists():
            header = (
                f"本文档是 {d.isoformat()} 全局长期记忆索引，"
                "详细的会话分段总结见 [memory/SUMMARY.md](memory/SUMMARY.md)。\n\n"
            )
            path.write_text(header + line + "\n", encoding="utf-8")
        else:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def append_summary_blocks(self, d: date, blocks: list[str]) -> None:
        """向指定日期的 SUMMARY.md 追加 block 摘要行"""
        path = self.summary_path(d)
        lines = "\n".join(blocks) + "\n"
        if not path.exists():
            header = (
                f"# 摘要索引：{d.isoformat()}（全局记忆）\n\n"
                "本文档记录当日所有对话的分段总结，"
                "每个 block 对应 jsonl 中一个完整的话题/任务段。\n\n"
            )
            path.write_text(header + lines, encoding="utf-8")
        else:
            with open(path, "a", encoding="utf-8") as f:
                f.write(lines)

    # ─── 加载策略 ────────────────────────────────────────────────────────

    def get_today_and_yesterday(self) -> tuple[date, date]:
        """返回（今日，昨日）"""
        today = date.today()
        yesterday = today - timedelta(days=1)
        return today, yesterday

    def list_recent_project_memories(
        self,
        hours: int = 48,
    ) -> list[tuple[Path, Path]]:
        """扫描所有项目最近修改的 MEMORY.md

        Returns:
            [(项目根, memory_path), ...] — 按 mtime 降序
        """
        from ..core.config import get_config

        config = get_config()
        root = self.storage_dir.parent  # ~/.auton/
        results: list[tuple[Path, Path]] = []

        # 扫描所有 ~/.auton/memory/projects/*/memory/MEMORY.md
        cutoff = timedelta(hours=hours)
        now = datetime.now()
        projects_dir = root / "memory" / "projects"
        if projects_dir.exists():
            for proj_dir in projects_dir.iterdir():
                if not proj_dir.is_dir():
                    continue
                memory_md = proj_dir / "memory" / "MEMORY.md"
                if not memory_md.exists():
                    continue
                mtime = datetime.fromtimestamp(memory_md.stat().st_mtime)
                if (now - mtime) <= cutoff:
                    results.append((proj_dir, memory_md))

        # 按 mtime 降序
        results.sort(
            key=lambda x: x[1].stat().st_mtime,
            reverse=True,
        )
        return results

    def get_loaded_memories_for_today(self) -> list[str]:
        """获取今日（闲聊模式）应加载的所有记忆内容

        包括：
          - 当日 global MEMORY.md
          - 昨日 global MEMORY.md
          - 近 48 小时修改过的项目 MEMORY.md
        """
        today, yesterday = self.get_today_and_yesterday()
        contents: list[str] = []

        # 当日
        today_mem = self.read_memory(today)
        if today_mem:
            contents.append(f"## ~/.auton/memory/dates/{today.isoformat()}/memory/MEMORY.md\n\n{today_mem}")

        # 昨日
        yesterday_mem = self.read_memory(yesterday)
        if yesterday_mem:
            contents.append(
                f"## ~/.auton/memory/dates/{yesterday.isoformat()}/memory/MEMORY.md\n\n{yesterday_mem}"
            )

        # 近 48 小时修改过的项目
        for project_dir, memory_path in self.list_recent_project_memories(hours=48):
            content = memory_path.read_text(encoding="utf-8")
            rel = memory_path.relative_to(project_dir / "memory")
            contents.append(f"## ~/.auton/memory/projects/{project_dir.name}/memory/{rel}\n\n{content}")

        return contents

    # ─── project_modify.md（近两天项目 session 路径索引）────────────────────

    def project_modify_path(self) -> Path:
        return self.storage_dir / "project_modify.md"

    def _parse_project_modify(self) -> dict[str, list[str]]:
        path = self.project_modify_path()
        if not path.exists():
            return {}

        result: dict[str, list[str]] = {}
        current_date: str | None = None
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("## "):
                current_date = line[3:].strip()
                result.setdefault(current_date, [])
                continue
            if line.startswith("- ") and current_date:
                result[current_date].append(line[2:].strip())
        return result

    def _write_project_modify(self, grouped_paths: dict[str, list[str]]) -> None:
        path = self.project_modify_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = ["# 最近两天项目会话索引", ""]
        for day in sorted(grouped_paths.keys(), reverse=True):
            paths = grouped_paths.get(day, [])
            if not paths:
                continue
            lines.append(f"## {day}")
            for session_path in paths:
                lines.append(f"- {session_path}")
            lines.append("")

        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    def record_project_session_path(self, d: date, session_path: str) -> None:
        """记录项目 session 路径到 project_modify.md（仅保留今天和昨天）"""
        grouped = self._parse_project_modify()
        key = d.isoformat()
        grouped.setdefault(key, [])
        if session_path not in grouped[key]:
            grouped[key].append(session_path)

        today, yesterday = self.get_today_and_yesterday()
        keep = {today.isoformat(), yesterday.isoformat()}
        filtered: dict[str, list[str]] = {}
        for day, paths in grouped.items():
            if day in keep:
                # 保留写入顺序并去重
                seen = set()
                uniq_paths: list[str] = []
                for p in paths:
                    if p not in seen:
                        seen.add(p)
                        uniq_paths.append(p)
                filtered[day] = uniq_paths

        self._write_project_modify(filtered)

    def read_recent_project_session_paths(self) -> list[str]:
        """读取 project_modify.md 中今天和昨天的所有项目 session 路径"""
        grouped = self._parse_project_modify()
        today, yesterday = self.get_today_and_yesterday()
        result: list[str] = []
        for day in [today.isoformat(), yesterday.isoformat()]:
            result.extend(grouped.get(day, []))
        return result
