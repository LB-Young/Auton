# Anthropic：New in Claude Managed Agents — dreaming, outcomes, and multiagent orchestration

| 项 | 内容 |
|---|---|
| 机构 | Anthropic（Claude Platform 产品更新） |
| 作者 | 页面未署名 |
| 发布 | 2026-05-19 |
| 链接 | https://claude.com/blog/new-in-claude-managed-agents |
| 主题 | Dreaming（研究预览）、Outcomes（rubric + 独立评分者驱动返工）、多 Agent 编排 |

> 本文件为阅读笔记，非原文转载。

## 核心内容

- **Dreaming**：定时进程，回顾 Agent 会话与记忆存储，提取模式并整理记忆；可以自动更新记忆，也可以先审查再生效。能发现单个 Agent 看不到的模式：反复出现的错误、Agent 趋同的工作流程、团队共享的偏好；并重组记忆以保持高信噪比。
- **Outcomes**：开发者写下描述成功标准的 rubric；**独立评分者在自己的上下文窗口中**按标准评估输出，不受 Agent 推理过程影响；不合格时指出需要修改之处，Agent 再做一轮。适用于注重细节、全面覆盖或主观质量（品牌语气、视觉规范）的任务。
- **多 Agent 编排**：主 Agent 拆分任务，委派给各自拥有模型、提示词、工具的子 Agent；子 Agent 在共享文件系统上并行工作；事件持久化，每一步可追踪（谁做了什么、为什么）。

## 数据（页面自述）

- Outcomes 相比标准提示循环，任务成功率最多提高 10 个百分点，最难的问题提升最大；内部基准 docx +8.4%、pptx +10.1%。
- 客户案例：Harvey 用 Dreaming 记住文件类型变通方法与工具模式，完成率约 6 倍；Wisedocs 用 Outcomes 审查速度快 50%；Spiral 用"从记忆中提取的编辑原则 + 用户文风"构成 rubric 给草稿打分，只返回达标草稿。
- 页面未给出测试设置与样本量。

## 原文短句

- "dreaming can update memory automatically, or you can review changes before they land."
- "A separate grader evaluates the output against your criteria in its own context window"

## 对 Auton 的启示

1. **运行时 Outcome 检查**：对重要任务，用独立上下文的评分者按 rubric 检查产出并驱动返工。它既是运行时能力（Artifacts 层），也是一个高质量评测信号来源（§6.2）。
2. **rubric 可以来自记忆**：用户偏好、风格类 knowledge 可以自动组成个性化 rubric，用于 Outcome 检查和评测中的"意图对齐"维度。
3. **Dreaming 两种模式**：自动生效 / 先审后生效——与 Auton 的分级自主一致，可按资产类型配置。
