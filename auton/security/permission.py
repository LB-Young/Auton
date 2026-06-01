"""Security — 四级权限管理器

| 模式 | 行为 | 适用场景 |
|-------|------|----------|
| default | 交互式确认（每次写操作询问） | 默认模式 |
| auto | ML 分类器自动审批低风险操作 | --auto 标志 |
| bypass | 跳过所有权限检查（危险） | 明确 opt-in |
| yolo | 全部自动拒绝（只读） | 安全研究 / CI |

设计原则：
  - 7 层安全校验始终执行，不可绕过（硬拦截）
  - 权限模式控制的是"已通过安全校验的命令是否放行"
  - bypass 模式跳过后续权限判断（但不跳过安全校验）
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from loguru import logger


class PermissionMode(Enum):
    """四级权限模式"""

    DEFAULT = "default"  # 交互式确认
    AUTO = "auto"  # ML 自动审批
    BYPASS = "bypass"  # 跳过所有权限检查
    YOLO = "yolo"  # 全部拒绝（只读模式）


@dataclass
class PermissionResult:
    """权限检查结果"""

    allowed: bool
    mode: PermissionMode
    reason: str
    requires_input: bool = False  # 是否需要用户交互确认


class PermissionManager:
    """权限管理器

    在 BashTool 7 层安全校验之后调用。
    决定是否放行已通过安全校验的命令。

    使用方式：
        pm = PermissionManager(mode="default")
        result = pm.check(command="rm -rf /tmp/test", category="destructive")
        if not result.allowed:
            return  # 拒绝
        if result.requires_input:
            confirmed = await self._ask_user(command, reason)
            if not confirmed:
                return  # 拒绝
    """

    def __init__(
        self,
        mode: str | PermissionMode = "default",
        stdin=None,
        stdout=None,
        yes_all: bool = False,
    ) -> None:
        if isinstance(mode, str):
            mode = PermissionMode(mode)
        self.mode = mode
        self.stdin = stdin
        self.stdout = stdout
        self.yes_all = yes_all
        self._logger = logger.bind(name="PermissionManager")

    # ─── 核心检查 ───────────────────────────────────────────────────

    def check(
        self,
        command: str,
        category: str = "unknown",
    ) -> PermissionResult:
        """检查命令是否允许执行

        Args:
            command: 待执行的命令
            category: 命令分类（read_only / write / destructive）

        Returns:
            PermissionResult
        """
        if self.mode == PermissionMode.YOLO:
            return PermissionResult(
                allowed=False,
                mode=self.mode,
                reason="yolo mode: all operations denied (read-only mode)",
            )

        if self.mode == PermissionMode.BYPASS:
            return PermissionResult(
                allowed=True,
                mode=self.mode,
                reason="bypass mode: all permission checks skipped",
            )

        if self.mode == PermissionMode.AUTO:
            return self._auto_check(command, category)

        # DEFAULT 模式
        return self._default_check(command, category)

    def _default_check(
        self,
        command: str,
        category: str,
    ) -> PermissionResult:
        """default 模式：读写操作需要确认"""
        if category in ("read_only", "read"):
            return PermissionResult(
                allowed=True,
                mode=self.mode,
                reason="read-only command, auto-approved",
            )

        if category in ("destructive", "write"):
            return PermissionResult(
                allowed=True,
                mode=self.mode,
                reason=f"command classified as {category}, requires confirmation",
                requires_input=True,
            )

        # unknown 分类也要确认
        return PermissionResult(
            allowed=True,
            mode=self.mode,
            reason="unclassified command, requires confirmation",
            requires_input=True,
        )

    def _auto_check(
        self,
        command: str,
        category: str,
    ) -> PermissionResult:
        """auto 模式：ML 分类器自动审批（当前为规则近似）"""
        # auto 模式：自动放行 read-only 和 write，非 destructive
        if category in ("read_only", "read"):
            return PermissionResult(
                allowed=True,
                mode=self.mode,
                reason="auto mode: read-only auto-approved",
            )

        if category == "write":
            # write 类（创建/修改文件）自动放行
            return PermissionResult(
                allowed=True,
                mode=self.mode,
                reason="auto mode: write operation auto-approved",
            )

        # destructive 类需要确认
        return PermissionResult(
            allowed=True,
            mode=self.mode,
            reason=f"auto mode: {category} operation requires confirmation",
            requires_input=True,
        )

    # ─── 交互确认 ───────────────────────────────────────────────────

    def ask_confirmation(self, command: str, reason: str) -> bool:
        """向用户询问确认（阻塞式）

        Returns:
            True = 用户同意，False = 用户拒绝
        """
        if self.yes_all:
            return True

        import asyncio
        import sys
        import time

        def _read() -> bool:
            stdout = self.stdout or sys.stdout
            stdin = self.stdin or sys.stdin
            
            # 等待一小段时间，让 Live 渲染完成
            time.sleep(0.3)
            
            # 清空当前行并移动到新行，确保提示在渲染内容下方
            # 使用多个换行来"推开" Live 渲染的内容
            print("\n" * 5, file=stdout)
            stdout.flush()
            
            # 再等待一下，确保输出已刷新
            time.sleep(0.1)
            
            print("┌" + "─" * 68 + "┐", file=stdout)
            print("│  ⚠️  命令需要确认" + " " * 49 + "│", file=stdout)
            print("├" + "─" * 68 + "┤", file=stdout)
            print(f"│  命令: {command:<58}│", file=stdout)
            print(f"│  原因: {reason:<58}│", file=stdout)
            print("└" + "─" * 68 + "┘", file=stdout)
            print("\n是否允许执行？(yes/no) ", end="", file=stdout)
            stdout.flush()
            try:
                response = stdin.readline().strip().lower()
                print("", file=stdout)  # 添加空行
                return response in ("yes", "y", "是", "true", "1")
            except (EOFError, AttributeError):
                return False

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行中的事件循环，直接同步读
            return _read()

        # 用独立线程池读 stdin，避免阻塞事件循环
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(_read)
            return asyncio.wrap_future(future)
        finally:
            executor.shutdown(wait=False)

    # ─── 工厂方法 ───────────────────────────────────────────────────

    @classmethod
    def from_config(cls, mode: str | None = None) -> "PermissionManager":
        """从配置创建 PermissionManager"""
        from ..core.config import get_config

        config = get_config()
        effective = mode or config.security.permission_mode
        return cls(mode=effective)

    # ─── 工具函数 ───────────────────────────────────────────────────

    @staticmethod
    def is_read_only(category: str) -> bool:
        """判断是否为只读分类"""
        return category in ("read_only", "read", "read-only")

    @staticmethod
    def is_write(category: str) -> bool:
        """判断是否为写操作"""
        return category in ("write", "destructive")

    @staticmethod
    def is_destructive(category: str) -> bool:
        """判断是否为破坏性操作"""
        return category == "destructive"
