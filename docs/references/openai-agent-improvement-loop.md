# OpenAI Cookbook：Build an Agent Improvement Loop with Traces, Evals, and Codex

| 项 | 内容 |
|---|---|
| 机构 | OpenAI Cookbook（Agents SDK 系列） |
| 作者 | 页面未在正文显著署名 |
| 发布 | 页面未标注日期（据搜索摘要约为 2026-05） |
| 链接 | https://developers.openai.com/cookbook/examples/agents_sdk/agent_improvement_loop |
| 主题 | 从真实 trace 出发：反馈 → 自动生成 eval → 验证门 → 排序后的 harness 改进建议 → 交给编码 Agent 实现 |

> 本文件为阅读笔记，非原文转载。

## 核心内容

- 场景：一个财务尽调分析 Agent，对虚构公司的资料（结构化导出 + 管理层叙述，部分互相矛盾）回答问题，并产出可审查的工件（答案、投资备忘录、风险登记、开放问题、引用、证据表）。
- **harness** 被定义为模型周围的完整契约：指令、工具、路由、输出要求、验证检查。被优化的对象不只是提示词。
- 循环七步：
  1. 运行 Agent，导出 trace（OpenTelemetry 风格 JSONL）；
  2. 加入人工反馈（专家指出：集中度应按母公司汇总；未经核实的 NRR 不能当正式指标；"SOC 2 完成"不能混淆 Type I/II）与 LLM 反馈；
  3. **由 LLM 根据 trace 和反馈自动生成 eval 定义**（可包含字面断言 `contains / not-contains` 和 LLM rubric），每条 eval 绑定来源 trace；
  4. 用 Promptfoo 跑验证门；
  5. HALO（Hierarchical Agent Loop Optimization）综合当前 harness 配置、trace、人工反馈、LLM 反馈、生成的 eval 和门结果，输出**排序后的 harness 改进建议**；
  6. 写出 `codex_handoff.md`：诊断、排序建议、证据、实现指导；
  7. 交给 Codex 实现，然后用同一套 eval 再验证。
- Agent 运行时自带确定性校验工具（检查每条结论的引用文件是否存在、检查输出工件格式），失败则必须修改再作答。
- 自动化程度可选：从"系统提出变更、开发者审 diff 后合并"开始，随着 eval 门可信度提高，再逐步自动开 PR、合并、部署。人可以在 trace 审阅、eval 修订、PR 审批、合并、部署任一处加门。
- 生成的 eval 应作为持久回归测试保存；人可以先收紧不够严格的 eval，再让它驱动反复优化。

## 原文要点

- "Traces show what happened, feedback explains what mattered, evals make those expectations reusable"（流程的四个角色）。
- "The larger idea of loop engineering is the durable part"。

## 对 Auton 的启示

1. **反馈 → eval 自动生成**：用户纠正或 `/feedback` 中的具体要求，自动转成带字面断言 + rubric 的 `EvalCase`（绑定来源 episode），先进入 train；用户可在 `/eval` 中审阅、收紧后升级为 val/test 回归用例。
2. **Genome 之外的改进走"交接文档"**：诊断为工具层 / Harness 代码层的问题（Auton 的熔断出口），不再只是"报告给用户"，而是生成结构化的 `handoff.md`（诊断、证据、排序建议、验证方式），交给编码 Agent 或用户实现，再用同一套 eval 验证。
3. **运行时自校验工具**：对高风险任务，在 skill 中捆绑确定性校验脚本（引用存在性、输出格式），作为 Agent 交付前的必经检查。
