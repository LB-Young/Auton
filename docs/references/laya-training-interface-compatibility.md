# Laya 训练接口与 Auton student 的兼容边界

- 原链接：[Laya fine-tuning 文档](https://github.com/NandhaKishorM/laya/blob/main/docs/finetune.md)。
- 核对日期：2026-11-19。以下是自己的理解与本项目的检查笔记，不是原文下载。

上游训练文档描述了选项重排和冻结 encoder 等设置。仅看上游文档存在训练入口，不能假设当前安装的发行包已经包含同一个入口；当前项目固定的 `laya==0.3.20` 包中没有 `laya.train` 模块。因此流程不能直接写一个未经核对的命令并宣称已支持原生 Laya 微调。

Auton 首期通用参考 student 是独立的 `encoder_choice`：通过部署方配置的 Hugging Face encoder、LoRA 和共享选项打分头，学习状态与候选项之间的选择。它不是 Laya 原始 head checkpoint，也不声称与 Laya 的 logits/校准相容。若要接入原生 Laya trainer，应针对审核后的固定发行版单独实现 backend，并验证其实际数据契约与保存/恢复格式。

encoder 数据保留状态、问题、稳定选项 ID 和所选标签；LLM JSON 读出另有独立导出适配，不复用执行模型的工具动作 SFT。训练增强重排选项时必须同步移动标签，不能用位置索引偷换答案。

教师合格 KEEP 标签适合筛选训练来源，不构成无偏独立评测集。即使 teacher 一致率、分类指标和 loss 都变好，也仍需 champion 对照、新鲜金标、完整隔离 Agent 对比及实际部署评估。
