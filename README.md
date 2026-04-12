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
pip install -e ".[dev]"
```

> `pip install -e .` 会以 editable（开发）模式安装，代码修改后无需重新安装。  
> `[dev]` 包含 pytest / pytest-asyncio / ruff / mypy 等开发工具。

### 3. 配置 API Key

```bash
# 创建配置文件
mkdir -p ~/.auton
cp config/default.yaml ~/.auton/config.yaml

# 编辑 API Key
# - Anthropic: 设置 provider=anthropic + api_key
# - MiniMax:   设置 provider=minimax   + api_key
```

或直接用环境变量：
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
export MINIMAX_API_KEY="your-minimax-api-key"
```

完整配置示例见 `config/default.yaml`，所有参数均有注释说明。

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
CLI args > 环境变量 > 项目配置 .auton/config.yaml
> 用户配置 ~/.auton/config.yaml > 默认值
```

### 完整配置示例

```yaml
# ~/.auton/config.yaml

llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key: "sk-..."
  max_tokens: 8192
  temperature: 0.0
  timeout: 60.0

memory:
  storage_dir: ~/.auton/memory
  chunk_size: 500
  chunk_overlap: 50
  vector_store: chroma
  vector_db_path: ~/.auton/memory/vector_db

heartbeat:
  enabled: false
  every: "30m"
  active_hours: "9:00-18:00"
  session_mode: main
  light_context: true

cron:
  enabled: false
  jobs_file: ~/.auton/cron/jobs.yaml
  logs_dir: ~/.auton/cron/logs

security:
  permission_mode: default  # default / auto / bypass / yolo
  audit_enabled: true
  sandbox_enabled: true
  max_bash_timeout: 60

log:
  level: INFO
  log_dir: ~/.auton/logs
  enable_file: true
  enable_console: true
```
