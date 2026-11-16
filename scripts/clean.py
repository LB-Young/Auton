# coding: utf-8
"""Clean reproducible outputs and empty directories below this repository only.

Never follow symlinks, remove tracked files, or enter Git/dependency environments.
Empty source files are not temporary outputs and are deliberately kept.
"""

import argparse
import errno
import os
from pathlib import Path
import subprocess


PROTECTED = {".git", ".venv", "venv", "env", "node_modules", ".agents", ".codex", ".aws"}
CACHES = {
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".hypothesis", ".tox", ".nox", ".vite", ".cache",
}
# Only these locations are assumed to be build output; a source folder named
# "build" elsewhere is not automatically disposable.
BUILD_PATHS = {"build", "dist", "htmlcov", "clients/web/dist", "clients/web/coverage"}


def category(relative):
    if any(part in CACHES for part in relative.parts):
        return "cache"
    if any(part.endswith(".egg-info") for part in relative.parts):
        return "build"
    if any(parent.as_posix() in BUILD_PATHS for parent in (relative, *relative.parents)):
        return "build"
    if relative.suffix in {".pyc", ".pyo"} or relative.name == ".coverage":
        return "cache"
    if relative.name.endswith(".tsbuildinfo"):
        return "build"
    return None


def tracked_files(root):
    if not (root / ".git").exists():
        return set()
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True, stdout=subprocess.PIPE,
    )
    return {os.fsdecode(name) for name in result.stdout.split(b"\0") if name}


def plan(root, scope):
    tracked = tracked_files(root)
    files, directories = [], []
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(current)
        dirnames[:] = sorted(
            name for name in dirnames
            if name not in PROTECTED and not (current / name).is_symlink()
        )
        directories.append(current)
        for name in sorted(filenames):
            path = current / name
            relative = path.relative_to(root)
            if name in PROTECTED or path.is_symlink() or relative.as_posix() in tracked:
                continue
            kind = category(relative)
            if kind and scope in {"all", kind}:
                files.append(path)

    # Simulate bottom-up removal so preview includes parents that will become
    # empty after their children or cache files are removed.
    removed = set(files)
    empty = []
    for path in reversed(directories):
        if path == root:
            continue
        if scope not in {"all", "empty"} and category(path.relative_to(root)) != scope:
            continue
        if all(child in removed for child in path.iterdir()):
            empty.append(path)
            removed.add(path)
    return files, empty


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("all", "cache", "build", "empty"), default="all")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    files, directories = plan(root, args.scope)
    if args.dry_run:
        print(f"Preview: {len(files)} generated files, {len(directories)} empty directories.")
        print(f"Root: {root}")
        return
    deleted_files = deleted_dirs = 0
    for path in files:
        try:
            path.unlink()
            deleted_files += 1
        except FileNotFoundError:
            pass
    for path in directories:
        try:
            path.rmdir()
            deleted_dirs += 1
        except OSError as error:
            # A concurrent writer may have populated the directory; leave it.
            if error.errno not in {errno.ENOENT, errno.ENOTEMPTY, errno.EEXIST}:
                raise
    print(f"Removed: {deleted_files} generated files, {deleted_dirs} empty directories.")


if __name__ == "__main__":
    main()
