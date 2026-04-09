"""Storage path helpers for memory/session data."""

from __future__ import annotations

import re
from pathlib import Path


def _sanitize_path_string(path: str) -> str:
    """Convert an absolute path into Claude-style folder names."""
    sanitized = path.replace("\\", "-").replace("/", "-")
    sanitized = sanitized.replace(":", "-")
    # Replace all other unsupported characters (e.g. spaces, CJK) with '-'
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "-", sanitized)
    sanitized = sanitized.strip()
    return sanitized or "project"


def project_storage_dir_name(project_root: Path) -> str:
    """Return ``sanitized_absolute_path`` for the given project root path."""
    resolved = Path(project_root).expanduser().resolve(strict=False)
    return _sanitize_path_string(resolved.as_posix())


def project_storage_base(storage_dir: Path, project_root: Path) -> Path:
    """Compute storage_dir/projects/<sanitized_absolute_path>."""
    return Path(storage_dir) / "projects" / project_storage_dir_name(project_root)
