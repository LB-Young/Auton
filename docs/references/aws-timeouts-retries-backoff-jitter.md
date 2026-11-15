# AWS：超时、重试、退避与抖动

| 项 | 内容 |
|---|---|
| 来源 / 时间 | AWS Builders’ Library，Marc Brooker；2019-12-05 |
| 原文 | [原始文章](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/) |
| 整理 | 2026-11-15；编号 REF002 |

> 本文件为中文阅读笔记与个人理解，非原文转载或逐段翻译；“我的理解”“对 Auton 的启示”“建议验证”为设计推论。未逐篇复现实验，公开案例的结果不等于 Auton 已验证的效果。

## 核心观点

远程调用失败可能是暂时的，但重试也可能加重过载。超时只说明调用方没有及时拿到结果，不能证明被调用方没有产生副作用。

## 关键机制与做法

- 连接与请求应有超时，重试采用退避与随机抖动。
- 有副作用操作需要可安全重复执行的接口语义。

## 我的理解

对 Agent 来说，SDK 自动重试、工具重试和模型自行重试是同一个业务动作的不同层。如果各层都独立“再试几次”，总出站请求会失控。

## 对 Auton 的启示

- 建立统一 attempt ledger 和父任务 deadline，下层不能重置总时间。
- 按错误类别确定重试 owner；结果未知的外部写先查询对账。

## 局限与适用前提

它是分布式系统文章，不直接定义 Agent 的目标恢复或权限模型；幂等语义仍需具体服务实现。

## 建议验证（尚未执行）

模拟提交后丢回执及持续 429，检查外部记录数量、总请求数和最大等待时间。

相关：[全部阅读笔记](./agent-article-reading-index.md) · [执行问题手册](../agent-execution-problems-and-solutions.md) · [构建案例分析](../agent-builder-case-studies.md)。
