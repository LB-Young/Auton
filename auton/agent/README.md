# Agent — Agent 核心

SessionProcessor 是唯一主循环，职责单一：continue / compact / stop 三态控制。

## 目录结构

| 文件 | 职责 |
|------|------|
| `agent.py` | ★ SessionProcessor 主执行循环（不超过 200 行）：while True → build_messages → llm.stream → 事件分发 → 三态决策 |
| `session.py` | 会话管理：多会话支持、compact 压缩、rewind 回退 |
| `context.py` | 动态上下文构建：从 Session + Memory 加载消息历史，构建 LLM 请求 |
| `message.py` | ★ Part 化消息模型：TextPart / ReasoningPart / ToolPart / StepPart，独立更新 |
| `session_store.py` | ★ Append-only 会话存储：每事件 append 到 jsonl，compact 时原始行 + 摘要同时 append |
| `policies.py` | 行为策略：何时询问、何时自治、何时停止 |
| `types.py` | Agent 相关数据类型（SessionStatus / Part 类型等） |

## 设计要点

- **Part 化消息**：一个 Message 包含多个 Part，每种 Part 独立增量更新，支持流式渲染
- **Append-only**：存储（session_store.py）和检索（memory_manager.py）完全分离，互不感知
- **三态控制**：`continue` 继续下一轮 LLM；`compact` 压缩历史后继续；`stop` 回到 idle
- **Compact 行为**：压缩时原始 jsonl 行 + compact 摘要事件同时 append，不修改原行
