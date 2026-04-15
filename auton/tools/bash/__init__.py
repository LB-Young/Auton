"""Bash Tool — 执行 Shell 命令（7 层安全校验）

7 层安全防线：
  Layer 1: 读写语义分类（read-only / write / destructive）
  Layer 2: 路径安全校验（path_traversal / unicode normalization）
  Layer 3: 危险命令过滤（rm -rf / curl|sh 等黑名单）
  Layer 4: 超时限制（防止资源耗尽）
  Layer 5: 沙箱隔离（macOS sandbox-exec / Linux bwrap）
  Layer 6: 输出截断（防止内存溢出）
  Layer 7: 审计日志（所有调用不可绕过）
"""

from __future__ import annotations

import asyncio
import os
import platform
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from ..base import Tool, ToolResult
from ...security.permission import PermissionManager, PermissionMode
from ...core.paths import resolve_userspace_path

from .path_validator import validate_command_paths, check_null_byte, normalize_path
from .sandbox import SandboxConfig, get_sandbox_config, run_sandboxed
from . import security

if TYPE_CHECKING:
    pass


# ─── 输出截断 ───────────────────────────────────────────────────────────────

MAX_OUTPUT_BYTES = 1024 * 1024  # 1MB


def truncate_output(output: str, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
    """截断输出到指定字节数"""
    encoded = output.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return output
    truncated = encoded[:max_bytes].decode("utf-8", errors="replace")
    return truncated + f"\n[output truncated at {max_bytes} bytes]"


# ─── 审计日志 ───────────────────────────────────────────────────────────────

AUDIT_LOG_PATH = resolve_userspace_path("logs", "commands.log")


def write_audit_log(
    session_id: str,
    command: str,
    category: str,
    allowed: bool,
    sandboxed: bool,
    result: str,
    returncode: int | None,
    duration_ms: float,
) -> None:
    """写入审计日志（第 7 层，不可绕过）"""
    import json

    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": time.time(),
        "session_id": session_id,
        "command": command,
        "category": category,
        "allowed": allowed,
        "sandboxed": sandboxed,
        "returncode": returncode,
        "duration_ms": round(duration_ms, 2),
        "result_preview": result[:200] if result else "",
        "platform": platform.system(),
    }

    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ─── BashTool ───────────────────────────────────────────────────────────────

@dataclass
class BashCheckResult:
    """Bash 命令检查结果"""
    allowed: bool
    reason: str
    category: str = "unknown"
    requires_confirmation: bool = False


class BashTool(Tool):
    """Bash 工具 — 7 层安全校验"""

    name = "bash"
    description = "Execute a shell command in the project directory"

    def __init__(
        self,
        timeout: int = 60,
        permission_mode: str = "default",
        sandbox_enabled: bool = True,
        session_id: str | None = None,
        permission_manager: PermissionManager | None = None,
        yes_all: bool = False,
    ) -> None:
        self.timeout = timeout
        self.permission_mode = permission_mode
        self.sandbox_enabled = sandbox_enabled
        self.session_id = session_id or str(uuid.uuid4())
        self._permission_manager = permission_manager or PermissionManager(mode=permission_mode, yes_all=yes_all)
        self._logger = logger.bind(name="BashTool")

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (defaults to project root)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds",
                },
            },
            "required": ["command"],
        }

    # ─── 7 层安全校验 ─────────────────────────────────────────────────────

    def _check_command(self, command: str) -> BashCheckResult:
        """执行 7 层安全检查，返回检查结果"""
        # Layer 3: 危险命令过滤（最先执行，零容忍）
        if security.check_dangerous(command):
            return BashCheckResult(
                allowed=False,
                reason="Command matches dangerous pattern blacklist",
                category="destructive",
            )

        # Layer 3: 危险确认命令
        if security.check_requires_confirmation(command):
            sec_result = security.security_check(command)
            return BashCheckResult(
                allowed=True,
                reason=sec_result.reason,
                category=sec_result.category.value,
                requires_confirmation=True,
            )

        # Layer 2: 路径安全校验
        all_allowed, path_results = validate_command_paths(command)
        if not all_allowed:
            denied = next(r for r in path_results if not r.allowed)
            return BashCheckResult(
                allowed=False,
                reason=f"Path validation failed: {denied.reason}",
                category="destructive",
            )

        # Layer 1: 读写语义分类
        sec_result = security.security_check(command)
        return BashCheckResult(
            allowed=True,
            reason=sec_result.reason,
            category=sec_result.category.value,
            requires_confirmation=sec_result.requires_confirmation,
        )

    async def execute(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int | None = None,
    ) -> ToolResult:
        """执行带 7 层安全校验的 Bash 命令"""
        start_time = time.time()

        # 归一化命令
        normalized = normalize_path(command)
        exec_timeout = timeout or self.timeout

        # Layer 4: 超时保护（防止资源耗尽）
        if exec_timeout > self.timeout:
            exec_timeout = min(exec_timeout, self.timeout)

        # 7 层安全检查
        check_result = self._check_command(normalized)

        # ── 权限层检查（permission mode）─────────────────────────────────
        perm_result = self._permission_manager.check(
            command=command,
            category=check_result.category,
        )

        if not perm_result.allowed:
            duration_ms = (time.time() - start_time) * 1000
            write_audit_log(
                session_id=self.session_id,
                command=command,
                category=check_result.category,
                allowed=False,
                sandboxed=False,
                result=perm_result.reason,
                returncode=None,
                duration_ms=duration_ms,
            )
            self._logger.warning(
                "command blocked by permission manager: {reason}",
                reason=perm_result.reason,
            )
            return ToolResult(
                content=f"[blocked] {perm_result.reason}",
                success=False,
                error=f"permission: {perm_result.reason}",
            )

        # 需要交互确认（default 模式下的 destructive/write 操作）
        if perm_result.requires_input:
            confirmed = await self._permission_manager.ask_confirmation(
                command=command,
                reason=perm_result.reason,
            )
            if not confirmed:
                duration_ms = (time.time() - start_time) * 1000
                write_audit_log(
                    session_id=self.session_id,
                    command=command,
                    category=check_result.category,
                    allowed=False,
                    sandboxed=False,
                    result="user denied",
                    returncode=None,
                    duration_ms=duration_ms,
                )
                return ToolResult(
                    content="[denied] user declined to confirm",
                    success=False,
                    error="user denied",
                )

        # ── 7 层安全校验 — Layer 1-3 结果判断 ──────────────────────────
        if not check_result.allowed:
            duration_ms = (time.time() - start_time) * 1000
            write_audit_log(
                session_id=self.session_id,
                command=command,
                category=check_result.category,
                allowed=False,
                sandboxed=False,
                result=check_result.reason,
                returncode=None,
                duration_ms=duration_ms,
            )
            self._logger.warning(
                "command blocked by security check: {reason}",
                reason=check_result.reason,
            )
            return ToolResult(
                content=f"[blocked] {check_result.reason}",
                success=False,
                error=f"security: {check_result.reason}",
            )

        # 沙箱执行（Layer 5）
        sandboxed = False
        sandbox_result = None
        if self.sandbox_enabled:
            config = get_sandbox_config(
                enabled=True,
                workspace_dir=Path(cwd) if cwd else None,
                allow_network=True,
            )
            sandbox_result = run_sandboxed(
                ["bash", "-c", command],
                config,
            )
            sandboxed = sandbox_result.sandboxed

        # 直接执行（非沙箱路径）
        if sandbox_result is None or not sandbox_result.sandboxed:
            try:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    cwd=cwd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=exec_timeout
                    )
                    output = (
                        stdout.decode("utf-8", errors="replace")
                        + ("\n[stderr]\n" + stderr.decode("utf-8", errors="replace") if stderr else "")
                    )
                    returncode = proc.returncode
                    sandboxed = False
                except asyncio.TimeoutError:
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        proc.kill()
                    output = f"[timeout after {exec_timeout}s]"
                    returncode = -1
            except Exception as exc:
                output = str(exc)
                returncode = -1
        else:
            # 沙箱路径
            output = sandbox_result.stdout + (
                "\n[stderr]\n" + sandbox_result.stderr if sandbox_result.stderr else ""
            )
            returncode = sandbox_result.returncode
            if not sandbox_result.success:
                output += f"\n[sandbox exit: {returncode}]"

        # Layer 6: 输出截断
        output = truncate_output(output, MAX_OUTPUT_BYTES)

        duration_ms = (time.time() - start_time) * 1000

        # Layer 7: 审计日志（不可绕过）
        write_audit_log(
            session_id=self.session_id,
            command=command,
            category=check_result.category,
            allowed=True,
            sandboxed=sandboxed,
            result=output,
            returncode=returncode,
            duration_ms=duration_ms,
        )

        self._logger.debug(
            "command executed: category={category} sandboxed={sandboxed} "
            "rc={rc} duration={duration_ms}ms",
            category=check_result.category,
            sandboxed=sandboxed,
            rc=returncode,
            duration_ms=round(duration_ms, 2),
        )

        return ToolResult(
            content=f"[exit {returncode}]\n{output}",
            success=(returncode == 0),
        )
