"""POSIX descriptor-relative file confinement; never follows path symlinks."""

import fcntl
import hashlib
import json
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from auton.tools.config import ToolConfig
from auton.tools.contracts import LocalDirectories, ToolWorkspace
from auton.tools.ports import ToolError


def components(path: str) -> tuple[str, ...]:
    parts = tuple(path.split("/"))
    if (
        "\\" in path
        or "\0" in path
        or path.startswith("/")
        or ":" in path
        or any(not part or part.startswith(".") for part in parts)
        or len(parts) > 16
    ):
        raise ToolError(
            "path_denied", "Only non-hidden relative paths in this workspace are allowed"
        )
    return parts


class FileSandbox:
    def __init__(self, config: ToolConfig) -> None:
        self.config = config

    def path(self, workspace: ToolWorkspace) -> Path:
        if workspace.root_path:
            return Path(workspace.root_path)
        return (
            self.config.directory
            / "workspaces"
            / hashlib.sha256(workspace.owner.encode()).hexdigest()
            / workspace.id
        )

    @staticmethod
    def selected_directory(path: str) -> tuple[str, int, int]:
        value = Path(path).expanduser()
        if not value.is_absolute():
            raise ToolError("project_path_invalid", "请输入本机项目目录的绝对路径")
        try:
            root = value.resolve(strict=True)
            if root == Path(root.anchor) or any(p.startswith(".") for p in root.parts[1:]):
                raise ToolError(
                    "project_path_denied", "请选择项目目录，不能选择文件系统根目录或隐藏目录"
                )
            descriptor = FileSandbox.open_directory(root)
            try:
                info = os.fstat(descriptor)
                return str(root), info.st_dev, info.st_ino
            finally:
                os.close(descriptor)
        except OSError as error:
            raise ToolError(
                "project_path_invalid", "目录不存在、不是文件夹或没有访问权限"
            ) from error

    @staticmethod
    def open_directory(root: Path) -> int:
        if not root.is_absolute() or len(root.parts) > 64:
            raise ToolError("project_path_invalid", "项目目录路径无效")
        descriptor = os.open(root.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for segment in root.parts[1:]:
                child = os.open(
                    segment, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
                )
                os.close(descriptor)
                descriptor = child
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    @staticmethod
    def browse_directories(path: str | None) -> LocalDirectories:
        try:
            root = Path(path).expanduser().resolve(strict=True) if path else Path.home().resolve()
            if any(p.startswith(".") for p in root.parts[1:]):
                raise ToolError("project_path_denied", "不能浏览隐藏目录")
            descriptor = FileSandbox.open_directory(root)
            try:
                names: list[str] = []
                scanned = 0
                with os.scandir(descriptor) as entries:
                    for entry in entries:
                        scanned += 1
                        if scanned > 1000:
                            break
                        if not entry.name.startswith(".") and entry.is_dir(follow_symlinks=False):
                            names.append(entry.name)
                return LocalDirectories(
                    path=str(root),
                    parent=str(root.parent) if root.parent != root else None,
                    directories=tuple(sorted(names)),
                    truncated=scanned > 1000,
                )
            finally:
                os.close(descriptor)
        except OSError as error:
            raise ToolError(
                "project_path_invalid", "无法浏览该目录，请检查路径或访问权限"
            ) from error

    @staticmethod
    def control_workspace(workspace: ToolWorkspace) -> ToolWorkspace:
        return workspace.model_copy(
            update={"root_path": None, "root_device": None, "root_inode": None}
        )

    @contextmanager
    def parent(
        self, workspace: ToolWorkspace, path: str, *, create: bool = False
    ) -> Iterator[tuple[int, str]]:
        parts = components(path)
        if workspace.root_path:
            try:
                descriptor = self.open_directory(Path(workspace.root_path))
            except OSError as error:
                raise ToolError(
                    "project_path_unavailable", "绑定的项目目录已移动或无法访问"
                ) from error
            info = os.fstat(descriptor)
            if (info.st_dev, info.st_ino) != (workspace.root_device, workspace.root_inode):
                os.close(descriptor)
                raise ToolError(
                    "project_path_changed", "项目目录已被替换，请重新选择目录开启新对话"
                )
            segments = parts[:-1]
        else:
            base = self.config.directory
            if create:
                base.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            segments = (
                "workspaces",
                hashlib.sha256(workspace.owner.encode()).hexdigest(),
                workspace.id,
                *parts[:-1],
            )
        try:
            for segment in segments:
                if create:
                    try:
                        os.mkdir(segment, mode=0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                child = os.open(
                    segment, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
                )
                os.close(descriptor)
                descriptor = child
            yield descriptor, parts[-1]
        except FileNotFoundError:
            raise
        except OSError as error:
            raise ToolError(
                "path_denied", "Path is inaccessible or contains an unsupported link"
            ) from error
        finally:
            os.close(descriptor)

    def initialize(self, workspace: ToolWorkspace) -> None:
        # Locks remain in Auton's private metadata, never added to the chosen project.
        control = self.control_workspace(workspace)
        with self.parent(control, "placeholder", create=True) as (directory, _):
            descriptor = os.open(
                ".auton-lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=directory
            )
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ToolError("path_denied", "Workspace lock is not an ordinary file")
            finally:
                os.close(descriptor)
        if workspace.root_path:
            with self.parent(workspace, "placeholder"):
                pass

    def list_files(self, workspace: ToolWorkspace, path: str) -> str:
        try:
            return self._list_files(workspace, path)
        except FileNotFoundError:
            raise ToolError("directory_not_found", "项目中不存在这个目录") from None

    def _list_files(self, workspace: ToolWorkspace, path: str) -> str:
        relative = path + "/placeholder" if path not in {"", "."} else "placeholder"
        with self.parent(workspace, relative) as (directory, _):
            values = []
            scanned = 0
            with os.scandir(directory) as entries:
                for entry in entries:
                    scanned += 1
                    if scanned > 1000:
                        break
                    if entry.name.startswith(".") or entry.name in {
                        "node_modules",
                        "__pycache__",
                        "dist",
                        "build",
                    }:
                        continue
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        values.append({"name": entry.name, "kind": "directory"})
                    elif entry.is_file(follow_symlinks=False):
                        values.append({"name": entry.name, "kind": "file"})
            values.sort(key=lambda entry: (entry["kind"] != "directory", entry["name"]))
            truncated = scanned > 1000 or len(values) > 100
            values = values[:100]
            while True:
                text = json.dumps(
                    {"path": path, "entries": values, "truncated": truncated}, ensure_ascii=False
                )
                if len(text.encode()) <= self.config.max_output_bytes:
                    return text
                values.pop()
                truncated = True

    def read(
        self, workspace: ToolWorkspace, path: str, *, missing_ok: bool = False
    ) -> bytes | None:
        try:
            return self._read(workspace, path, missing_ok=missing_ok)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise ToolError("file_not_found", "File does not exist") from None

    def _read(
        self, workspace: ToolWorkspace, path: str, *, missing_ok: bool = False
    ) -> bytes | None:
        with self.parent(workspace, path) as (directory, name):
            try:
                descriptor = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
                )
            except FileNotFoundError:
                if missing_ok:
                    return None
                raise ToolError("file_not_found", "File does not exist") from None
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ToolError(
                        "path_denied", "Only ordinary non-hardlinked files are supported"
                    )
                with os.fdopen(descriptor, "rb", closefd=False) as handle:
                    data = handle.read(self.config.max_file_bytes + 1)
                if len(data) > self.config.max_file_bytes:
                    raise ToolError("file_too_large", "File exceeds the configured byte limit")
                return data
            finally:
                os.close(descriptor)

    def write(
        self,
        workspace: ToolWorkspace,
        path: str,
        content: bytes,
        expected_sha256: str | None,
        operation_key: str,
    ) -> tuple[str, int]:
        if self.config.read_only or workspace.read_only:
            raise ToolError("read_only", "This workspace is read-only")
        with self.parent(self.control_workspace(workspace), "placeholder") as (directory, _):
            lock = os.open(
                ".auton-lock",
                os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
                dir_fd=directory,
            )
            try:
                info = os.fstat(lock)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ToolError("path_denied", "Workspace lock is not an ordinary file")
                fcntl.flock(lock, fcntl.LOCK_EX)
                return self._write(workspace, path, content, expected_sha256, operation_key)
            finally:
                os.close(lock)

    def _write(
        self,
        workspace: ToolWorkspace,
        path: str,
        content: bytes,
        expected_sha256: str | None,
        operation_key: str,
    ) -> tuple[str, int]:
        if self.config.read_only or workspace.read_only:
            raise ToolError("read_only", "This workspace is read-only")
        if len(content) > self.config.max_file_bytes:
            raise ToolError("file_too_large", "Content exceeds the configured byte limit")
        before = self.read(workspace, path, missing_ok=True)
        actual = hashlib.sha256(before).hexdigest() if before is not None else None
        if actual != expected_sha256:
            raise ToolError("file_changed", "File changed; review a new plan before writing")
        with self.parent(workspace, path, create=True) as (directory, name):
            temporary = ".auton-write-" + operation_key
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            renamed = False
            try:
                if workspace.root_path and before is not None:
                    mode = os.stat(name, dir_fd=directory, follow_symlinks=False).st_mode & 0o777
                    os.fchmod(descriptor, mode)
                with os.fdopen(descriptor, "wb", closefd=False) as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(descriptor)
                # Recheck after preparing bytes, before atomic replacement. Cooperative
                # writers are serialized by the host; no claim of hostile OS-user isolation.
                current = self.read(workspace, path, missing_ok=True)
                if (
                    hashlib.sha256(current).hexdigest() if current is not None else None
                ) != expected_sha256:
                    raise ToolError("file_changed", "File changed during preparation")
                os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
                renamed = True
                os.fsync(directory)
            except OSError as error:
                raise ToolError(
                    "file_write_failed", "File write could not be confirmed", uncertain=renamed
                ) from error
            finally:
                os.close(descriptor)
                if not renamed:
                    try:
                        os.unlink(temporary, dir_fd=directory)
                    except FileNotFoundError:
                        pass
        return hashlib.sha256(content).hexdigest(), len(content)


class SandboxFactory:
    def create(self, config: ToolConfig) -> FileSandbox:
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
            raise ValueError("This file sandbox currently requires POSIX descriptor operations")
        return FileSandbox(config)
