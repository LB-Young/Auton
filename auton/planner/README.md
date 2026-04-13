# Planner — 规划引擎

将复杂目标分解为可执行步骤，支持风险识别、替代方案生成和持久化管理。

> **架构说明：** `auton/planner/` 与 `auton/subagents/planner/` 是互补关系。
> - `auton/planner/` — 生产级规划引擎，调用 LLM，持久化存储
> - `auton/subagents/planner/` — LLM 的 system prompt 提示词模板
> 详见 [docs/subagent-planner-architecture.md](../../docs/subagent-planner-architecture.md)

## 目录结构

| 文件 | 职责 |
|------|------|
| `engine.py` | 主引擎：协调分解、风险、方案、存储 |
| `decomposer.py` | 任务分解器：调用 LLM 将高层目标拆解为原子步骤 |
| `risks.py` | 风险分析器：评估每步风险等级（low/medium/high） |
| `formatter.py` | 格式化器：将 Plan 对象渲染为 Markdown |
| `storage.py` | 持久化存储：SQLite 保存所有计划 |
| `types.py` | 数据模型：Plan, PlanStep, Risk, Alternative |

## 核心概念

### 计划生命周期

```
draft → proposed → confirmed → in_progress → completed
                                  ↘ cancelled / failed
```

### 计划数据结构

- **Plan** — 完整计划，含任务、目标、步骤、风险、替代方案
- **PlanStep** — 单个步骤，含描述、工具、参数、依赖、置信度
- **Risk** — 风险项，含等级、描述、缓解措施
- **Alternative** — 替代方案，含名称、变更点、置信度、权衡

## 使用示例

```python
from auton.planner import Planner

# 初始化（需要 LLM Provider）
planner = Planner(llm=llm_provider)

# 生成计划
plan = planner.plan(
    task="重构 auth 模块",
    context="FastAPI + SQLAlchemy + Pydantic",
)

# plan 是结构化对象
print(f"计划 ID: {plan.id}")
print(f"目标: {plan.goal}")
print(f"步骤数: {plan.step_count()}")
print(f"风险等级: {plan.total_risk()}")

# 遍历步骤
for step in plan.steps:
    print(f"  [{step.index}] {step.description} (tool={step.tool})")

# 格式化输出
print(planner.format(plan))

# 生命周期管理
planner.confirm(plan.id)    # 确认计划
planner.complete(plan.id)   # 标记完成

# 查看历史
plans = planner.list_plans(status="completed")
```

## 与 Subagent 的协作

```
用户请求规划
    ↓
TaskDelegatorSubagent 分析任务
    ↓
PlannerSubagent.system_prompt() 注入 LLM
    ↓
LLM 生成轻量 Markdown 计划
    ↓
（或）auton.planner.Planner 深度规划
    ↓
分派给 TDDRunnerSubagent / CodeReviewSubagent 等执行
```

## 风险分析

`RiskAnalyzer` 自动识别：

- 高风险：删除文件、重写核心逻辑、破坏性迁移
- 中风险：新增依赖、修改接口、大规模重构
- 低风险：新增辅助函数、文档更新、小范围调整

每步附带缓解建议（mitigation）。
