# 模块边界与工厂模式开发规范

> v0.1，2026-11-16。所有里程碑必须遵守的开发约定；M01 已实现公共工厂/组装与 Demo，其他模块按本规范逐步落地。

## 1. 基本结构

采用模块化单体起步：Python 后端、独立 Web 前端、明确公共契约。先获得可替换、可测试的模块边界，不先拆成多进程微服务。运行与学习的隔离需求由受限 worker/进程实现，不以拆分服务代替权限控制。

每个业务模块必须有公开 Port、配置模型、Factory 和生命周期；默认实现、Mock、外部适配器都由工厂创建。普通值对象、纯函数、内部算法和 React 基础组件不强制各造一个工厂；工厂作用于模块与可替换策略边界。

```text
src/auton/<module>/
  __init__.py       # 仅导出稳定公共契约
  ports.py          # Protocol、请求/返回类型
  config.py         # 类型化配置与验证
  factory.py        # ModuleFactory + 显式实现注册
  service.py        # 默认应用服务，必要时再拆子文件
  adapters/         # 存储、provider、运行后端等实现
  events.py         # 模块事件，沿用 kernel 事件信封
```

小模块可从 ports/config/factory/service 四个文件开始；不为尚未开发功能批量填充空文件。M01 先提供模块清单与公开契约草案，后续在对应里程碑落地内部实现。

## 2. 工厂契约

以下是设计示意，不是现成代码或必须复制的泛型库：

```python
class ModuleFactory(Protocol[ConfigT, DependenciesT, ServiceT]):
    def create(self, config: ConfigT, deps: DependenciesT) -> ServiceT: ...
```

- 依赖显式传入：clock、event sink、允许的 repository/client、logger、资源限额；业务服务不能自己查全局容器。
- 工厂根据已验证配置与白名单创建实现，例如 mock/sqlite/provider；未知实现直接报错，不能静默降级为 Mock。
- 只有 composition root 可以组装具体实现；模块间通过公开 Port 交互，不 import 对方 adapters 或私有 service。
- create 不偷偷发网络请求或启动后台循环；资源打开、健康检查、start/stop/close 的 async 生命周期由 bootstrap 编排。
- 默认实例作用域显式：应用级连接池、会话级状态、run 级预算；不能把 session/run 状态藏进全局 singleton。
- 启动失败关闭已创建资源，正常停机先停止接收任务再排空或保存 checkpoint；重复关闭安全。
- Mock 与真实实现遵守同一契约测试，但 Mock 记录不得进入真实训练池或发布证据。

按需提供子工厂，如 ProviderFactory、CheckerFactory、TrainingBackendFactory、ReleaseStrategyFactory；禁止一个巨大 switch 同时承包全部业务。

## 3. 组装、注册与可替换性

`src/auton/bootstrap/` 是组装入口，读取配置、验证依赖 DAG、构建资源与服务、启动生命周期。模块注册清单包含 id、config schema、提供的 Port、依赖 Port、工厂入口、状态和能力版本。

未实现模块返回 `not_implemented`/`disabled` 能力说明，不注册假服务伪装 ready。依赖缺失或出现环时启动配置校验失败；允许关闭非必需模块后以受限能力启动，限制必须在 UI 和 API 一致可见。

禁止直接从配置加载任意 Python/JS 路径。实现选择使用应用内白名单注册；引入外部插件另行走供应链和权限设计，不默认开放执行任意代码。

后端工厂选择本地或远程 provider，不等于允许动态路由 Jev/DecisionStudent。判断来源选择依赖批准的发布配置；未批准的本地 candidate 永远不能由 factory 默认启用。

## 4. 前端工厂与模块接口

每个 feature 具有 `createXxxFeature(deps)` 工厂，返回路由、页面/面板注册、使用的 controller 或 hooks、能力需求和清理逻辑。依赖是 API client、事件订阅器、导航与能力服务，不从页面直接创建 provider/训练进程。

可替换的 MessageRenderer、ArtifactViewer、DecisionPanel、MetricView 使用类型注册与 renderer factory。未知类型提供可读的“不支持该内容”视图，不动态执行服务器传来的组件代码。

前端工厂是创建模块与适配器的机制，不要求给每个函数组件套类。组件只调用 feature controller；API transport 由 ApiClientFactory 建立，Mock 与真实 backend 是显式开发配置。

## 5. 依赖规则

- kernel 不依赖业务模块；业务事件使用共享信封，业务 schema 保留在所属模块公共契约。
- constitution 是代码执行的固定边界；学习与进化模块不能改自己的 checker、权限与 holdout。
- Agent Loop 不依赖 experience/assess/evolve/learning 实现；只发事件，后台消费它们。
- model 与判断接口不反向依赖训练代码；release 经专用受限接口激活 bundle。
- server handler 调用应用 Port；前端通过版本化 API，不能访问 Python 内部对象、数据库或 Git 工作目录。
- composition root 可以同时依赖各模块工厂；它不得成为存放路由、训练或评审业务逻辑的地方。

## 6. 模块完成的统一要求

交付工厂、契约、默认实现及最小可信 Mock；至少验证一次替换实现仍能工作，以及非法配置/资源失败不会静默继续。涉及持久化、外部写、训练或发布时，加入相应恢复与失败场景；不为纯样板代码堆测试。

每个里程碑提供 API/schema 变更、事件与迁移说明、对应 UI 状态、可执行验收步骤和证据。lint、类型检查、相关契约/集成检查通过；新增依赖方向由 import-linter/前端边界检查约束。

禁止用“页面画完”“Mock 演示成功”“loss 降低”替代真实模块验收。尚未满足的范围留在计划，不在状态表标完成。

## 7. 模块实现归属

里程碑是开发与验收单元，不要求每个单元变成独立 Python 包或服务。同一个大包内的子模块也必须具备自己的工厂与公共契约，不能因为共享父目录就读取彼此私有状态。

| 里程碑 | 主要实现归属 | 边界说明 |
|---|---|---|
| M01 | `src/auton/bootstrap`、最小 `server`、`clients/web` | 负责组装与演示，后续模块增量替换 Demo |
| M02 | `src/auton/kernel` | 共享信封、日志和基础资源 |
| M03 | `src/auton/constitution` | 固定策略，供运行和后台只读使用 |
| M04 | `src/auton/model/gateway`、`registry` | 执行模型 provider，不含训练 |
| M05 | `src/auton/model/judgment`、`routing` | 判断来源与执行模型路由分开 |
| M06 | `src/auton/tools` | 工具、隔离与操作账本 |
| M07 | `src/auton/genome` | 项目/资产引用与记忆治理 |
| M08 | `src/auton/context` | 装配、检索与压缩 |
| M09 | `src/auton/agent`、`clients/cli` | 单 Agent 运行与命令入口 |
| M10 | `src/auton/experience` | 可重建投影、轨迹和检查点 repository |
| M11 | `src/auton/server` | handler 调应用 Port，不内嵌运行/训练业务 |
| M12 | `clients/web/src/features` | 完善框架已建立的工作台 |
| M13 | `src/auton/assess` | 独立评估与受保护评测服务 |
| M14 | `src/auton/agent/delegation` | 委派、租约与结果集成 |
| M15 | `src/auton/evolve` | 诊断、候选、门禁；正式激活留发布子模块 |
| M16 | `src/auton/learning/decision_review` | 证据复核与三态准入 |
| M17 | `src/auton/learning/datasets`、`lineage`、`ingest` | 数据快照与导出，不能越权读取 holdout |
| M18 | `src/auton/learning/executor_training` | 执行模型训练；共用 job Port/资源服务 |
| M19 | `src/auton/learning/decision_training` | 决策模型训练，与执行 SFT 分开 |
| M20 | `src/auton/evolve/release`、`learning/release` | 不同发布权限与状态机，共用批准/审计契约 |
| M21 | `src/auton/scheduling`、`observability` | 全局调度与遥测；各模块基础日志/取消不等到此时才做 |

每个模块对应的 Web feature 随该模块交付。依赖关系由任务单和可用 Port 决定，不由文件夹位置或实例注册顺序决定。
