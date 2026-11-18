# Auton 开发里程碑

> v0.1，2026-11-16。M01 项目框架已实现并通过本地验收，见 [验收记录](./evidence/M01.md)。M02 已完成，见 [验收](./evidence/M02.md)。M03 已完成，见 [验收](./evidence/M03.md)。M04 已接入真实 DeepSeek，见 [验收](./evidence/M04.md)。M05 已完成本地工程接入，当前质量未达自动采用门槛，见 [验收](./evidence/M05.md)。M06 受控工具范围已完成，见 [验收](./evidence/M06.md)。M07 人工资产与记忆治理已完成，见 [验收](./evidence/M07.md)。M08 固定检索与完整轮次压缩已完成，见 [验收](./evidence/M08.md)。M09 受控单 Agent 执行闭环已完成，见 [验收](./evidence/M09.md)。M10–M21 计划中。
> 开发顺序以本目录为准，替代总架构原先 M1–M6 的粗粒度安排；旧 M/J/R/D/T 编号只是研究阶段参考，不直接等同本目录编号。

## 1. 必须先做什么

**第一步必须是 M01：搭项目框架、模块工厂、前后端可运行骨架。** 不先写 Agent、工具业务或训练再回头补结构。此后逐模块开发与完善，每个模块有独立 Factory/Port、契约检查、前端增量和验收证据。

- [M01 项目框架任务单](./M01-project-foundation.md)
- [模块与工厂模式规范](./module-factory-contract.md)
- [前端页面与交互设计](./frontend-design.md)：参考 ChatGPT 的项目/对话组织与 Claude 的产物工作区，首期即进入开发。

采用模块化单体起步，按契约隔离运行、评估、进化、数据与训练。工厂作用于模块和可替换实现，不要求每个函数/值对象都套工厂。

## 2. 里程碑总表

编号表示推荐顺序，前置依赖是实际准入门槛。编号靠后不意味着所有前面的模块都必须完成，例如评审模块可在多 Agent 完成前准备，但 M01 不可跳过。每份任务单都有专属功能、工厂、页面、验收与故障场景。

| 里程碑 | 前置 | 模块工厂/范围 | 首要完成标志 | 状态 |
|---|---|---|---|---|
| [M01 项目框架](./M01-project-foundation.md) | 无 | bootstrap/最小 API/Web 骨架 | 框架工厂、可启动前后端、明确 Demo | 已完成（本地验收） |
| [M02 核心内核与事件持久化](./M02-kernel.md) | M01 | KernelFactory、EventLogFactory、ClockFactory | 追加后进程重启能按序读取；同 event_id 重试不产生重复事实。 | 已完成（本地验收） |
| [M03 固定策略、权限与配置](./M03-constitution.md) | M02 | ConstitutionFactory、PolicyEvaluatorFactory | 禁止外发的数据在模型调用前被拦截，禁止动作在工具执行前被拦截。 | 已完成（本地验收） |
| [M04 执行模型网关与能力注册](./M04-model.md) | M02、M03 | ModelGatewayFactory、ProviderFactory、ModelRegistryFactory | 相同 Port 可替换两个实现；真实请求可流式返回并记录模型版本、成本和结束原因。 | 已完成（本地与真实协议验收） |
| [M05 本地 Laya 判断层与执行模型路由](./M05-judgment.md) | M03、M04 | JudgmentFactory、LayaAdapterFactory、RoutePolicyFactory | 每次本地判断关联输入、问题、原始响应、策略建议与任务版本。 | 工程验收通过；自动采用关闭 |
| [M06 工具宿主、执行隔离与操作账本](./M06-tools.md) | M02、M03 | ToolHostFactory、ToolAdapterFactory、SandboxFactory、OperationLedgerFactory | 可只读的任务不能写入；越界路径、过期审批和取消后新动作被拒绝。 | 已完成（受控本地范围） |
| [M07 资产、项目资料与记忆治理](./M07-genome.md) | M02、M03 | GenomeFactory、AssetRepositoryFactory、MemoryPolicyFactory、ResolverFactory | 同一 snapshot 可复现；历史版本能查看和回退，来源与项目权限可追踪。 | 已完成（人工治理范围） |
| [M08 上下文装配、检索与压缩](./M08-context.md) | M04、M06、M07 | ContextEngineFactory、RetrieverFactory、CompressorFactory | 长会话超限前有可解释压缩/阻塞，消息与工具协议保持完整。 | 已完成（固定检索与轮次压缩） |
| [M09 单 Agent 运行时与任务状态机](./M09-agent.md) | M05、M06、M08 | AgentRuntimeFactory、SessionFactory、RunFactory | 完成一个受控文件任务与一个只读调研任务，交付真实 artifact 和验收结果。 | 已完成（受控单 Agent） |
| [M10 轨迹投影、检查点与恢复](./M10-experience.md) | M02、M09 | ExperienceFactory、ProjectionFactory、CheckpointRepositoryFactory | 删掉可重建投影后从 EventLog 恢复得到一致查询结果。 | 计划中 |
| [M11 服务端 API、命令与事件流](./M11-server.md) | M03、M09、M10 | ServerFactory、CommandHandlerFactory、EventStreamFactory | 浏览器断开不取消服务端任务；重连后正确恢复状态且不重复命令。 | 计划中 |
| [M12 前端工作台完善与真实联调](./M12-web.md) | M07、M09、M10、M11 | WebAppFactory、createChatFeature、createProjectsFeature、ArtifactViewerFactory | 真实任务从新建到审批、工具、产物、刷新恢复可完整操作。 | 计划中 |
| [M13 独立评估、可信信号与校准](./M13-assess.md) | M03、M10 | AssessFactory、CheckerFactory、JudgeFactory、EvalStoreFactory | 评测者不能被优化/训练模块修改，test/meta 不泄漏给候选生成器。 | 计划中 |
| [M14 多 Agent 委派与结果集成](./M14-delegation.md) | M06、M09、M10、M13 | DelegationFactory、RoleFactory、WorkspaceLeaseFactory、ResultIntegratorFactory | 同一受控任务的单/多 Agent 对照记录总成本与收益，不以更多调用宣称提升。 | 计划中 |
| [M15 资产诊断、候选补丁与门禁](./M15-evolve.md) | M07、M13 | EvolutionFactory、DiagnoserFactory、MutationStrategyFactory、GateFactory | 用一个受控 Skill 改进案例跑通候选到评测报告，失败候选被保留原因。 | 计划中 |
| [M16 决策轨迹复核与样本筛选](./M16-decision-review.md) | M05、M10、M13 | DecisionReviewFactory、AttributionPolicyFactory、ReviewerAdapterFactory | 错误但被补救成功的判断不会自动 KEEP，合理但环境失败的判断不会机械 DROP。 | 计划中 |
| [M17 数据加工、快照与谱系](./M17-datasets.md) | M10、M13、M16 | DatasetPipelineFactory、ExporterFactory、LineageStoreFactory | 任一训练目标可追溯原始事件与准入理由，未来轨迹不混入当时输入。 | 计划中 |
| [M18 本地执行模型训练](./M18-executor-training.md) | M04、M13、M17 | ExecutorTrainingFactory、TrainingBackendFactory、TrainingJobFactory | 同一数据与配置可复现并恢复训练，失败不触发重复昂贵 job。 | 计划中 |
| [M19 本地类 Jev 训练与四层评估](./M19-decision-training.md) | M05、M13、M17 | DecisionTrainingFactory、DecisionBackendFactory、ShadowEvaluatorFactory | 新模型不靠只测 KEEP、只看一致率或几乎全弃权取得通过。 | 计划中 |
| [M20 统一发布控制面、灰度与回滚](./M20-release.md) | M13、M15；模型发布另需 M18 或 M19 | ReleaseFactory、GenomeReleaseFactory、ModelReleaseFactory、RolloutPolicyFactory | 未经批准或报告范围不匹配的候选不能激活；自动训练不获得发布权。 | 计划中 |
| [M21 后台调度、运行监控与长期验证](./M21-scheduler-operations.md) | M10、M15、M17、M18/M19、M20 | SchedulerFactory、JobQueueFactory、TelemetryFactory、RetentionPolicyFactory | 进程重启不重复训练或发布，worker 失联可恢复且不会双重执行。 | 计划中 |

## 3. 用户可见的交付节奏

1. **M01 后**：可启动的工程与对话工作台 Demo；可以演示布局和交互，明确不是实际 Agent。
2. **M09 后**：CLI/服务应用层完成受控真实单 Agent 任务，模型、Jev、工具、上下文和日志已经按模块接通。
3. **M12 后**：主 Web 工作台真实联调完成，具备会话、状态恢复、审批、产物与异常交互。
4. **M13–M17**：可信评测、多 Agent、资产改进候选与合格数据链路逐项可用；资产进化和模型学习保持独立。
5. **M18–M19**：得到受评估的本地执行/决策候选，均不因训练完成自动上线。
6. **M20–M21**：在独立批准和范围政策下发布、观测、回滚，之后再自动化常驻调度。

每个模块都交付相应 UI，而不是等全部后端完工再统一补前端。M12 是主工作台完善；评测、训练和发布页仍在各自里程碑实现。

M02–M10 的查询和页面增量挂载到 M01 已建立的最小 server/API 壳；不必等 M11 才能联调。M11 是命令、权限、事件续传与恢复协议的完整化，M12 再完成主流程真实联调和可用性验收。学习与发布模块也通过同一注册机制增量接入。

## 4. 通用开发与验收流程

每个里程碑先确认 Port/schema/状态机和依赖，随后落地工厂与最小实现，再做 API/事件/前端联调，最后验证真实成功、失败和恢复。一次任务围绕一个模块或清楚界定的契约变更，避免一个 PR 把多个里程碑整体落地。

提交需列出对应 Mxx、接口变化、数据迁移、验收步骤、实际检查结果和未完成范围。以可运行结果验收，不以创建目录数量、文档页数或测试数量验收。对于安全、持久化、训练和发布，故障路径是功能的一部分。

状态枚举：计划中 → 进行中 → 待验收 → 已完成；阻塞需说明具体依赖/原因。仅更新当前真实状态，不能因为文档已写好就把模块标完成。完成证据建议记在 `docs/milestones/evidence/Mxx.md`，目录在首次产生真实证据时再建。

不预报无依据的日期。M01 完成后，依据实际速度、可用开发时间、硬件和外部服务限制细化工期；每个模块可划分小任务，但不得绕过准入依赖。

## 5. 贯穿整个计划的约束

- 当前判断接入按 [最新用户选择](./model-provider-decision.md) 使用本地 Laya（待 M05）；执行任务的 2B/7B/强模型路由仍是独立功能。
- 本地 DecisionStudent 在 M19 只离线训练/影子评测；M20 只提供经批准的按 scope 发布能力，不默认激活任何模型，也不引入难度/置信度的动态 Jev/本地路由。
- Jev 逐次判断关联 trajectory，经独立 reviewer 筛选 KEEP/DROP/HOLD；DROP 不混进正向训练，证据不足不强判。
- 运行权限、业务 checker、受保护 holdout 不归候选模型/进化代码修改；训练与发布权独立。
- Demo/Mock、真实运行、合成训练样本和生产证据明确标来源；真实失败不能静默退回 Mock。
- 任何会话、工具、灰度或模型切换都需要保留副作用与操作账本语义，不能盲重放。

## 6. 与设计资料的关系

- [总架构](../self-evolution-architecture.md)：对象、边界和资产设计；本目录明确实施顺序。
- [执行问题手册](../agent-execution-problems-and-solutions.md)与[构建案例](../agent-builder-case-studies.md)：各模块风险与故障验证输入。
- [执行模型路由/学习](../model-routing-and-local-learning.md)：M04/M05/M17/M18 的详细数据与能力契约。
- [Jev 判断/本地决策学习](../jev-decision-learning.md)：M05/M16/M17/M19 的判断与归因契约。
- [决策模型评估/发布](../decision-model-evaluation-and-release.md)：M13/M19/M20 的四层评估、灰度、证据量与回滚策略。

如后续更改模块边界或上线政策，先同步本目录与专项设计，不能在实现中悄悄改变。
