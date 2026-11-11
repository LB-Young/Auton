# Google DeepMind：AlphaEvolve — A Gemini-powered coding agent for designing advanced algorithms

| 项 | 内容 |
|---|---|
| 机构 | Google DeepMind |
| 作者 | AlphaEvolve team |
| 发布 | 2025-05-14 |
| 链接 | https://deepmind.google/discover/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/ |
| 主题 | LLM + 自动评估器 + 进化框架，进化整个代码库以发现算法 |

> 本文件为阅读笔记，非原文转载。

## 核心内容

- 组成：**提示采样器**组装提示 → LLM 集成生成新程序 → **评估器**验证、运行、打分 → 存入**程序数据库**；数据库实现进化算法，决定哪些程序用于后续提示。
- **模型集成**：快速高效的 Gemini Flash 负责扩大探索的广度，最强的 Gemini Pro 提供有深度的建议。
- 适用范围：解可以写成算法、并且能**自动验证**的问题。自动评估指标提供客观、可量化的评价。
- 从单函数发现扩展到进化整个代码库。

## 数据

- 数据中心调度（Borg）：一条简单的启发式规则已在生产运行一年多，平均持续回收全球约 0.7% 的计算资源；且是人类可读代码，便于解释、调试、部署。
- 硬件：提出的 Verilog 改写通过了严格验证，进入下一代 TPU。
- 训练：Gemini 架构中一个矩阵乘法内核提速 23%，训练时间减少 1%；FlashAttention 内核最多提速 32.5%；内核优化从数周专家工作缩短到数天自动实验。
- 数学：4×4 复数矩阵乘法用 48 次标量乘法，改进了 Strassen 1969 年的结果；在 50 多个开放问题上，约 75% 重新发现已知最优解，约 20% 改进了已知最优解（如 11 维 kissing number 新下界 593）。

## 对 Auton 的启示

1. **快模型求广、强模型求深**：生成候选时，用便宜模型批量产出多样的变体，用强模型对最有希望的方向做深入修改；与 Decagon"反思必须用强模型"的结论互补——广度可以便宜，深度不能省。
2. **自动验证能力决定自主程度**：有确定性 checker（测试、构建、格式校验）的 task_type 可以更快升级自主等级；只能靠 Judge 的 task_type 保持较低自主等级。
3. **产出保持人类可读**：进化出的资产必须是可读的 Markdown / YAML / 代码，便于审查与部署（Auton 已满足）。
