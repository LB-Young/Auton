"""Security — 密钥管理器

支持从多个来源读取密钥：
  1. 环境变量（最高优先级）
  2. OS Keychain（macOS Keychain / Linux secret-service）
  3. 配置文件（最低优先级，已知风险）

设计原则：密钥永不写入日志或审计记录。
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from typing import Literal

from loguru import logger

from ..core.paths import resolve_userspace_path


@dataclass
class KeyInfo:
    """密钥元信息（不包含实际值）"""
    name: str
    source: Literal["env", "keychain", "config"]  # noqa: A002
    present: bool


_KEYCHAIN_SERVICE = "auton"


class KeyManager:
    """密钥管理器单例"""

    _instance: "KeyManager | None" = None

    def __init__(self) -> None:
        self._logger = logger.bind(name="KeyManager")

    @classmethod
    def get_instance(cls) -> "KeyManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ─── 读取接口 ───────────────────────────────────────────────────

    def get(self, key_name: str) -> str | None:
        """获取密钥值，依次尝试 env → keychain → config"""
        # 1. 环境变量
        value = os.environ.get(key_name)
        if value:
            self._logger.debug("key {k} found in environment", k=key_name)
            return value

        # 2. OS Keychain
        value = self._get_from_keychain(key_name)
        if value:
            self._logger.debug("key {k} found in OS keychain", k=key_name)
            return value

        # 3. 配置文件（风险已知，仅用于开发）
        value = self._get_from_config(key_name)
        if value:
            self._logger.warning("key {k} read from config file — use env or keychain in production", k=key_name)
            return value

        return None

    def get_or_raise(self, key_name: str) -> str:
        """获取密钥，不存在则抛出异常"""
        value = self.get(key_name)
        if value is None:
            raise KeyError(f"required key '{key_name}' not found in env/keychain/config")
        return value

    def is_present(self, key_name: str) -> bool:
        """检查密钥是否存在"""
        return self.get(key_name) is not None

    def info(self, key_name: str) -> KeyInfo:
        """返回密钥元信息（不暴露实际值）"""
        if os.environ.get(key_name):
            return KeyInfo(name=key_name, source="env", present=True)
        if self._get_from_keychain(key_name):
            return KeyInfo(name=key_name, source="keychain", present=True)
        if self._get_from_config(key_name):
            return KeyInfo(name=key_name, source="config", present=True)
        return KeyInfo(name=key_name, source="env", present=False)

    # ─── OS Keychain ─────────────────────────────────────────────────

    def _get_from_keychain(self, key_name: str) -> str | None:
        """从 OS Keychain 读取"""
        system = platform.system()
        if system == "Darwin":
            return self._get_from_macos_keychain(key_name)
        elif system == "Linux":
            return self._get_from_linux_keychain(key_name)
        return None

    def _get_from_macos_keychain(self, key_name: str) -> str | None:
        """macOS Keychain 读取（通过 security 命令）"""
        import subprocess

        try:
            cmd = [
                "security", "find-generic-password",
                "-s", _KEYCHAIN_SERVICE,
                "-a", key_name,
                "-w",  # 只输出密码
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return None

    def _get_from_linux_keychain(self, key_name: str) -> str | None:
        """Linux secret-service 读取（通过 dbus 命令）"""
        import subprocess

        try:
            # 尝试 secret-tool
            cmd = ["secret-tool", "lookup", "auton", key_name]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return None

    # ─── 配置文件（仅开发）──────────────────────────────────────────

    def _get_from_config(self, key_name: str) -> str | None:
        """从配置目录读取（仅开发模式）"""
        config_path = resolve_userspace_path("credentials")
        if not config_path.exists():
            return None

        # 命名规范：<key_name>.txt 或 credentials.env
        txt_path = config_path / f"{key_name}.txt"
        if txt_path.exists():
            return txt_path.read_text(encoding="utf-8").strip()

        env_path = config_path / "credentials.env"
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.startswith(f"{key_name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")

        return None

    # ─── 写入接口（仅 keychain）────────────────────────────────────

    def set_keychain(self, key_name: str, value: str) -> bool:
        """写入 OS Keychain"""
        system = platform.system()
        if system == "Darwin":
            return self._set_macos_keychain(key_name, value)
        elif system == "Linux":
            return self._set_linux_keychain(key_name, value)
        self._logger.warning("keychain not supported on {s}", s=system)
        return False

    def _set_macos_keychain(self, key_name: str, value: str) -> bool:
        """macOS Keychain 写入"""
        import subprocess

        try:
            cmd = [
                "security", "add-generic-password",
                "-s", _KEYCHAIN_SERVICE,
                "-a", key_name,
                "-w", value,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _set_linux_keychain(self, key_name: str, value: str) -> bool:
        """Linux Keychain 写入"""
        import subprocess

        try:
            cmd = ["secret-tool", "store", "--label=auton", "auton", key_name]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            proc.communicate(input=value.encode("utf-8"), timeout=10)
            return proc.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
