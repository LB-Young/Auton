# Anthropic：Claude Code 质量退化复盘

| 项 | 内容 |
|---|---|
| 来源 / 时间 | Anthropic Engineering；2026-04-23 |
| 原文 | [原始文章](https://www.anthropic.com/research/april-23-postmortem) |
| 整理 | 2026-11-15；编号 REF028 |

> 本文件为中文阅读笔记与个人理解，非原文转载或逐段翻译；“我的理解”“对 Auton 的启示”“建议验证”为设计推论。未逐篇复现实验，公开案例的结果不等于 Auton 已验证的效果。

## 核心观点

复盘涉及默认推理投入调整、历史清理重复触发的 bug，以及提示组合变化。不同时间和用户群的影响叠加，使整体质量问题难以复现；作者报告回退或修复。

## 关键机制与做法

- 底层模型之外，运行参数与上下文处理也改变表现。
- 聚合评测可能掩盖特定长任务或恢复路径的退化。

## 我的理解

我的理解是运行版本不能只等于模型 ID。任何影响模型实际可见状态和投入的配置，都属于发布面，必须能追踪和单独回退。

## 对 Auton 的启示

- RunManifest 保存 effort、prompt、清理/缓存策略、runtime 和 cohort。
- 一次性动作测试第二次与第 N 次；质量异常先核对运行时，别让 Skill 进化掩盖 bug。

## 局限与适用前提

厂商自报根因和修复不代表全部质量投诉已解释；不能推出高 effort 在所有任务最优。

## 建议验证（尚未执行）

空闲后恢复多轮，检查历史仅按规则清理；按任务长度和复杂度比较配置变更。

相关：[全部阅读笔记](./agent-article-reading-index.md) · [执行问题手册](../agent-execution-problems-and-solutions.md) · [构建案例分析](../agent-builder-case-studies.md)。
