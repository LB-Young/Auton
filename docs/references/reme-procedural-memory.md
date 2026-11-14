# Remember Me, Refine Me: A Dynamic Procedural Memory Framework for Experience-Driven Agent Evolution

| 项 | 内容 |
|---|---|
| 作者 / 来源 | Zouying Cao 等 |
| 发布 / 版本 | Findings of ACL 2026；2026-07 |
| 原文 | [原始来源](https://aclanthology.org/2026.findings-acl.829/) |
| 查阅 | 2026-11-14 |

> 中文参考笔记，非原文转载。本次依据原始摘要、出版页面或官方报告整理，未逐篇复现实验；“对 Auton 的启示”为设计推论，尚未合并进架构正文。

## 核心观点

程序性记忆需要提炼、按情境复用、依据效用修订，避免被动累积。

## 机制与证据

- 多角度提炼：成功模式、失败触发因素、对比经验。
- 情境适应复用：通过场景感知索引将历史经验用于新任务。
- 效用驱动修订：加入验证过的记忆，清理过期内容。
- 论文在 BFCL-V3 和 AppWorld 上验证。官方实现：[agentscope-ai/ReMe](https://github.com/agentscope-ai/ReMe)。

## 对 Auton 的启示（待验证）

- §4.3：对 insight/skill 明确来源、适用场景、验证状态与淘汰依据。
- §7.1：Dreaming 同时处理成功与失败轨迹，避免只从失败提炼规则。
- §5.2、§6.5：用下游任务表现验证复用价值，避免把检索命中当作有效贡献。

## 局限

论文系统与持续更新的官方仓库不是同一版本快照；本笔记未做代码审计，不能把仓库新增功能算作论文结论。
