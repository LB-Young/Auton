# Subagent 与 Planner 模块架构说明

> 本文档说明 `auton/subagents/` 和 `auton/planner/` 两个模块的关系与职责边界。

---

## 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent (SessionProcessor)                │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   ┌──────────┐  ┌──────────┐  ┌────────────┐
   │ Planner  │  │ Subagents │  │ Skills     │
   │ Subagent │  │ (8 个)    │  │ System     │
   └────┬─────┘  └────┬─────┘  └────────────┘
        │             │
        │    ┌────────┴────────┐
        │    ▼                 ▼
        │ ┌──────────────────────────┐
        └►│   auton.planner.*        │  (生产级规划引擎)
          │  - TaskDecomposer        │
          │  - RiskAnalyzer          │
          │  - PlanStorage (SQLite)   │
          └──────────────────────────┘
```

---

## 两个模块的本质区别

| | `auton/subagents/` | `auton/planner/` |
|---|---|---|
| **定位** | Subagent 的**系统提示词模板** | **生产级规划引擎** |
| **执行者** | LLM（通过 system_prompt 注入） | Python 代码 |
| **是否有状态** | 无（每次调用独立） | 有（SQLite 持久化） |
| **是否调用 LLM** | 否（仅提供提示词） | 是（TaskDecomposer 调用 LLM） |
| **输出** | Markdown 文本 | 结构化 `Plan` 对象 |
| **生命周期管理** | 无 | proposed → confirmed → completed |

---

## `auton/planner/` — 生产级规划引擎

**文件结构：**

```
auton/planner/
├── types.py        # Plan, PlanStep, Risk, Alternative 数据模型
├── decomposer.py   # LLM 驱动的任务分解
├── risks.py        # 风险分析与评估
├── formatter.py   # 计划格式化输出
├── storage.py      # SQLite 持久化存储
├── engine.py       # 协调所有组件的 Planner 主引擎
└── README.md      # 详细使用说明
```

**核心能力：**

1. **任务分解** — `TaskDecomposer` 调用 LLM 将复杂任务分解为有序步骤
2. **风险分析** — `RiskAnalyzer` 评估每步风险等级（low/medium/high）
3. **替代方案** — 自动生成渐进式重构等备选方案
4. **持久化存储** — SQLite 保存所有计划，支持版本追踪
5. **生命周期管理** — `proposed → confirmed → in_progress → completed`

**使用示例：**

```python
from auton.planner import Planner

planner = Planner(llm=llm_provider)
plan = planner.plan("重构 auth 模块", context="FastAPI + SQLAlchemy")

# plan 是一个完整的结构化对象
print(plan.goal)           # "在不改变外部行为的前提下改善代码质量"
print(plan.steps[0].tool) # "Edit"
print(plan.risks[0].level) # "high"

# 确认计划
planner.confirm(plan.id)

# 标记完成
planner.complete(plan.id)
```

---

## `auton/subagents/planner/` — LLM 提示词模板

**文件结构：**

```
auton/subagents/planner/
├── __init__.py
└── planner.py   # PlannerSubagent
```

**职责：** 提供一段 `system_prompt()` 文本，告诉 LLM **如何做规划**。

**内容要点：**
- 每个步骤 2-5 分钟的小粒度分解
- 精确文件路径（exact file paths）
- 每个步骤完整的 TDD 循环（RED → GREEN → REFACTOR）
- DRY、YAGNI 原则
- 频繁小提交

---

## 协作模式

Agent 在不同场景下使用不同组件：

### 场景 1：LLM 自己生成计划（轻量）

```
用户: "帮我规划一个登录功能"
  → Agent 注入 PlannerSubagent.system_prompt()
  → LLM 生成 Markdown 计划（PlannerSubagent._execute()）
  → Agent 返回给用户
```

### 场景 2：生产级规划（重量）

```
用户: "/plan 重构整个 auth 模块"
  → Agent 调用 auton.planner.Planner.plan()
  → LLM 深度分解 + 风险分析 + 存储
  → 返回结构化 Plan 对象
  → 支持确认/取消/修改/版本追踪
```

### 场景 3：其他 Subagent 也用 Planner

```
用户: "帮我实现一个新功能"
  → TaskDelegatorSubagent 分析任务
  → 发现需要规划 → 调用 PlannerSubagent
  → 生成计划后分派给 TDDRunnerSubagent 等执行
```

---

## 关键设计决策

### 为什么不让 PlannerSubagent 直接调用 LLM？

Subagent 的设计原则是**无状态工具类**：
- `run(context)` 是一次性调用，不保留结果
- 无法管理 `Plan` 对象的生命周期（confirmed/completed）
- 无法持久化，无法版本追踪

真正的规划需要状态管理，所以由 `auton.planner.Planner` 处理。

### 为什么还要 PlannerSubagent？

作为 **system prompt 注入**，PlannerSubagent 让任何 LLM 调用都能获得高质量的规划指导：
- 不需要导入 `auton.planner` 依赖
- 不需要启动 SQLite 连接
- 作为 Skill/MCP 的轻量补充

---

## 何时用哪个

| 场景 | 使用 |
|------|------|
| LLM 对话中生成轻量计划 | `PlannerSubagent` |
| `/plan` 命令式规划 | `auton.planner.Planner` |
| 多 Subagent 协作中的规划 | `PlannerSubagent` (via TaskDelegator) |
| 需要持久化/版本管理 | `auton.planner.Planner` |
| 需要风险分析/替代方案 | `auton.planner.Planner` |
| LLM system prompt 模板 | `PlannerSubagent.system_prompt()` |
