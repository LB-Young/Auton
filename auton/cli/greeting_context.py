"""启动问候上下文收集。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from ..memory.global_memory import GlobalMemory


@dataclass
class GreetingContext:
    cwd: Path
    today: date
    yesterday: date
    has_project_history: bool
    should_ask_project_mode: bool
    date_memory_snippets: list[str]
    project_memory_snippets: list[str]


def _extract_snippets(markdown: str, limit: int) -> list[str]:
    snippets: list[str] = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        snippets.append(line)
        if len(snippets) >= limit:
            break
    return snippets


def _project_memory_path_from_session_path(storage_dir: Path, session_path: str) -> Path | None:
    """从 projects/*/sessions/*.jsonl 路径反推出 projects/*/memory/MEMORY.md。"""
    try:
        full = Path(session_path).expanduser()
        if not full.is_absolute():
            full = (storage_dir / full).resolve()
    except Exception:
        return None

    full = full.resolve()
    projects_root = (storage_dir / "projects").resolve()
    if projects_root not in full.parents:
        return None

    parts = full.parts
    if "projects" not in parts:
        return None
    idx = parts.index("projects")
    if idx + 1 >= len(parts):
        return None
    project_name = parts[idx + 1]
    return storage_dir / "projects" / project_name / "memory" / "MEMORY.md"


def collect_greeting_context(storage_dir: Path, cwd: Path, has_project_history: bool) -> GreetingContext:
    """收集问候生成所需的本地上下文。"""
    gm = GlobalMemory(storage_dir)
    today = date.today()
    yesterday = today - timedelta(days=1)

    date_memory_snippets: list[str] = []
    for d in [today, yesterday]:
        content = gm.read_memory(d)
        date_memory_snippets.extend(_extract_snippets(content, limit=3))
    date_memory_snippets = date_memory_snippets[:6]

    project_memory_snippets: list[str] = []
    recent_project_session_paths = gm.read_recent_project_session_paths()
    seen_project_memory_paths: set[Path] = set()
    for session_path in recent_project_session_paths:
        memory_path = _project_memory_path_from_session_path(storage_dir, session_path)
        if not memory_path or memory_path in seen_project_memory_paths:
            continue
        seen_project_memory_paths.add(memory_path)
        if memory_path.exists():
            content = memory_path.read_text(encoding="utf-8")
            project_memory_snippets.extend(_extract_snippets(content, limit=2))
    project_memory_snippets = project_memory_snippets[:6]

    return GreetingContext(
        cwd=cwd,
        today=today,
        yesterday=yesterday,
        has_project_history=has_project_history,
        should_ask_project_mode=not has_project_history,
        date_memory_snippets=date_memory_snippets,
        project_memory_snippets=project_memory_snippets,
    )

