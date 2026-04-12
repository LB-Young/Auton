# CLI — 命令行入口

基于 Typer 的 CLI 应用，注册所有子命令，统一入口。

## 目录结构

| 文件 | 职责 |
|------|------|
| `main.py` | ★ CLI 主入口：Typer 应用注册，聚合所有子命令 |
| `chat.py` | 交互式对话命令：默认 TUI 入口 |
| `run.py` | 单次执行命令：`auton run <prompt>` |
| `serve.py` | 服务启动命令：`auton serve` 启动 API Server |
| `tui.py` | TUI 渲染模块：基于 Rich / Textual 的终端 UI |

## CLI 子命令

| 命令 | 说明 |
|------|------|
| `auton` | 启动交互式 TUI（默认） |
| `auton run <prompt>` | 单次执行 prompt |
| `auton serve` | 启动 API Server |
| `auton skill list` | 列出所有技能 |
| `auton memory list` | 列出所有记忆 |
| `auton cron list` | 列出所有定时任务 |

## 设计要点

- **默认 TUI**：不传参数时启动交互式 TUI，支持流式输出
- **run vs serve**：run 是单次执行（headless），serve 是常驻 HTTP 服务
- **结构化输出**：所有命令输出 JSON 或 Markdown，便于脚本消费
