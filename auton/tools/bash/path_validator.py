"""Bash Path Validator — 路径安全校验

7 层安全校验第 2 层：
  - 路径遍历攻击检测（../ 序列）
  - Unicode 标准化攻击（全角字符、空格注入）
  - 符号链接穿透检测
  - 敏感路径保护
"""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ─── 敏感路径 ───────────────────────────────────────────────────────────────

PROTECTED_PATHS: list[str] = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/ssh/ssh_host",
    "/.ssh/authorized_keys",
    "/.ssh/id_rsa",
    "/.ssh/id_ed25519",
    "/.ssh/id_dsa",
    "/.git/objects",  # Git 对象库
]

# 禁止操作的项目根路径
PROTECTED_PREFIXES: list[str] = [
    "/System",
    "/Library/Caches",
    "/Library/Application Support",
    "/usr/sbin",
    "/usr/bin",
    "/bin",
    "/sbin",
    "/boot",
    "/sys",
    "/proc",
    "/dev",
]


# ─── 路径校验结果 ───────────────────────────────────────────────────────────

class PathValidationResult:
    def __init__(
        self,
        allowed: bool,
        real_path: str | None = None,
        reason: str = "",
        is_symlink: bool = False,
    ) -> None:
        self.allowed = allowed
        self.real_path = real_path
        self.reason = reason
        self.is_symlink = is_symlink


# ─── 核心校验函数 ───────────────────────────────────────────────────────────

def normalize_path(path: str) -> str:
    """Unicode NFC 标准化 + 去除空字节"""
    # NFD 分解后去除空字节
    normalized = unicodedata.normalize("NFC", path)
    normalized = normalized.replace("\x00", "")
    return normalized


def check_path_traversal(command: str) -> bool:
    """检测命令中是否包含路径遍历攻击"""
    # 匹配 ../ 或绝对路径逃逸
    traversal_patterns = [
        r"\.\./",     # ../
        r"/\.\./",    # /../
        r"\.\.$",     # .. at end
        r"^\.\./",    # starts with ../
    ]
    import re
    for pattern in traversal_patterns:
        if re.search(pattern, command):
            return True
    return False


def check_null_byte(command: str) -> bool:
    """检测空字节注入"""
    return "\x00" in command or "\0" in command


def check_protected_path(path: str) -> bool:
    """检查是否为受保护路径"""
    import re
    normalized = normalize_path(path)
    for protected in PROTECTED_PATHS:
        if normalized == protected or normalized.endswith(protected):
            return True
    return False


def check_protected_prefix(path: str) -> bool:
    """检查路径前缀是否受保护"""
    import re
    normalized = normalize_path(path)
    for prefix in PROTECTED_PREFIXES:
        if normalized.startswith(prefix):
            return True
    return False


def resolve_symlinks(path: str) -> tuple[bool, str]:
    """解析符号链接，返回 (是否包含符号链接, 真实路径)"""
    try:
        real = os.path.realpath(path)
        # 判断是否经过符号链接
        is_link = os.path.islink(path) or real != os.path.abspath(path)
        return is_link, real
    except (OSError, ValueError):
        return False, path


def validate_single_path(path: str) -> PathValidationResult:
    """校验单个路径的安全性"""
    normalized = normalize_path(path)

    # 1. 脱空字节
    if check_null_byte(normalized):
        return PathValidationResult(
            allowed=False,
            reason="Null byte injection detected",
        )

    # 2. 检查受保护路径
    if check_protected_path(normalized):
        return PathValidationResult(
            allowed=False,
            reason=f"Access to protected path denied: {path}",
        )

    # 3. 检查受保护前缀
    if check_protected_prefix(normalized):
        return PathValidationResult(
            allowed=False,
            reason=f"Access to protected prefix denied: {path}",
        )

    # 4. 符号链接解析
    is_link, real = resolve_symlinks(path)
    if is_link:
        # 符号链接指向的目标也要校验
        if check_protected_path(real):
            return PathValidationResult(
                allowed=False,
                real_path=real,
                reason=f"Symlink targets protected path: {real}",
                is_symlink=True,
            )
        if check_protected_prefix(real):
            return PathValidationResult(
                allowed=False,
                real_path=real,
                reason=f"Symlink targets protected prefix: {real}",
                is_symlink=True,
            )

    return PathValidationResult(allowed=True, real_path=real or normalized)


def validate_paths_from_command(command: str) -> list[PathValidationResult]:
    """从命令中提取所有路径并校验"""
    import re

    results: list[PathValidationResult] = []

    # 简单提取引号包裹的路径
    quoted_paths = re.findall(r'''['"]([^'"]+)['"]''', command)
    for p in quoted_paths:
        results.append(validate_single_path(p))

    # 提取 -f/-o/-c 等参数后的路径
    path_args = re.findall(
        r'''(?:^|\s)(-[a-zA-Z][\w-]*|\w+)\s+(['"]?)([^\s'"]+)\3''',
        command,
    )
    for _, _, path in path_args:
        if path.startswith("-"):
            continue
        if Path(path).is_absolute():
            results.append(validate_single_path(path))
        elif "/" in path or path.startswith("."):
            results.append(validate_single_path(path))

    return results


def validate_command_paths(command: str) -> tuple[bool, list[PathValidationResult]]:
    """验证命令中所有路径，返回 (是否全部通过, 结果列表)"""
    results = validate_paths_from_command(command)

    # 允许无路径的命令（如纯计算）
    if not results:
        return True, []

    all_allowed = all(r.allowed for r in results)
    return all_allowed, results
