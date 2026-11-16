# M01：项目框架、模块工厂与前端骨架

> 状态：已完成（2026-11-16，本地验收通过）。M01 首先完成了框架、工厂与前端骨架；真实模型/工具仍未接入。详见 [验收证据](./evidence/M01.md)。

## 目标与依赖

从仅有 docs 的分支搭建可启动、可检查、可替换模块实现的工程。依赖为已存在的设计文档，无前置开发里程碑。M01 完成后才开始具体模块实现。

## 1. 项目结构

```text
Auton/
  pyproject.toml             # Python 包、开发依赖、工具配置
  <python-lockfile>          # 选定依赖管理工具后落定名称
  src/auton/
    bootstrap/               # 配置、模块注册、组装、生命周期
    kernel/                  # 最小契约，M02 再补持久化等实现
    server/                  # 健康检查、能力清单、Demo API
  clients/web/               # React + TypeScript + Vite
  contracts/                 # OpenAPI/schema 快照与生成说明
  tests/                     # 契约、集成、浏览器端到端
  config/                    # 无密钥配置样例：demo/dev/test
  scripts/                   # 启动、检查、契约生成
  docs/milestones/
  .github/workflows/         # CI
```

Python 使用既有 3.12 设计基线，后端延续 FastAPI/asyncio/Pydantic；前端采用上述组件栈。M01 核对相容稳定版本并锁定 Node、包管理器和依赖，不使用漂移的 latest。运行数据、密钥、权重、训练样本和临时产物加入忽略规则；配置样例只含合成值。

## 2. 工厂与模块注册先落地

- [x] 实现 ModuleFactory、显式 Dependencies、LifecycleHandle、ModuleDescriptor 和 capability registry 的最小契约，遵守 [模块工厂规范](./module-factory-contract.md)。
- [x] composition root 负责依赖验证、实例创建、启动/停止与异常清理；业务代码不得通过全局 service locator 找依赖。
- [x] 将 README 模块表登记为开发清单；仅给当前可演示模块提供实现，其他标 planned/disabled，按里程碑逐个落地。
- [x] 用 DemoConversationFactory 的两个实现验证替换能力：内存回声实现与固定事件流实现；测试中替换不修改 handler 或 UI。
- [x] 后端 ServerFactory 与前端 createChatFeature/ApiClientFactory/EventStreamFactory 都通过组装入口创建，不从组件直接 new 网络实现。
- [x] 明确 app/session/run 作用域，配置不合法、工厂未注册、依赖环与启动失败都可诊断；不能失败后默默切 Mock。

## 3. 前后端可操作骨架

- [x] 后端提供健康、能力查询和版本化 Demo 会话 API；默认仅监听本机，开发跨域白名单显式配置，变更命令具备基本来源/会话校验。
- [x] 定义消息、命令响应和事件信封的首版 schema，生成 TypeScript 类型；暂不把 Demo 内存事件当持久 EventLog。
- [x] 实现侧栏、项目/会话导航、中央对话、输入区、右侧产物面板、明暗主题与窄屏布局，详见 [前端设计](./frontend-design.md)。
- [x] Demo 模式可新建会话、发送、接收模拟流、发停止命令并展示确认、打开合成产物；后台持续标 Demo，Demo 来源不可进入真实数据管线。
- [x] 加载、空状态、失败、断线和未开发功能有明确文案；无后端能力的按钮不可伪装可用。
- [x] 正式配置下模块未实现就明确不可用，不生成模拟回答；provider key 不进入前端包。

## 4. 工程质量与交付文档

- [x] 新增根 README：环境、安装、配置、启动前后端、运行检查、Demo 限制与模块开发入口。
- [x] 固定格式、lint、严格类型检查、相关测试、前端 typecheck/build、API 类型生成一致性与依赖边界检查到 CI。
- [x] 演示一条跨 HTTP/WebSocket 的端到端链路，记录启动和停止行为；基础日志脱敏，不把完整 payload 默认写日志。
- [x] 每个后续里程碑建立可追踪任务列表与验收证据位置；状态从计划中变为进行中/待验收/已完成时附证据。

## 验收

1. 干净 checkout 按 README 能启动前后端，主页面可操作，无需真实模型密钥。
2. 替换 Demo 工厂实现只改组装配置；API 调用方与页面不改，相关契约检查通过。
3. 页面能完成“新会话 → 发消息 → 收到模拟流 → 停止确认 → 查看产物”，桌面和 390px 窄屏可用。
4. 正式 profile 调用未实现模块返回明确不可用；未知 factory、依赖缺失和启动失败不会显示 ready。
5. CI 所列检查通过，类型生成一致；截图、运行记录和配置说明足以复现。

## 范围边界与下一步

M01 不接真实 Jev、执行模型、工具写入、训练或发布；只实现框架所需的最小契约与 Demo。真实持久化从 M02、执行模型从 M04、Jev 从 M05 开始。不能以“先做最小 Agent”为由跳过工厂和前端骨架。

交付后进入 [M02 核心内核](./M02-kernel.md)。
