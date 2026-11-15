# Anthropic：分离 session、harness 与 sandbox

| 项 | 内容 |
|---|---|
| 来源 / 时间 | Anthropic Engineering；2026-04-08 |
| 原文 | [原始文章](https://www.anthropic.com/research/managed-agents) |
| 整理 | 2026-11-15；编号 REF031 |

> 本文件为中文阅读笔记与个人理解，非原文转载或逐段翻译；“我的理解”“对 Auton 的启示”“建议验证”为设计推论。未逐篇复现实验，公开案例的结果不等于 Auton 已验证的效果。

## 核心观点

组件共置时，容器故障牵连会话，流式输出难以区分故障来源。文章介绍分离控制循环、执行环境与持久会话，并把凭据移出生成代码可访问环境。

## 关键机制与做法

- 各组件用稳定接口连接，可独立替换与恢复。
- 历史位于活动上下文之外，支持按需回查。

## 我的理解

我的理解是先分生命周期，不一定马上分成微服务。单机原型也应知道哪些状态必须持久、哪些工作区能重建、哪些在途副作用不能重放。

## 对 Auton 的启示

- 建立工作区 provision recipe 和产物 manifest。
- Credential Broker 代理实际授权，Session Store 独立于 sandbox；恢复先核实未决操作。

## 局限与适用前提

重新建容器不能自动恢复未保存文件，也不能保证 exactly-once；平台接口不等同于通用一致性协议。

## 建议验证（尚未执行）

分别杀流连接、控制进程和沙箱，检查错误可区分、状态可接续、秘密不进入生成代码环境。

相关：[全部阅读笔记](./agent-article-reading-index.md) · [执行问题手册](../agent-execution-problems-and-solutions.md) · [构建案例分析](../agent-builder-case-studies.md)。
