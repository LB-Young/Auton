# LangChain：Continual learning for AI agents

| 项 | 内容 |
|---|---|
| 机构 | LangChain（Harrison's In the Loop） |
| 作者 | Harrison Chase |
| 发布 | 2026-04-05 |
| 链接 | https://blog.langchain.com/continual-learning-for-ai-agents |
| 主题 | Agent 持续学习的三层：模型、Harness、上下文 |

> 本文件为阅读笔记，非原文转载。

## 核心内容

- 三层：
  - **模型**：更新权重（SFT、RL）。难点是灾难性遗忘；实践中多为整个 Agent 系统训练一个模型，很少按用户训练。
  - **Harness**：驱动 Agent 的代码，以及始终存在的指令和工具。例：Meta-Harness——在一批任务上运行并评估，把日志存进文件系统，让编码 Agent 阅读 trace 并提出 harness 代码修改。通常在 Agent 层面进行。
  - **上下文**：Harness 之外、用来配置它的指令、skill、甚至工具，也常被称为记忆。
- 对应关系示例：Claude Code（模型 / Claude Code / CLAUDE.md、skills、mcp.json）；OpenClaw（模型 / Pi 等脚手架 / SOUL.md、skills）。
- 上下文学习可以在多个层级进行：Agent 级（Agent 自己的持久记忆，如 OpenClaw 的 SOUL.md）；更常见的是租户级（用户、组织、团队各自的上下文，如 Hex Context Studio、Decagon Duet、Sierra Explorer）；也可以混合。
- 两种更新方式：事后离线批处理（扫描最近的 trace，提取洞见，更新上下文——OpenClaw 称为 "dreaming"）；在热路径中，Agent 边工作边更新记忆。
- 另一个维度：更新是显式的（用户让它记住）还是隐式的（Agent 按 harness 中的指令自己记）。
- **trace 是一切的核心**：三层的改进都依赖完整的执行轨迹。

## 对 Auton 的启示

1. **Harness 层的改进作为单独通道**：Auton 原则上不进化代码，但可以借鉴 Meta-Harness / OpenAI HALO：编码 Agent 阅读 trace 和评测结果，对 Auton 自身代码**提出 PR**，始终需要人工审查合并，并用同一套 Eval Store 回归。它与 Genome 进化并行，不共享自动发布通道。
2. **上下文的层级**：Auton 目前是全局 + 项目两级 overlay，可以预留"组织/团队"一级，供将来多人共享 Genome。
3. **显式记忆请求优先**：用户明确要求"记住"的内容，跳过 learnings 晋升门槛，直接作为 user-origin knowledge 写入（仍受敏感信息扫描）。
