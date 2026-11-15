# LangChain：多 Agent 的上下文模式

| 项 | 内容 |
|---|---|
| 来源 / 时间 | LangChain，Thushanth Bengre、Chester Curme；2026-09-08 |
| 原文 | [原始文章](https://www.langchain.com/blog/organizing-context-in-a-multi-agent-harness) |
| 整理 | 2026-11-15；编号 REF022 |

> 本文件为中文阅读笔记与个人理解，非原文转载或逐段翻译；“我的理解”“对 Auton 的启示”“建议验证”为设计推论。未逐篇复现实验，公开案例的结果不等于 Auton 已验证的效果。

## 核心观点

新上下文子 Agent 具有隔离优势，但可能重复收集主 Agent 已读资料；fork 可继承背景。worker 与独立 verifier 的需要不同。

## 关键机制与做法

- isolated 只接任务包，fork 从主上下文继续。
- 背景复用可减少重复读取，但也带入已有判断。

## 我的理解

我理解应把上下文模式设为可评测的委派选择，而不是全局开关。共享背景有成本和权限影响；验证独立性也不等于故意不给关键规格。

## 对 Auton 的启示

- 增加 curated 模式传递目标、相关证据与决策，不复制全部历史。
- fork 前过滤敏感内容，且绝不自动继承父任务的写权限。

## 局限与适用前提

缓存和省时效果依赖 provider、任务与历史结构；共享上下文不能成为默认可信授权。

## 建议验证（尚未执行）

比较三种模式的重复读取、成功率、审查偏置、token 和秘密暴露。

相关：[全部阅读笔记](./agent-article-reading-index.md) · [执行问题手册](../agent-execution-problems-and-solutions.md) · [构建案例分析](../agent-builder-case-studies.md)。
