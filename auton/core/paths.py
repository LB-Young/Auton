"""Filesystem path helpers for Auton userspace resources.

Centralizing the logic keeps the project consistent and enables the AUTON_HOME
environment variable to redirect every ``~/.auton`` access to a sandbox-safe
location (useful for tests or constrained environments).
"""

from __future__ import annotations

import os
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Iterable

AUTON_HOME_ENV = "AUTON_HOME"
_DEFAULT_HOME_DIRNAME = ".auton"


@lru_cache(maxsize=1)
def get_userspace_root() -> Path:
    """Return the root of the Auton userspace directory.

    Priority:
      1. AUTON_HOME environment variable (expanded, created if missing)
      2. ``Path.home() / ".auton"``
    """
    candidate = os.environ.get(AUTON_HOME_ENV)
    if candidate:
        base = Path(candidate).expanduser()
    else:
        base = Path.home() / _DEFAULT_HOME_DIRNAME
    base = _ensure_writable_base(base)
    return base


def _ensure_writable_base(base: Path) -> Path:
    """确保返回的目录可写，否则 fallback 到本地工作区。"""
    try:
        base.mkdir(parents=True, exist_ok=True)
        probe_dir = base / ".auton_probe"
        probe_file = probe_dir / ".write_test"
        probe_dir.mkdir(parents=True, exist_ok=True)
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)  # type: ignore[arg-type]
        probe_dir.rmdir()
        return base
    except OSError as exc:  # Permission denied or read-only home
        fallback = Path.cwd() / f"{_DEFAULT_HOME_DIRNAME}_local"
        if fallback == base:
            raise
        warnings.warn(
            f"Auton userspace fallback to {fallback} (unable to access {base}: {exc})",
            RuntimeWarning,
            stacklevel=2,
        )
        os.environ.setdefault(AUTON_HOME_ENV, str(fallback))
        return _ensure_writable_base(fallback)


def resolve_userspace_path(*parts: str | os.PathLike[str] | Path) -> Path:
    """Build a path under the userspace root."""
    root = get_userspace_root()
    if not parts:
        return root
    converted: Iterable[Path] = (
        Path(str(part)).expanduser()
        for part in parts
    )
    result = root.joinpath(*converted)
    result.parent.mkdir(parents=True, exist_ok=True)
    return result


def expand_auton_path(value: str | os.PathLike[str] | Path) -> Path:
    """Expand a path that may start with ``~/.auton`` using the runtime root.

    Normalises path separators before matching so that Windows paths using
    backslashes (e.g. ``~\\.auton\\memory``) are handled correctly.
    """
    path_str = str(value).replace("\\", "/")
    if path_str.startswith("~/.auton"):
        suffix = path_str[len("~/.auton"):].lstrip("/")
        return resolve_userspace_path(suffix)
    return Path(value).expanduser()
