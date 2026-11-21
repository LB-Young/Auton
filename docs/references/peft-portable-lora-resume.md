# PEFT：LoRA 与恢复状态

- 原链接：[PEFT：LoRA 与恢复状态](https://huggingface.co/docs/peft/developer_guides/lora)
- 核对日期：2026-11-19。以下是自己的理解笔记，不是原文副本。

LoRA 通过少量低秩参数适配基础模型。Auton 固定 base、tokenizer、template、数据、超参数与 seed；恢复不仅需要 adapter，还要有优化器和随机状态，全部以 safetensors 保存并校验摘要。恢复到不同设备/库版本不能视为同一可复现实验。训练产物仅登记为离线候选，量化部署和真实任务效果仍需独立检查。
