# Auton

> 个人 AI Agent 助手 — 参考 Claude Code v2.1.88 和 OpenCode 架构设计

## 模块概览

| 模块 | 说明 |
|------|------|
| `core/` | 核心基础设施：配置、事件总线、快照、日志、错误类型 |
| `agent/` | Agent 核心：SessionProcessor 主循环、Part 化消息、会话管理、append-only 存储 |
| `llm/` | LLM 接口层：多 Provider 抽象（Anthropic/OpenAI/Ollama）、Prompt 管理 |
| `tools/` | 工具系统：每个工具独立目录，Registry 统一管理 |
| `commands/` | 斜杠命令系统：/help /memory /tasks /cron 等 |
| `memory/` | 记忆系统：四类记忆、三层检索、冲突管理、auton.md |
| `heartbeat/` | 心跳机制：HEARTBEAT.md 检查清单、主会话周期性感知 |
| `cron/` | 定时任务：at/every/cron 调度、announce/webhook/none 交付、指数退避重试 |
| `planner/` | 规划引擎：任务分解、计划执行、动态调整 |
| `task/` | 后台任务系统：状态机、输出文件、断点续执 |
| `workflow/` | 工作流引擎：DSL 解析、断点管理 |
| `security/` | 安全与权限：四模式权限、审计日志、路径校验 |
| `context_aware/` | 上下文感知：项目扫描、结构分析、主动建议 |
| `skills/` | 技能系统：SKILL.md 加载、渐进式披露、experiences 经验记录 |
| `plugins/` | 插件系统：热加载、沙箱隔离 |
| `api/` | API 服务：FastAPI 路由层 |
| `cli/` | CLI 入口：Typer 命令注册 |
