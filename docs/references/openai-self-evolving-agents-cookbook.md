# OpenAI Cookbook：Self-Evolving Agents — A Cookbook for Autonomous Agent Retraining

| 项 | 内容 |
|---|---|
| 机构 | OpenAI Cookbook（Partners 系列） |
| 作者 | 页面列出 Calvin Maguranis、Valentina Frenkel、Fanny Perraudeau、Giorgio Saladino 等 |
| 发布 | 页面未标注日期；当前标记为 archived（"may reference outdated models or APIs"） |
| 链接 | https://developers.openai.com/cookbook/examples/partners/self_evolving_agents/autonomous_agent_retraining |
| 主题 | 基于反馈的提示自动优化循环（医药监管文档摘要场景） |

> 本文件为阅读笔记，非原文转载。

## 核心内容

- 问题：Agent 系统在概念验证后常进入平台期，因为诊断边界情况、修正失败都依赖人。
- 循环：基线 Agent → 人工反馈或 LLM-as-Judge 评估 → 元提示（metaprompt）Agent 生成新提示 → 用 Evals 评测 → 聚合得分超过阈值（例 0.8）或达到最大重试次数（例 10 次）→ 达标则替换基线，否则告警需要人工介入。
- 三种优化方式：在 Evals 平台 UI 中手动迭代；全自动 API 循环（LLM-as-Judge）；结合 GEPA 的优化。
- 四个互补的评分器：
  1. Python 评分器：摘要是否保留了原文中的关键化学名称（领域实体保真）；
  2. Python 评分器：字数偏差（约束长度，防止冗长掩盖内容质量）；
  3. 文本相似度：防止偏离原文；
  4. LLM Judge：按 0–1 分档的 rubric 打分，兜底规则覆盖不到的语义问题。
  先用确定性评分器稳定优化，再做语义调优。
- `VersionedPrompt`：每个提示版本记录版本号、模型、关联的 eval id / run id、元数据，支持回滚。
- UI 迭代的停止条件：超过 80% 输出获得正面反馈；收益递减；已识别的失败模式全部解决。

## 局限

- 示例刻意简化（单个摘要 Agent + 合规检查）。
- 页面注明 Evals 平台当时没有 API 可编程获取用户反馈。

## 对 Auton 的启示

1. **一个评测用例可以挂多个评分器**：确定性检查（实体保真、长度）+ 相似度 + Judge，按权重聚合。Auton 的 `EvalCase.checkers` 应支持这种组合，并记录每个评分器的分数，便于诊断。
2. **"重试上限 → 告警人工"** 与 Auton 的熔断一致；可补充明确的目标阈值。
3. **版本记录关联评测 run id**：与 Auton 用 git note 关联评测报告一致。
