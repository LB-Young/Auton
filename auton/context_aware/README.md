# Context Aware — 上下文感知

理解当前工作环境，主动提供相关帮助和建议。

## 目录结构

| 文件 | 职责 |
|------|------|
| `project_scanner.py` | 项目类型扫描器：检测 pyproject.toml / package.json / Cargo.toml 等判断项目类型 |
| `project_analyzer.py` | 项目结构分析器：解析目录树、依赖配置、主要模块 |
| `recent_history.py` | 最近操作历史感知：记录并理解用户最近编辑的文件和操作 |
| `suggestion_engine.py` | 主动建议引擎：基于上下文主动提供下一步行动建议 |

## 设计要点

- **主动建议**：不等待用户询问，在合适时机主动提供建议（如新文件创建后建议写测试）
- **项目感知**：`project_scanner` 在启动时扫描一次，缓存结果供整个会话使用
- **最近历史**：`recent_history` 记录最近 N 个编辑操作，用于推断用户当前的工作重点
- 与 Memory System 联动：上下文感知结果可写入会话记忆，供后续会话检索
