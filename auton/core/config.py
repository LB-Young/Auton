"""Auton Core — 配置加载

配置来源优先级（后者覆盖前者）：
  CLI args > 环境变量 > 指定配置文件
  > 项目配置 .auton/config.yaml（兼容 legacy）
  > 用户配置 ~/.auton/config.json（LLM 快速配置，旧版兼容 ~/.auton/config.yaml）
  > ~/.auton/config/extensions_abilities.json
  > ~/.auton/config/auton_config.json（global + 项目覆盖）
  > ~/.auton/config/buildin_abilities.json
  > 内置默认值
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, Literal

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings

from .errors import ConfigurationError
from .paths import expand_auton_path, resolve_userspace_path


# ─── 配置模型 ────────────────────────────────────────────────────────────────

class LLMConfig(BaseModel):
    # 支持的 provider 名称（不区分大小写）：
    #   云端：anthropic / minimax / openai(gpt) / qwen(dashscope/tongyi) /
    #         deepseek / doubao(ark/volcengine) / kimi(moonshot) /
    #         gemini(google) / openrouter
    #   本地：ollama / lm_studio(lmstudio/lm-studio) / vllm
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int = 8192
    temperature: float = 0.0
    timeout: float = 60.0


class MemoryConfig(BaseModel):
    storage_dir: Path = Field(default_factory=lambda: resolve_userspace_path("memory"))
    chunk_size: int = 500  # token
    chunk_overlap: int = 50
    vector_store: Literal["chroma", "qdrant"] = "chroma"
    vector_db_path: Path = Field(default_factory=lambda: resolve_userspace_path("memory", "vector_db"))

    @field_validator("storage_dir", "vector_db_path", mode="before")
    @classmethod
    def _expand_home(cls, v: Any) -> Path:
        """从配置文件加载时，确保 ~ 被展开为实际 home 目录。"""
        return expand_auton_path(v)


class HeartbeatConfig(BaseModel):
    enabled: bool = False
    every: str = "30m"  # 5m / 1h / 2h / 自定义
    active_hours: str | None = None  # e.g. "9:00-18:00"
    session_mode: Literal["main", "isolated"] = "main"
    light_context: bool = True
    target: Literal["main", "isolated", "current"] = "main"


class CronConfig(BaseModel):
    jobs_file: Path = Field(default_factory=lambda: resolve_userspace_path("cron", "jobs.yaml"))
    logs_dir: Path = Field(default_factory=lambda: resolve_userspace_path("cron", "logs"))
    enabled: bool = False


class SecurityConfig(BaseModel):
    permission_mode: Literal["default", "auto", "bypass", "yolo"] = "default"
    audit_enabled: bool = True
    sandbox_enabled: bool = True
    allowed_paths: list[Path] = Field(default_factory=list)
    max_bash_timeout: int = 60


class LogConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_dir: Path = Field(default_factory=lambda: resolve_userspace_path("logs"))
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


class CapabilityToggle(BaseModel):
    enabled: bool = True
    notes: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class CapabilityGroup(BaseModel):
    subagents: dict[str, CapabilityToggle] = Field(default_factory=dict)
    skills: dict[str, CapabilityToggle] = Field(default_factory=dict)
    tools: dict[str, CapabilityToggle] = Field(default_factory=dict)
    workflows: dict[str, CapabilityToggle] = Field(default_factory=dict)


class CapabilitiesConfig(BaseModel):
    builtin: CapabilityGroup = Field(default_factory=CapabilityGroup)
    project: CapabilityGroup = Field(default_factory=CapabilityGroup)
    extensions: CapabilityGroup = Field(default_factory=CapabilityGroup)


class SubagentLLMOverride(BaseModel):
    """单个 subagent 的 LLM 覆盖配置。留空则继承主 Agent 设置。"""
    provider: str = ""   # 留空 = 继承主 Agent
    model: str = ""      # 留空 = 继承主 Agent


class AutonConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    subagents: dict[str, SubagentLLMOverride] = Field(default_factory=dict)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    cron: CronConfig = Field(default_factory=CronConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    log: LogConfig = Field(default_factory=LogConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    capabilities: CapabilitiesConfig = Field(default_factory=CapabilitiesConfig)


# ─── 配置加载器 ──────────────────────────────────────────────────────────────

class ConfigManager:
    """分层配置加载器"""

    def __init__(
        self,
        *,
        config_file: Path | None = None,
        env_prefix: str = "AUTON_",
        defaults: AutonConfig | None = None,
        config_dir: Path | None = None,
    ) -> None:
        self._defaults = defaults or AutonConfig()
        self._config_file = config_file
        self._env_prefix = env_prefix
        self._config_dir = (config_dir or resolve_userspace_path("config")).expanduser()
        self._raw: dict[str, Any] = {}
        self._config: AutonConfig = self._defaults

    def load(self) -> Self:
        """加载所有配置层，返回合并后的配置"""
        # 1. 默认值
        merged: dict[str, Any] = self._defaults.model_dump()

        # 2. auton_config.json（全局 + 项目覆盖）
        global_cfg, project_cfg = _load_auton_config(self._config_dir / "auton_config.json")
        merged = _deep_merge(merged, global_cfg)
        merged = _deep_merge(merged, project_cfg)

        # 3. buildin_abilities.json（内置能力）
        merged = _deep_merge(merged, _load_buildin_capabilities(self._config_dir / "buildin_abilities.json"))

        # 4. extensions_abilities.json（用户安装能力）
        merged = _deep_merge(merged, _load_extension_capabilities(self._config_dir / "extensions_abilities.json"))

        # 5. 用户配置 ~/.auton/config.json（LLM 快速配置，兼容 legacy YAML）
        user_config_json = resolve_userspace_path("config.json")
        if user_config_json.exists():
            try:
                user_data = json.loads(user_config_json.read_text(encoding="utf-8")) or {}
            except json.JSONDecodeError as exc:
                raise ConfigurationError(f"无法解析配置文件 {user_config_json}: {exc}") from exc
            merged = _deep_merge(merged, user_data)
        else:
            legacy_user_config = resolve_userspace_path("config.yaml")
            if legacy_user_config.exists():
                with open(legacy_user_config, encoding="utf-8") as f:
                    user_data = yaml.safe_load(f) or {}
                merged = _deep_merge(merged, user_data)

        # 6. 项目配置 .auton/config.yaml（当前目录，legacy）
        project_config = Path(".auton/config.yaml")
        if project_config.exists():
            with open(project_config, encoding="utf-8") as f:
                project_data = yaml.safe_load(f) or {}
            merged = _deep_merge(merged, project_data)

        # 7. 指定配置文件
        if self._config_file and self._config_file.exists():
            with open(self._config_file, encoding="utf-8") as f:
                file_data = yaml.safe_load(f) or {}
            merged = _deep_merge(merged, file_data)

        # 8. 环境变量 AUTON_* 覆盖
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


def _load_buildin_capabilities(path: Path) -> dict[str, Any]:
    data = _load_json_config(path)
    if not data:
        return {}
    return {"capabilities": {"builtin": data}}


def _load_extension_capabilities(path: Path) -> dict[str, Any]:
    data = _load_json_config(path)
    if not data:
        return {}
    caps = data.get("capabilities", {}).get("extensions", {})
    if not isinstance(caps, dict):
        caps = {}
    return {"capabilities": {"extensions": caps}}


def _load_json_config(path: Path) -> dict[str, Any]:
    """读取 JSON 配置文件，过滤掉 _comment 等元字段"""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"无法解析配置文件 {path}: {exc}") from exc

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigurationError(f"JSON 配置 {path} 必须是对象")

    return _strip_private_keys(raw)


def _strip_private_keys(obj: Any) -> Any:
    """移除键名以 _ 开头的注释字段"""
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for key, value in obj.items():
            if isinstance(key, str) and key.startswith("_"):
                continue
            result[key] = _strip_private_keys(value)
        return result
    if isinstance(obj, list):
        return [_strip_private_keys(item) for item in obj]
    return obj


def _load_project_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """同时返回全局项目配置和针对当前工作目录的配置"""
    # Deprecated helper retained for compatibility (unused in new flow)
    data = _load_json_config(path)
    if not data:
        return {}, {}

    projects = data.pop("projects", {})
    scoped: dict[str, Any] = {}

    if isinstance(projects, dict):
        cwd = Path.cwd().resolve()
        default_cfg = projects.get("__default__")
        if isinstance(default_cfg, dict):
            scoped = _deep_merge(scoped, default_cfg)

        for root_str, cfg in projects.items():
            if root_str == "__default__" or not isinstance(cfg, dict):
                continue
            resolved = _safe_resolve_path(root_str)
            if resolved and (cwd == resolved or resolved in cwd.parents):
                scoped = _deep_merge(scoped, cfg)

    return data, scoped


def _load_auton_config(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    data = _load_json_config(path)
    if not data:
        return {}, {}

    global_cfg = data.get("global", {})
    projects = data.get("projects", {})
    scoped = _select_project_config(projects)
    return global_cfg if isinstance(global_cfg, dict) else {}, scoped


def _select_project_config(projects: Any) -> dict[str, Any]:
    if not isinstance(projects, dict):
        return {}
    result: dict[str, Any] = {}
    default_cfg = projects.get("__default__")
    if isinstance(default_cfg, dict):
        result = _deep_merge(result, default_cfg)

    cwd = Path.cwd().resolve()
    for root_str, cfg in projects.items():
        if root_str == "__default__" or not isinstance(cfg, dict):
            continue
        resolved = _safe_resolve_path(root_str)
        if resolved and (cwd == resolved or resolved in cwd.parents):
            result = _deep_merge(result, cfg)
    return result


def _safe_resolve_path(path_str: str) -> Path | None:
    try:
        return Path(path_str).expanduser().resolve()
    except OSError:
        return None


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


CapabilityScope = Literal["builtin", "project", "extensions"]
CapabilityCategory = Literal["subagents", "skills", "tools", "workflows"]


def get_capability_toggle(
    scope: CapabilityScope,
    category: CapabilityCategory,
    name: str,
) -> CapabilityToggle | None:
    """获取指定能力的配置（未配置则返回 None）"""
    config = get_config().capabilities
    group = getattr(config, scope, None)
    if group is None:
        return None
    toggles = getattr(group, category, {})
    return toggles.get(name)


def is_capability_enabled(
    scope: CapabilityScope,
    category: CapabilityCategory,
    name: str,
) -> bool:
    """判断某能力是否启用（默认启用）"""
    toggle = get_capability_toggle(scope, category, name)
    if toggle is None:
        return True
    return bool(toggle.enabled)
