"""auton/compress — 独立实时会话压缩组件

完全独立于主 agent / subagent 体系。

用法：
    from auton.compress import StandaloneCompressor, CompressConfig
    compressor = StandaloneCompressor(llm=llm_provider, config=CompressConfig())
    compressed = await compressor.compress(messages, session_id="xxx")
"""

from .boundary import (
    CompressBoundary,
    compute_compress_boundary,
    should_compress,
    ABSOLUTE_TOKEN_THRESHOLD,
    DEFAULT_THRESHOLD_PERCENT,
)
from .compressor import StandaloneCompressor
from .config import CompressConfig
from .parser import parse_compact_summary
from .prompts import (
    COMPACT_SYSTEM_PROMPT,
    get_base_compact_prompt,
    get_incremental_compact_prompt,
)
from .pruner import prune_tool_results, TOOL_OUTPUT_PLACEHOLDER
from .sanitizer import sanitize_tool_pairs

__all__ = [
    "CompressConfig",
    "CompressBoundary",
    "compute_compress_boundary",
    "should_compress",
    "ABSOLUTE_TOKEN_THRESHOLD",
    "DEFAULT_THRESHOLD_PERCENT",
    "StandaloneCompressor",
    "parse_compact_summary",
    "COMPACT_SYSTEM_PROMPT",
    "get_base_compact_prompt",
    "get_incremental_compact_prompt",
    "prune_tool_results",
    "TOOL_OUTPUT_PLACEHOLDER",
    "sanitize_tool_pairs",
]
