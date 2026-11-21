# 功能与使用指南

默认前端已改为 [对话工作区](conversation-workspace.md)：左侧历史、中间多轮对话、右侧按需工作面板。下文的模块页面描述保留给 `?legacy=1&view=模块ID` 的开发入口及后端接口使用；日常对话不需要逐项配置这些模块。


先阅读 [快速启动](quickstart.md)。配置字段与约束见 [配置指南](configuration.md) / [完整参数表](reference/configuration.md)，每个 HTTP 请求/响应的全部字段见 [API 参数](reference/api-schemas.md)。

## 工作台入口

默认首页为真实任务入口；`?view=chat` 是独立的合成演示。以下参数加在前端地址之后，例如 `http://127.0.0.1:5173/?view=genome`。

| 页面 | URL view | 用途 |
| --- | --- | --- |
| 任务 | agent | 创建任务、选模型、逐项审批、交付与恢复 |
| 资产 | genome | 项目、说明、Skill/资料/记忆、候选、晋升和撤回 |
| 工具 | tools | 独立工作区、受控文件/固定程序、差异、审批与凭据 |
| 上下文 | context | 资料检索、保留证据、精确 tokenizer 和预算 |
| 模型 | model | 执行模型连接、实际能力/用量、判断预览 |
| 评测 | assess | 独立报告、题库、盲测窗口、裁判校准 |
| 多 Agent | delegation | 文件 worker DAG、依赖、子审批、最终合并 |
| 进化 | evolve | 诊断、Skill 差异、隔离实验、候选审核 |
| 决策复核 | decision_review | 合理性/贡献审查、KEEP/DROP/HOLD、人工校准 |
| 学习数据 | datasets | 精确授权、快照、谱系/划分、导出和撤权 |
| 执行训练 | training | 冻结计划、离线 worker、checkpoint 和候选 |
| 决策训练 | decision_training | 类 Jev 学生训练、四层评估和离线回放 |
| 发布 | release | 独立批准、固定任务灰度、暂停和回滚 |
| 后台 | operations | 显式计划、队列、资源窗口、趋势和恢复 |
| 设置 | settings | 本地身份、策略、存储与连接状态 |
| 演示 | chat | 内存合成会话、流式显示、停止和演示产物 |

## 建议的完整使用顺序

1. 配置 key 和模型资源，启动服务；在模型页核对可用性。
2. 在资产页创建项目，上传/录入资料，审阅后晋升。上传不等于批准发布。
3. 在工具页建立独立工作区；初次调研用只读模式，文件任务才选择可审批写入模式。
4. 在任务页选项目、工作区和执行模型，填写目标/边界/验收；需要远程模型时明确确认输入和资料可外发。
5. 逐项审核写入差异。完成后检查实际交付和轨迹；未知副作用先对账，不盲目重试。
6. 需要学习时先独立评测和复核，再授权指定历史记录、构建/导出数据，在最终部署环境训练。
7. 独立报告达到门槛后，由用户在发布页审核批准；后台自动化不会取得发布权。

## 演示与实际能力

演示聊天不需要 key，内容和产物标记 demo，后端重启后清空。真实任务、项目、检查点及身份使用持久本地存储。浏览器和 CLI 默认是不同身份，不能仅凭同一个项目名共享数据。

当前通用训练、发布和调度工程均已实现；真实训练质量、独立金标/live shadow/完整 Agent 收益及部署验证并未由工程测试替代。本地 Laya 为建议来源，自动采用门槛未通过；线上决策学生仍未接手。模型失联、缺权重或门槛不足会明确阻塞，不自动改用测试输出。

## 模型连接

复制 `.env.example` 到忽略的 `.env`，本机填入 `DEEPSEEK_API_KEY`，或使用同名环境变量。默认配置仅授权 public 数据发往 DeepSeek；演示对话保留独立入口，默认任务页接真实执行。模型页可发送固定公开短句检测连接并显示用量，失败不会切到 Mock。

`ModelGatewayPort` 支持流式文本、JSON 和工具协议，预算/幂等/断流状态落事件日志。显式真实验收：`.venv/bin/python scripts/model_smoke.py`，会调用六个短请求并产生少量费用；不在 CI 自动执行。详情见 [M04 验收](milestones/evidence/M04.md)。

## 本地判断

`make judgment-setup` 安装可选依赖并下载固定多语言权重到忽略的 `weights/laya-multilingual`；`make judgment-smoke` 运行本地小样本验收。启动不会自动下载，缺权重时在模型页显示实际状态，推理不回退云端。

模型页提供四种类型化判断的独立预览与轨迹记录。**当前 checkpoint 的领域质量未达自动采用要求，默认保持建议模式**；真实中英六例中档位/信息充分性各正确 3/6，保留高分误判。开启自动链路前需独立质量门禁，见 [M05 验收](milestones/evidence/M05.md)。

## 受控工具（M06）

工具页可创建独立只读/审批写入工作区，预览差异、逐次批准、原子写入、读回并下载校验后的文件。另有固定 Python 版本/语法检查和本地 MCP SHA256。默认目录 `.auton_local/tools` 被忽略，不授权修改本仓库或其他目录。

未知写入结果先对账，不盲重放；重复命令复用原凭据。当前只提供 POSIX 受控目录和固定程序，不开放任意代码，也不宣称 OS 安全沙箱。M11 已提供浏览器身份跨后端重启保持。见 [M06 验收](milestones/evidence/M06.md)。

## 版本资产与记忆（M07）

资产页可创建项目说明，管理 Skill/Prompt/角色/知识/资料/记忆候选。候选进入本地 Git learning 分支；人工晋升才更新正式 main。可查看历史、差异、回退和固定使用快照。

撤回会传播到派生引用并阻止旧快照再次读取；过期记录不参与解析。Git 审计历史仍保留，逻辑撤回不等于物理擦除。默认本地目录 `.auton_local/genome` 被忽略，资料不随代码推送 GitHub。见 [M07 验收](milestones/evidence/M07.md)。


## 上下文装配（M08）

先在资产页创建项目并审核资料，再在上下文页选择项目/执行模型，输入目标、必留边界和可选旧轮次。页面仅装配和保存输入，不调用模型；演示对话与默认真实任务入口独立。远程模型准入需明确声明此次输入与项目资料均可公开。

```sh
make context-setup   # 下载并校验两套固定 tokenizer，约 13 MB，不下载执行模型权重
make context-smoke   # 本地真实 tokenizer：中英文、工具定义与调用/响应历史
.venv/bin/python scripts/context_smoke.py --hosted  # 显式调用两个真实 DeepSeek 短请求
```

缺少 tokenizer 时明确阻塞，不用字符近似或测试替身降级。检索使用词项/中文 bigram 基线，显示来源、内容 SHA256 和字符区间；不可信资料不授予权限。预算不足时先移除低优先级证据，再移除完整旧轮次，目标、边界、未决操作 receipt 和最新修订始终保留，仍放不下则阻塞。原始轨迹和 checkpoint 不被覆盖。

界面分别显示本地 token 数与保守准入预算；服务端实际 usage 用于结算。配置 `[context]` 支持 `tokenizer_directory`、`max_evidence`、`chunk_characters`、`hosted_overhead_tokens`。见 [M08 验收与限制](milestones/evidence/M08.md)。


## 真实任务（M09）

在资产页创建项目并审核资料，在工具页创建受限工作区，再进入任务页。当前支持已有项目资料的只读调研和精确文本文件交付；执行模型由用户明确选择，Laya 仅记录建议。远程调用前应明确声明任务、资料及工作区内容可外发。写入需逐项审阅批准，不提供任意 shell 或任意 Python 执行。

文件验收比对实际文件与用户预先给出的 SHA256；资料报告检查引用是否指向本次保留证据。结构验收通过不等于语义质量已评估，独立质量评估接 M13。停止先进入 cancelling，等待在途动作结果；未知写入需要对账，不能盲目重试。默认任务工作台展示真实消息、审批与交付；Demo 有独立入口。

CLI 使用同一应用接口，身份文件仅保存在忽略的 `.auton_local/cli`：

```sh
.venv/bin/python scripts/agent_cli.py init example --notes /path/to/public-notes.md
.venv/bin/python scripts/agent_cli.py create --file /path/to/run.json
.venv/bin/python scripts/agent_cli.py list example
.venv/bin/python scripts/agent_cli.py get RUN_ID
.venv/bin/python scripts/agent_cli.py command RUN_ID pause --revision 1
.venv/bin/python scripts/agent_cli.py command RUN_ID resume --revision 1
```

`init --editable` 才允许建立可申请写入的工作区；已有工作区的权限范围不会被修改。`init --notes` 显式导入并晋升选定资料，不覆盖已有不同内容。浏览器与 CLI 默认是不同主体，分别初始化自己的项目。

公开资料调研的 `run.json` 示例：

```json
{
  "request_id": "research-example-1",
  "project_id": "example",
  "workspace_id": "example",
  "model_id": "deepseek-flash",
  "goal": "Research the public project notes and cite [asset:notes].",
  "allowed_tools": ["file.read"],
  "data_domain": "public",
  "acceptance": {"kind": "research", "min_sources": 1}
}
```

`make agent-smoke` 会使用本地 Laya 与真实 DeepSeek，在独立公开测试项目完成文件/调研验收，产生少量 API 费用；不会作为默认 CI。默认单任务最多 8 次模型调用、8 次工具调用、16000 tokens、10000 microUSD（按登记价格估算），并叠加 M03 的独立权限/预算门禁。M09 安全点可以用相同可信主体恢复；浏览器/CLI 跨后端重启的持久身份已接 M11，轨迹投影与恢复管理已接入 M10。见 [M09 验收](milestones/evidence/M09.md)。


## 轨迹与检查点恢复（M10）

任务执行记录下新增“轨迹与恢复”：查看原始事件时间线、处理游标、判断/授权/模型/工具/验收关联、episode 用量与缺失证据。在暂停或阻塞的安全边界，可从已核对检查点恢复；旧版本会被拒绝，未知工具仍须先对账，恢复不会跳过原审批。

投影缓存位于忽略的 `.auton_local/experience`，只保存事件元数据与检查点引用，不复制原始模型消息或凭据。可从 M02 原始事件重建；当前支持索引 schema 1→2 重投影，未知版本明确拒绝。查询仅供用户检查和恢复，不授予训练导出权限。

```sh
.venv/bin/python scripts/agent_cli.py trajectory RUN_ID --project example
.venv/bin/python scripts/agent_cli.py recover RUN_ID --project example --version VERSION --revision REVISION --checkpoint-event EVENT_ID
.venv/bin/python scripts/agent_smoke.py --inspect-existing  # 复核已存在的隔离真实验收记录，不新增模型/工具调用
```

`state_cutoff` 的 run checkpoint version 与全局事件 cursor 分开保存。未知用量、缺失快照和旧修订晚到结果不会被当成完整的成功证据。后端已验证独立进程重启、确认写入后进程直接退出的恢复，两者均不重复写入；浏览器/CLI 跨后端重启的持久身份已接 M11。见 [M10 验收](milestones/evidence/M10.md)。

## M11 本机服务协议

任务页使用持久检查点游标的 WebSocket 通知与 HTTP 精确快照恢复。断开页面不会停止任务；连接恢复不会重发命令。临时生成内容明确标记为尚未保存，重启后只恢复已确认结果。Demo 会话仍为内存存储，独立 Agent 任务和项目资料保持原来的持久存储。

默认身份与上传元数据保存在 `.auton_local/server/` 的 SQLite WAL/FULL 数据库；当前有效 Cookie 只保存散列，内部身份独立于 Cookie。浏览器和 CLI 各自使用身份，重启服务后有效身份继续访问自己的原有数据；身份默认有效 30 天，数据库与私有 Cookie 文件不可删除或提交。过期会显式拒绝，不自动创建另一个身份。设置页提供显式新建身份；此操作不会转移旧数据。

M10 及更早版本的 Cookie 只有在原浏览器/CLI 私有文件仍保留时才能证明归属。升级后若提示身份无效，可在设置页选择“恢复升级前的本机身份”，填写原身份拥有的项目 ID。服务端从原项目验证归属，旋转 Cookie 并保留原 namespace；旧 Cookie 被撤销，不能重复迁移。没有旧 Cookie 或有效身份证明时不会通过项目名称认领他人数据。当前不提供公网账号/跨设备找回或已过期新身份的恢复流程。

资产页可上传 UTF-8 文本/Markdown：先声明项目、大小、SHA256，再提交原始字节；默认最多 128 KiB、32000 字符，意图 10 分钟过期。上传仅进入学习候选，仍需人工审阅晋升；不支持二进制附件。默认上传/身份元数据各限 1000 项；创建新记录时清理过期超过 7 天的记录，旧身份迁移撤销标记保留。HTTP 请求总量限制为 2 MiB，包括 chunked body。

`[server]` 可配置 `directory`、`identity_ttl_seconds`、`max_identities`、`max_upload_bytes`、`upload_ttl_seconds`、`stream_page_size`、`stream_send_timeout`。`identity_backend="memory"` 只允许 test profile。服务仍绑定回环地址，拒绝非本机客户端。详见 [M11 验收及协议](milestones/evidence/M11.md)。

## M12 真实任务工作台

默认首页可选择项目、工作区和执行模型，创建调研或精确文件任务，查看模型消息、暂停/恢复、修订目标、批准或拒绝写入。拒绝会记录审批反馈并通过当前目标/检查点 CAS 停止任务；反馈记录不等于独立质量结论。项目资料仍从资产页上传、审阅和晋升；未公开的数据不会因选择远程模型而自动授权外发。

打开任务页或点击“新任务”后，会显示聊天式输入框并自动聚焦。输入目标后点击向上箭头或按 Enter 发送，Shift + Enter 换行。项目、工作区、模型、验收方式和权限收在输入框下方的“任务设置”里，默认折叠；项目任务列表也默认折叠，可展开“项目会话与任务”查看。没有项目或工作区时也可以先输入目标，再通过提示进入资产页或工具页配置；在页面间切换会保留当前草稿，开始执行前仍需选择项目、工作区和模型。缺少配置时点击发送或按 Enter，会展开任务设置并提示缺少的项目，不创建任务，也不会丢弃输入。“新任务”清空目标、任务边界、文件要求和远程外发确认，保留项目、工作区及模型选择。

`?view=agent&project=项目ID&run=任务ID` 可刷新恢复授权任务；URL 只保存标识，不保存用户目标或 Cookie。模型失败不会替换成 Demo。新任务保留独立 run；历史原文和检查点不被编辑覆盖。当前继续操作是恢复已暂停任务；终态需创建新任务，不宣称任意多轮自由聊天或自动继承其他任务历史。

历史按创建顺序使用持久游标分页，支持大小写无关目标搜索；每页默认 10、最多 20 项。一次最多扫描 1000 条来源事件，可能出现空但仍可继续的页面；新分页接口不会触发旧整表接口的 100 项限制。消息区支持 Markdown、代码复制、手动回到底部和阅读位置保持；产物经授权接口只读预览/下载，HTML 不执行，面板宽度可用键盘调整。

`make workbench-smoke` 显式使用本地 Laya 与真实 DeepSeek 运行公开文件任务，人工审批由验收脚本操作，再只重启本次创建的隔离后端核对恢复。`scripts/workbench_smoke.py --reuse-completed` 用忽略目录中的 0600 私有测试 Cookie 检查已有任务，不新增模型调用。脚本不会停止其他服务或上传用户数据，结果在 `test-results/workbench-native.json`。见 [M12 验收](milestones/evidence/M12.md)。


## 独立评测（M13）

评测页可选择真实运行的确切检查点，独立核验文件摘要/工具协议，查看四类证据、未知样本、分组、候选对照与盲测窗口。`semantic` 默认关闭，显式开启才调用强裁判并产生费用；人工偏好与模型自信不能作为gold。

题库区分train/development/test/meta，默认种子只生成train；人工金标需单独审核导入。裁判原始输入/答案保存于私有`assess.directory/judge-journal`，不进入训练轨迹。校准不足/漂移/自评/重复分歧保持未知，评测不会自动上线模型。参见[M13证据与接口配置](milestones/evidence/M13.md)。

真实验收可运行`.venv/bin/python scripts/workbench_smoke.py --assess`（公开合成数据，会调用Laya、DeepSeek执行模型及两次强裁判）；`--reuse-completed --assess`复用同一已完成任务/报告验证恢复，不重复付费。


## 多 Agent 委派（M14）

`多 Agent`页提供用户明确的父目标、文件worker DAG、固定资料快照与总预算。子任务使用私有工作区、独立审批与独立评测；父文件先核验合并摘要，再单独批准写入。取消停止后继并传播到子任务，未知结果保留租约等待对账，重启不会自动重复执行。

初期只支持受控文件worker与固定顺序拼接，不开放递归分工或未校准的语义子任务。单、多Agent对照记录实际用量，更多调用不会自动得到“改进”标签。参见[M14验收、API、预算与限制](milestones/evidence/M14.md)。

`make delegation-smoke`显式运行真实Laya/DeepSeek公开合成任务及单Agent基线（使用API额度）；`.venv/bin/python scripts/delegation_smoke.py --reuse-completed`复用本机已完成结果验证进程恢复，不重复模型调用。

## 资产诊断与隔离进化（M15）

进化工作台 `?view=evolve` 支持证据诊断、单 Skill 小节 diff、一次有界反思、基线/候选/移除 Skill 同预算评测、逐次文件审批、Playbook 和学习候选审核。门禁不足保留 HOLD，候选不自动启用；真实公开工程案例三组均成功，未证明改进收益。

运行 `make evolution-smoke` 可执行真实付费验收；已有结果通过 `.venv/bin/python scripts/evolution_smoke.py --reuse-completed` 只读重用。参见[M15 接口、持久化、边界与验收](milestones/evidence/M15.md)。

## 决策轨迹独立复核（M16）

决策复核工作台 `?view=decision_review` 将当时合理性与后续贡献分开审查，校验真实引用、是否采用、验收、目标版本和多 Agent 影响链。DROP/HOLD 不进正样本；人工修订、晚到纠正和配置变化会使旧资格失效。当前 Laya 未采用且缺少真实人工 meta/因果对照，自动 KEEP 门禁关闭。

`make decision-review-smoke` 在已完成的 M15 公开工程轨迹上进行两次有界真实复核；已有记录用 `.venv/bin/python scripts/decision_review_smoke.py --reuse-completed` 只读重用。真实 reviewer 无引用的环境归因被拒绝并保留 HOLD，未把模型输出当作真值。参见[M16 接口、门禁与验收](milestones/evidence/M16.md)。

## 数据快照与谱系（M17）

`?view=datasets` 提供范围明确的授权、三类数据批次、来源/分组/划分、拒绝原因、JSONL 导出与撤回。授权默认关闭；原始模型事件、工具凭据、独立验收与固定版本必须匹配。私有数据库和导出文件不入 Git。test/meta、reviewer meta、全部进化实验分支禁止进入学习；测试来源只能验证工程，不能导出训练。

`make dataset-smoke` 复用本机 M15 的公开原始诊断任务，验证真实文件动作导出、授权撤回与下载拒绝，不增加付费模型调用。`.venv/bin/python scripts/dataset_smoke.py --reuse-completed` 验证新进程重用。当前只有一条真实样本，尚未开始训练，也不能据此宣称效果提升。见 [M17 验收与限制](milestones/evidence/M17.md)。

## 通用执行模型训练流程（M18）

`?view=training` 提供训练计划、数据与基础模型版本检查、手动作业、预算、checkpoint、取消/恢复和离线候选。配置见 `config/training.example.toml`；模型、模板、镜像和资源由目标部署环境决定，不绑定当前开发电脑。默认训练后端关闭，核心服务不安装训练依赖。

参考离线 Docker worker 实现 Transformers/PEFT LoRA、精确目标 token mask、基线/训练后验证和 safetensors 恢复。所有候选保持发布资格关闭；本次只验证通用工程流程，没有在当前电脑执行训练，也没有证明模型效果改善。部署与未验证项见 [M18 验收](milestones/evidence/M18.md)。

## 决策 student 通用流程（M19）

`?view=decision_training` 与执行训练分开。`DecisionTrainingFactory` 只接受当前合格 Decision 数据，参考后端是可配置 HF encoder 的选项排序训练；LLM JSON 读出另有数据导出适配。指标分别记录覆盖率、校准、各判断点与来源组，不把 teacher KEEP 一致率当独立金标准确率。

四层评估只消费已登记候选与真实引用，缺少 gold、champion、完整隔离 Agent 或部署证据时保持 HOLD。离线预测回放标明不是实时影子，永不影响在线动作。本次没有在开发电脑训练模型，线上 student 路由保持关闭。见 [M19 工程与待验范围](milestones/evidence/M19.md)。


## 独立发布、灰度和回滚

发布页固定候选来源、报告 digest、执行版本、语言/数据范围及比例。先保存报告，满足独立门槛后勾选风险确认并批准，再显式激活。缺报告、来源撤权、工件/部署 fingerprint 变化或预热失败会拒绝激活。

执行模型的隔离验证授权不改变默认模型。任务页显式选择“项目批准的灰度策略”才进入稳定 goal 分组；原手选模型不被覆盖。暂停停止新分配，回滚撤销后续执行权并对账受影响任务；未知工具结果不会被伪称成功撤销。决策学生当前只支持 offline 登记，线上继续教师来源。

部署工件、三个运行时接口、完整请求步骤和回滚条件见 [本地运行时与发布](local-runtime-and-release.md)。

## 后台调度、告警与恢复

后台默认关闭。部署方启用宿主后，用户仍需登记有截止时间、资源窗口、预算、固定输入且明确确认的计划。review/数据/训练是一次性操作；只有监控和监控采样保留允许周期执行。新训练需要足够新的合格监督数据，不靠计划改名重复训练。

页面可暂停/恢复当前身份、控制具体任务、检查未知用量和告警、生成私有调度备份。恢复要求空目标与精确 SHA，并默认保持暂停。原始业务数据不被监控 retention 顺带删除。完整 API、参数语义、成本预留、前台优先、checkpoint 恢复与部署演练见 [后台运行说明](background-operations.md)。
