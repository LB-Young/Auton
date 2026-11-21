# 分类评估：按类别、阈值与错误类型看模型

- 原文：[Evaluate AutoML classification and regression models](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/classification-regression/evaluate-model)
- 来源：Google Cloud 官方文档；查阅：2026-11-16。
- 本文为中文理解笔记，非原文转载。

## 来源要点

文档展示分类评估中的 precision、recall、混淆矩阵及不同 confidence threshold 下的指标，帮助分析阈值与分类表现，而不是只查看一个总体分数。

## 我的理解与 Auton 推论

工具域或 Skill 选择可以按分类任务分析，但不同错误代价不同。把复杂任务误下放与把简单任务交给强执行模型，不应只按同样的一次分类错误处理。需要按判断点、任务类别和关键错误分别设门槛。

先用开发集选择阈值，再冻结候选做盲测。拒绝或弃权也要报告覆盖率，不能通过减少回答把正确率刷高。本地上线依据应包含端到端任务成功与效率，这超出文档中的普通分类评估。

## 局限与建议验证

文档的云产品接口不必引入 Auton；借鉴的是指标维度。可变选项、多解题、评分区间和时序依赖需要另定评估方法，不能全部套固定标签的 accuracy。
