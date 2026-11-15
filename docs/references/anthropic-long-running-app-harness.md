# Anthropic：长应用任务中的规划、生成与评估

| 项 | 内容 |
|---|---|
| 来源 / 时间 | Anthropic，Prithvi Rajasekaran；2026-03-24 |
| 原文 | [原始文章](https://www.anthropic.com/research/harness-design-long-running-apps) |
| 整理 | 2026-11-15；编号 REF030 |

> 本文件为中文阅读笔记与个人理解，非原文转载或逐段翻译；“我的理解”“对 Auton 的启示”“建议验证”为设计推论。未逐篇复现实验，公开案例的结果不等于 Auton 已验证的效果。

## 核心观点

长任务可能失去连贯性或提前收尾，自评也偏乐观。文章探索结构化交接、重置上下文，以及 planner、generator、evaluator 分工；独立评估仍需校准。

## 关键机制与做法

- 把主观质量转成可讨论的维度。
- 区分应用看起来完成与真正交互可用。

## 我的理解

我的理解是外观、静态产物、主路径和边界功能应分开验收。评估者若只读实现说明，就很容易重述实现者的自信。

## 对 Auton 的启示

- reviewer 先看规格与实际产物，缺陷附复现和证据。
- 限制迭代轮数、范围扩张和预算，按模型实验选择 reset 或 compaction。

## 局限与适用前提

独立角色不等于独立正确；旧模型的重置补丁可能在新模型上变成负担。

## 建议验证（尚未执行）

用外观完整但功能缺失的产物测盲评，再测试交接策略的质量、返工与成本。

相关：[全部阅读笔记](./agent-article-reading-index.md) · [执行问题手册](../agent-execution-problems-and-solutions.md) · [构建案例分析](../agent-builder-case-studies.md)。
