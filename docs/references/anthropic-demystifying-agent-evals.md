# Anthropic：理解 Agent 评测的基本对象

| 项 | 内容 |
|---|---|
| 来源 / 时间 | Anthropic Engineering；2026-01-09 |
| 原文 | [原始文章](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) |
| 整理 | 2026-11-15；编号 REF011 |

> 本文件为中文阅读笔记与个人理解，非原文转载或逐段翻译；“我的理解”“对 Auton 的启示”“建议验证”为设计推论。未逐篇复现实验，公开案例的结果不等于 Auton 已验证的效果。

## 核心观点

Agent 的任务、trial、grader、trace 与最终环境结果应分别建模。能力评测探索边界，回归评测保护已有行为。

## 关键机制与做法

- 一个任务可以由多个评分器检查，多次 trial 用于观察随机性。
- 代码、模型与人工评分各有适用面，Judge 需要校准。

## 我的理解

我理解评测的基础是先明确“成功发生在哪里”。文件、数据库或外部资源才是实际结果；漂亮的最终答复只能是展示，不能代替验证。

## 对 Auton 的启示

- Eval Store 将 train/val/test 划分与能力/回归用途分开。
- 报告任务成功、过程合规、成本和不确定性，不把所有维度硬压成一个分数。

## 局限与适用前提

工程报告中的案例不是统一条件的算法比较，不能直接据此设定一个通用通过阈值。

## 建议验证（尚未执行）

用正确文字但错误环境、错误文字但正确环境，以及两条不同有效路径检验评分器。

相关：[全部阅读笔记](./agent-article-reading-index.md) · [执行问题手册](../agent-execution-problems-and-solutions.md) · [构建案例分析](../agent-builder-case-studies.md)。
