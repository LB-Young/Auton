"""Auton Core — 配置加载

配置来源优先级（后者覆盖前者）：
  CLI args > 环境变量 > 项目配置 .auton/config.yaml
  > 用户配置 ~/.auton/config.yaml > config/default.yaml
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any, Literal

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from .errors import ConfigurationError


# ─── 配置模型 ────────────────────────────────────────────────────────────────

class LLMConfig(BaseModel):
    provider: Literal["anthropic", "openai", "ollama", "minimax"] = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key: str | None = None
    base_url: str | None = None  # Ollama / OpenAI compatible
    max_tokens: int = 8192
    temperature: float = 0.0
    timeout: float = 60.0


class MemoryConfig(BaseModel):
    storage_dir: Path = Path("~/.auton/memory").expanduser()
    chunk_size: int = 500  # token
    chunk_overlap: int = 50
    vector_store: Literal["chroma", "qdrant"] = "chroma"
    vector_db_path: Path = Path("~/.auton/memory/vector_db").expanduser()


class HeartbeatConfig(BaseModel):
    enabled: bool = False
    every: str = "30m"  # 5m / 1h / 2h / 自定义
    active_hours: str | None = None  # e.g. "9:00-18:00"
    session_mode: Literal["main", "isolated"] = "main"
    light_context: bool = True
    target: Literal["main", "isolated", "current"] = "main"


class CronConfig(BaseModel):
    jobs_file: Path = Path("~/.auton/cron/jobs.yaml").expanduser()
    logs_dir: Path = Path("~/.auton/cron/logs").expanduser()
    enabled: bool = False


class SecurityConfig(BaseModel):
    permission_mode: Literal["default", "auto", "bypass", "yolo"] = "default"
    audit_enabled: bool = True
    sandbox_enabled: bool = True
    allowed_paths: list[Path] = Field(default_factory=list)
    max_bash_timeout: int = 60


class LogConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_dir: Path = Path("~/.auton/logs").expanduser()
    enable_file: bool = True
    enable_console: bool = True


class MCPServerConfig(BaseModel):
    name: str
    command: list[str] = Field(default_factory=list)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class MCPConfig(BaseModel):
    servers: list[MCPServerConfig] = Field(default_factory=list)
    auto_start: bool = True


class AutonConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    cron: CronConfig = Field(default_factory=CronConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    log: LogConfig = Field(default_factory=LogConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)


# ─── 配置加载器 ──────────────────────────────────────────────────────────────

class ConfigManager:
    """分层配置加载器"""

    def __init__(
        self,
        *,
        config_file: Path | None = None,
        env_prefix: str = "AUTON_",
        defaults: AutonConfig | None = None,
    ) -> None:
        self._defaults = defaults or AutonConfig()
        self._config_file = config_file
        self._env_prefix = env_prefix
        self._raw: dict[str, Any] = {}
        self._config: AutonConfig = self._defaults

    def load(self) -> Self:
        """加载所有配置层，返回合并后的配置"""
        # 1. 默认值
        merged: dict[str, Any] = self._defaults.model_dump()

        # 2. 用户配置 ~/.auton/config.yaml
        user_config = Path(os.path.expanduser("~/.auton/config.yaml"))
        if user_config.exists():
            with open(user_config, encoding="utf-8") as f:
                user_data = yaml.safe_load(f) or {}
            merged = _deep_merge(merged, user_data)

        # 3. 项目配置 .auton/config.yaml（当前目录）
        project_config = Path(".auton/config.yaml")
        if project_config.exists():
            with open(project_config, encoding="utf-8") as f:
                project_data = yaml.safe_load(f) or {}
            merged = _deep_merge(merged, project_data)

        # 4. 指定配置文件
        if self._config_file and self._config_file.exists():
            with open(self._config_file, encoding="utf-8") as f:
                file_data = yaml.safe_load(f) or {}
            merged = _deep_merge(merged, file_data)

        # 5. 环境变量 AUTON_* 覆盖
        merged = _deep_merge(merged, _env_overrides(self._env_prefix))

        self._raw = merged
        self._config = AutonConfig.model_validate(merged)
        return self

    def get(self) -> AutonConfig:
        """获取最终配置"""
        return self._config

    def get_raw(self, key: str, default: Any = None) -> Any:
        """获取原始值（未验证的）"""
        keys = key.split(".")
        val = self._raw
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并 override 到 base（override 优先）"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _env_overrides(prefix: str) -> dict:
    """从环境变量提取 AUTON_* 配置"""
    result = {}
    for key, value in os.environ.items():
        if key.startswith(prefix):
            parts = key[len(prefix):].lower().split("_")
            d = result
            for part in parts[:-1]:
                d = d.setdefault(part, {})
            # 类型转换
            if value.lower() in ("true", "false"):
                value = value.lower() == "true"
            elif value.isdigit():
                value = int(value)
            d[parts[-1]] = value
    return result


# ─── 全局便捷函数 ──────────────────────────────────────────────────────────

_config: ConfigManager | None = None


def get_config() -> AutonConfig:
    global _config
    if _config is None:
        _config = ConfigManager().load()
    return _config.get()
