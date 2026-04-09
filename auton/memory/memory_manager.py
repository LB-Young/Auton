"""Memory Manager — 统一检索入口

M4 里程碑的核心模块。负责：
  1. 模式判断（项目模式 vs 无项目模式）
  2. 加载对应范围的记忆
  3. 触发记忆蒸馏（compaction / daily / startup）
  4. 提供检索接口给 SessionProcessor
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from loguru import logger

from .auton_md import AutonMDManager
from .conflict_resolver import ConflictResolver
from .forgetting import run_gc, get_forgetting_stats
from .global_memory import GlobalMemory
from .keyword_store import KeywordStore
from .memory_md import MemoryMDManager
from .project_memory import ProjectMemory
from .session_summarizer import SessionSummarizer
from .storage_utils import project_storage_base
from .types import MemoryEntry, MemoryType, RetrievalResult, SummaryBlock


@dataclass
class MemoryMode:
    """记忆模式"""

    mode: Literal["project", "date"]  # 项目模式 或 日期模式
    project_root: Path | None = None  # 项目根目录（项目模式时）
    storage_dir: Path | None = None  # storage_dir（日期模式时）


class MemoryManager:
    """统一记忆管理器

    使用示例（SessionProcessor 集成）：
      mm = MemoryManager(storage_dir=Path("~/.auton/memory"))
      mode = mm.detect_mode(cwd=Path.cwd())
      context = mm.get_context(mode, session_store=session_store)
      mm.trigger_daily_distillation(date.today())
    """

    def __init__(
        self,
        storage_dir: Path | None = None,
        project_root: Path | None = None,
    ) -> None:
        if storage_dir is None:
            storage_dir = Path("~/.auton/memory").expanduser()
        self.storage_dir = Path(storage_dir)
        self.project_root = project_root

        self.global_mem = GlobalMemory(storage_dir)
        self.project_mem: ProjectMemory | None = None
        if self.project_root:
            self.project_mem = ProjectMemory(self.project_root)

        self.summarizer = SessionSummarizer()
        self.md_manager = MemoryMDManager()
        self.auton_md = AutonMDManager()
        self.conflict_resolver = ConflictResolver()
        self.keyword_store = KeywordStore(storage_dir)
        self._logger = logger.bind(name="MemoryManager")

    # ─── 模式检测 ─────────────────────────────────────────────────────

    def detect_mode(self, cwd: Path | None = None) -> MemoryMode:
        """检测当前是项目模式还是日期模式"""
        if cwd is None:
            cwd = Path.cwd()

        project_root = ProjectMemory.find_project_root(cwd)
        if project_root:
            self.project_root = project_root
            self.project_mem = ProjectMemory(project_root)
            return MemoryMode(mode="project", project_root=project_root)

        return MemoryMode(mode="date", storage_dir=self.storage_dir)

    # ─── 上下文加载 ───────────────────────────────────────────────────

    def get_context(self, mode: MemoryMode) -> str:
        """获取要注入到 system prompt 的记忆上下文"""
        parts: list[str] = []

        # 1. auton.md 合并内容（跨项目偏好）
        auton = self.auton_md.load_as_markdown()
        if auton:
            parts.append("## 用户偏好（来自 auton.md）\n" + auton)

        if mode.mode == "project":
            parts.append(self._get_project_context())
        else:
            parts.append(self._get_date_context())

        return "\n\n".join(parts)

    def _get_project_context(self) -> str:
        """项目模式上下文"""
        if not self.project_mem:
            return ""

        parts = ["## 项目记忆"]

        memory = self.project_mem.read_memory()
        if memory:
            parts.append(f"### MEMORY.md\n{memory}")

        # L0 关键词检索（从 chunks.jsonl，取 top-3）
        l0_hits = self.keyword_store.search(
            query="",
            top_k=3,
        )
        if l0_hits:
            ctx_lines = ["### 相关长期记忆"]
            for hit in l0_hits:
                ctx_lines.append(f"- [{hit.source_type}] {hit.text[:150]}")
            parts.append("\n".join(ctx_lines))

        return "\n\n".join(parts)

    def _get_date_context(self) -> str:
        """日期模式上下文"""
        memories = self.global_mem.get_loaded_memories_for_today()
        if not memories:
            return "## 全局记忆\n\n（暂无全局记忆）"
        return "\n\n".join(memories)

    # ─── 蒸馏触发 ─────────────────────────────────────────────────────

    def distill_session(
        self,
        session_store,
        session_id: str,
    ) -> int:
        """将会话 jsonl 蒸馏到 SUMMARY.md 和 MEMORY.md

        调用时机：会话结束时、compaction 时、每日启动时

        Args:
            session_store: SessionStore 实例（已包含 project_root）
            session_id: 会话 ID

        Returns:
            新增 MEMORY.md 条目数
        """
        mode = self.detect_mode()
        blocks = self.summarizer.summarize_from_store(
            session_store.sessions_dir(), session_id
        )
        if not blocks:
            return 0

        if mode.mode == "project" and self.project_mem:
            # 项目模式：写入 ~/.auton/memory/projects/<绝对路径字符串>/memory/
            project_base = project_storage_base(self.storage_dir, mode.project_root)
            summary_path = project_base / "memory" / "SUMMARY.md"
            memory_path = project_base / "memory" / "MEMORY.md"

            block_lines = [b.to_line() for b in blocks]
            self.project_mem.append_summary_blocks(block_lines)

            new_count = self.md_manager.distill_summary_to_memory(
                summary_path, memory_path
            )
            self._logger.info(
                "distilled session {s}: {n} blocks, {c} MEMORY entries (project)",
                s=session_id,
                n=len(blocks),
                c=new_count,
            )
            return new_count
        else:
            # 日期模式：写入 dates/YYYY-MM-DD/memory/
            today = date.today()
            summary_path = self.global_mem.summary_path(today)
            memory_path = self.global_mem.memory_path(today)

            block_lines = [b.to_line() for b in blocks]
            self.global_mem.append_summary_blocks(today, block_lines)

            new_count = self.md_manager.distill_summary_to_memory(
                summary_path, memory_path
            )
            self._logger.info(
                "distilled session {s}: {n} blocks, {c} MEMORY entries (date)",
                s=session_id,
                n=len(blocks),
                c=new_count,
            )
            return new_count

    def trigger_daily_distillation(self, d: date | None = None) -> int:
        """每日首次启动时：扫描昨日 date 目录的 session jsonl，提取主题，更新当日 MEMORY

        调用时机：每日首次启动时

        Args:
            d: 目标日期（默认昨日）
        """
        if d is None:
            d = date.today()

        # 扫描昨日 date 目录中的所有 jsonl
        import json

        sessions_dir = self.global_mem.sessions_dir(d)
        if not sessions_dir.exists():
            return 0

        total_new = 0
        for jsonl_file in sessions_dir.glob("*.jsonl"):
            session_id = jsonl_file.stem
            try:
                events = []
                with open(jsonl_file, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            events.append(json.loads(line))
                if not events:
                    continue
                blocks = self.summarizer.summarize_session(events, session_id)
                block_lines = [b.to_line() for b in blocks]

                summary_path = self.global_mem.summary_path(d)
                memory_path = self.global_mem.memory_path(d)
                self.global_mem.append_summary_blocks(d, block_lines)
                new_count = self.md_manager.distill_summary_to_memory(
                    summary_path, memory_path
                )
                total_new += new_count
            except Exception as exc:
                self._logger.warning("failed to distill {f}: {e}", f=jsonl_file.name, e=exc)

        self._logger.info("daily distillation {d}: {n} new entries", d=d.isoformat(), n=total_new)
        return total_new

    # ─── 三层检索 ─────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        mode: MemoryMode | None = None,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """四层检索：L0 chunks.jsonl → L1 MEMORY.md → L2 SUMMARY.md → L3 jsonl"""
        if mode is None:
            mode = self.detect_mode()

        results: list[RetrievalResult] = []
        query_lower = query.lower()

        # L0: BM25 关键词检索（chunked store）
        if query.strip():
            l0_hits = self.keyword_store.search(query, top_k=top_k)
            for hit in l0_hits:
                results.append(RetrievalResult(
                    content=hit.text,
                    source=f"long_term:{hit.source_type}:{hit.source_id}",
                    score=hit.score,
                ))

        if mode.mode == "project" and self.project_mem:
            # L1: memory/MEMORY.md
            memory_text = self.project_mem.read_memory()
            results.extend(
                self._search_memory(query_lower, memory_text, "MEMORY.md", top_k)
            )
            # L2: memory/SUMMARY.md
            summary_text = self.project_mem.read_summary()
            results.extend(
                self._search_summary(query_lower, summary_text, mode, top_k)
            )
        else:
            # 日期模式：搜索当日 + 近 2 天
            today, yesterday = self.global_mem.get_today_and_yesterday()
            for d in [today, yesterday]:
                memory_text = self.global_mem.read_memory(d)
                rel = f"dates/{d.isoformat()}/memory/MEMORY.md"
                results.extend(
                    self._search_memory(query_lower, memory_text, rel, top_k)
                )
                summary_text = self.global_mem.read_summary(d)
                results.extend(
                    self._search_summary(query_lower, summary_text, mode, top_k)
                )

        # 去重
        seen: dict[str, RetrievalResult] = {}
        for r in results:
            key = r.source
            if key not in seen or r.score > seen[key].score:
                seen[key] = r

        deduped = list(seen.values())
        deduped.sort(key=lambda x: x.score, reverse=True)
        return deduped[:top_k]

    def _search_memory(
        self,
        query: str,
        text: str,
        source: str,
        top_k: int,
    ) -> list[RetrievalResult]:
        """L1 检索：MEMORY.md"""
        results: list[RetrievalResult] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if query in line.lower():
                results.append(
                    RetrievalResult(
                        content=line,
                        source=f"MEMORY.md:{source}",
                        score=1.0,
                    )
                )
        return results[:top_k]

    def _search_summary(
        self,
        query: str,
        text: str,
        mode: MemoryMode,
        top_k: int,
    ) -> list[RetrievalResult]:
        """L2 检索：SUMMARY.md"""
        import re

        results: list[RetrievalResult] = []
        session_id = ""

        for line in text.splitlines():
            line = line.strip()
            m = re.match(r"## (.+\.jsonl)", line)
            if m:
                session_id = m.group(1).replace(".jsonl", "")
                continue
            bm = re.match(r"- block_(\d+): (.*)", line)
            if bm and query in line.lower():
                block_index = int(bm.group(1))
                summary = bm.group(2).strip()
                results.append(
                    RetrievalResult(
                        content=line,
                        source=f"SUMMARY.md:{session_id}:block_{block_index}",
                        session_id=session_id,
                        block_index=block_index,
                        score=0.8,
                    )
                )

        return results[:top_k]

    # ─── 主题文件管理 ─────────────────────────────────────────────────

    def write_memory_entry(
        self,
        entry: MemoryEntry,
        mode: MemoryMode | None = None,
    ) -> None:
        """写入一条记忆条目（带 frontmatter 的主题文件）"""
        if mode is None:
            mode = self.detect_mode()

        filename = entry.type.filename(slug=entry.name.replace(" ", "_"))

        if mode.mode == "project" and self.project_mem:
            self.project_mem.write_topic_file(filename, entry.to_markdown())
        else:
            # 日期模式：写入 dates/YYYY-MM-DD/memory/
            today = date.today()
            memory_dir = self.global_mem.memory_dir(today)
            memory_dir.mkdir(parents=True, exist_ok=True)
            path = memory_dir / filename
            path.write_text(entry.to_markdown(), encoding="utf-8")

    def list_memory_entries(
        self,
        mode: MemoryMode | None = None,
    ) -> list[MemoryEntry]:
        """列出所有记忆条目"""
        if mode is None:
            mode = self.detect_mode()

        entries: list[MemoryEntry] = []

        if mode.mode == "project" and self.project_mem:
            for topic_path in self.project_mem.list_topic_files():
                try:
                    text = topic_path.read_text(encoding="utf-8")
                    entry = MemoryEntry.from_markdown(text, topic_path)
                    entries.append(entry)
                except Exception as exc:
                    self._logger.warning("failed to parse {p}: {e}", p=topic_path, e=exc)
        else:
            # 日期模式：扫描近 2 天的 memory 目录
            today, yesterday = self.global_mem.get_today_and_yesterday()
            for d in [today, yesterday]:
                memory_dir = self.global_mem.memory_dir(d)
                if not memory_dir.exists():
                    continue
                for md_file in memory_dir.glob("*.md"):
                    if md_file.name in ("MEMORY.md", "SUMMARY.md"):
                        continue
                    try:
                        text = md_file.read_text(encoding="utf-8")
                        entry = MemoryEntry.from_markdown(text, md_file)
                        entries.append(entry)
                    except Exception as exc:
                        self._logger.warning("failed to parse {p}: {e}", p=md_file, e=exc)

        return entries

    # ─── L0 长期记忆管理 ─────────────────────────────────────────────

    def rebuild_long_term_index(self, mode: MemoryMode | None = None) -> int:
        """重建 L0 长期记忆索引"""
        if mode is None:
            mode = self.detect_mode()

        if mode.mode == "project" and mode.project_root:
            memory_dir = project_storage_base(self.storage_dir, mode.project_root)
        else:
            memory_dir = self.storage_dir

        count = self.keyword_store.rebuild_index(memory_dir=memory_dir)
        self._logger.info("rebuilt L0 index: {n} chunks", n=count)
        return count

    def run_forgetting_gc(
        self,
        mode: MemoryMode | None = None,
        dry_run: bool = False,
    ) -> list[str]:
        """运行遗忘 GC"""
        if mode is None:
            mode = self.detect_mode()

        if mode.mode == "project" and mode.project_root:
            memory_dir = project_storage_base(self.storage_dir, mode.project_root)
        else:
            memory_dir = self.storage_dir

        deleted = run_gc(memory_dir, dry_run=dry_run)
        if dry_run:
            self._logger.info("forgetting GC (dry-run): {n} entries would be deleted", n=len(deleted))
        else:
            self._logger.info("forgetting GC: {n} entries deleted", n=len(deleted))
        return deleted

    def get_memory_stats(self, mode: MemoryMode | None = None) -> dict:
        """获取记忆统计信息"""
        if mode is None:
            mode = self.detect_mode()

        if mode.mode == "project" and mode.project_root:
            memory_dir = project_storage_base(self.storage_dir, mode.project_root)
        else:
            memory_dir = self.storage_dir

        forgetting_stats = get_forgetting_stats(memory_dir)
        entries = self.list_memory_entries(mode=mode)

        return {
            "total_entries": len(entries),
            "forgetting": forgetting_stats,
            "storage_dir": str(memory_dir),
        }
