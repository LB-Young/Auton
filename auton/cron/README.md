# Cron — 定时任务系统

精确时间点的独立自动化任务，与心跳互补：心跳维持感知，cron 处理精确时机。

## 目录结构

| 文件 | 职责 |
|------|------|
| `config.py` | Cron Job 配置结构：name / schedule / session / delivery / retry |
| `scheduler.py` | Cron 调度器：基于 croniter，计算下一次触发时间，注册 asyncio Task |
| `triggers.py` | 触发器解析：支持 at（一次性）/ every（间隔）/ cron（标准 5 字段）表达式 |
| `job_manager.py` | 任务注册表：持久化到 jobs.yaml，支持 add/edit/remove/enable/disable |
| `executor.py` | 任务执行器：main-session（系统事件触发）vs isolated（独立 turn） |
| `delivery.py` | 交付模式：announce（主会话输出）/ webhook（POST JSON）/ none（仅日志） |
| `retry.py` | 指数退避重试：30s → 1m → 5m → 15m → 60m，连续失败 N 次后暂停 |
| `logs.py` | 任务日志：每个执行一个 jsonl，记录时间/耗时/输入输出/退出码 |

## jobs.yaml 配置结构
```yaml
jobs:
  - name: "daily-report"
    schedule: "0 9 * * *"           # 每天早上 9 点
    session: "isolated"             # 隔离会话
    light_context: true
    delivery: "announce"
    webhook_url: "https://..."     # delivery=webhook 时填写
    enabled: true
    description: "生成每日开发报告"
    retry:
      max_attempts: 3
      backoff: "exponential"

  - name: "deploy-check"
    schedule: "every 1h"
    session: "main"
    delivery: "announce"
    enabled: false
```

## 调度类型
| 类型 | 格式 | 示例 |
|------|------|------|
| at（一次性） | `at YYYY-MM-DD HH:MM` | `at 2024-01-20 09:00` |
| every（间隔） | `every <duration>` | `every 1h`, `every 30m`, `every 1d` |
| cron（表达式） | 标准 5 字段 | `0 9 * * 1-5`（工作日 9 点）|

## 存储结构
```
~/.auton/cron/
  jobs.yaml              # 所有定时任务配置
  logs/                  # 执行日志
    daily-report/
      2024-01-15T09-00-00.jsonl
    deploy-check/
      ...
```

## 设计要点

- **main-session**：作为主会话的系统事件触发，下次心跳时执行，适合与上下文相关的任务
- **isolated**：完全隔离的独立 agent turn，适合定时报告、数据采集
- **指数退避重试**：30s → 1m → 5m → 15m → 60m，连续失败 3 次后暂停并写入 HEARTBEAT_ASK
- **与心跳组合**：心跳维持持续感知（定期检查提醒/待办），cron 处理精确时机任务
