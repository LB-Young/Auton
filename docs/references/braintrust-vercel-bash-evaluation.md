# Braintrust × Vercel：检验 bash 是否足够

| 项 | 内容 |
|---|---|
| 来源 / 时间 | Braintrust / Vercel，Ankur Goyal 等；2026-01-22 |
| 原文 | [原始文章](https://vercel.com/blog/testing-if-bash-is-all-you-need) |
| 整理 | 2026-11-15；编号 REF026 |

> 本文件为中文阅读笔记与个人理解，非原文转载或逐段翻译；“我的理解”“对 Auton 的启示”“建议验证”为设计推论。未逐篇复现实验，公开案例的结果不等于 Auton 已验证的效果。

## 核心观点

对比 SQL、bash 与文件工具后，调试发现工具性能、schema、数据加载及参考答案都影响结果；修复后差距改变，混合验证也引入额外成本。

## 关键机制与做法

- 检查真实 trace 并纠正错误或歧义的评分条件。
- 不同工具更适合结构化查询或探索复核。

## 我的理解

我理解评价一个抽象前先核对测量链。不能把慢工具或错误答案造成的失败都归因给模型，也不能为了喜欢的方案任意改 checker。

## 对 Auton 的启示

- 为数据、加载、schema、答案与环境建 manifest。
- checker 修订独立审查，在相同新版本上重测全部候选。

## 局限与适用前提

初始和修复后结果不是同一实验条件，文章也不能证明混合工具在任何任务都值得成本。

## 建议验证（尚未执行）

分别注入漏行、错误答案、分组歧义和慢扫描，检查根因分类与公平重测。

相关：[全部阅读笔记](./agent-article-reading-index.md) · [执行问题手册](../agent-execution-problems-and-solutions.md) · [构建案例分析](../agent-builder-case-studies.md)。
