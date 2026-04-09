"""Security 模块 — M5 权限与审计

导出所有安全子模块的公共接口。
"""

from .audit import AuditEntry, AuditLog
from .injection import escape_injection, is_injection_suspect, InjectionGuard
from .key_manager import KeyInfo, KeyManager
from .permission import PermissionMode, PermissionManager, PermissionResult

__all__ = [
    "AuditEntry",
    "AuditLog",
    "escape_injection",
    "InjectionGuard",
    "is_injection_suspect",
    "KeyInfo",
    "KeyManager",
    "PermissionMode",
    "PermissionManager",
    "PermissionResult",
]
