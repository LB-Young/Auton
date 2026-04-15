"""Bash Sandbox — 沙箱隔离

7 层安全校验第 5 层：
  - Linux: unshare + chroot 到只读根文件系统
  - macOS: sandbox-exec 配置文件

仅在 security.sandbox_enabled=True 时启用。
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class SandboxConfig:
    """沙箱配置"""
    enabled: bool = True
    workspace_dir: Path | None = None  # None = 使用系统临时目录
    allow_network: bool = True          # 是否允许网络访问
    read_only_paths: list[str] = field(default_factory=list)  # 只读挂载路径列表


@dataclass
class SandboxResult:
    """沙箱执行结果"""
    success: bool
    command: str
    stdout: str
    stderr: str
    returncode: int
    sandboxed: bool
    reason: str = ""


def get_sandbox_exec_cmd(command: str, config: SandboxConfig) -> list[str]:
    """生成带沙箱的命令前缀（Linux）"""
    cmds: list[str] = []

    # unshare: 创建新命名空间
    # -r: 使用新的 root（需 root 权限，非 root 下仅网络隔离）
    # -n: 新网络命名空间
    # -p: 新 PID 命名空间
    unshare_cmds = ["unshare"]

    if not config.allow_network:
        unshare_cmds.append("--net")

    # 新用户命名空间（允许非 root 映射）
    unshare_cmds.extend(["--user", "--map-root-user"])

    cmds.extend(unshare_cmds)

    # chroot 到只读最小系统（如果有）
    # 默认使用 /usr/sbin/chroot /path/to/jail /bin/sh -c "command"

    return cmds


# ─── macOS Sandbox Profile ───────────────────────────────────────────────────

# 默认允许的可写路径（临时目录、用户目录）
DEFAULT_ALLOW_WRITE_PATHS = [
    "/tmp/",
    "/var/tmp/",
    "/Users/",  # 用户 home
]

# 危险路径（绝对禁止）
DENY_WRITE_PATHS = [
    "/System/",
    "/etc/",
    "/usr/libexec/",
    "/bin/",
    "/sbin/",
    "/usr/sbin/",
]


def _build_macos_profile(workspace_dir: str | None = None) -> str:
    """构建 macOS 沙箱配置"""
    deny_rules = "\n".join(
        f'(deny file-write*\n  (regex #"^{path}"))' for path in DENY_WRITE_PATHS
    )

    # 可写路径：临时目录 + workspace
    writable_paths = DEFAULT_ALLOW_WRITE_PATHS.copy()
    if workspace_dir:
        # 确保 workspace 路径以 / 结尾
        wpath = workspace_dir.rstrip("/") + "/"
        if wpath not in writable_paths:
            writable_paths.append(wpath)

    allow_write_rules = "\n".join(
        f'(allow file-write*\n  (regex #"^{path}"))' for path in writable_paths
    )

    return f"""(name "auton-agent")
(version 1)
(allow default)

{deny_rules}

{allow_write_rules}

(allow file-read*
  (regex #"^/"))

(allow process-exec
  (regex #"^/bin/|/usr/bin/|/usr/local/bin/"))

(allow network*
  (regex #"^tcp://|:\\d{{4}}/"))

(allow ipc-posix-shm-read*
  (regex #""))

(allow mach-lookup
  (regex #"^com.apple\\."))
"""


MACOS_SANDBOX_PROFILE = _build_macos_profile()


# ─── macOS sandbox-exec ─────────────────────────────────────────────────────

def run_with_macos_sandbox(command: str, config: SandboxConfig) -> SandboxResult:
    """使用 macOS sandbox-exec 执行命令"""
    import tempfile

    # 构建沙箱配置（包含 workspace 可写路径）
    profile = _build_macos_profile(
        workspace_dir=str(config.workspace_dir) if config.workspace_dir else None
    )

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".sb",
        delete=False,
    ) as f:
        f.write(profile)
        profile_path = f.name

    try:
        result = subprocess.run(
            ["sandbox-exec", "-f", profile_path] + command,
            capture_output=True,
            text=True,
            timeout=config.workspace_dir and 60 or 30,
        )
        return SandboxResult(
            success=(result.returncode == 0),
            command=" ".join(command),
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            sandboxed=True,
        )
    except FileNotFoundError:
        return SandboxResult(
            success=False,
            command=" ".join(command),
            stdout="",
            stderr="sandbox-exec not available on this system",
            returncode=-1,
            sandboxed=False,
            reason="sandbox-exec not found",
        )
    finally:
        os.unlink(profile_path)


# ─── Linux seccomp / bubblewrap ──────────────────────────────────────────────

def run_with_linux_sandbox(command: str, config: SandboxConfig) -> SandboxResult:
    """使用 Linux 沙箱（bubblewrap 或 unshare）执行命令"""
    bwrap = shutil.which("bwrap")
    if bwrap:
        args = [
            bwrap,
            "--ro-bind", "/", "/",
            "--tmpfs", "/tmp",
            "--dev", "/dev",
            # 允许网络
            *(["--unshare-net"] if not config.allow_network else []),
            "--",
        ]
        args.extend(command)
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return SandboxResult(
                success=(result.returncode == 0),
                command=" ".join(command),
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
                sandboxed=True,
            )
        except FileNotFoundError:
            pass

    # fallback: unshare
    if os.geteuid() == 0:
        result = subprocess.run(
            ["unshare", "--user"] + command,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return SandboxResult(
            success=(result.returncode == 0),
            command=" ".join(command),
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            sandboxed=True,
        )

    return SandboxResult(
        success=False,
        command=" ".join(command),
        stdout="",
        stderr="No sandboxing mechanism available (requires root or bwrap)",
        returncode=-1,
        sandboxed=False,
        reason="root or bwrap required for sandboxing",
    )


# ─── 主入口 ─────────────────────────────────────────────────────────────────

def get_sandbox_config(**kwargs) -> SandboxConfig:
    """从配置字典创建沙箱配置"""
    defaults = SandboxConfig()
    for key, value in kwargs.items():
        if hasattr(defaults, key):
            setattr(defaults, key, value)
    return defaults


def run_sandboxed(command: str | list[str], config: SandboxConfig | None = None) -> SandboxResult:
    """在沙箱中执行命令"""
    if isinstance(command, str):
        import shlex
        cmd_list = shlex.split(command)
    else:
        cmd_list = command

    if config is None:
        config = SandboxConfig()

    if not config.enabled:
        return SandboxResult(
            success=False,
            command=" ".join(cmd_list),
            stdout="",
            stderr="Sandbox disabled",
            returncode=-1,
            sandboxed=False,
            reason="sandbox disabled",
        )

    system = platform.system()
    if system == "Darwin":
        return run_with_macos_sandbox(cmd_list, config)
    elif system == "Linux":
        return run_with_linux_sandbox(cmd_list, config)
    else:
        return SandboxResult(
            success=False,
            command=" ".join(cmd_list),
            stdout="",
            stderr=f"Sandbox not supported on {system}",
            returncode=-1,
            sandboxed=False,
            reason=f"Sandbox not supported on {system}",
        )
