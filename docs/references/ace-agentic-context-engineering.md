# ACE：Agentic Context Engineering — Evolving Contexts for Self-Improving Language Models

| 项 | 内容 |
|---|---|
| 机构 | Stanford University、SambaNova Systems、UC Berkeley |
| 作者 | Qizheng Zhang、Changran Hu 等（共同一作），James Zou、Kunle Olukotun 等 |
| 发布 | arXiv 2510.04618（v2，2026-01-29）；ICLR 2026 |
| 链接 | https://arxiv.org/abs/2510.04618 ；代码 https://github.com/ace-agent/ace |
| 主题 | 把上下文当作持续演进的"playbook"，用增量条目更新避免上下文坍缩 |

> 本文件为阅读笔记，非原文转载。论文以 CC BY 4.0 发布。

## 核心观点

- 现有上下文自适应方法的两个问题：
  - **简短偏置（brevity bias）**：优化倾向于收敛到简短、通用的提示，丢掉领域细节；
  - **上下文坍缩（context collapse）**：让 LLM 每步整体重写累积的上下文，体积大了会被压缩成很短的摘要，信息骤失。论文实例：第 60 步上下文 18,282 token、准确率 66.7；下一步坍缩到 122 token、准确率 57.1，低于不做适配的 63.7。
- ACE 把上下文当作不断积累、精炼、组织策略的 playbook，而不是压缩成摘要。

## 关键机制

- **三个角色**：
  - Generator：解题、产生轨迹，并标出哪些条目有用、哪些误导；
  - Reflector：从成功与失败中提炼具体经验，可多轮迭代精炼；
  - Curator：把经验整理成紧凑的**增量条目（delta）**，由**确定性的非 LLM 逻辑**合并进上下文。
- **条目化（bullet）**：上下文由带元数据的条目组成——唯一 id、被标记为 helpful / harmful 的计数器，以及一小段内容（可复用策略、领域概念、常见失败模式）。好处：只更新相关条目（局部化）、细粒度检索、可增量合并与剪枝。
- **Grow-and-refine**：新条目追加，已有条目原地更新（如计数器）；用 embedding 语义去重。去重可以每次 delta 后立即做，也可以等上下文超限时再做。
- 支持离线（系统提示优化）和在线（测试时记忆）两种适配；支持多轮 epoch；离线预热后再在线适配效果更好。
- **不需要标签**：可以只用执行反馈（如代码是否运行成功）。

## 数据

- AppWorld（Agent 基准）：离线设置下，ReAct + ACE 比 ReAct + ICL 高 12.3%、比 ReAct + GEPA 高 11.9%；在线设置比 Dynamic Cheatsheet 平均高 7.6%；无标签时比 ReAct 基线平均高 14.8%。
- 排行榜（2025-09-20）：使用较小的开源模型 DeepSeek-V3.1，平均 59.4%，与排名第一的基于 GPT-4.1 的生产级 Agent（60.3%）相当；在更难的 test-challenge 上在线适配后超过它。
- 金融领域基准平均 +8.6%。
- 成本：离线 AppWorld 相比 GEPA，适配延迟降低 82.3%、rollout 数降低 75.1%；在线 FiNER 相比 DC，延迟降低 91.5%、token 费用降低 83.6%。

## 局限

- 依赖足够强的 Reflector；Reflector 提炼不出有用经验时，上下文会变得嘈杂甚至有害。
- 不是所有任务都需要长而详细的上下文（如 HotPotQA、Game of 24）。

## 对 Auton 的启示

1. **禁止让 LLM 整体重写记忆**：knowledge / insight / playbook 只能通过条目级 delta 修改，合并、去重由确定性代码完成。这是对 Auton Diff 模式的有力佐证，并应扩展到记忆资产。
2. **条目级 helpful / harmful 计数**：Agent 在每个 episode 结束时标出用到的哪些条目有帮助、哪些误导，作为比 episode 级功劳分配更细的信号，直接驱动条目的 strength 和淘汰。
3. **警惕简短偏置**：Gardener / 精简类变异不能以"更短"为目标本身；精简必须通过 val 验证不掉分。
4. **离线预热**：新领域冷启动时，先用种子评测集离线跑几轮生成初始条目，再进入在线适配。
