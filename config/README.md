# Config — 配置文件

## 配置文件位置

运行时配置会按以下顺序查找（后者覆盖前者）：

| 优先级 | 路径 | 说明 |
|--------|------|------|
| 1 | CLI 参数 | `--model`, `--provider` 等 |
| 2 | 环境变量 | `ANTHROPIC_API_KEY`, `MINIMAX_API_KEY` 等 |
| 3 | `~/.auton/config.yaml` | 用户全局配置 |
| 4 | `.auton/config.yaml` | 项目级配置 |
| 5 | `config/default.yaml` | 本仓库默认配置 |

## 快速上手

**1. 创建用户配置：**
```bash
mkdir -p ~/.auton
cp config/default.yaml ~/.auton/config.yaml
```

**2. 修改 API Key：**
```yaml
llm:
  provider: minimax  # 或 anthropic
  api_key: "your-key-here"
```

**3. 验证生效：**
```bash
auton main -m "你好"
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `default.yaml` | **完整配置示例**，所有参数及注释 |
| `tools.yaml` | 工具配置：超时/白名单/沙箱参数（待实现） |
| `heartbeat.yaml` | 心跳配置模板（待实现） |
| `cron.yaml` | Cron 配置模板（待实现） |

## 环境变量

| 变量 | 对应配置 | 说明 |
|------|---------|------|
| `ANTHROPIC_API_KEY` | `llm.api_key` | Anthropic API Key |
| `MINIMAX_API_KEY` | `llm.api_key` | MiniMax API Key |
| `OPENAI_API_KEY` | `llm.api_key` | OpenAI API Key |
| `AUTON_LLM_MODEL` | `llm.model` | 默认模型 |
| `AUTON_LOG_LEVEL` | `log.level` | 日志级别 |
