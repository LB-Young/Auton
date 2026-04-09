# API — API 服务

FastAPI + Uvicorn，提供 HTTP API 接口，支持 Web 客户端和远程调用。

## 目录结构

| 文件 | 职责 |
|------|------|
| `server.py` | FastAPI 应用入口：路由注册、中间件（认证/日志/限流）、启动 Uvicorn |
| `middleware.py` | 中间件：JWT 认证 / 结构化日志 / 速率限制（基于 limits） |
| `routes/` | API 路由 |
| `routes/chat.py` | 对话路由：POST /chat（请求通道） + SSE 事件流 |
| `routes/memory.py` | 记忆管理路由：GET/POST/DELETE /memory |
| `routes/task.py` | 任务管理路由：GET/POST /tasks |
| `routes/tool.py` | 工具管理路由：列出可用工具、调用工具 |

## API 路由

| 端点 | 方法 | 说明 |
|------|------|------|
| `/chat` | POST | 发送消息，返回 SSE 事件流 |
| `/memory` | GET/POST/DELETE | 记忆 CRUD |
| `/tasks` | GET/POST/DELETE | 任务 CRUD |
| `/tools` | GET | 列出可用工具 |

## 设计要点

- **请求通道 + 事件通道分离**：HTTP POST 下发 prompt，SSE 上行推送事件流
- **认证**：JWT Bearer Token，支持用户级 API Key
- **限流**：基于 IP + User 的双维度限流，防止滥用
- **无状态**：API Server 无状态，会话状态在 `session_store.py` 持久化
