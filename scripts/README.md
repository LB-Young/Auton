# Scripts — 脚本

## 快速开始

```bash
# 运行全部 debug 脚本
python scripts/debug_all.py

# 只运行某个里程碑
python scripts/debug_all.py --module M5

# 跳过需要网络的测试（M7 向量库、M11 MCP）
python scripts/debug_all.py --skip-network

# 列出所有可用模块
python scripts/debug_all.py --list
```

---

## 脚本索引

| 脚本 | 说明 | M里程碑 |
|------|------|---------|
| `debug_all.py` | 运行全部 debug 脚本 | — |
| `debug_m1_core.py` | CLI / SessionProcessor / EventBus / Message / Config | M1 |
| `debug_m2_tools.py` | ToolRegistry / MCP 集成 / 各内置工具 | M2 |
| `debug_m3_commands.py` | CommandRegistry / 命令解析 / 各内置命令 | M3 |
| `debug_m4_memory.py` | SessionMemory / ProjectMemory / GlobalMemory | M4 |
| `debug_m5_security.py` | PermissionManager / AuditLog / InjectionGuard | M5 |
| `debug_m6_skills.py` | SkillLoader / SkillRegistry / SkillInjector | M6 |
| `debug_m7_longterm_memory.py` | ChunkedStore / KeywordStore / BM25 / Forgetting | M7 |
| `debug_m8_planning.py` | Planner / TaskDecomposer / RiskAnalyzer / PlanStorage | M8 |
| `debug_m9_tasks.py` | TaskManager / TaskStore / TaskRunner / task_create | M9 |
| `debug_m10_workflow.py` | WorkflowStore / RunStore / DSLParser / WorkflowRunner | M10 |
| `debug_m11_mcp.py` | MCP / MCPTool / CLI 生命周期 | M11 |
| `debug_m12_agents.py` | AgentManager / agent_create / agent_list / /agents | M12 |
| `verify_m5.py` | M5 安全验证（独立脚本） | M5 |
| `test_actual_injection.py` | Prompt injection 实际测试 | M5 |
| `test_injection_charclass.py` | 字符类 injection 测试 | M5 |

---

## 每个脚本的测试项

### M1 — Core
- 模块导入、配置加载、EventBus 订阅/发布
- Session 创建/消息管理/compact 压缩
- Message + Part 结构、序列化
- LLMContext、PermissionMode 类型

### M2 — Tools
- ToolRegistry 单例、注册/查询/状态管理
- 按来源筛选、schema 生成、摘要
- BashTool / ReadTool 等内置工具实例化
- agent_create / agent_list 注册（M12）

### M3 — Commands
- CommandRegistry 单例、命令数量（14 个）
- HelpCommand / ModelCommand / CompactCommand 等
- CommandResult 数据类、参数模式匹配
- 所有命令 handle() 不抛异常

### M4 — Memory
- MemoryType 枚举、MemoryEntry 数据类
- MemoryManager 增/查/列表/过滤/持久化
- ProjectMemory / GlobalMemory
- SessionSummarizer、关键词提取、分块

### M5 — Security
- PermissionManager 4 种权限模式（default/auto/bypass/yolo）
- AuditLog 读写、AuditEntry
- InjectionGuard triple-backtick / horizontal-rule / comment
- KeyManager 单例、KeyInfo
- SecurityCommand /security 命令

### M6 — Skills
- Skill 类型、SkillSource 枚举
- parse_skill_text / write_skill_file / roundtrip
- SkillLoader / SkillRegistry / SkillInjector
- SkillSearcher / SkillChecker
- SkillCommand /skill 命令

### M7 — Long-term Memory
- split_into_chunks / extract_keywords
- KeywordStore BM25 增/查/排序/持久化
- compute_decay / score_memory / score_all_memories
- run_gc / get_forgetting_stats
- ConflictResolver / ChunkedStore

### M8 — Planning
- Plan / PlanStep / Risk / Alternative 数据类
- TaskDecomposer 分解、RiskAnalyzer 分析
- PlanFormatter / PlanStorage save/load/list
- Planner.create_plan、PlanStatus 转换

### M9 — Tasks
- Task / TaskStatus 枚举、is_terminal / is_runnable
- TaskStore 增/查/列表/过滤/持久化
- TaskManager 完整生命周期（create → running → completed/stopped）
- task_create / task_list 工具、/tasks 命令

### M10 — Workflow
- StepType / StepStatus / RunStatus 枚举
- WorkflowDefinition / WorkflowRun / WorkflowCondition
- DSLParser 解析（task/condition 步骤类型）
- DSLParseError、TemplateRenderer
- WorkflowStore / RunStore 持久化、list_active()

### M11 — Extensibility (MCP)
- MCPServerConfig / MCPConfig 模型
- MCPTool schema、execute list/status
- MCPCommand /mcp list/status
- load_mcp_servers(auto_start=False) 快速返回

### M12 — Multi-Agent
- AgentDefinition / AgentRun / AgentStatus
- AgentManager 加载（≥4 agents）、get/list/list_by_tools
- create_run / get_run / list_runs
- agent_create / agent_list 工具
- /agents list/show 命令
- ~/.auton/agents/ 文件加载

---

## 输出格式

```
[PASS] 测试名    — 测试通过
[FAIL] 测试名: 错误信息  — 测试失败
[WARN] 说明     — 警告（不影响退出码）
```

退出码：0 = 全部通过，1 = 有失败
