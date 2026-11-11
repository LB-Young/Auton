# 参考资料

Auton 自进化架构设计（[`../self-evolution-architecture.md`](../self-evolution-architecture.md)）所参考的文章、论文与开源项目。

- 用户提供的 PDF 原样保存。
- 第三方文章与论文保存为中文**阅读笔记**（元信息、核心观点、关键机制、数据、局限、对 Auton 的启示），附原文链接与少量原文短句，不转载全文。
- 开源项目保存为代码分析。

收集时间：2026-11-11。

## 目录

| 文件 | 来源 | 机构 | 日期 | 主题 |
|---|---|---|---|---|
| [tencent-agent-self-evolution-flywheel.pdf](./tencent-agent-self-evolution-flywheel.pdf) · [笔记](./tencent-agent-self-evolution-flywheel.md) | 一篇讲透 Agent 自进化飞轮怎么搭 | 腾讯技术工程 | 2026-08-27 | 评测→记忆→落地→控制的四齿飞轮 |
| [evoagentx-analysis.md](./evoagentx-analysis.md) | EvoAgentX（开源项目） | EvoAgentX 团队 | — | 工作流优化算法：TextGrad、AFlow、MIPRO、EvoPrompt、SEW、MAP-Elites |
| [anthropic-components-of-agent-memory.md](./anthropic-components-of-agent-memory.md) | The components of agent memory | Anthropic | 2026-11-06 | 记忆分层、显著性、Dreaming 验证与 wiki |
| [anthropic-managed-agents-dreaming-outcomes.md](./anthropic-managed-agents-dreaming-outcomes.md) | New in Claude Managed Agents | Anthropic | 2026-05-19 | Dreaming、Outcomes（独立评分者）、多 Agent |
| [anthropic-agent-skills.md](./anthropic-agent-skills.md) | Equipping agents for the real world with Agent Skills | Anthropic | 2025-10-16 | Skill 格式、渐进披露、开发与评估 |
| [openai-self-evolving-agents-cookbook.md](./openai-self-evolving-agents-cookbook.md) | Self-Evolving Agents cookbook | OpenAI Cookbook | 未标注（已归档） | 多评分器 + 元提示优化循环 |
| [openai-agent-improvement-loop.md](./openai-agent-improvement-loop.md) | Build an Agent Improvement Loop with Traces, Evals, and Codex | OpenAI Cookbook | 约 2026-05 | trace → 反馈 → 生成 eval → 门 → HALO → Codex 交接 |
| [ace-agentic-context-engineering.md](./ace-agentic-context-engineering.md) | Agentic Context Engineering (ACE) | Stanford · SambaNova · UC Berkeley | ICLR 2026 | 条目化增量更新、上下文坍缩 |
| [gepa-reflective-prompt-evolution.md](./gepa-reflective-prompt-evolution.md) | GEPA | UC Berkeley · Stanford · Databricks 等 | ICLR 2026 | 反思式提示进化、Pareto 候选选择 |
| [decagon-gepa-in-production.md](./decagon-gepa-in-production.md) | Optimizing GEPA for production | Decagon | 2026-03-25 | 样本量、反思模型、长度约束的消融 |
| [sakana-darwin-godel-machine.md](./sakana-darwin-godel-machine.md) | The Darwin Gödel Machine | Sakana AI · UBC | 2025-05-30 | 自改代码、Agent 存档、奖励作弊 |
| [deepmind-alphaevolve.md](./deepmind-alphaevolve.md) | AlphaEvolve | Google DeepMind | 2025-05-14 | 进化编码 Agent、模型集成、自动评估 |
| [letta-sleep-time-compute.md](./letta-sleep-time-compute.md) | Sleep-time Compute / Agent Memory | Letta | 2025-04-21 / 2025-07-07 | 空闲时整理记忆、主 Agent 与记忆 Agent 分工 |
| [langchain-continual-learning.md](./langchain-continual-learning.md) | Continual learning for AI agents | LangChain | 2026-04-05 | 模型 / Harness / 上下文三层 |

## 跨来源共识

| 共识 | 出处 | Auton 设计中的位置 |
|---|---|---|
| 当前最划算的进化发生在 Harness / 上下文层，而不是权重 | 腾讯、LangChain、ACE、GEPA | §0.1 |
| trace（完整执行轨迹）是一切改进的基础 | LangChain、OpenAI、Anthropic | §1、§5.3 事件溯源 |
| 离线、异步地整理经验（Dreaming / sleep-time） | Anthropic、Letta、腾讯、LangChain | §3.1 慢回路、§7.1 |
| 自然语言反馈比标量分数信息量大 | GEPA、ACE、TextGrad | §7.1 文本梯度 |
| 不要整体重写，只做局部增量修改 | ACE（上下文坍缩）、腾讯（Diff 模式）、AlphaEvolve（diff） | §7.4 |
| 不只从当前最优出发，保留多样的"垫脚石" | DGM、GEPA、AFlow、MAP-Elites | §7.3、§7.8 |
| 评测者独立于被评测者；评测与检测逻辑不可被进化修改 | Anthropic Outcomes、DGM、腾讯 | §6.3、§8.1 |
| 人类把关关键节点，自动化程度随信任逐步提高 | OpenAI、腾讯、Anthropic Dreaming | §8.2–§8.4 |

## 对 v0.4 设计的新增启示（待合并）

| # | 启示 | 来源 | 建议落点 |
|---|---|---|---|
| 1 | Dreaming 增加"对照原始事件核验记忆"步骤，错误即修正或降级 | Anthropic memory | §7.1、§4.3 |
| 2 | 捕获阶段告诉模型记忆的用途，不预设"只记 X"之类规则；治理放在后端 | Anthropic memory | §3.1 快回路、§4.3 |
| 3 | knowledge 采用 wiki 结构（页面 + 链接 + 索引）；常驻层只放索引 | Anthropic memory | §4.1、§5.2 |
| 4 | 同一记忆页面一次只由一个写入者修改 | Anthropic memory | §4.3 |
| 5 | 主 Agent 只追加 learnings；长期记忆的编辑全部由后台 Curator 完成，并用更强模型 | Letta | §3.1、§5.1 |
| 6 | 记忆与 playbook 只做条目级 delta，合并去重由确定性代码完成；条目带 helpful / harmful 计数，由 Agent 在 episode 结束时标注 | ACE | §4.2、§4.3、§6.5 |
| 7 | 警惕简短偏置：精简不能是目标本身，必须通过 val 验证 | ACE | §7.4 Gardener |
| 8 | 父版本选择改用 Pareto 前沿（按每个 val case 的最好版本保留，按领先 case 数加权抽样） | GEPA、DGM | §7.3 |
| 9 | checker 除分数外返回失败原因文字，供文本梯度使用 | GEPA | §6.4 |
| 10 | 反思 / 补丁生成 / Dreaming 必须用前沿模型；单次反思约 10 个样本，单个诊断的训练样本 20–100 | Decagon | §5.1、§7.1 |
| 11 | 资产 token 预算同时作为 G1 门禁（长度正则化） | Decagon | §7.5 |
| 12 | 快模型批量产出多样变体，强模型深入改进最有希望的方向 | AlphaEvolve | §7.4 |
| 13 | 有确定性 checker 的 task_type 可更快升级自主等级 | AlphaEvolve | §8.2 |
| 14 | 评测只信任 Tool Host 事件记录，不信任 Agent 自述的结果；Guard 拒绝删除或绕过检测逻辑的补丁 | DGM | §6.2、§8.1 |
| 15 | 切换主模型后，对 evolved 资产跑全量回归 | DGM | §7.7 |
| 16 | 用户反馈自动生成带字面断言 + rubric 的 eval 用例，人可收紧后升级为回归用例 | OpenAI loop | §6.4 |
| 17 | 一个 eval 用例挂多个评分器（确定性 + 相似度 + Judge），分别记录 | OpenAI cookbook | §6.4 |
| 18 | 工具层 / 代码层问题生成结构化 `handoff.md`，交给编码 Agent 或用户；Auton 自身代码的改进作为独立的、始终人工审核的 PR 通道 | OpenAI loop、LangChain Meta-Harness | §7.1 熔断、新增章节 |
| 19 | 运行时 Outcome 检查：独立上下文的评分者按 rubric 驱动返工；rubric 可来自用户偏好记忆 | Anthropic Outcomes | §5、§6.2 |
| 20 | skill 对齐开放标准（`name` + `description` 必填）；description 作为独立字段，评测其触发准确率；skill 可捆绑确定性脚本；外部 skill 视为不可信 | Anthropic Skills | §4.2、§7.4、§8.1 |
| 21 | 用户显式要求"记住"的内容跳过晋升门槛，作为 user-origin 直接写入 | LangChain | §4.3 |
| 22 | 空闲时预读用户常用项目，生成项目级 knowledge | Letta | §3.1 |
