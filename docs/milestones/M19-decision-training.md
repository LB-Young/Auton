# M19：本地类 Jev 训练与四层评估

> 状态：通用决策训练、描述性评估和证据门禁已实现；真实训练、完整隔离 Agent 与实时影子验收待目标环境完成。见 [M19 证据与限制](./evidence/M19.md)。

## 目标与前置依赖

持续训练本地决策 student，并用独立评估判断它何时具备接手资格。

前置：M05、M13、M17。M01 必须先完成；其余按依赖验收后进入。

## 模块与工厂

DecisionTrainingFactory、DecisionBackendFactory、ShadowEvaluatorFactory。对外 Port、配置、实现选择、依赖注入与生命周期遵守 [工厂规范](./module-factory-contract.md)，调用方不得依赖具体 adapter。

## 开发任务

- [ ] 按 Laya/AnyJev 等候选的实际训练接口导出数据，encoder 与 LLM 读出分别适配，不统一套聊天 SFT。
- [ ] 对照 seed、上版本地 champion 和 Jev；测各判断点质量、校准、覆盖、旧能力与真实硬件资源。
- [ ] 构建完整隔离 Agent 对照，固定执行模型/工具/Genome；仅历史静态回放不宣称完整收益。
- [ ] 影子只保存预测，使用新近盲测与关键难例、报告证据量和区间；仅生成 release report。

## 前端交付

决策模型候选、按判断点对照、校准/遗忘、Agent 任务收益与影子差异。页面遵循 [前端规格](./frontend-design.md)，具备加载、空、失败、不可用与权限不足状态。

## 验收条件

1. 新模型不靠只测 KEEP、只看一致率或几乎全弃权取得通过。
2. 影子结果不影响任何动作，未批准本地 candidate 无法成为在线 JudgmentFactory 默认值。
3. 按 scope 发布质量/回归/成本/覆盖证据；不足就保留 champion 或 Jev-only。

## 必验故障

选项重排、中文长状态、未知域、高置信错答、旧任务退化、反复 test 过拟合。针对行为做契约/集成或端到端验证，交付可复现步骤与结果。

## 范围与完成证据

实际上线见 M20；本里程碑无 Jev/本地动态路由或故障接管。

交付实现、相关检查结果、接口/配置/迁移说明和页面演示；由验收证据更新 [总表](./README.md)，不以 Mock 通过替代真实模块完成。

## 本次流程范围

遵循用户最新要求，不根据开发电脑选硬件、不在此执行真实训练。首期参考 backend 是独立 HF encoder-choice student，不冒充原生 Laya head；encoder 与 LLM JSON 读出有分离的数据适配，LLM 实际训练 backend 仍需目标模型模板验证。

已交付 DecisionTrainingFactory、DecisionBackendFactory、ShadowEvaluatorFactory、受限作业、候选、描述性指标、四层缺失项报告、历史留出预测回放与前端。实际 champion/独立金标、完整隔离 Agent 执行、实时影子及部署效果继续保持未验；当前报告只出 HOLD，不引入在线 student 路由。
