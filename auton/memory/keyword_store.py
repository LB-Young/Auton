"""Memory — L0 关键词长期记忆检索

位于 MEMORY.md L1 和 SUMMARY.md L2 之下的深层检索层。

工作原理：
  - 将 MEMORY.md / SUMMARY.md 内容分块后写入 chunks.jsonl
  - 查询时：用 BM25 关键词 + TF-IDF 评分
  - 结合时间衰减（recent boost）排序
  - 每次查询命中自动更新访问索引

检索分层：
  L0 (keyword_store): chunks.jsonl — 全量内容块，关键词匹配
  L1 (memory_md):    MEMORY.md — 高价值记忆行
  L2 (summary_md):   SUMMARY.md — 会话摘要块
  L3 (jsonl):        sessions/*.jsonl — 原始事件流
"""

from __future__ import annotations

import json
import time
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.paths import resolve_userspace_path

if TYPE_CHECKING:
    from .chunking import Chunk

# 检索参数
RECENT_BOOST_DAYS = 30       # 30 天内的条目获得 boost
RECENT_BOOST_FACTOR = 1.5    # 近期条目评分乘数
DEFAULT_TOP_K = 10           # 默认返回数量


@dataclass
class RetrievalHit:
    """检索命中结果"""
    text: str
    source_type: str        # memory / summary / topic
    source_id: str
    score: float
    keywords_matched: list[str]
    chunk_index: int | None


class KeywordStore:
    """关键词长期记忆检索器（L0）"""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = storage_dir or resolve_userspace_path("memory")
        self.chunks_path = self.storage_dir / "chunks.jsonl"
        self.access_path = self.storage_dir / ".access_index.json"
        self._doc_freq: dict[str, int] = {}  # 词 → 包含该词的文档数
        self._total_docs = 0
        self._avg_doc_len = 0
        self._load_stats()

    # ─── 索引构建 ───────────────────────────────────────────────────

    def rebuild_index(
        self,
        memory_dir: Path | None = None,
    ) -> int:
        """从内存目录重建 chunks 索引"""
        from .chunking import ChunkedStore, split_into_chunks

        memory_dir = memory_dir or self.storage_dir
        chunked = ChunkedStore(storage_dir=memory_dir)

        # 索引 MEMORY.md
        memory_md = memory_dir / "MEMORY.md"
        summary_md = memory_dir / "SUMMARY.md"

        chunks = []
        if memory_md.exists():
            text = memory_md.read_text(encoding="utf-8")
            # 去除 frontmatter
            text = self._strip_frontmatter(text)
            chunks.extend(split_into_chunks(text, source_type="memory", source_id="MEMORY.md"))

        if summary_md.exists():
            text = summary_md.read_text(encoding="utf-8")
            text = self._strip_frontmatter(text)
            chunks.extend(split_into_chunks(text, source_type="summary", source_id="SUMMARY.md"))

        # 索引 topic 文件
        for topic_path in memory_dir.glob("*.md"):
            if topic_path.name in ("MEMORY.md", "SUMMARY.md", "index.jsonl"):
                continue
            text = topic_path.read_text(encoding="utf-8")
            text = self._strip_frontmatter(text)
            chunks.extend(split_into_chunks(text, source_type="topic", source_id=topic_path.name))

        added = chunked.add_chunks(chunks)
        # 重建后重新加载统计
        self._load_stats()
        return added

    def _strip_frontmatter(self, text: str) -> str:
        """去除 YAML frontmatter"""
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                text = parts[2]
        return text.lstrip("\n")

    def _load_stats(self) -> None:
        """加载文档频率统计"""
        if not self.chunks_path.exists():
            self._total_docs = 0
            self._doc_freq = {}
            self._avg_doc_len = 0.0
            return

        doc_count = 0
        word_counter: Counter = Counter()
        total_words = 0

        with open(self.chunks_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                doc_count += 1
                words = self._tokenize(rec.get("text", ""))
                word_counter.update(set(words))
                total_words += len(words)

        self._total_docs = doc_count
        self._doc_freq = dict(word_counter)
        self._avg_doc_len = total_words / max(doc_count, 1)

    # ─── BM25 检索 ─────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        source_type: str | None = None,
    ) -> list[RetrievalHit]:
        """BM25 + 时间衰减检索"""
        if not self.chunks_path.exists():
            return []

        # 1. 提取查询词
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        # 2. BM25 评分
        hits: list[RetrievalHit] = []
        k1 = 1.5
        b = 0.75

        # 预计算 query term IDF
        idf: dict[str, float] = {}
        for term in query_terms:
            df = self._doc_freq.get(term, 0)
            if df == 0:
                idf[term] = 0
            else:
                idf[term] = math.log((self._total_docs - df + 0.5) / (df + 0.5) + 1)

        with open(self.chunks_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                stype = rec.get("source_type", "")
                if source_type and stype != source_type:
                    continue

                text = rec.get("text", "")
                words = self._tokenize(text)
                if not words:
                    continue

                # BM25
                bm25_score = 0.0
                matched: list[str] = []
                doc_len = len(words)

                for term in set(query_terms):
                    if term in words:
                        tf = words.count(term)
                        matched.append(term)
                        bm25_score += idf.get(term, 0) * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / max(self._avg_doc_len, 1)))

                if not matched:
                    continue

                # 时间衰减 boost
                # 优先使用记录中的 updated_at，fallback 到文件 mtime
                updated_at = rec.get("updated_at")
                if updated_at is None:
                    src_path = self.storage_dir / rec.get("source_id", "")
                    if src_path.exists():
                        updated_at = src_path.stat().st_mtime
                    else:
                        updated_at = time.time()
                days_old = (time.time() - updated_at) / 86400
                recency_boost = RECENT_BOOST_FACTOR if days_old < RECENT_BOOST_DAYS else 1.0
                final_score = bm25_score * recency_boost

                # 类型 boost
                type_boost = {"memory": 1.2, "summary": 1.0, "topic": 0.9}.get(stype, 1.0)
                final_score *= type_boost

                hits.append(RetrievalHit(
                    text=text[:300],  # 最多返回 300 字符
                    source_type=stype,
                    source_id=rec.get("source_id", ""),
                    score=final_score,
                    keywords_matched=matched,
                    chunk_index=rec.get("chunk_index"),
                ))

                # 更新访问索引
                self._bump_access(rec.get("source_id", ""))

        hits.sort(key=lambda h: h.score, reverse=True)

        # 去重：同一 source_id 只保留评分最高的
        seen: dict[str, RetrievalHit] = {}
        for h in hits:
            key = f"{h.source_type}:{h.source_id}"
            if key not in seen or h.score > seen[key].score:
                seen[key] = h

        result = list(seen.values())
        result.sort(key=lambda h: h.score, reverse=True)
        return result[:top_k]

    # ─── 辅助 ─────────────────────────────────────────────────────

    def _tokenize(self, text: str) -> list[str]:
        """中英文混合分词"""
        # 去除 Markdown 格式
        text = re.sub(r"```[\s\S]*?```", " ", text)
        text = re.sub(r"`[^`]+`", " ", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"[#*_~>-]", " ", text)

        words: list[str] = []

        # 中文词（2+ 连续汉字）
        for w in re.findall(r"[\u4e00-\u9fff]{2,}", text):
            words.append(w)

        # 英文词
        for w in re.findall(r"[a-zA-Z]{2,}", text):
            words.append(w.lower())

        return words

    def _bump_access(self, source_id: str) -> None:
        """更新访问计数"""
        if not source_id:
            return
        index: dict[str, int] = {}
        if self.access_path.exists():
            try:
                index = json.loads(self.access_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                index = {}
        index[source_id] = index.get(source_id, 0) + 1
        self.access_path.parent.mkdir(parents=True, exist_ok=True)
        self.access_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    def search_text(self, query: str, memory_path: Path, top_k: int = 5) -> list[RetrievalHit]:
        """在单个文本文件内关键词搜索（备用，不用索引时）"""
        text = memory_path.read_text(encoding="utf-8")
        text = self._strip_frontmatter(text)

        query_terms = [t.lower() for t in self._tokenize(query)]
        if not query_terms:
            return []

        lines = text.splitlines()
        hits: list[RetrievalHit] = []
        for i, line in enumerate(lines):
            line_lower = line.lower()
            matched = [t for t in query_terms if t in line_lower]
            if matched:
                hits.append(RetrievalHit(
                    text=line.strip(),
                    source_type="memory",
                    source_id=memory_path.name,
                    score=len(matched) / len(query_terms),
                    keywords_matched=matched,
                    chunk_index=i,
                ))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]
