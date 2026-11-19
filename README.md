# Auton

个人 Agent 工作台。当前完成 **M01 项目框架、M02 持久事件内核、M03 固定控制策略、M04 执行模型网关、M05 本地判断接入、M06 受控工具、M07 版本资产、M08 上下文引擎、M09 单 Agent 执行闭环、M10 轨迹恢复、M11 服务协议、M12 真实工作台、M13 独立评测工程、M14 受控多 Agent 、M15 资产诊断/隔离进化、M16 决策复核工程与 M17 数据快照/谱系**：模块工厂、显式依赖组装、FastAPI API、React 对话界面与合成 Demo；M18–M21 尚未实现；M13 尚缺真实人工金标校准，语义可信门禁关闭。

后端和开发/验收辅助工具优先使用 Python。仅浏览器界面及其必要构建配置使用 TypeScript/React；Makefile 是 Python 命令入口。

## 启动

需要 Python 3.12、uv 0.11.7、Node 22.14.0、npm 11.8.0。Python/Node 版本分别记录在 `.python-version` / `.node-version`；依赖由 `uv.lock` 与 `clients/web/package-lock.json` 锁定。

```bash
make setup
make dev
```

打开 [本机工作台](http://127.0.0.1:5173)。后端监听 `127.0.0.1:8000`，开发前端通过代理访问 API/WebSocket。Ctrl+C 停止两个进程。端口被占用时先停止占用服务；开发工具不会杀掉其他进程。

也可以直接运行 Python：

```bash
.venv/bin/python scripts/dev.py all
```

`make api` / `make web` 可以分别启动。`make help` 列出全部入口。安装需要网络；运行 Demo 对话不需要模型 key。模型页连接检测会按需调用 DeepSeek；配置方法见下。

## 可以体验什么

- 新建会话、建议提示、发送消息、通过真实 WebSocket 查看合成流式回复。
- 停止演示并等待服务端确认；断开页面不等于停止任务。
- 查看/下载合成 Markdown 产物、展开/调整/关闭产物面板。
- 项目/会话导航与标题搜索、明暗主题、桌面与手机布局。
- 未来模块的真实状态说明，以及设置页的连接/运行配置。

默认首页是真实任务工作台，`?view=chat` 或侧栏“演示对话 · Demo”才进入合成演示。

**Demo 数据仅在当前后端进程内存中存在。** 同一浏览器刷新可重新查询会话；重启后端后全部清空。主题存 localStorage，所选会话 ID 存 sessionStorage，浏览器归属 cookie 为 HttpOnly；这些不是模型密钥。

Demo 对话是合成框架演示；默认任务页使用真实 Agent 和持久记录。Demo 聊天尚未接入持久数据库；独立资产页已支持人工项目资料与记忆治理，工具页可真实执行受控操作；训练与发布尚未实现；右侧笔记标记 `source=demo`，未写入项目目录。每个服务最多 50 个会话、每个会话 100 条消息、200 个幂等命令，达到限制时提示重置/新建，不无限占用内存。

## 配置与替换实现

默认读取 `config/demo.toml`，启用固定事件流 `scripted`。配置通过 Pydantic 严格校验，未知字段/实现和依赖异常直接报错，不能静默 fallback。

```bash
AUTON_CONFIG=config/echo.toml make dev
AUTON_CONFIG=config/dev.toml make dev
```

`echo.toml` 换成内存回声实现，API/页面不变。`dev.toml` 关闭 Demo；真实执行在任务页通过独立 Agent API 使用，不会伪造模型输出。`test.toml` 用于本地单元/契约测试，来源仅允许 testserver，不用于浏览器演示。

服务仅面向本机开发。HTTP 写命令校验来源白名单、浏览器归属和命令头；WebSocket 校验 Origin 与归属，跨会话访问返回不存在。当前不提供生产账号/公网认证或完整业务操作审计，不应改成公网监听使用。M03/M06/M11 已提供策略、操作账本与完整本机任务服务协议。

## 工程结构与模块规范

```text
src/auton/
  kernel/       公共工厂、生命周期、错误、模块描述与 DAG 校验
  bootstrap/    配置、白名单模块清单与 composition root
  demo/         会话 Port、两种 responder 工厂、内存流与命令去重
  server/       ServerFactory、HTTP/WebSocket handler
clients/web/    React/TypeScript 界面，feature/transport 工厂
scripts/        Python 安装、启动、检查、契约生成、清理工具
contracts/      从后端生成的 HTTP 与 WebSocket schema
tests/          Python 契约/集成/浏览器验收
config/         不含密钥的运行配置样例
docs/           设计、参考笔记与 M01–M21 开发计划
```

新增模块遵守 [工厂与边界规范](docs/milestones/module-factory-contract.md)。工厂只创建实例，bootstrap 编排启动/关闭；应用级、会话级、run 级状态分开。只有组装入口了解具体实现，handler/页面只使用公共 Port。未来模块在 capability registry 中标 planned，不创建假服务或空业务目录。

## 检查与契约

```bash
make check
make contracts
```

`make check` 包含 Ruff 格式/lint、mypy strict、非浏览器测试、Python/前端依赖边界、OpenAPI/生成类型漂移检查、ESLint/Prettier 和 TypeScript/生产构建。契约检查在临时目录比较，不修改工作区。

`make contracts` 从 Python schema 导出 `contracts/openapi.json`，再使用必要的 TypeScript 工具生成浏览器类型；不要手动修改生成文件。WebSocket 的 `session.updated` 是带完整状态的快照，包含 sequence、run/goal 引用、schema_version 和来源。慢客户端可合并旧快照；重连重新获取当前内存状态，不承诺持久事件回放或保存每个 token。M02 已提供独立 SQLite WAL/FULL EventLog；Demo 聊天尚未接入，真实任务的持久轨迹与游标恢复见 M10/M11，Demo 会话仍单独使用内存快照。

## Python 浏览器验收

```bash
make browser-install
make e2e
```

`make e2e` 使用独立临时端口、配置与数据库启动服务，运行 Python Playwright 测试后只关闭本次创建的进程，不干扰已有 `make dev`。Linux CI 使用 `python -m playwright install --with-deps chromium`。也可以使用已安装的 Chrome，跳过 Chromium 下载：

```bash
AUTON_BROWSER_CHANNEL=chrome make e2e
```

覆盖桌面/390px 手机、真实流式回复与停止、产物、刷新恢复、主题保持、输入法 Enter 和断网后草稿恢复。截图默认输出到忽略的 `test-results/`；M01 已验收结果见 [证据记录](docs/milestones/evidence/M01.md)。CI 会重新运行这些检查；本地通过不等于远端 CI 已通过。

## 清理与后续

`make clean-preview` 预览，`make clean` 删除可再生成缓存/构建文件及空目录；保留 Git 跟踪文件、依赖环境、符号链接与运行数据。

M02 存储默认位于 `.auton_local/kernel/events.sqlite3`，设置页明确区分事件日志持久化与聊天内存模式。见 [M02 验收](docs/milestones/evidence/M02.md)。

M03 设置页展示权限、外发边界和单目标预算，并提供不实际执行动作的预检。策略/预算日志可恢复，用户配置修订不会在普通重启时丢失。参见 [M03 验收](docs/milestones/evidence/M03.md)。

下一步是 [M04 执行模型网关](docs/milestones/M04-model.md)；当前指定 DeepSeek 执行、后续本地 Laya 判断，见 [接入选择](docs/milestones/model-provider-decision.md)。完整路线见 [里程碑总表](docs/milestones/README.md)；Jev-only、独立评审筛数据、本地候选须经发布批准等边界保持不变。

## 模型连接（M04）

复制 `.env.example` 到忽略的 `.env`，本机填入 `DEEPSEEK_API_KEY`，或使用同名环境变量。默认配置仅授权 public 数据发往 DeepSeek；演示对话保留独立入口，默认任务页接真实执行。模型页可发送固定公开短句检测连接并显示用量，失败不会切到 Mock。

`ModelGatewayPort` 支持流式文本、JSON 和工具协议，预算/幂等/断流状态落事件日志。显式真实验收：`.venv/bin/python scripts/model_smoke.py`，会调用六个短请求并产生少量费用；不在 CI 自动执行。详情见 [M04 验收](docs/milestones/evidence/M04.md)。

## 本地 Laya 判断（M05）

`make judgment-setup` 安装可选依赖并下载固定多语言权重到忽略的 `weights/laya-multilingual`；`make judgment-smoke` 运行本地小样本验收。启动不会自动下载，缺权重时在模型页显示实际状态，推理不回退云端。

模型页提供四种类型化判断的独立预览与轨迹记录。**当前 checkpoint 的领域质量未达自动采用要求，默认保持建议模式**；真实中英六例中档位/信息充分性各正确 3/6，保留高分误判。开启自动链路前需独立质量门禁，见 [M05 验收](docs/milestones/evidence/M05.md)。

## 受控工具（M06）

工具页可创建独立只读/审批写入工作区，预览差异、逐次批准、原子写入、读回并下载校验后的文件。另有固定 Python 版本/语法检查和本地 MCP SHA256。默认目录 `.auton_local/tools` 被忽略，不授权修改本仓库或其他目录。

未知写入结果先对账，不盲重放；重复命令复用原凭据。当前只提供 POSIX 受控目录和固定程序，不开放任意代码，也不宣称 OS 安全沙箱。M11 已提供浏览器身份跨后端重启保持。见 [M06 验收](docs/milestones/evidence/M06.md)。

## 版本资产与记忆（M07）

资产页可创建项目说明，管理 Skill/Prompt/角色/知识/资料/记忆候选。候选进入本地 Git learning 分支；人工晋升才更新正式 main。可查看历史、差异、回退和固定使用快照。

撤回会传播到派生引用并阻止旧快照再次读取；过期记录不参与解析。Git 审计历史仍保留，逻辑撤回不等于物理擦除。默认本地目录 `.auton_local/genome` 被忽略，资料不随代码推送 GitHub。见 [M07 验收](docs/milestones/evidence/M07.md)。


## 上下文装配（M08）

先在资产页创建项目并审核资料，再在上下文页选择项目/执行模型，输入目标、必留边界和可选旧轮次。页面仅装配和保存输入，不调用模型；演示对话与默认真实任务入口独立。远程模型准入需明确声明此次输入与项目资料均可公开。

```sh
make context-setup   # 下载并校验两套固定 tokenizer，约 13 MB，不下载执行模型权重
make context-smoke   # 本地真实 tokenizer：中英文、工具定义与调用/响应历史
.venv/bin/python scripts/context_smoke.py --hosted  # 显式调用两个真实 DeepSeek 短请求
```

缺少 tokenizer 时明确阻塞，不用字符近似或测试替身降级。检索使用词项/中文 bigram 基线，显示来源、内容 SHA256 和字符区间；不可信资料不授予权限。预算不足时先移除低优先级证据，再移除完整旧轮次，目标、边界、未决操作 receipt 和最新修订始终保留，仍放不下则阻塞。原始轨迹和 checkpoint 不被覆盖。

界面分别显示本地 token 数与保守准入预算；服务端实际 usage 用于结算。配置 `[context]` 支持 `tokenizer_directory`、`max_evidence`、`chunk_characters`、`hosted_overhead_tokens`。见 [M08 验收与限制](docs/milestones/evidence/M08.md)。


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

`make agent-smoke` 会使用本地 Laya 与真实 DeepSeek，在独立公开测试项目完成文件/调研验收，产生少量 API 费用；不会作为默认 CI。默认单任务最多 8 次模型调用、8 次工具调用、16000 tokens、10000 microUSD（按登记价格估算），并叠加 M03 的独立权限/预算门禁。M09 安全点可以用相同可信主体恢复；浏览器/CLI 跨后端重启的持久身份已接 M11，轨迹投影与恢复管理已接入 M10。见 [M09 验收](docs/milestones/evidence/M09.md)。


## 轨迹与检查点恢复（M10）

任务执行记录下新增“轨迹与恢复”：查看原始事件时间线、处理游标、判断/授权/模型/工具/验收关联、episode 用量与缺失证据。在暂停或阻塞的安全边界，可从已核对检查点恢复；旧版本会被拒绝，未知工具仍须先对账，恢复不会跳过原审批。

投影缓存位于忽略的 `.auton_local/experience`，只保存事件元数据与检查点引用，不复制原始模型消息或凭据。可从 M02 原始事件重建；当前支持索引 schema 1→2 重投影，未知版本明确拒绝。查询仅供用户检查和恢复，不授予训练导出权限。

```sh
.venv/bin/python scripts/agent_cli.py trajectory RUN_ID --project example
.venv/bin/python scripts/agent_cli.py recover RUN_ID --project example --version VERSION --revision REVISION --checkpoint-event EVENT_ID
.venv/bin/python scripts/agent_smoke.py --inspect-existing  # 复核已存在的隔离真实验收记录，不新增模型/工具调用
```

`state_cutoff` 的 run checkpoint version 与全局事件 cursor 分开保存。未知用量、缺失快照和旧修订晚到结果不会被当成完整的成功证据。后端已验证独立进程重启、确认写入后进程直接退出的恢复，两者均不重复写入；浏览器/CLI 跨后端重启的持久身份已接 M11。见 [M10 验收](docs/milestones/evidence/M10.md)。

## M11 本机服务协议

任务页使用持久检查点游标的 WebSocket 通知与 HTTP 精确快照恢复。断开页面不会停止任务；连接恢复不会重发命令。临时生成内容明确标记为尚未保存，重启后只恢复已确认结果。Demo 会话仍为内存存储，独立 Agent 任务和项目资料保持原来的持久存储。

默认身份与上传元数据保存在 `.auton_local/server/` 的 SQLite WAL/FULL 数据库；当前有效 Cookie 只保存散列，内部身份独立于 Cookie。浏览器和 CLI 各自使用身份，重启服务后有效身份继续访问自己的原有数据；身份默认有效 30 天，数据库与私有 Cookie 文件不可删除或提交。过期会显式拒绝，不自动创建另一个身份。设置页提供显式新建身份；此操作不会转移旧数据。

M10 及更早版本的 Cookie 只有在原浏览器/CLI 私有文件仍保留时才能证明归属。升级后若提示身份无效，可在设置页选择“恢复升级前的本机身份”，填写原身份拥有的项目 ID。服务端从原项目验证归属，旋转 Cookie 并保留原 namespace；旧 Cookie 被撤销，不能重复迁移。没有旧 Cookie 或有效身份证明时不会通过项目名称认领他人数据。当前不提供公网账号/跨设备找回或已过期新身份的恢复流程。

资产页可上传 UTF-8 文本/Markdown：先声明项目、大小、SHA256，再提交原始字节；默认最多 128 KiB、32000 字符，意图 10 分钟过期。上传仅进入学习候选，仍需人工审阅晋升；不支持二进制附件。默认上传/身份元数据各限 1000 项；创建新记录时清理过期超过 7 天的记录，旧身份迁移撤销标记保留。HTTP 请求总量限制为 2 MiB，包括 chunked body。

`[server]` 可配置 `directory`、`identity_ttl_seconds`、`max_identities`、`max_upload_bytes`、`upload_ttl_seconds`、`stream_page_size`、`stream_send_timeout`。`identity_backend="memory"` 只允许 test profile。服务仍绑定回环地址，拒绝非本机客户端。详见 [M11 验收及协议](docs/milestones/evidence/M11.md)。

## M12 真实任务工作台

默认首页可选择项目、工作区和执行模型，创建调研或精确文件任务，查看模型消息、暂停/恢复、修订目标、批准或拒绝写入。拒绝会记录审批反馈并通过当前目标/检查点 CAS 停止任务；反馈记录不等于独立质量结论。项目资料仍从资产页上传、审阅和晋升；未公开的数据不会因选择远程模型而自动授权外发。

`?view=agent&project=项目ID&run=任务ID` 可刷新恢复授权任务；URL 只保存标识，不保存用户目标或 Cookie。模型失败不会替换成 Demo。新任务保留独立 run；历史原文和检查点不被编辑覆盖。当前继续操作是恢复已暂停任务；终态需创建新任务，不宣称任意多轮自由聊天或自动继承其他任务历史。

历史按创建顺序使用持久游标分页，支持大小写无关目标搜索；每页默认 10、最多 20 项。一次最多扫描 1000 条来源事件，可能出现空但仍可继续的页面；新分页接口不会触发旧整表接口的 100 项限制。消息区支持 Markdown、代码复制、手动回到底部和阅读位置保持；产物经授权接口只读预览/下载，HTML 不执行，面板宽度可用键盘调整。

`make workbench-smoke` 显式使用本地 Laya 与真实 DeepSeek 运行公开文件任务，人工审批由验收脚本操作，再只重启本次创建的隔离后端核对恢复。`scripts/workbench_smoke.py --reuse-completed` 用忽略目录中的 0600 私有测试 Cookie 检查已有任务，不新增模型调用。脚本不会停止其他服务或上传用户数据，结果在 `test-results/workbench-native.json`。见 [M12 验收](docs/milestones/evidence/M12.md)。


## 独立评测（M13）

评测页可选择真实运行的确切检查点，独立核验文件摘要/工具协议，查看四类证据、未知样本、分组、候选对照与盲测窗口。`semantic` 默认关闭，显式开启才调用强裁判并产生费用；人工偏好与模型自信不能作为gold。

题库区分train/development/test/meta，默认种子只生成train；人工金标需单独审核导入。裁判原始输入/答案保存于私有`assess.directory/judge-journal`，不进入训练轨迹。校准不足/漂移/自评/重复分歧保持未知，评测不会自动上线模型。参见[M13证据与接口配置](./docs/milestones/evidence/M13.md)。

真实验收可运行`.venv/bin/python scripts/workbench_smoke.py --assess`（公开合成数据，会调用Laya、DeepSeek执行模型及两次强裁判）；`--reuse-completed --assess`复用同一已完成任务/报告验证恢复，不重复付费。


## 多 Agent 委派（M14）

`多 Agent`页提供用户明确的父目标、文件worker DAG、固定资料快照与总预算。子任务使用私有工作区、独立审批与独立评测；父文件先核验合并摘要，再单独批准写入。取消停止后继并传播到子任务，未知结果保留租约等待对账，重启不会自动重复执行。

初期只支持受控文件worker与固定顺序拼接，不开放递归分工或未校准的语义子任务。单、多Agent对照记录实际用量，更多调用不会自动得到“改进”标签。参见[M14验收、API、预算与限制](./docs/milestones/evidence/M14.md)。

`make delegation-smoke`显式运行真实Laya/DeepSeek公开合成任务及单Agent基线（使用API额度）；`.venv/bin/python scripts/delegation_smoke.py --reuse-completed`复用本机已完成结果验证进程恢复，不重复模型调用。

## 资产诊断与隔离进化（M15）

进化工作台 `?view=evolve` 支持证据诊断、单 Skill 小节 diff、一次有界反思、基线/候选/移除 Skill 同预算评测、逐次文件审批、Playbook 和学习候选审核。门禁不足保留 HOLD，候选不自动启用；真实公开工程案例三组均成功，未证明改进收益。

运行 `make evolution-smoke` 可执行真实付费验收；已有结果通过 `.venv/bin/python scripts/evolution_smoke.py --reuse-completed` 只读重用。参见[M15 接口、持久化、边界与验收](./docs/milestones/evidence/M15.md)。

## 决策轨迹独立复核（M16）

决策复核工作台 `?view=decision_review` 将当时合理性与后续贡献分开审查，校验真实引用、是否采用、验收、目标版本和多 Agent 影响链。DROP/HOLD 不进正样本；人工修订、晚到纠正和配置变化会使旧资格失效。当前 Laya 未采用且缺少真实人工 meta/因果对照，自动 KEEP 门禁关闭。

`make decision-review-smoke` 在已完成的 M15 公开工程轨迹上进行两次有界真实复核；已有记录用 `.venv/bin/python scripts/decision_review_smoke.py --reuse-completed` 只读重用。真实 reviewer 无引用的环境归因被拒绝并保留 HOLD，未把模型输出当作真值。参见[M16 接口、门禁与验收](./docs/milestones/evidence/M16.md)。

## 数据快照与谱系（M17）

`?view=datasets` 提供范围明确的授权、三类数据批次、来源/分组/划分、拒绝原因、JSONL 导出与撤回。授权默认关闭；原始模型事件、工具凭据、独立验收与固定版本必须匹配。私有数据库和导出文件不入 Git。test/meta、reviewer meta、全部进化实验分支禁止进入学习；测试来源只能验证工程，不能导出训练。

`make dataset-smoke` 复用本机 M15 的公开原始诊断任务，验证真实文件动作导出、授权撤回与下载拒绝，不增加付费模型调用。`.venv/bin/python scripts/dataset_smoke.py --reuse-completed` 验证新进程重用。当前只有一条真实样本，尚未开始训练，也不能据此宣称效果提升。见 [M17 验收与限制](./docs/milestones/evidence/M17.md)。
