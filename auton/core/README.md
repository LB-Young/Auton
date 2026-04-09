# Core — 核心基础设施

所有模块共享的基础组件，不依赖上层业务逻辑。

## 目录结构

| 文件 | 职责 |
|------|------|
| `config.py` | 配置加载（YAML / env / CLI args，优先级：CLI > env > YAML > default） |
| `events.py` | 事件总线：全系统模块间通信，所有 UI/记录器/快照订阅事件流 |
| `event_types.py` | 结构化事件类型定义（text-* / reasoning-* / tool-* / step-* / system-*） |
| `errors.py` | 统一错误类型（`RetryableError` vs `FatalError`） |
| `logging.py` | 结构化日志（JSON + Console 双输出，基于 Loguru） |
| `snapshot.py` | 快照与 Patch 系统：每步执行前后记录快照，产出 patch 文件清单 |

## 设计要点

- **事件总线**是一等公民：所有模块间通信走事件，UI 订阅增量渲染，AuditLog 记录，Snapshot 构建
- **Snapshot** 驱动可追溯性：每个 `step-finish` 事件携带 `files_changed` 列表，供 Snapshot 模块记录
- 配置分层：开发环境 / 生产环境 / CI 环境通过不同 YAML 文件覆盖
- 错误类型分层：`RetryableError`（网络超时等可重试）vs `FatalError`（权限拒绝等不可重试）
