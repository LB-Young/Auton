# Auton

个人 Agent 工作台。当前完成 **M01 项目框架、M02 持久事件内核、M03 固定控制策略、M04 执行模型网关与 M05 本地判断接入**：模块工厂、显式依赖组装、FastAPI API、React 对话界面与合成 Demo；M06–M21 尚未实现。

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

**Demo 数据仅在当前后端进程内存中存在。** 同一浏览器刷新可重新查询会话；重启后端后全部清空。主题存 localStorage，所选会话 ID 存 sessionStorage，浏览器归属 cookie 为 HttpOnly；这些不是模型密钥。

这是框架演示，不是已实现的 Agent 执行。聊天尚未接入持久数据库；没有真实项目资料管理、工具执行、长期记忆、训练或发布；右侧笔记标记 `source=demo`，未写入项目目录。每个服务最多 50 个会话、每个会话 100 条消息、200 个幂等命令，达到限制时提示重置/新建，不无限占用内存。

## 配置与替换实现

默认读取 `config/demo.toml`，启用固定事件流 `scripted`。配置通过 Pydantic 严格校验，未知字段/实现和依赖异常直接报错，不能静默 fallback。

```bash
AUTON_CONFIG=config/echo.toml make dev
AUTON_CONFIG=config/dev.toml make dev
```

`echo.toml` 换成内存回声实现，API/页面不变。`dev.toml` 关闭 Demo，真实执行接口返回 `501 not_implemented`，不会伪造模型输出。`test.toml` 用于本地单元/契约测试，来源仅允许 testserver，不用于浏览器演示。

服务仅面向本机开发。HTTP 写命令校验来源白名单、浏览器归属和命令头；WebSocket 校验 Origin 与归属，跨会话访问返回不存在。当前不提供生产账号/公网认证或完整业务操作审计，不应改成公网监听使用。M03/M06/M11 会进一步实现策略、操作账本与完整服务协议。

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

`make contracts` 从 Python schema 导出 `contracts/openapi.json`，再使用必要的 TypeScript 工具生成浏览器类型；不要手动修改生成文件。WebSocket 的 `session.updated` 是带完整状态的快照，包含 sequence、run/goal 引用、schema_version 和来源。慢客户端可合并旧快照；重连重新获取当前内存状态，不承诺持久事件回放或保存每个 token。M02 已提供独立 SQLite WAL/FULL EventLog；Demo 聊天尚未接入，业务投影与会话恢复留给 M10/M11。

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

复制 `.env.example` 到忽略的 `.env`，本机填入 `DEEPSEEK_API_KEY`，或使用同名环境变量。默认配置仅授权 public 数据发往 DeepSeek；主对话仍是 Demo。模型页可发送固定公开短句检测连接并显示用量，失败不会切到 Mock。

`ModelGatewayPort` 支持流式文本、JSON 和工具协议，预算/幂等/断流状态落事件日志。显式真实验收：`.venv/bin/python scripts/model_smoke.py`，会调用六个短请求并产生少量费用；不在 CI 自动执行。详情见 [M04 验收](docs/milestones/evidence/M04.md)。

## 本地 Laya 判断（M05）

`make judgment-setup` 安装可选依赖并下载固定多语言权重到忽略的 `weights/laya-multilingual`；`make judgment-smoke` 运行本地小样本验收。启动不会自动下载，缺权重时在模型页显示实际状态，推理不回退云端。

模型页提供四种类型化判断的独立预览与轨迹记录。**当前 checkpoint 的领域质量未达自动采用要求，默认保持建议模式**；真实中英六例中档位/信息充分性各正确 3/6，保留高分误判。开启自动链路前需独立质量门禁，见 [M05 验收](docs/milestones/evidence/M05.md)。
