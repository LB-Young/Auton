"""Userspace Bootstrap — ~/.auton 目录结构定义与启动校验

在 Auton 启动时调用 ``ensure_userspace()``，它会：
  1. 检查 ~/.auton 是否存在，缺失则创建
  2. 逐一检查必要的子目录，缺失则创建
  3. 检查默认配置文件，缺失则写入模板

目录规范
--------
::

    ~/.auton/
    ├── auton.md                ← 全局用户指令（注入每个会话的系统提示词）
    ├── config.json             ← 主 Agent LLM 快速配置
    ├── config/                 ← JSON 配置目录（buildin_abilities.json / auton_config.json / extensions_abilities.json）
    ├── skills/                 ← 用户安装的 Skill（每个子目录含 SKILL.md）
    │   └── <name>/SKILL.md
    ├── subagents/              ← 用户安装的 Subagent（每个子目录含 AGENT.md）
    │   └── <name>/AGENT.md
    ├── workflows/              ← 用户定义的工作流（YAML 文件）
    ├── workflow_runs/          ← 工作流执行历史
    ├── storage/                ← 结构化存储根目录
    │   ├── projects/           ← 项目级会话/记忆存储
    │   └── dates/              ← 日期级会话/记忆存储
    ├── memory/                 ← 全局记忆文件（legacy 兼容）
    ├── plans/                  ← 规划器存储
    ├── tasks/                  ← 任务队列存储
    ├── logs/                   ← 日志文件
    ├── tmp/                    ← 临时文件
    └── workspace/              ← 默认工作区

"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from ..core.paths import get_userspace_root

# ~/.auton 根目录（支持 AUTON_HOME 覆盖）
USERSPACE_ROOT: Path = get_userspace_root()

# auton.md 默认模板
_DEFAULT_AUTON_MD = """\
# Auton — 用户全局指令

在此文件中编写你对 Auton 的持久指令，内容会注入到每个会话的系统提示词中。

示例：
- 请始终用中文回复
- 我的主要编程语言是 Python
- 编码风格偏好：遵循 PEP8，函数注释使用 Google style

"""

# config.json 默认模板（LLM 快速配置）
_DEFAULT_CONFIG_JSON = """{
  "_notes": "LLM Provider 说明\\n- anthropic / minimax / openai / qwen / deepseek / doubao / kimi / gemini / openrouter\\n- 本地：ollama / lm_studio / vllm（可自定义 base_url）\\n在此文件中填写主 Agent 专属的 provider / model / api_key",
  "llm": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "api_key": "sk-...",
    "max_tokens": 8192,
    "temperature": 0.0,
    "timeout": 60.0
  }
}
"""

# config/buildin_abilities.json 默认模板
_DEFAULT_BUILDIN_ABILITIES_JSON = """{
  "_comment": "Toggle built-in subagents / skills / tools / workflows here.",
  "subagents": {
    "planner": {"enabled": true, "role": "任务拆解与计划"},
    "debugging": {"enabled": true, "role": "系统化调试"},
    "tdd": {"enabled": true, "role": "TDD 工作流执行"},
    "code_review": {"enabled": true, "role": "代码审查"},
    "security": {"enabled": true, "role": "安全审计"},
    "refactor": {"enabled": true, "role": "重构清理"},
    "architect": {"enabled": true, "role": "架构建议"},
    "delegator": {"enabled": true, "role": "任务分发"}
  },
  "skills": {
    "ai-research": {"enabled": true, "description": "检索研究资料"},
    "code-review": {"enabled": true, "description": "代码审查模板"},
    "git-workflow": {"enabled": true, "description": "Git 操作模板"},
    "github": {"enabled": true, "description": "GitHub API 操作"},
    "skill-creator": {"enabled": true, "description": "技能生成器"},
    "web-search": {"enabled": true, "description": "联网搜索"}
  },
  "tools": {
    "read": {"enabled": true},
    "write": {"enabled": true},
    "edit": {"enabled": true},
    "glob": {"enabled": true},
    "grep": {"enabled": true},
    "bash": {"enabled": true},
    "web_search": {"enabled": true},
    "web_fetch": {"enabled": true},
    "task_create": {"enabled": true},
    "task_get": {"enabled": true},
    "task_list": {"enabled": true},
    "task_stop": {"enabled": true},
    "mcp": {"enabled": true},
    "agent_create": {"enabled": true},
    "agent_list": {"enabled": true}
  },
  "workflows": {}
}
"""

# config/auton_config.json 默认模板
_DEFAULT_AUTON_CONFIG_JSON = """{
  "_notes": "此文件管理除主 Agent LLM 外的所有参数：memory / heartbeat / cron / security / log / MCP / project capabilities。",
  "global": {
    "memory": {
      "storage_dir": "~/.auton/memory",
      "chunk_size": 500,
      "chunk_overlap": 50,
      "vector_store": "chroma",
      "vector_db_path": "~/.auton/memory/vector_db"
    },
    "heartbeat": {
      "enabled": false,
      "every": "30m",
      "session_mode": "main",
      "light_context": true
    },
    "cron": {
      "enabled": false,
      "jobs_file": "~/.auton/cron/jobs.yaml",
      "logs_dir": "~/.auton/cron/logs"
    },
    "security": {
      "permission_mode": "default",
      "audit_enabled": true,
      "sandbox_enabled": true,
      "allowed_paths": [],
      "max_bash_timeout": 60
    },
    "log": {
      "level": "INFO",
      "log_dir": "~/.auton/logs",
      "enable_file": true,
      "enable_console": true
    },
    "mcp": {
      "auto_start": true,
      "servers": []
    },
    "capabilities": {
      "project": {
        "subagents": {},
        "skills": {},
        "tools": {},
        "workflows": {}
      }
    }
  },
  "projects": {
    "__default__": {
      "description": "Fallback configuration for any project.",
      "memory": {},
      "security": {},
      "capabilities": {
        "project": {
          "skills": {
            "<project-skill-name>": {
              "enabled": true,
              "path": "/abs/path/to/project/.auton/skills/<project-skill-name>"
            }
          },
          "subagents": {},
          "tools": {},
          "workflows": {}
        }
      }
    },
    "/absolute/path/to/project": {
      "description": "示例：针对特定仓库覆盖配置。",
      "memory": {
        "storage_dir": "/absolute/path/to/project/.auton/memory"
      },
      "capabilities": {
        "project": {
          "skills": {
            "custom-review": {
              "enabled": true,
              "path": "/absolute/path/to/project/.auton/skills/custom-review"
            }
          }
        }
      }
    }
  }
}
"""

# config/extensions_abilities.json 默认模板
_DEFAULT_EXTENSIONS_ABILITIES_JSON = """{
  "_comment": "State for user-installed capabilities (skills, subagents, tools, workflows).",
  "paths": {
    "skills_dir": "~/.auton/skills",
    "subagents_dir": "~/.auton/subagents",
    "workflows_dir": "~/.auton/workflows"
  },
  "capabilities": {
    "extensions": {
      "subagents": {
        "<user-subagent-name>": {
          "enabled": true,
          "path": "~/.auton/subagents/<user-subagent-name>",
          "notes": "AGENT.md 描述文件路径"
        }
      },
      "skills": {
        "<user-skill-name>": {
          "enabled": true,
          "path": "~/.auton/skills/<user-skill-name>",
          "version": "0.1.0",
          "params": {}
        }
      },
      "tools": {
        "<user-tool-name>": {
          "enabled": true,
          "entrypoint": "python -m your_tool",
          "params": {}
        }
      },
      "workflows": {
        "<user-workflow-name>": {
          "enabled": true,
          "path": "~/.auton/workflows/<user-workflow-name>.yaml",
          "description": ""
        }
      }
    }
  }
}
"""


@dataclass
class UserspaceLayout:
    """~/.auton 目录结构规范

    Attributes:
        root:        根目录（默认 ~/.auton）
        dirs:        必须存在的子目录列表（相对路径）
        default_files: 不存在时写入模板的文件 {相对路径: 默认内容}
    """

    root: Path = field(default_factory=get_userspace_root)

    dirs: list[str] = field(default_factory=lambda: [
        "config",           # 新版配置目录
        "skills",           # 用户安装的 Skill
        "subagents",        # 用户安装的 Subagent
        "workflows",        # 用户定义的工作流
        "workflow_runs",    # 工作流执行历史
        "storage",          # 结构化存储根
        "storage/projects", # 项目级存储
        "storage/dates",    # 日期级存储
        "memory",           # 全局记忆（legacy 兼容）
        "plans",            # 规划器
        "tasks",            # 任务队列
        "logs",             # 日志
        "tmp",              # 临时文件
        "workspace",        # 默认工作区
    ])

    default_files: dict[str, str] = field(default_factory=lambda: {
        "auton.md": _DEFAULT_AUTON_MD,
        "config.json": _DEFAULT_CONFIG_JSON,
        "config/buildin_abilities.json": _DEFAULT_BUILDIN_ABILITIES_JSON,
        "config/auton_config.json": _DEFAULT_AUTON_CONFIG_JSON,
        "config/extensions_abilities.json": _DEFAULT_EXTENSIONS_ABILITIES_JSON,
    })

    # ─── 便捷属性 ────────────────────────────────────────────────────────────

    @property
    def skills_dir(self) -> Path:
        return self.root / "skills"

    @property
    def subagents_dir(self) -> Path:
        return self.root / "subagents"

    @property
    def workflows_dir(self) -> Path:
        return self.root / "workflows"

    @property
    def storage_dir(self) -> Path:
        return self.root / "storage"

    @property
    def memory_dir(self) -> Path:
        return self.root / "memory"

    @property
    def auton_md(self) -> Path:
        return self.root / "auton.md"

    @property
    def config_json(self) -> Path:
        return self.root / "config.json"


# 全局默认布局（单例）
_default_layout = UserspaceLayout()


def ensure_userspace(
    layout: UserspaceLayout | None = None,
    *,
    quiet: bool = False,
) -> UserspaceLayout:
    """校验并创建 ~/.auton 完整目录结构。

    在 Auton 启动时调用，幂等操作——目录已存在则跳过，不存在则创建。

    Args:
        layout: 自定义布局（默认使用 ``UserspaceLayout()``）
        quiet:  True 时只记录 debug 日志，False 时对新创建的项记录 info

    Returns:
        实际使用的 UserspaceLayout（方便调用方获取路径）
    """
    layout = layout or _default_layout
    log = logger.bind(name="userspace.bootstrap")

    created_root = False
    if not layout.root.exists():
        layout.root.mkdir(parents=True, exist_ok=True)
        created_root = True
        _log(log, quiet, "info", "创建 Auton 用户目录: {p}", p=layout.root)
    else:
        log.debug("Auton 用户目录已存在: {p}", p=layout.root)

    # 创建缺失的子目录
    for rel in layout.dirs:
        d = layout.root / rel
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            _log(log, quiet, "info", "创建目录: {p}", p=d)
        else:
            log.debug("目录已存在: {p}", p=d)

    # 写入缺失的默认文件
    for rel, default_content in layout.default_files.items():
        f = layout.root / rel
        if not f.exists():
            f.write_text(default_content, encoding="utf-8")
            _log(log, quiet, "info", "创建默认文件: {p}", p=f)
        else:
            log.debug("文件已存在: {p}", p=f)

    if created_root:
        log.info("Auton 用户目录初始化完成: {p}", p=layout.root)

    return layout


def _log(log: "loguru.Logger", quiet: bool, level: str, msg: str, **kwargs: object) -> None:
    if quiet:
        log.debug(msg, **kwargs)
    else:
        getattr(log, level)(msg, **kwargs)


def get_layout() -> UserspaceLayout:
    """获取默认的 UserspaceLayout（已 ensure 后调用）"""
    return _default_layout
