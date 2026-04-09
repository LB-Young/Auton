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

## 调试脚本

项目自带 3 个调试脚本，位于 `scripts/` 目录，方便在代码中打断点逐步跟踪核心链路。

> 运行前确保已激活虚拟环境：`conda activate auton_env`

### debug_query.py — 单轮对话

测试最基础的文本回复流程：用户输入 → Session → LLM 响应 → SessionStore 持久化。

```bash
# 默认问题
python scripts/debug_query.py

# 自定义问题
python scripts/debug_query.py "你好，介绍一下你自己"

# 指定 provider / model
python scripts/debug_query.py "你好" -p minimax -m MiniMax-M2.7
```

**核心断点：**
- `auton/agent/session.py:57` — `add_user_message`
- `auton/agent/agent.py:193` — `run_stream` 入口
- `auton/agent/agent.py:257` — `_handle_llm_event` 处理 LLM 流事件
- `auton/llm/anthropic_provider.py:78` — `stream` LLM 调用

### debug_multiturn.py — 多轮对话

测试多轮对话的上下文累积：每次 `run_stream()` 结束后续加 `session.add_user_message()`，再调 `run_stream()` 继续。

```bash
# 默认 3 轮
python scripts/debug_multiturn.py

# 自定义轮次
python scripts/debug_multiturn.py -q "你好" "你能做什么" "再见"

# 指定 provider
python scripts/debug_multiturn.py -q "你好" "你是谁" -p minimax
```

**核心断点：**
- `auton/agent/agent.py:248` — `_decide()` 决策（continue/stop）
- `auton/agent/session.py:65` — `add_assistant_message`
- `auton/agent/session.py:57` — `add_user_message`（每次续上下文）

### debug_tool.py — 工具调用

测试完整工具调用链路：LLM 决定调用工具 → `_execute_tools()` → `Tool.execute()` → 工具结果注入 `session.messages` → 第二轮 LLM 基于结果回复。

```bash
# 自动匹配合适工具
python scripts/debug_tool.py "读取 auton/__init__.py 的内容"

# 强制指定工具
python scripts/debug_tool.py --tool bash "echo hello"
python scripts/debug_tool.py --tool glob "**/*.py"
python scripts/debug_tool.py --tool grep "class Session"
python scripts/debug_tool.py --tool read "scripts/debug_query.py"

# 指定 provider / 权限模式
python scripts/debug_tool.py --tool glob "**/*.py" -p minimax -s yolo
```

**核心断点：**
- `auton/agent/agent.py:296` — `_handle_llm_event` 捕获 `tool_use` 事件
- `auton/agent/agent.py:314` — `_execute_tools` 工具执行入口
- `auton/agent/agent.py:337` — `tool.execute()` 实际工具逻辑
- `auton/agent/agent.py:348` — 工具结果注入 `session.messages`

### 断点速查表

| 断点位置 | 文件:行号 | 说明 |
|---|---|---|
| 添加用户消息 | `agent/session.py:57` | `add_user_message` |
| `run_stream` 入口 | `agent/agent.py:193` | 主循环启动 |
| LLM 流事件处理 | `agent/agent.py:257` | `_handle_llm_event` |
| 工具调用决策 | `agent/agent.py:296` | `tool_use` 事件 |
| 工具执行入口 | `agent/agent.py:314` | `_execute_tools` |
| 工具结果注入 | `agent/agent.py:348` | 结果写入 session |
| 决策 | `agent/agent.py:248` | `_decide` → continue/stop |
| LLM Provider | `llm/anthropic_provider.py:78` | `stream` |
| Session 存储 | `agent/session_store.py:50` | `append_event` |
| 归档 | `agent/session_store.py:130` | `archive_session` |

## 运行测试

```bash
# 端到端测试（3 个 E2E 场景）
python -m pytest tests/e2e/ -v

# 单元测试
python -m pytest tests/unit/ -v

# 带覆盖率
python -m pytest tests/ --cov=auton --cov-report=term-missing
```

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

## 内置工具

| 工具 | 说明 |
|------|------|
| `read` | 读取文件内容 |
| `write` | 创建或覆盖文件 |
| `edit` | 替换文件中指定字符串 |
| `glob` | 文件名模式匹配 |
| `grep` | 正则搜索文件内容 |
| `bash` | 执行 Shell 命令 |
| `browser` | 浏览器自动化（Playwright） |
| `web_search` | 网络搜索（需配置 API） |
| `web_fetch` | 抓取网页内容 |
| `git` | Git 操作代理 |
| `http` | 发送 HTTP 请求 |

## 项目结构

```
auton/
├── core/           # 核心基础设施
│   ├── config.py       # 配置加载
│   ├── events.py       # 事件总线
│   ├── event_types.py  # 事件类型定义
│   ├── logging.py       # 日志配置
│   ├── snapshot.py     # 快照管理
│   └── errors.py       # 错误类型
├── agent/          # Agent 核心
│   ├── agent.py         # SessionProcessor 主循环
│   ├── context.py       # LLM 上下文构建
│   ├── policies.py      # 决策策略
│   ├── session.py       # 会话管理
│   ├── session_store.py # append-only 存储
│   └── message.py       # Part 化消息模型
├── llm/            # LLM 接口层
│   ├── base.py          # Provider 抽象
│   ├── anthropic_provider.py  # Anthropic 实现
│   └── prompt.py        # Prompt 模板
├── tools/          # 工具系统
│   ├── base.py          # Tool 基类
│   ├── bash.py
│   ├── read.py
│   ├── write.py
│   ├── edit.py
│   └── ...
└── cli/            # CLI 入口
    └── main.py          # Typer 命令
```

## 架构设计

详见 [docs/DESIGN.md](./docs/DESIGN.md) 和 [docs/Feature.md](./docs/Feature.md)。

### 核心循环（SessionProcessor）

```
while True:
    1. build context from session + memory
    2. stream LLM response (emit events)
    3. handle tool calls
    4. policy.decide() → continue / compact / stop
```

### 存储/检索分离

- `session_store.py` 只负责 append jsonl，永不修改
- `memory_manager.py` 只负责读取和检索
- 两者完全解耦
