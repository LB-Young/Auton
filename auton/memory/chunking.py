"""Memory — 文本分块（Chunking）

将长文本切分为语义块，用于长期记忆检索。
策略：按段落 > 按句子 > 按字符数上限。

分块原则：
  - 段落是最自然的语义边界
  - 每个 chunk 不超过 CHUNK_SIZE 字符
  - 连续 chunk 之间有 OVERLAP 重叠（保留上下文）
  - 保留 chunk 元信息（来源文件、段落索引、关键词）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ..core.paths import resolve_userspace_path


# 分块参数
CHUNK_SIZE = 512       # 最大字符数
CHUNK_OVERLAP = 64     # 重叠字符数
MIN_CHUNK_SIZE = 128  # 最小 chunk（太短的直接合并到上一块）


@dataclass
class Chunk:
    """单个文本块"""
    text: str                          # 块文本内容
    chunk_index: int                   # 在原文中的块序号
    source_type: str                   # 来源类型：memory / summary / topic
    source_id: str                     # 来源标识：文件名或 session_id
    keywords: list[str]                # 块内提取的关键词
    char_start: int                    # 在原文中的起始位置
    char_end: int                      # 在原文中的结束位置


def split_into_chunks(
    text: str,
    source_type: str = "memory",
    source_id: str = "",
    max_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """将长文本切分为语义块

    Args:
        text: 待分块文本
        source_type: 来源类型
        source_id: 来源标识
        max_size: 最大字符数
        overlap: 重叠字符数

    Returns:
        Chunk 列表
    """
    if not text or not text.strip():
        return []

    # 1. 先按段落分割（双换行或单个换行分隔）
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        paragraphs = [text]

    chunks: list[Chunk] = []
    current: list[str] = []
    current_size = 0
    char_pos = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            char_pos += 1  # 跳过空行
            continue

        para_len = len(para)

        # 段落本身超过 max_size → 按句子拆分
        if para_len > max_size:
            # 先 flush 当前累积的段落
            if current:
                _flush_chunk(current, chunks, char_pos, source_type, source_id)
                current = []
                current_size = 0

            sub_chunks = _split_oversized_paragraph(para, max_size, overlap)
            for sub in sub_chunks:
                sub_start = text.index(sub, char_pos) if sub in text[char_pos:] else char_pos
                chunks.append(_make_chunk(sub, len(chunks), source_type, source_id, sub_start, sub_start + len(sub)))
            char_pos += para_len + 1
            continue

        # 累积后超过 max_size → 先 flush
        if current_size + para_len + 1 > max_size and current:
            _flush_chunk(current, chunks, char_pos, source_type, source_id)
            current = []
            current_size = 0

        current.append(para)
        current_size += para_len + 1
        char_pos += para_len + 1

    # Flush 剩余内容
    if current:
        _flush_chunk(current, chunks, char_pos, source_type, source_id)

    # 合并太小的 chunks
    chunks = _merge_small_chunks(chunks)

    return chunks


def _split_paragraphs(text: str) -> list[str]:
    """按段落分割文本"""
    # 优先双换行（段落分隔）
    parts = text.split("\n\n")
    if len(parts) > 1:
        return parts
    # 其次单换行
    parts = text.split("\n")
    return [p for p in parts if p.strip()]


def _split_oversized_paragraph(text: str, max_size: int, overlap: int) -> list[str]:
    """将超长段落按句子拆分为多个子块"""
    sentences = _split_sentences(text)
    sub_chunks: list[str] = []
    current = ""

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(current) + len(sent) + 1 <= max_size:
            current = (current + "\n" + sent).strip()
        else:
            if current:
                sub_chunks.append(current)
            # 保留 overlap 字符的上下文
            current = sent[-overlap:] if len(sent) > overlap else sent

    if current:
        sub_chunks.append(current)

    return sub_chunks or [text[:max_size]]


def _split_sentences(text: str) -> list[str]:
    """按句子分割文本（中文/英文）"""
    # 中文句号/感叹号/问号
    sentences = re.split(r"(?<=[。！？])\s*", text)
    if len(sentences) > 1:
        return sentences
    # 英文句子边界
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return sentences


def _flush_chunk(
    paragraphs: list[str],
    chunks: list[Chunk],
    char_pos: int,
    source_type: str,
    source_id: str,
) -> None:
    """将累积的段落 flush 为一个 chunk"""
    text = "\n\n".join(paragraphs)
    start = char_pos - len(text)
    chunks.append(_make_chunk(text, len(chunks), source_type, source_id, max(0, start), char_pos))


def _make_chunk(
    text: str,
    index: int,
    source_type: str,
    source_id: str,
    char_start: int,
    char_end: int,
) -> Chunk:
    """创建 Chunk 并提取关键词"""
    keywords = extract_keywords(text)
    return Chunk(
        text=text,
        chunk_index=index,
        source_type=source_type,
        source_id=source_id,
        keywords=keywords,
        char_start=char_start,
        char_end=char_end,
    )


def _merge_small_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """合并太小的 chunks"""
    if not chunks:
        return chunks
    merged: list[Chunk] = []
    for chunk in chunks:
        if not merged:
            merged.append(chunk)
            continue
        last = merged[-1]
        if len(chunk.text) < MIN_CHUNK_SIZE:
            # 合并到上一块
            merged[-1] = Chunk(
                text=last.text + "\n\n" + chunk.text,
                chunk_index=last.chunk_index,
                source_type=last.source_type,
                source_id=last.source_id,
                keywords=list(set(last.keywords + chunk.keywords)),
                char_start=last.char_start,
                char_end=chunk.char_end,
            )
        else:
            merged.append(chunk)
    return merged


def extract_keywords(text: str, top_k: int = 10) -> list[str]:
    """从文本中提取关键词（基于词频）"""
    # 去除 Markdown 格式
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[#*_~>-]", "", text)

    # 分词（中文按字符，英文按空格）
    # 过滤停用词
    STOPWORDS = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
        "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
        "你", "会", "着", "没有", "看", "好", "自己", "这", "那",
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "can", "must",
        "and", "or", "but", "if", "then", "so", "as", "at",
        "in", "on", "for", "to", "of", "with", "by", "from",
    }

    words: list[str] = []
    # 中文（每两个以上连续汉字）
    for w in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if w not in STOPWORDS:
            words.append(w)
    # 英文
    for w in re.findall(r"[a-zA-Z]{3,}", text):
        if w.lower() not in STOPWORDS:
            words.append(w.lower())

    # 词频统计
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1

    # 按频率排序
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w for w, _ in sorted_words[:top_k]]


class ChunkedStore:
    """分块存储管理器

    将 MEMORY.md / SUMMARY.md 的内容分块后存储到 JSONL，
    支持关键词检索和 chunk 重建。
    """

    def __init__(self, storage_dir: "Path | None" = None) -> None:
        self.storage_dir = storage_dir or resolve_userspace_path("memory")
        self.index_path = self.storage_dir / "chunks.jsonl"

    def add_chunks(self, chunks: list[Chunk]) -> int:
        """添加 chunks 到存储，返回添加数量"""
        if not chunks:
            return 0
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with open(self.index_path, "a", encoding="utf-8") as f:
            import json
            for chunk in chunks:
                record = {
                    "text": chunk.text,
                    "chunk_index": chunk.chunk_index,
                    "source_type": chunk.source_type,
                    "source_id": chunk.source_id,
                    "keywords": chunk.keywords,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
        return count

    def search_chunks(
        self,
        query: str,
        top_k: int = 5,
        source_type: str | None = None,
    ) -> list[Chunk]:
        """关键词搜索 chunks"""
        if not self.index_path.exists():
            return []
        import json

        query_keywords = set(w.lower() for w in extract_keywords(query, top_k=15))
        candidates: list[tuple[float, Chunk]] = []

        with open(self.index_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if source_type and rec.get("source_type") != source_type:
                    continue

                chunk_keywords = set(k.lower() for k in rec.get("keywords", []))
                score = len(query_keywords & chunk_keywords) / max(len(query_keywords), 1)

                # 也考虑文本内容中的匹配
                text_lower = rec.get("text", "").lower()
                text_matches = sum(1 for kw in query_keywords if kw in text_lower)
                text_score = text_matches / max(len(query_keywords), 1)
                combined_score = score * 0.6 + text_score * 0.4

                if combined_score > 0:
                    chunk = Chunk(
                        text=rec["text"],
                        chunk_index=rec["chunk_index"],
                        source_type=rec["source_type"],
                        source_id=rec["source_id"],
                        keywords=rec.get("keywords", []),
                        char_start=rec.get("char_start", 0),
                        char_end=rec.get("char_end", 0),
                    )
                    candidates.append((combined_score, chunk))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in candidates[:top_k]]

    def rebuild_index(
        self,
        memory_path: "Path | None" = None,
        summary_path: "Path | None" = None,
    ) -> int:
        """从 MEMORY.md 和 SUMMARY.md 重建 chunks 索引"""
        import json
        from pathlib import Path

        # 清空现有索引
        if self.index_path.exists():
            self.index_path.unlink()

        total = 0

        # 索引 MEMORY.md
        if memory_path and memory_path.exists():
            text = memory_path.read_text(encoding="utf-8")
            chunks = split_into_chunks(text, source_type="memory", source_id=str(memory_path.name))
            total += self.add_chunks(chunks)

        # 索引 SUMMARY.md
        if summary_path and summary_path.exists():
            text = summary_path.read_text(encoding="utf-8")
            chunks = split_into_chunks(text, source_type="summary", source_id=str(summary_path.name))
            total += self.add_chunks(chunks)

        return total
