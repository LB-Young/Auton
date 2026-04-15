"""Auton Memory — 记忆系统模块

四层记忆：会话 / 项目 / 全局 / 长期。

导出公共接口供 agent 和 commands 使用。
"""

from .auton_md import AutonMDManager
from .chunking import Chunk, ChunkedStore, split_into_chunks, extract_keywords
from .compression_improver import (
    CompressionImprover,
    QualityReport,
    SummaryQualityAnalyzer,
)
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
from .memory_read_hook import MemoryReadHook
from .msg_id_assigner import MsgBlock, MsgIdAssigner
from .project_memory import ProjectMemory
from .retrieval_analytics import RetrievalAnalytics, RetrievalRecord
from .session_summarizer import SessionSummarizer
from .summary_parser import SummaryEntry, parse_summary_for_analytics
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
    # 检索质量分析（summary 自优化）
    "RetrievalAnalytics",
    "RetrievalRecord",
    "QualityReport",
    "SummaryQualityAnalyzer",
    "CompressionImprover",
    "MemoryReadHook",
    "MsgBlock",
    "MsgIdAssigner",
    "SummaryEntry",
    "parse_summary_for_analytics",
    # 工具函数
    "split_into_chunks",
    "extract_keywords",
    "compute_decay",
    "score_memory",
    "score_all_memories",
    "run_gc",
    "get_forgetting_stats",
]
