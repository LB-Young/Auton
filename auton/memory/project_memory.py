"""Project Memory — 项目级记忆管理

项目级记忆存储在 {项目根}/.auton/memory/ 目录：

  {项目根}/.auton/memory/
    sessions/           # append-only session jsonl
      <session_id>.jsonl
    memory/             # 长期记忆沉淀
      MEMORY.md         # 顶层索引
      SUMMARY.md        # 所有 jsonl 的分段详细摘要
      user_role.md      # type: user
      feedback_*.md     # type: feedback
      project_*.md      # type: project
      reference_*.md    # type: reference
      ...
    index.jsonl         # session 索引
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from loguru import logger


class ProjectMemory:
    """项目级记忆管理器

    存储结构：
      {项目根}/.auton/memory/
        sessions/<session_id>.jsonl
        memory/MEMORY.md
        memory/SUMMARY.md
        memory/user_role.md, feedback_*.md, project_*.md, reference_*.md ...
        index.jsonl
    """

    SESSIONS_DIR = "sessions"
    MEMORY_SUBDIR = "memory"
    INDEX_FILE = "index.jsonl"
    MEMORY_FILENAME = "MEMORY.md"
    SUMMARY_FILENAME = "SUMMARY.md"

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)
        self.memory_dir = self.project_root / ".auton" / "memory"
        self._logger = logger.bind(name="ProjectMemory")

    # ─── 目录初始化 ─────────────────────────────────────────────────────

    def ensure(self) -> None:
        """确保项目记忆目录存在"""
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir().mkdir(exist_ok=True)
        self.memory_subdir().mkdir(exist_ok=True)

    def sessions_dir(self) -> Path:
        return self.memory_dir / self.SESSIONS_DIR

    def memory_subdir(self) -> Path:
        return self.memory_dir / self.MEMORY_SUBDIR

    def exists(self) -> bool:
        """当前项目是否已有记忆目录"""
        return self.memory_dir.exists() and self.memory_dir.is_dir()

    @classmethod
    def find_project_root(cls, cwd: Path | None = None) -> Path | None:
        """查找最近的项目根目录（当前目录或其父目录有 .auton/）"""
        import os

        if cwd is None:
            cwd = Path.cwd()
        for dir_path in [cwd] + list(cwd.parents):
            if (dir_path / ".auton").exists() and (dir_path / ".auton").is_dir():
                return dir_path
            if (dir_path / ".auton" / "memory").exists():
                return dir_path
        return None

    # ─── 路径 ───────────────────────────────────────────────────────────

    def session_path(self, session_id: str) -> Path:
        return self.sessions_dir() / f"{session_id}.jsonl"

    def get_memory_path(self) -> Path:
        return self.memory_subdir() / self.MEMORY_FILENAME

    def get_summary_path(self) -> Path:
        return self.memory_subdir() / self.SUMMARY_FILENAME

    def get_index_path(self) -> Path:
        return self.memory_dir / self.INDEX_FILE

    # ─── MEMORY.md ─────────────────────────────────────────────────────

    def read_memory(self) -> str:
        """读取 MEMORY.md 全文"""
        path = self.get_memory_path()
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def write_memory(self, content: str) -> None:
        """写入 MEMORY.md"""
        self.ensure()
        path = self.get_memory_path()
        path.write_text(content, encoding="utf-8")
        self._logger.info("written MEMORY.md size={n} bytes", n=len(content))

    def append_memory_entry(self, line: str) -> None:
        """向 MEMORY.md 追加一条索引条目"""
        self.ensure()
        path = self.get_memory_path()
        if not path.exists():
            header = (
                "本文档是项目记忆顶层索引，"
                "详细的会话分段总结见 [memory/SUMMARY.md](memory/SUMMARY.md)。\n\n"
            )
            path.write_text(header + line + "\n", encoding="utf-8")
        else:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    # ─── SUMMARY.md ────────────────────────────────────────────────────

    def read_summary(self) -> str:
        """读取 SUMMARY.md 全文"""
        path = self.get_summary_path()
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def write_summary(self, content: str) -> None:
        """写入 SUMMARY.md"""
        self.ensure()
        path = self.get_summary_path()
        path.write_text(content, encoding="utf-8")

    def append_summary_blocks(self, blocks: list[str]) -> None:
        """向 SUMMARY.md 追加 block 摘要行"""
        self.ensure()
        path = self.get_summary_path()
        lines = "\n".join(blocks) + "\n"
        if not path.exists():
            header = f"# 摘要索引：{datetime.now().strftime('%Y-%m-%d')}（项目记忆）\n\n"
            header += (
                "本文档记录本项目所有对话的分段总结，"
                "每个 block 对应 jsonl 中一个完整的话题/任务段。\n\n"
            )
            path.write_text(header + lines, encoding="utf-8")
        else:
            with open(path, "a", encoding="utf-8") as f:
                f.write(lines)

    # ─── 主题文件（带 frontmatter 的 .md）───────────────────────────────

    def get_topic_path(self, filename: str) -> Path:
        return self.memory_subdir() / filename

    def write_topic_file(self, filename: str, content: str) -> None:
        self.ensure()
        path = self.get_topic_path(filename)
        path.write_text(content, encoding="utf-8")

    def read_topic_file(self, filename: str) -> str:
        path = self.get_topic_path(filename)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def list_topic_files(self) -> list[Path]:
        """列出所有主题文件（排除 MEMORY.md / SUMMARY.md / index.jsonl）"""
        subdir = self.memory_subdir()
        if not subdir.exists():
            return []
        skip = {self.MEMORY_FILENAME, self.SUMMARY_FILENAME, self.INDEX_FILE}
        return [
            p for p in subdir.iterdir()
            if p.is_file() and p.suffix == ".md" and p.name not in skip
        ]

    # ─── index.jsonl ─────────────────────────────────────────────────

    def append_session_index(self, session_id: str, started_at: str) -> None:
        """追加 session 到 index.jsonl"""
        import json

        self.ensure()
        path = self.get_index_path()
        entry = {
            "session_id": session_id,
            "started_at": started_at,
            "path": f"{self.SESSIONS_DIR}/{session_id}.jsonl",
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_session_index(self) -> list[dict]:
        """读取 index.jsonl"""
        import json

        path = self.get_index_path()
        if not path.exists():
            return []
        entries = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    # ─── 执行摘要蒸馏 ─────────────────────────────────────────────────

    def distill_from_jsonl(
        self,
        session_store_path: Path,
        session_id: str,
        blocks: list[dict],
    ) -> list[str]:
        """从 jsonl block 生成 SUMMARY.md 条目行"""
        lines = []
        for i, block in enumerate(blocks, start=1):
            summary = block.get("summary", "")
            files = block.get("files", [])
            decisions = block.get("decisions", [])
            intent = block.get("intent", "")

            parts = [summary]
            if files:
                parts.append(f"涉及文件：{', '.join(files)}。")
            if decisions:
                parts.append(f"关键决策：{'；'.join(decisions)}。")
            if intent:
                parts.append(f"用户意图：{intent}。")

            lines.append(f"- block_{i:03d}: {''.join(parts)}")
        return lines
