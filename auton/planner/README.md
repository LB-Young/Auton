# Planner — 规划引擎

将复杂目标分解为可执行步骤，支持动态调整和风险识别。

## 目录结构

| 文件 | 职责 |
|------|------|
| `planner.py` | 主规划器：调用 LLM 生成计划，输出结构化步骤列表 |
| `task_decomposer.py` | 任务分解器：将高层目标拆解为原子可执行子任务 |
| `plan_executor.py` | 计划执行器：与 SessionProcessor 协同，按序/并行执行子任务 |
| `plan_revisor.py` | 计划动态调整器：遇阻时重新规划，保留已完成步骤 |
| `risk_analyzer.py` | 风险分析器：执行前识别风险点、瓶颈、依赖项 |

## 设计要点

- **计划格式**：结构化步骤列表（step / description / tool / depends_on / rollback）
- **动态调整**：执行失败时，`plan_revisor` 基于已完成步骤重新规划，不重复执行
- **风险前置**：执行前通过 `risk_analyzer` 标记高风险步骤，供用户确认
- **与 SessionProcessor 协同**：Plan Executor 在 SessionProcessor 之上编排，不替代主循环
