# Auton — Personal AI Agent

个人 AI Agent 助手，参考 Claude Code v2.1.88 和 OpenCode 架构设计。

## 环境要求

- Python 3.11+
- Conda 或 venv 虚拟环境

## 安装

### 1. 创建并激活虚拟环境

```bash
conda create -n auton_env python=3.12 -y
conda activate auton_env
```

### 2. 安装依赖

```bash
cd /path/to/Auton
pip install -e .
```

### 3. 初始化用户目录

```bash
auton init
```

执行后会在 `~/.auton/` 下生成所有配置文件，并提示配置文件路径。

### 4. 配置 API Key

编辑 `~/.auton/config.json`，这是**最小必填**的 LLM 配置，填好即可立即启动：

```json
{
  "llm": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "api_key": "sk-...",
    "max_tokens": 8192,
    "temperature": 0.0,
    "timeout": 60.0
  }
}
```

`~/.auton/config/` 目录中还准备了 `buildin_abilities.json`（所有内置能力开关）、`auton_config.json`（全局 / 各项目参数）和 `extensions_abilities.json`（用户自定义能力占位）。

或直接用环境变量：
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
export MINIMAX_API_KEY="your-minimax-api-key"
```

完整配置示例可直接查看 `~/.auton/config/auton_config.json`，首次运行已自动生成并包含所有可调字段。

### MiniMax 配置

```yaml
llm:
  provider: minimax
  model: MiniMax-M2.7
  api_key: "your-minimax-api-key"
```

```bash
# 或通过命令行指定
auton main --provider minimax --model MiniMax-M2.7 -m "..."

# 环境变量
export MINIMAX_API_KEY="your-minimax-api-key"
```

## 使用

### 交互式会话

```bash
conda activate auton_env
auton main
```

```bash
# 带初始消息
auton main -m "帮我写一个快速排序算法"

# 指定项目目录
auton main -p /path/to/project -m "审查这个项目的代码"

# 指定模型
auton main --model claude-opus-4-20250514 -m "..."

# 使用 MiniMax
auton main --provider minimax --model MiniMax-M2.7 -m "..."

# 指定闲聊 / 项目模式
auton main --session-mode chat
auton main --session-mode project
```

### Web 界面（实验）

```bash
auton web --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000` 即可体验：

- 左侧侧边栏可配置单个本地项目路径；为空则进入日期模式并加载最近 7 天会话。
- 选择会话后即可查看历史记录，新的对话根据模式写入对应的 session 目录。
- 右侧对话区域支持流式渲染，体验类似 ChatGPT/Gemini。

### 回放历史会话

```bash
auton replay <session_id>
```

session_id 可通过查看 `~/.auton/memory/execution/` 目录下的 jsonl 文件名获得。

## 配置

配置文件优先级（后者覆盖前者）：

```
CLI args > 环境变量 > 指定配置文件
> 项目级 .auton/config.yaml（legacy）
> 用户级 ~/.auton/config.json（LLM 快速配置）
> ~/.auton/config/extensions_abilities.json
> ~/.auton/config/auton_config.json
> ~/.auton/config/buildin_abilities.json
> 内置默认值
```

### LLM 快速配置（`~/.auton/config.json`）

只需按照“安装步骤”中的 JSON 模板填入 provider/model/api_key，即可让 Auton 运行起来。**主 Agent 的 provider / model 只能在此文件配置**，`auton_config.json` 不再接收 LLM 字段；该文件优先级高于 `auton_config.json` / `buildin_abilities.json`，适合存放敏感 LLM 凭证。

### `~/.auton/config/` 中的 JSON

| 文件 | 作用 |
|------|------|
| `buildin_abilities.json` | 只管理内置 Subagent / Skill / Tool / Workflow 的启用状态及描述。 |
| `auton_config.json` | Auton 全局/项目级参数（记忆、日志、安全、MCP、`capabilities.project.*` 等，**不再**包含主 Agent 的 LLM 设置）。 |
| `extensions_abilities.json` | 预先组织 `~/.auton` 下可安装的能力结构，记录用户后续安装的名称、路径、版本、启用状态。 |

`buildin_abilities.json` 示例：

```json
{
  "subagents": {
    "planner": { "enabled": true, "role": "任务拆解与计划" },
    "debugging": { "enabled": true, "role": "系统化调试" },
    "tdd": { "enabled": true, "role": "TDD 工作流执行" },
    "code_review": { "enabled": true },
    "security": { "enabled": true },
    "refactor": { "enabled": true },
    "architect": { "enabled": true },
    "delegator": { "enabled": true }
  },
  "skills": {
    "ai-research": { "enabled": true },
    "code-review": { "enabled": true },
    "git-workflow": { "enabled": true },
    "github": { "enabled": true },
    "skill-creator": { "enabled": true },
    "web-search": { "enabled": true }
  },
  "tools": {
    "read": { "enabled": true },
    "write": { "enabled": true },
    "edit": { "enabled": true },
    "glob": { "enabled": true },
    "grep": { "enabled": true },
    "bash": { "enabled": true },
    "web_search": { "enabled": true },
    "web_fetch": { "enabled": true },
    "task_create": { "enabled": true },
    "task_get": { "enabled": true },
    "task_list": { "enabled": true },
    "task_stop": { "enabled": true },
    "mcp": { "enabled": true },
    "agent_create": { "enabled": true },
    "agent_list": { "enabled": true }
  },
  "workflows": {}
}
```

`auton_config.json` 示例（global + 项目覆盖）：

```json
{
  "global": {
    "memory": {
      "storage_dir": "~/.auton/memory",
      "chunk_size": 500,
      "chunk_overlap": 50,
      "vector_store": "chroma",
      "vector_db_path": "~/.auton/memory/vector_db"
    },
    "cron": {
      "enabled": false,
      "jobs_file": "~/.auton/cron/jobs.yaml",
      "logs_dir": "~/.auton/cron/logs"
    },
    "log": {
      "level": "INFO",
      "log_dir": "~/.auton/logs",
      "enable_file": true,
      "enable_console": true
    },
    "capabilities": {
      "project": {
        "skills": {},
        "subagents": {},
        "tools": {},
        "workflows": {}
      }
    }
  },
  "projects": {
    "__default__": {
      "security": {
        "permission_mode": "default"
      }
    },
    "/Users/demo/work/project-A": {
      "memory": {
        "storage_dir": "/Users/demo/work/project-A/.auton/memory"
      },
      "capabilities": {
        "project": {
          "skills": {
            "custom-review": {
              "enabled": true,
              "path": "/Users/demo/work/project-A/.auton/skills/custom-review"
            }
          }
        }
      }
    }
  }
}
```

`extensions_abilities.json` 用于记录用户后续安装的能力，结构示例：

```json
{
  "paths": {
    "skills_dir": "~/.auton/skills",
    "subagents_dir": "~/.auton/subagents",
    "workflows_dir": "~/.auton/workflows"
  },
  "capabilities": {
    "extensions": {
      "skills": {
        "langchain-retriever": {
          "enabled": true,
          "path": "~/.auton/skills/langchain-retriever",
          "version": "0.1.0"
        }
      },
      "subagents": {
        "my-reviewer": {
          "enabled": false,
          "path": "~/.auton/subagents/my-reviewer"
        }
      }
    }
  }
}
```
