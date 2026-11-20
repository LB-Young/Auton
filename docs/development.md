# 开发、测试与维护

工程以 Python 工具编排后端与前端，React/TypeScript 用于浏览器界面。模块开发遵循 [工厂和依赖边界规范](milestones/module-factory-contract.md)。

## 目录

| 目录 | 内容 |
| --- | --- |
| src/auton/bootstrap、kernel、constitution | 应用组装、公共生命周期/存储与固定权限预算 |
| src/auton/model、judgment、context、tools、genome | 执行/判断模型、上下文、受控工具、项目资料 |
| src/auton/agent、experience、server、cli | Agent 闭环、轨迹、本地服务和 CLI |
| src/auton/assess、delegation、evolve、decision_review | 独立评测、委派、隔离进化和复核 |
| src/auton/datasets、training、release、operations | 数据、通用离线训练、独立发布和后台运行 |
| clients/web | 前端 feature/transport 工厂与页面 |
| contracts | 自动生成 OpenAPI/协议 schema |
| scripts、tests | Python 开发工具与契约/集成/浏览器验收 |
| config、containers、docs | 配置示例、部署 worker 配方与使用/设计文档 |

## 常用命令

| 命令 | 作用 |
| --- | --- |
| make server | 自动准备完整推理资源并用预设真实配置启动；仅需 key |
| make setup | 安装锁定的核心/开发与前端依赖 |
| make dev / api / web | 同时/分别启动本机服务 |
| make check | Ruff、格式、strict mypy、非浏览器测试、依赖边界、敏感信息、契约漂移、前端 lint/build |
| make contracts | 从 Python schema 更新 OpenAPI 及前端类型；不要手工改生成类型 |
| make browser-install | 下载 Playwright Chromium |
| make e2e | 在独立临时端口/目录启动服务，运行浏览器测试，仅关闭自己的进程 |
| AUTON_BROWSER_CHANNEL=chrome make e2e | 使用已安装 Chrome |
| make clean-preview | 仅预览可再生成缓存/空目录清理 |
| make clean / clean-cache / clean-build / clean-empty | 清理全部指定范围 / 缓存 / 构建 / 空目录 |

Python 等价入口：`python3 scripts/setup.py`；`.venv/bin/python scripts/dev.py all|api|web|check|contracts|e2e`。清理脚本参数为 `--scope all|cache|build|empty` 和 `--dry-run`。清理保留 Git 跟踪文件、依赖环境、符号链接与运行数据，不用删除私有数据来解决版本冲突。

浏览器截图输出到忽略的 test-results。`PYTEST_ADDOPTS='-k background_operations' AUTON_BROWSER_CHANNEL=chrome make e2e` 可定向执行。CI 配置在 [.github/workflows/check.yml](../.github/workflows/check.yml)；本地通过不等于远端 CI 通过。

## 参数文档更新

```bash
make contracts
.venv/bin/python scripts/export_user_docs.py
.venv/bin/python scripts/export_user_docs.py --check
```

生成 docs/reference 下的配置、HTTP 路由和请求/响应参数表。生成器只读取代码默认值和提交的 OpenAPI 文件，不读取密钥，不创建应用，不调用模型。接口/配置增加字段后同步更新这些参考；使用指南中的业务步骤另需人工维护。

## 可选资源和显式验收

| 命令 | 资源/效果 |
| --- | --- |
| make context-setup | 下载固定 tokenizer，不下载执行权重 |
| make judgment-setup | 安装可选 Laya 依赖并下载固定权重 |
| make context-smoke / judgment-smoke | 本地上下文/判断验收；本地推理需要相应资源 |
| python scripts/model_smoke.py | 真实模型连接/协议验收，使用 API 额度 |
| make agent-smoke / workbench-smoke | 真实 Agent/页面与重启验收，使用 API 额度 |
| make delegation-smoke / evolution-smoke / decision-review-smoke | 真实委派、隔离实验或决策复核，使用 API 额度 |
| make dataset-smoke | 基于已存在的指定真实历史整理/验证数据，不自动补造历史 |
| make operations-smoke | 观察专用命名空间中复用既有历史，监控/备份，不训练或发布 |

复用参数按具体脚本区分：delegation/evolution/decision_review/dataset 支持 `--reuse-completed`；agent_smoke 支持 `--inspect-existing`；context_smoke 的 `--hosted` 会额外调用真实模型。workbench_smoke 的其他选项以 `--help` 为准。不要把付费脚本加入默认启动/普通测试，也不要把 fixture 或一次运行的成功当作质量提升结论。

## 状态、备份与排障

权威数据库、身份与原始事件需要一致备份，不能只删其中一个目录。发生未知模型/工具结果时先保留记录、读取凭据与检查点，再显式对账。恢复后台状态默认暂停；正式资产后续被人工改动时，回滚应报告冲突而不是覆盖。

调度备份范围、恢复顺序及故障演练见 [后台运行](background-operations.md)。真实模型训练/运行、资源硬隔离、质量、跨机恢复与长期收益仍需最终部署环境验证。
