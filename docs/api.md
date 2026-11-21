# API、WebSocket 与 CLI

完整接口、路径/查询参数、请求体/响应类型见 [HTTP 路由目录](reference/api-endpoints.md)；全部字段、默认值和约束见 [请求响应参数](reference/api-schemas.md)。原始契约是 [contracts/openapi.json](../contracts/openapi.json)，启动后也可读取 `/openapi.json` 或查看 `/docs`。

## 身份与通用约定

接口前缀为 `/api/v1`。首次 `GET /api/v1/bootstrap` 建立当前本地身份，之后保留服务设置的 HttpOnly Cookie。ID/URL 不是访问凭证，不能注入 owner 或 role 取得权限。浏览器与 CLI 默认各自持有身份。

浏览器写请求使用同源 Cookie、`Origin` 和 `X-Auton-Client: web`；JSON 写请求还需 `Content-Type: application/json`。前端代理转发 `/api` HTTP/WebSocket 到后端。swagger 的类型展示可直接查看，但写接口不能忽略这些传输校验。

示例只读查询（Cookie 文件属于凭据，应保存在私有忽略目录）：

```bash
mkdir -p .auton_local/manual-client
curl -c .auton_local/manual-client/cookies.txt http://127.0.0.1:8000/api/v1/bootstrap
chmod 600 .auton_local/manual-client/cookies.txt
curl -b .auton_local/manual-client/cookies.txt http://127.0.0.1:8000/api/v1/models
```

创建项目：

```bash
curl -b .auton_local/manual-client/cookies.txt \
  -H 'Origin: http://127.0.0.1:8000' \
  -H 'X-Auton-Client: web' -H 'Content-Type: application/json' \
  -d '{"id":"my-project","title":"My project"}' \
  http://127.0.0.1:8000/api/v1/projects
```

重试写命令复用相同 request_id/原输入；版本冲突先刷新当前对象。分页 after 通常为事件 cursor，具体接口以目录定义为准。默认响应错误结构为 code/message；401 身份失效、403 权限/外发拒绝、404 无当前身份对象、409 版本/状态/证据冲突、422 参数不合格、429 预算/队列/容量上限、503 资源不可用。错误不表示可以盲目重发未知模型/工具调用。

## 常用请求参数

| 对象 | 关键字段与使用方式 |
| --- | --- |
| CreateRun | request_id/project_id/workspace_id/model_id/goal；可选 boundaries、limits、asset_snapshot_id；data_domain 默认 local-only；acceptance 必填 |
| Acceptance | research 使用 min_sources；file 必须给出相对 path 和预先确定的目标 sha256 |
| RunCommand | action=pause/cancel/resume/approve/reconcile/revise；expected_goal_revision 必填，expected_version 可收紧；只有 revise 接受新 goal |
| 工具计划/审批 | 先 prepare 看差异，批准绑定当前计划/版本与请求摘要；文件 expected_sha256 表示写入前已有内容，不是最终目标摘要 |
| 评测 | 精确 run/version；受保护题库需 case/bank/window；独立来源/校准不足不会变成质量通过 |
| 数据授权/导出 | 指定 run/用途/条款与授权，授权布尔默认 false；导出绑定 snapshot content digest、split 和目的 |
| TrainingPlanCommand | 固定基础模型、train/validation/replay/anchor artifact、rank/优化参数/seed；engineering_probe 不是正式效果资格 |
| ReleasePlanCommand | 固定 kind/source/mode/比例/范围/候选与基线报告；批准需当前版本和精确 evidence digest |
| ScheduleCommand | 固定 operation、确认/开关、expires_at、UTC window、预算、depends_on；付费/数据/训练不能设置 repeat |

表仅作导航，所有可用字段/枚举/上限以 [完整参数](reference/api-schemas.md) 为准。审批、校准、训练权利和发布门禁是额外业务校验，不因 JSON 类型正确就自动放行。

## WebSocket

- 真实任务：`/api/v1/agent/runs/{run_id}/events?after=游标`，使用同一身份 Cookie 和允许的 Origin。通知/临时进度与已持久检查点分开；重连获取当前快照和游标，不重发创建/审批命令。
- Demo 会话：`/api/v1/sessions/{session_id}/events`，用于内存会话状态；后端重启会清空，不能当成真实轨迹持久回放。

断开页面不停止任务。停止需独立命令并等待确认；临时 token 不等于已确认模型结果。协议 schema 见 [生成契约](../contracts/)，实现及状态语义见 [M11](milestones/evidence/M11.md)。

## Python CLI

所有命令从项目根目录运行。CLI 使用本地 HTTP 应用与 `.auton_local/cli` 私有身份文件；不绕过浏览器相同的业务规则。`--base` 必须放在子命令前，默认 `http://127.0.0.1:8000`。

```bash
.venv/bin/python scripts/agent_cli.py --help
.venv/bin/python scripts/agent_cli.py init example --notes /path/to/public-notes.md
.venv/bin/python scripts/agent_cli.py create --file /path/to/run.json
.venv/bin/python scripts/agent_cli.py list example
.venv/bin/python scripts/agent_cli.py get RUN_ID
.venv/bin/python scripts/agent_cli.py command RUN_ID pause --revision 1
.venv/bin/python scripts/agent_cli.py trajectory RUN_ID --project example
```

| 子命令 | 参数 |
| --- | --- |
| init PROJECT | --title，默认 CLI project；--editable 显式允许申请写入；--notes 选定并晋升公开 UTF-8 资料 |
| create | --file 必填，文件为 CreateRun JSON，使用固定 request_id |
| list / get | 项目 ID / 运行 ID |
| command RUN ACTION | action 为 pause/cancel/resume/approve/reconcile/revise；--revision 必填；--request-id 可固定重试命令；revise 另需 --goal |
| trajectory RUN | --project 必填 |
| recover RUN | --project、--version、--revision、--checkpoint-event 必填；--request-id 可选 |

`init --notes` 是显式导入/晋升，不覆盖不同的旧资料；`--editable` 不扩大已有工作区权限。与原浏览器不共享身份时，应在 CLI 自己初始化项目。

公开资料调研的 run.json：

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

这会使用真实模型额度。首次执行前按快速启动准备资源，并确认选定资料确实允许外发。
