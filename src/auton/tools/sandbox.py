"""POSIX descriptor-relative file confinement; never follows path symlinks."""

import fcntl
import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from auton.tools.config import ToolConfig
from auton.tools.contracts import ToolWorkspace
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
        return (
            self.config.directory
            / "workspaces"
            / hashlib.sha256(workspace.owner.encode()).hexdigest()
            / workspace.id
        )

    @contextmanager
    def parent(
        self, workspace: ToolWorkspace, path: str, *, create: bool = False
    ) -> Iterator[tuple[int, str]]:
        parts = components(path)
        # The configured base is trusted; all owner/workspace/path components are opened
        # relative to descriptors with O_NOFOLLOW. Root is never obtained from model input.
        base = self.config.directory
        if create:
            base.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            segments = (
                "workspaces",
                hashlib.sha256(workspace.owner.encode()).hexdigest(),
                workspace.id,
                *parts[:-1],
            )
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
        with self.parent(workspace, "placeholder", create=True) as (directory, _):
            descriptor = os.open(
                ".auton-lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=directory
            )
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ToolError("path_denied", "Workspace lock is not an ordinary file")
            finally:
                os.close(descriptor)

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
        with self.parent(workspace, "placeholder") as (directory, _):
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
