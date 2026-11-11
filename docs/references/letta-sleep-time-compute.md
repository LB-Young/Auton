# Letta：Sleep-time Compute / Agent Memory

| 项 | 内容 |
|---|---|
| 机构 | Letta（MemGPT 团队） |
| 文章 1 | Sleep-time Compute，2025-04-21，https://www.letta.com/blog/sleep-time-compute （论文 arXiv 2504.13171，Lin、Snell、Wang、Packer、Wooders、Stoica、Gonzalez） |
| 文章 2 | Agent Memory: How to Build Agents That Learn and Remember，2025-07-07，https://www.letta.com/blog/agent-memory |
| 主题 | 利用空闲时间整理记忆；主 Agent 与 sleep-time Agent 分工；记忆即上下文工程 |

> 本文件为阅读笔记，非原文转载。

## 核心内容

**Sleep-time compute**
- 从"测试时扩展"到"睡眠时扩展"：Agent 在用户不在时也运行，提前重组信息、推理，把"原始上下文"变成"学到的上下文"，之后答题时需要的额外推理更少。
- 依赖有状态的 Agent：持久化的记忆是把空闲时的成果带到下一次交互的桥梁。
- 论文结论：在数学基准上把计算负载从高延迟的用户交互转移到空闲时段，形成成本—性能的帕累托改进。
- **实现（Letta 0.7.0）**：创建 sleep-time Agent 时，底层生成两个 Agent：
  - 主 Agent：与用户对话、调用工具、搜索外部记忆，**但没有编辑核心记忆的工具**；
  - sleep-time Agent：持有编辑工具，管理主 Agent 和自己的上下文内记忆块。
  - 好处：记忆管理异步进行，不拖慢对话；避免一个 Agent 同时处理对话工具和记忆工具导致不可靠；增量写入导致的凌乱记忆可以被持续整理成干净、简洁的版本。
- sleep-time Agent 宜用更强、更慢的模型（不受延迟约束）；运行频率可配置，频率越高越费 token。
- 记忆以"anytime"方式更新：主 Agent 随时可读，不必等整理完成。

**Agent Memory**
- Agent "记住"什么，取决于某一刻上下文窗口里有什么；设计记忆本质上是上下文工程。
- 组成：消息缓冲区（最近消息）；核心记忆（固定在上下文中的记忆块，每块有 label、description、value、字符上限）；回忆记忆（完整对话历史，可检索）；归档记忆（显式整理的知识，存于向量库或图数据库）。
- 上下文满时一般只驱逐部分消息（如 70%）并递归摘要；"检索（RAG）是记忆的工具，但不是记忆本身"。

## 对 Auton 的启示

1. **主 Agent 只能追加，不能编辑长期记忆**：快回路中主 Agent 只往 `learnings` 追加；knowledge / insight 的修改全部由后台 Curator（中/慢回路）完成。职责分离，主循环更快更可靠。
2. **后台整理用更强的模型**，频率按 policy 配置（与 Dreaming 节奏合并管理）。
3. **记忆块带 description 和字符上限**：常驻层的每个块（用户画像、当前项目、目录）都声明用途和上限，与 Auton §5.2 的预算一致。
4. **空闲时预读**：除了整理记忆，空闲时也可预先研读用户常用的项目（结构、约定），生成项目级 knowledge。
