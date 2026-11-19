# 配置指南

[全部配置字段、默认值、类型、枚举和数值限制](reference/configuration.md) 由当前 ApplicationConfig 生成，包含所有模块及 ModelSpec/BaseModelSpec 等嵌套类型。本文说明这些参数如何使用；请求级参数见 [API 参数](reference/api-schemas.md)。

## 文件与覆盖规则

`AUTON_CONFIG` 指定一个完整 TOML 文件；未指定时读取仓库的 `config/demo.toml`。不会自动合并多个 TOML，未写的字段使用代码默认值。示例 training.example.toml/operations.example.toml 的内容需要合并到你的部署配置中；不是额外读取的文件。

从项目根目录启动。相对 AUTON_CONFIG、数据目录、权重目录和 `.env` 按启动工作目录解析；在其他目录运行时使用绝对路径。未知字段、未知实现、错误枚举和越界值会拒绝启动，不自动回退。

| 环境变量 | 作用 |
| --- | --- |
| AUTON_CONFIG | 运行配置 TOML 的路径 |
| DEEPSEEK_API_KEY | 默认 DeepSeek 凭据，或改用 models.secret_reference 指定的变量名 |
| AUTON_LOCAL_MODEL_… | 每个本地执行模型的独立运行时凭据引用，不能复用云 key |
| AUTON_API_PORT | Vite 开发代理的 API 目标端口；不改变 `make api` 的监听端口 |
| AUTON_WEB_PORT | 单独 `make web` 时的前端端口；`make dev` 会覆盖为默认值 |
| AUTON_BROWSER_CHANNEL | Playwright 浏览器渠道，例如 chrome |
| AUTON_BASE_URL / AUTON_EVIDENCE_DIR | 手动运行浏览器测试时的服务地址/截图目录；make e2e 提供隔离配置 |
| PYTEST_ADDOPTS | pytest 原生选项，可用于定向浏览器验收 |
| PYTHON / DEV_PYTHON | Make 变量：安装/清理所用 Python 与项目环境 Python 路径 |

.env 只存密钥，由 SecretStore 读取；进程环境同名值优先于 .env，不会把整个 .env 注入所有 worker。AUTON_CONFIG/端口等启动变量应在命令环境设置，不能以为写入 .env 就会被启动器读取。`.env`、Cookie、数据库、权重、导出和 checkpoint 均不提交 Git。

## 根字段与运行模式

| 字段 | 语义 |
| --- | --- |
| profile | demo/test/dev/production；与 mock、身份后端、实现的组合会校验 |
| implementation | scripted/echo 提供合成 Demo；disabled 关闭 Demo。dev/production 要求 disabled |
| chunk_delay_seconds | Demo 分块间隔秒数，不控制真实模型速度 |
| allowed_origins | HTTP/WebSocket 使用的明确本机 Origin 白名单，不能含 URL 路径或用户名 |

`test` 要显式使用 mock 执行模型和判断模型；内存身份/内存事件日志仅允许 test。配置名 production 不代表已经提供公网账户或完成生产验收。

## 模块参数的用途

模块的全部具体字段与范围在参数表中按类型列出。`directory` 是模块私有状态目录；kernel 使用 `data_directory`，context 的 tokenizer_directory、judgment 的 directory 则是资源目录。

| TOML 表 / 类型 | 参数如何使用 |
| --- | --- |
| kernel / KernelConfig | backend 选择持久 SQLite 或仅测试 memory；data_directory 下保存 kernel/events.sqlite3；busy_timeout_ms 是数据库忙等待毫秒 |
| server / ServerSettings | 身份后端、有效期、数量上限、上传体积/有效期、流分页和发送超时；各 *_seconds 为秒 |
| constitution / ConstitutionConfig | allowed_actions、remote_providers、需审批动作、自治上限、目标总预算、并发与授权期限；首次加载后的政策修订/持久行为见 M03 证据 |
| models / ModelConfig | 云执行后端、密钥引用、请求超时和并行度；local_targets 是显式固定的本地部署列表；fixture_scenario 只用于测试 |
| judgment / JudgmentConfig | 本地 Laya 目录、固定 revision、推理 device、token 和加载/推理超时；application_enabled 不等于质量门槛已通过 |
| tools / ToolConfig | 受控工作区根目录、只读总开关、单文件/输出字节上限、固定程序超时和本地 MCP 开关；不授予任意 shell 权限 |
| genome / GenomeConfig | 项目资产 Git 仓库、发布 profile 的存储目录；正式/候选分支由模块管理 |
| context / ContextConfig | tokenizer_directory、最大证据数量、切块字符数和远程协议预算余量；不能以字符近似冒充精确 tokenizer |
| agent / AgentConfig | 模型步数、token/声明成本/工具调用、输出和活动运行数上限；judgment_wait_seconds 只等待确知未派发的判断容量拒绝 |
| experience / ExperienceConfig | 轨迹投影位置、分页/重建批次等边界；原事件仍是事实来源 |
| assess / AssessConfig | 裁判模型、题库/文档/并发/窗口上限，真实校准样本及下界；rubric/checker/statistics 版本受固定实现约束 |
| delegation / DelegationConfig | 父工作流数、子任务数、并发、保留数量和超时；父子预算/验收仍逐项核对 |
| evolve / EvolutionConfig | 诊断/反思模型、隔离实验的调用/步数/时间/重复/独立家族与收益门槛；候选不自动发布 |
| decision_review / DecisionReviewConfig | 复核模型、每阶段成本、输入体积、并发，以及真实人工 meta 家族/类别覆盖/污染上界等门槛 |
| datasets / DatasetConfig | 来源/样本/单样本/快照/导出大小上限与格式版本；配置上限不替代逐项数据许可 |
| training / TrainingConfig | disabled/docker、固定镜像、基础模型清单、目标 device、资源/空间/时长/并发和训练步数上限 |
| decision_training / DecisionTrainingConfig | 独立目录与同类训练资源；workload 固定为 decision，参考训练架构为 encoder_choice |
| release / ReleaseConfig | 独立家族数、质量区间下界、初始灰度比例、监控数量及文档上限；不自动批准 |
| operations / OperationsConfig | 显式宿主开关/observer-only、循环间隔、租约/派发期限、队列/重试/预算/新样本门槛、前台抢占与监控保留 |

## 参数单位与层级

- `*_bytes` 是字节，`chunk_characters` 是字符，`*_tokens` 是 token；不是同一种预算。
- `*_microusd` 为百万分之一美元，1,000,000 μUSD = 1 USD。金额是登记价格下的已知声明成本；未知费用另列，不包含 GPU 电费/租金。
- `*_seconds` 为秒，busy_timeout_ms 为毫秒；比例有 0–1（置信/质量下界）和 1–100（percentage）两种，遵循字段范围。
- 宿主配置设最大权限/资源；请求的 RunLimits 等只能收紧，不能借一次请求扩大宿主权限。
- `expected_version` 是目标对象的当前版本；`expected_goal_revision` 是目标修订；state_cutoff/checkpoint version 与全局事件 cursor 不能混用。
- request_id 应为固定逻辑命令生成一次并在重试时复用；改变目标或输入使用新 ID。不要每次网络重试都换 ID。

## 本地模型与训练对象

`models.local_targets` 中每个 ModelSpec 必须绑定 loopback endpoint、独立 secret reference、精确 bundle/adapter/base/template/runtime/fingerprint、解析器和 LoRA rank。配置该条目只登记部署目标，不会取得生产执行权。字段和跨字段相容要求见 [发布部署](local-runtime-and-release.md)。

`training.base_models` / `decision_training.base_models` 中 BaseModelSpec 记录完整模型 revision、许可证、架构、目录内每个文件的 SHA、工具解析器/模板。镜像须固定 image@sha256。禁止从 TOML 任意导入 Python 实现或远程代码。训练由部署环境决定模型与 CPU/CUDA 资源，不依赖开发电脑配置。

示例见 [训练配置](../config/training.example.toml)、[后台配置](../config/operations.example.toml)。worker 的输入/输出 manifest、部署运行时 JSON 和模型资格门槛分别见 [M18](milestones/evidence/M18.md)、[M19](milestones/evidence/M19.md)、[运行时发布](local-runtime-and-release.md)、[后台运行](background-operations.md)。

## 数据与迁移

`.auton_local/` 保存身份、政策、事件、工作区、投影、报告、数据、训练/发布/后台状态；具体子目录以配置表为准。`weights/` 保存显式下载的本地资源。删除私有身份或权威数据库可能使历史无法恢复归属；仅删除投影缓存和删除原始事实不是一回事。

政策和任务有固定版本/持久状态，改 TOML 不会无条件重写已经批准的运行、旧预算或工件。需要迁移目录时停止原服务并按模块恢复，保持身份/数据库/事件日志一致。调度备份仅覆盖 operations，详见后台说明。
