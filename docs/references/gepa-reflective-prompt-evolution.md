# GEPA：Reflective Prompt Evolution Can Outperform Reinforcement Learning

| 项 | 内容 |
|---|---|
| 机构 | UC Berkeley、Stanford、Notre Dame、Databricks 等 |
| 作者 | Lakshya A. Agrawal 等 |
| 发布 | arXiv 2507.19457；ICLR 2026（Oral） |
| 链接 | https://arxiv.org/abs/2507.19457 ；代码 https://github.com/gepa-ai/gepa （已集成为 DSPy 优化器） |
| 主题 | 用自然语言反思代替标量奖励的提示进化；Pareto 前沿候选选择 |

> 本文件为阅读笔记，非原文转载。

## 核心观点

- 语言的可解释性提供了比稀疏标量奖励更丰富的学习信号。GEPA（Genetic-Pareto）对系统中的一个或多个提示，采样执行轨迹（推理、工具调用、工具输出），用自然语言反思诊断问题、提出并测试提示更新，并合并 Pareto 前沿上互补的经验。
- 往往只需少量 rollout 就能得到较大的质量提升。

## 关键机制

- **输入**：系统 Φ、训练集、评估指标 μ、**反馈函数 μ_f**（除分数外返回文字反馈，如编译错误、失败原因）、预算 B。
- 训练集拆为 D_feedback（用于反思）和 D_pareto（用于候选选择，大小 n_pareto）。
- **反思式变异**：选一个候选和其中一个模块，在小批量上运行，读取轨迹与文字反馈，让反思模型重写该模块的提示。
- **先小批量、再全量**：新候选先在小批量上评测，有提升才在 D_pareto 上全量评测并加入候选池。
- **Pareto 候选选择**：对 D_pareto 的每个实例，记录所有候选中的最高分，形成 Pareto 前沿；只保留至少在一个实例上取得最好成绩的候选，剪掉被严格支配的；再按"领先实例数"加权随机抽样作为下一次变异的父本。避免总在当前最优上细改而陷入局部最优。
- **System-aware merge**：多模块系统中，把两个候选在不同模块上各自更好的提示组合起来（交叉）。

## 数据

- 六个任务上平均比 GRPO 高 6%、最多高 20%，rollout 最多少 35 倍（对比 GRPO 使用 24,000 rollout 的设置）。
- 比 MIPROv2 高 10% 以上（如 AIME-2025 +12%）。
- 也可用作推理时的代码优化搜索策略。

## 对 Auton 的启示

1. **父版本选择改用 Pareto 前沿**：按"每个 val case 上的最好版本"保留候选，按领先 case 数加权抽样，比按总分 top-k 抽样更能保留"在某类任务上特别好"的版本。
2. **反馈函数返回文字**：Auton 的 checker 不仅给分，还要返回失败原因文字（测试报错、断言失败内容），供文本梯度使用。
3. **跨字段合并**：同一资产不同字段（如 skill 的步骤段落与 examples）分别在不同候选上变好时，尝试组合成新候选。
4. **先小批量、再全量**：与 Auton §7.5 的分层评测一致。

另见同目录 [`decagon-gepa-in-production.md`](./decagon-gepa-in-production.md)：生产环境中使用 GEPA 的消融经验。
