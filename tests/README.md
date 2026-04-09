# Tests — 测试套件

## 目录结构

| 目录 | 测试类型 | 说明 |
|------|----------|------|
| `unit/` | 单元测试 | 每个模块独立测试，使用 pytest + unittest.mock |
| `unit/core/` | 核心模块测试 | config / events / snapshot |
| `unit/agent/` | Agent 模块测试 | session_processor / session_store |
| `unit/llm/` | LLM 模块测试 | router / prompt 模板 |
| `unit/tools/` | 工具测试 | 每个工具独立测试 |
| `unit/commands/` | 命令测试 | handler / registry |
| `unit/memory/` | 记忆系统测试 | session_summarizer / memory_md / conflict_resolver |
| `unit/heartbeat/` | 心跳测试 | scheduler / checklist / contracts |
| `unit/cron/` | 定时任务测试 | triggers / executor / retry |
| `unit/planner/` | 规划引擎测试 | task_decomposer / plan_revisor |
| `unit/task/` | 任务系统测试 | state_machine / registry |
| `unit/workflow/` | 工作流测试 | parser / engine / checkpoint |
| `unit/security/` | 安全测试 | permission / path_validator |
| `unit/skills/` | 技能系统测试 | loader / injector / frontmatter |
| `integration/` | 集成测试 | SessionProcessor 执行闭环 / 记忆系统全流程 / 事件总线 |
| `e2e/` | E2E 测试 | CLI 端到端测试 |
| `fixtures/` | 测试固件 | mock 数据 / 测试数据库 |

## 测试覆盖率目标

- **单元测试**：每个模块 > 80% 覆盖率
- **集成测试**：核心链路（SessionProcessor / Memory 全流程）必须有集成测试
- **E2E 测试**：CLI 主路径（run / serve / TUI）

## 测试约定

- `test_*.py` 命名
- `pytest.ini` 配置覆盖率阈值
- Fixtures 放在 `conftest.py`
- Mock 外部依赖（LLM API / 文件系统）
