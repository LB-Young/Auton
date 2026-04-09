"""Auton Memory — 记忆系统模块

四层记忆：会话 / 项目 / 全局 / 长期。

导出公共接口供 agent 和 commands 使用。
"""

from .auton_md import AutonMDManager
from .chunking import Chunk, ChunkedStore, split_into_chunks, extract_keywords
from .conflict_resolver import ConflictResolver
from .forgetting import (
    compute_decay,
    score_memory,
    score_all_memories,
    run_gc,
    get_forgetting_stats,
    MemoryScore,
)
from .global_memory import GlobalMemory
from .keyword_store import KeywordStore, RetrievalHit
from .memory_manager import MemoryManager, MemoryMode
from .memory_md import MemoryMDManager
from .project_memory import ProjectMemory
from .session_summarizer import SessionSummarizer
from .types import MemoryEntry, MemoryType, RetrievalResult, SummaryBlock

__all__ = [
    # 类型
    "MemoryType",
    "MemoryEntry",
    "SummaryBlock",
    "RetrievalResult",
    "MemoryScore",
    "Chunk",
    "RetrievalHit",
    # 管理器
    "MemoryManager",
    "MemoryMode",
    "ProjectMemory",
    "GlobalMemory",
    "SessionSummarizer",
    "MemoryMDManager",
    "AutonMDManager",
    "ConflictResolver",
    "ChunkedStore",
    "KeywordStore",
    # 工具函数
    "split_into_chunks",
    "extract_keywords",
    "compute_decay",
    "score_memory",
    "score_all_memories",
    "run_gc",
    "get_forgetting_stats",
]
