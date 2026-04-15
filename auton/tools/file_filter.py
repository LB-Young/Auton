"""tools/file_filter.py — 工具层文件类型过滤

供 ReadTool、GrepTool、GlobTool 共用，防止 LLM 读取：
  1. 二进制 / 编译产物文件（.pyc、.so、图片、压缩包等）
  2. 高噪声目录（__pycache__、.git、node_modules、.auton/memory 等）

这两类文件进入上下文只会消耗 token 且无任何意义。
"""

from __future__ import annotations

from pathlib import Path


# ─── 二进制 / 无意义扩展名 ────────────────────────────────────────────────────
#
# 凡在此集合中的扩展名，ReadTool 和 GrepTool 均拒绝读取。
# 扩展名统一使用小写（匹配时 lower() 后比较）。

BINARY_EXTENSIONS: frozenset[str] = frozenset({
    # Python 编译产物
    ".pyc", ".pyo", ".pyd",
    # C/C++ 编译产物
    ".so", ".a", ".o", ".dylib", ".dll", ".lib", ".exe",
    # Java / JVM
    ".class", ".jar", ".war", ".ear",
    # 图片
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif",
    ".ico", ".svg", ".heic", ".avif",
    # 音视频
    ".mp3", ".mp4", ".wav", ".ogg", ".flac", ".m4a",
    ".mkv", ".avi", ".mov", ".webm",
    # 压缩包
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".whl", ".egg",
    # 数据库 / 二进制数据
    ".db", ".sqlite", ".sqlite3", ".pkl", ".pickle",
    ".npy", ".npz", ".parquet", ".arrow", ".feather",
    ".bin", ".dat",
    # 字体
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    # PDF / Office
    ".pdf", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt",
    # 其他
    ".DS_Store", ".lock",
})

# ─── 高噪声目录名 ─────────────────────────────────────────────────────────────
#
# 路径中包含这些目录名（任何层级）的文件，GrepTool / GlobTool 会跳过。
# ReadTool 不过滤目录（允许用户主动读取），但会通过扩展名过滤。

NOISY_DIRS: frozenset[str] = frozenset({
    # Python
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", "dist", "build", "*.egg-info",
    # JS / Node
    "node_modules", ".next", ".nuxt", "dist", ".turbo",
    # VCS
    ".git", ".hg", ".svn",
    # IDE
    ".idea", ".vscode", ".cursor",
    # 虚拟环境
    "venv", ".venv", "env", ".env", "site-packages",
    # Auton 自身运行时数据（含 session logs、向量数据库等）
    "memory", "sessions",        # ~/.auton/memory/projects/*/sessions/
    "chroma_db", "vector_db",
    # 系统
    ".Trash", ".DS_Store",
})


def is_binary_path(path: Path) -> bool:
    """判断文件路径是否为二进制/无意义文件（仅按扩展名）。

    不做文件读取，仅检查扩展名，速度快、无 I/O。
    """
    return path.suffix.lower() in BINARY_EXTENSIONS


def is_noisy_path(path: Path) -> bool:
    """判断文件路径是否在高噪声目录中（按路径各部分判断）。

    检查路径的每一级目录名是否在 NOISY_DIRS 中。
    """
    parts = set(path.parts)
    return bool(parts & NOISY_DIRS)


def should_skip_for_read(path: Path) -> tuple[bool, str]:
    """ReadTool 用：判断是否应该拒绝读取此文件。

    Returns:
        (should_skip, reason): should_skip=True 时附带拒绝原因
    """
    if is_binary_path(path):
        return True, (
            f"拒绝读取二进制/编译文件 `{path.name}`（扩展名 `{path.suffix}`）。"
            "请检查是否读取了错误的文件路径。"
        )
    return False, ""


def should_skip_for_search(path: Path) -> bool:
    """GrepTool / GlobTool 用：判断是否应该在搜索中跳过此文件。

    同时检查二进制扩展名和高噪声目录，两者满足其一即跳过。
    """
    return is_binary_path(path) or is_noisy_path(path)


def binary_sniff(path: Path, sample_bytes: int = 512) -> bool:
    """通过读取文件头部字节判断是否为二进制文件（扩展名未知时使用）。

    检测逻辑：如果前 sample_bytes 字节中含有 NULL 字节，则视为二进制。
    """
    try:
        chunk = path.read_bytes()[:sample_bytes]
        return b"\x00" in chunk
    except OSError:
        return False
