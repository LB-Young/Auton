# 里程碑索引

本文档记录 Auton 项目所有里程碑的开发进度。

---

## 里程碑总览

| 里程碑 | 名称 | 状态 | 完成日期 |
|--------|------|------|----------|
| M1 | Core | ✅ 已完成 | 2026-04-07 |
| M2 | Tools | ✅ 已完成 | 2026-04-07 |
| M3 | Commands | ✅ 已完成 | 2026-04-07 |
| M4 | Memory | ✅ 已完成 | 2026-04-07 |
| M5 | Security | ✅ 已完成 | 2026-04-07 |
| M6 | Skills | ✅ 已完成 | 2026-04-07 |
| M7 | Long-term Memory | ✅ 已完成 | 2026-04-07 |
| M8 | Planning | ✅ 已完成 | 2026-04-07 |
| M9 | Tasks | ✅ 已完成 | 2026-04-07 |
| M10 | Workflow | ✅ 已完成 | 2026-04-07 |
| M11 | Extensibility | ✅ 已完成 | 2026-04-07 |
| M12 | Multi-Agent | ✅ 已完成 | 2026-04-07 |

**状态说明**:
- ✅ 已完成 — 功能全部实现并测试通过
- 🔄 开发中 — 正在开发中
- 📋 待开发 — 尚未开始

---

## 里程碑详情

### [M1 — Core](./M1.md)
CLI 入口、SessionProcessor 执行闭环、Part 化消息、事件总线、内置 8 工具、MiniMax 支持、append-only JSONL 存储。

### [M2 — Tools](./M2.md) ✅
工具注册表、BashTool 7 层安全校验、MCP 协议集成。

### [M3 — Commands](./M3.md) 🔄
斜杠命令系统、命令注册表、Command 接口。

### [M4 — Memory](./M4.md) 🔄
会话记忆、项目记忆（指针文件）。

### [M5 — Security](./M5.md) ✅
权限系统（BashTool 7 层安全）、审计日志。

### [M6 — Skills](./M6.md) 📋
技能系统（SKILL.md + scripts/ + references/ + 渐进式披露）、skill-creator 内置技能、/skill 管理命令。

### [M7 — Long-term Memory](./M7.md) ✅
长期记忆（BM25 关键词检索）、遗忘策略、四层检索、/memory 命令（list/search/get/edit/delete/gc/reindex/stats）。

### [M8 — Planning](./M8.md) ✅
规划引擎、任务分解、风险分析、多方案比较、/plan 命令（confirm/list/show/modify/cancel）。

### [M9 — Tasks](./M9.md) ✅
后台任务系统、任务状态机、task_create/get/list/stop 工具、/tasks 命令（list/get/stop/retry/stats）。

### [M10 — Workflow](./M10.md) ✅
工作流引擎、DSL（YAML）、断点续执、条件分支、/workflow 命令（list/show/run/pause/resume/stop/log/delete/create）。

### [M11 — Extensibility](./M11.md) ✅
MCP 集成（MCPClient / MCPTool / /mcp 命令）、CLI 生命周期管理。

### [M12 — Multi-Agent](./M12.md) ✅
子代理委托、多 Agent 协作。

---

## 添加新里程碑

每个里程碑完成后，在本目录新建 `M{n}.md` 文件（{n} 为里程碑编号），
并在上面的总览表中添加对应条目。
