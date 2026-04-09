# Heartbeat — 心跳机制

在主会话中周期性插入轻量 turn，读取检查清单并响应，维持"常驻感知"状态。

## 目录结构

| 文件 | 职责 |
|------|------|
| `config.py` | 心跳配置：every（间隔）/ active_hours / session_mode / light_context / target |
| `scheduler.py` | 心跳调度器：asyncio Timer，按 every 间隔定时触发，active_hours 生效判断 |
| `heartbeat_manager.py` | 心跳管理器：触发心跳 turn → 读取 HEARTBEAT.md → 执行检查清单 → 写入契约 |
| `checklist.py` | HEARTBEAT.md 读写与解析：提取所有 `-[ ]` 未完成条目 |
| `contracts.py` | HEARTBEAT_OK / HEARTBEAT_ASK 契约写入：心跳完成后写入状态块 |

## HEARTBEAT.md 格式
```markdown
# Heartbeat Checklist

## 待处理任务
- [ ] review PR #42
- [ ] 确认部署时间

## 待确认决策
- [ ] auth 模块是否采用 JWT？

---
# HEARTBEAT_OK
timestamp: 2024-01-15T15:30:00
issues_responded: 2
issues_raised: 0
```

## 配置项（heartbeat.yaml）
```yaml
enabled: true
every: "30m"              # 间隔（5m / 1h / 2h / 自定义）
active_hours: "9:00-18:00"  # 仅此时段生效（可选，默认全天）
session_mode: "main"      # main | isolated
light_context: true       # isolated 模式建议开启，减少 token 消耗
target: "main"           # main | isolated | current
```

## 设计要点

- **main-session 模式**：主会话周期性被打断，执行心跳 turn 后恢复等待（携带完整上下文）
- **isolated 模式**：独立 session turn，不影响主会话上下文，token 消耗低
- **light_context**：isolated + light_context = 仅加载 auton.md + HEARTBEAT.md，适合高频心跳（每 5 分钟）
- **HEARTBEAT_OK**：心跳正常完成时写入，包含 issues_responded / issues_raised 统计
- **HEARTBEAT_ASK**：有问题需要用户确认时写入，附具体问题描述
