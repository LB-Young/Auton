# M17：数据加工、快照与谱系

> 状态：计划中。当前仅建立开发计划，未实现本里程碑。

## 目标与前置依赖

把合格历史加工成分离、可追踪、可直接导出的训练/验证数据产物。

前置：M10、M13、M16。M01 必须先完成；其余按依赖验收后进入。

## 模块与工厂

DatasetPipelineFactory、ExporterFactory、LineageStoreFactory。对外 Port、配置、实现选择、依赖注入与生命周期遵守 [工厂规范](./module-factory-contract.md)，调用方不得依赖具体 adapter。

## 开发任务

- [ ] 资格/授权/脱敏/去重/家族分组/split 锁定先行；派生或 teacher 重写不能跨 split。
- [ ] 分别构建 RouterDataset、ExecutorDataset、DecisionDataset；判断正样本只消费合格 KEEP。
- [ ] canonical 样本与具体训练导出分离，manifest 关联 source、模型、模板、input_cutoff 和质量报告。
- [ ] 实现幂等批处理、不可变 snapshot、撤回传播与受限导出，真实数据不入公开 Git。

## 前端交付

数据批次、质量报告、分组/来源、导出任务和删除影响范围。页面遵循 [前端规格](./frontend-design.md)，具备加载、空、失败、不可用与权限不足状态。

## 验收条件

1. 任一训练目标可追溯原始事件与准入理由，未来轨迹不混入当时输入。
2. 近重复和同源分支不跨 split，test/meta 不进入训练导出。
3. 撤回/旧 KEEP 撤销能阻止后续使用并定位受影响快照和候选。

## 必验故障

截断工具对、错误 loss mask、teacher 条款未知、secret 泄漏、重复构建、撤回与导出竞态。针对行为做契约/集成或端到端验证，交付可复现步骤与结果。

## 范围与完成证据

只产获准数据，不启动训练或直接决定模型可上线。

交付实现、相关检查结果、接口/配置/迁移说明和页面演示；由验收证据更新 [总表](./README.md)，不以 Mock 通过替代真实模块完成。
