# Anthropic：The components of agent memory

| 项 | 内容 |
|---|---|
| 机构 | Anthropic（Engineering） |
| 作者 | Lance Martin |
| 发布 | 2026-11-06 |
| 链接 | https://anthropic.com/research/components-of-agent-memory |
| 主题 | Agent 记忆的分层、写入时机、显著性判断、Dreaming（离线整理记忆） |

> 本文件为阅读笔记，非原文转载。引文为原文短句。

## 核心观点

- 以海马体—皮层分工类比：Agent 把工作记录在日志/转录中，**Dreaming** 在会话之间离线回放日志、修正错误、生成笔记与新的记忆表示，相当于睡眠时的记忆巩固。
- 会话中写下的记忆是对"什么值得记住"的**预测**，可能写错或随环境漂移，需要离线对照原始转录纠正。
- 每次注入的上下文必须小；更深层的 wiki 和转录搜索承担大部分知识；Dreaming 负责在层之间维护与提升。
- 告诉模型"记忆是用来做什么的"，而不是"怎么用"：把显著性判断交给模型。

## 关键机制

- **记忆定义**：从经验中获得、跨会话保存为可读上下文的知识；不包括权重更新、上下文内学习、compaction。
- **四层**（自下而上）：transcripts（可搜索的事件日志）→ memory notes（模型写的笔记）→ memory representations（如 wiki）→ injected context（每个会话预加载）。Dreaming 在相邻层之间双向流动。
- **显著性**：Pokémon 实验中，较弱模型把一切都记下来（413 个文件、约 98 万字符，1 枚徽章），较强模型只记屏幕上读不到的信息——策略、计划、已验证规则（10 个文件、约 4.3 万字符，4 枚徽章），用 `global.md` 做仪表盘。
- **固定规则有害**："只记录失败"这类预设规则会削弱较强模型的记忆收益（例如 Opus 5 的收益下降 0.234）。
- **Dreaming 验证笔记**：把笔记与原始转录对照，发现错误就重写。Mt. Moon 案例中，一条错误笔记（PokéCenter 位置记错）导致反复掉下单向崖壁；Dreaming 纠正后，Agent 顺利抵达目的地。
- **Dreaming 构建 wiki**：互相链接的页面集合，充当导航地图；Dreaming 负责新增、编辑、修剪、合并重复、核对来源；跨会话发现模式（如把 9 个死链改指向已有页面、新增 3 个页面）。
- **提升到注入层**：Dreaming 可把笔记提升为每次会话预加载的内容，但注入消耗 token、错误会进入每个会话，所以也要把细节下沉、只留链接。Claude Code 的 auto memory 只加载 `MEMORY.md` 前 200 行或 25 KB 作为索引。
- **面向目标的 Dreaming**：指令可按任务定制。合同条款任务中，多个 Agent 同时写一张共享表会互相覆盖；改为"每份合同一个页面、由单个 Agent 写、逐字引用条款"后，准确率从 72% 到 100%。

## 数据

- CL-Bench 1.0（每题一个新会话，唯一的跨会话通道是记忆目录，30 题均值）：多数模型有记忆后平均奖励明显上升（如 Opus 4.7：0.383 → 0.700；Sonnet 5：0.306 → 0.610）。
- 大语料 wiki（约 35 万文件、4.2 亿 token，25 题）：仅用 wiki 作答，Dreaming 从 2 个会话扩展到 128 个会话，得分从 13% 到 48%；wiki + 搜索 61%，仅搜索 53%；同时使用每题省约 2 万 token。
- 风险：某任务中 wiki 体积达到原始文档的约 1.77 倍。

## 局限 / 开放问题

- 何时写记忆：会话中写会分散注意力；后台 Dreaming 的产出不一定立即可用。
- 如何保持最新：Dreaming 需要算力，无法持续检查所有记忆，建议按易变程度或访问频率调节节奏。
- 注入层会带入错误、加载不等于遵循；wiki 可能过度细化、累积错误或幻觉。
- 部分对比是单次运行。

## 原文短句

- "We’ve found that it helps to tell Claude what memory is for, but not how to use it."
- "By writing down a rule, an agent predicts that the pattern it’s describing will be relevant again."
- "Dreaming gives Claude a way to test its notes against the original transcripts."

## 对 Auton 的启示

1. **Dreaming 增加"对照原始事件验证记忆"步骤**：对 learnings/knowledge/insight，按 provenance 回到事件日志核对，错误则修正或降级。
2. **捕获层给目的、不给规则**：快回路只告诉模型"记忆用于什么"，由模型判断显著性；治理（晋升、遗忘）放在后端，而不是在写入时用死规则过滤。
3. **knowledge 采用 wiki 结构**：页面 + 链接 + 索引；常驻层只放索引（类似 200 行上限），细节下沉。
4. **单写者原则**：同一记忆页面在一次 Dreaming 中只由一个写入者修改，避免并发覆盖。
5. **Dreaming 节奏按易变性/访问频率调度**，并设体积上限（防止表示比原文还大）。
