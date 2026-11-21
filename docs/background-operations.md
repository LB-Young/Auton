# 通用后台调度、监控与恢复

M21 将已获准、冻结输入的操作接入后台队列。默认关闭，最终部署环境决定资源配置；不根据开发电脑的 CPU/GPU、内存或平台选择模型，也不在本机训练。主要模块是 SchedulerFactory、JobQueueFactory、TelemetryFactory、RetentionPolicyFactory，依赖公共 Port，由应用根组装和管理生命周期。

## 开关与权限

`config/operations.example.toml` 是部署配置示例。仅 `operations.enabled=true` 还不够：每个身份、项目、操作都需要有效的 ScheduleCommand、`enabled=true`、`confirm_background_actions=true`、到期时间和资源窗口。创建计划不隐式授权数据使用，M17 的精确 run/grant/目的许可、M18/M19 的冻结训练计划、独立评测边界仍然逐次校验。修改配置策略后，旧计划的 config digest 不匹配会停止新分派，需重新审查计划。

`observer_only=true` 使用独立审计/状态命名空间 `operations_observe`，只接受 telemetry 和监控记录 retention；不能调用模型、构建训练数据、撤回源数据权利或启动训练。原有业务状态及真实历史仍通过公共只读 Port 观察。该模式用于低成本运行检查，不是模型质量评测。

执行模块和训练模块不能反向依赖 operations；operations 不能导入发布、审批、工具执行器或进化实现。它没有自动批准、发布、Jev/学生路由切换、任意脚本执行或创建授权的能力。告警仅保留在当前身份的本地控制面，不发邮件、Slack 或其他外部消息。

## 可调度操作

| 操作 | 输入/效果 | 回路与限制 |
| --- | --- | --- |
| telemetry | 汇总运行、真实用量/未知副作用、复核积压、数据授权变化、训练及队列状态 | 快回路；可重复，描述性指标 |
| retention | 物理删除当前身份/项目超过保留期的监控采样行 | 快回路；可重复，不删原始 trajectory/模型/授权/审计 |
| review | 一个精确的 M16 ReviewCommand | 中回路；一次性、按两阶段最大声明成本预留预算 |
| dataset | 一个 M17 DatasetBuild | 中回路；一次性，沿用既有逐项授权及当前资格 |
| export | 精确 snapshot ID + ExportCommand | 中回路；一次性，仍核对 digest、train/validation 用途 |
| withdraw | 一个精确 DatasetWithdrawal | 高优先级、一次性；撤回指定 run 或 grant 的后续使用权 |
| executor_training / decision_training | 已审核的 TrainingJobCommand，包含精确 plan digest | 慢回路；一次性、非 engineering probe、足够新监督数据 |

依赖必须指向当前身份、同项目中已经存在的作业 ID。未来 ID、跨项目/身份依赖均拒绝，因此不能通过更新计划制造循环。只有依赖成功，后续作业才分派。没有自动扩展未来 run 授权或从 protected test/meta 生成训练输入。当前不是自动发现无限新任务的爬虫：新历史先由现有模块取得精确授权/独立证据、形成冻结输入，再登记相应后台操作。避免把“常驻”误解为无限消费未授权历史。

周期计划只允许 telemetry / retention。review、数据、训练等固定源操作只能执行一次；换 request_id 不能把同一份数据伪装成新的自动训练轮次。用户仍可通过训练页面执行独立、明确审查过的手动实验。

## API 与页面

前端 `?view=operations` 提供宿主状态、当前身份暂停/恢复、计划 JSON、UTC 资源窗口、队列/错误/成本、趋势和状态告警、备份/空目标恢复。默认示例 `enabled=false`、确认 false；宿主未启用、无项目、空队列、加载、请求失败均有明确状态。移动端主导航可滚动访问所有模块。

API 均使用既有身份 Cookie、同源检查和 CSRF 约束；不能通过 owner 字符串冒用其他身份。

| API | 用途 |
| --- | --- |
| GET /api/v1/operations/status | 宿主开关、观察模式、身份暂停、策略 digest、健康错误 |
| GET/POST /api/v1/operations/schedules | 查询/登记精确计划 |
| POST /api/v1/operations/schedules/{id}/commands | 版本受控的计划暂停/恢复 |
| GET /api/v1/operations/jobs | 查看当前项目的实际作业 |
| POST /api/v1/operations/jobs/{id}/commands | 暂停、恢复监控或取消具体作业 |
| POST /api/v1/operations/control | 当前身份暂停/恢复；不影响其他身份 |
| POST /api/v1/operations/tick | 执行一次受相同宿主开关约束的调度/对账，不是绕过禁用的后门 |
| GET /api/v1/operations/samples / alerts | 项目趋势与告警 |
| POST /api/v1/operations/backups | 当前身份的调度状态私有备份，仅返回 manifest |
| POST /api/v1/operations/restores | 校验精确 SHA、空目标与确认后恢复，并保持暂停 |

最小一次性监控计划示例（将 expires_at 换成真实未来 UTC Unix 秒）：

```json
{
  "request_id": "observe-project-v1",
  "project_id": "my-project",
  "operation": {"kind": "telemetry"},
  "enabled": true,
  "confirm_background_actions": true,
  "expires_at": 1800000000,
  "repeat": false,
  "interval_seconds": 3600,
  "window": {"start_hour_utc": 0, "end_hour_utc": 24},
  "budget_microusd": 0,
  "depends_on": []
}
```

若使用 review，需要明确填写 ReviewCommand，并至少预留宿主 `2 * decision_review.max_stage_cost_microusd` 的预算。默认每个身份的后台模型调用生命周期预算上限为 1,000,000 μUSD；它按已知声明模型成本和未决预留额度计账，不等于云厂商的最终账单，也不含 GPU 租金、电费或主任务成本。未知用量保持完整预留并进入 attention，不当成免费，不自动重试未知模型调用。各源模块仍执行各自成本、时长、输出及资源硬限制。

## 租约、重试与恢复语义

一个状态目录只有一个协调进程，以 flock 排他持有 SQLite WAL/FULL 状态。作业写入使用 CAS；领取作业产生新的随机 lease token、版本和截止时间。过期或被替换的 worker 无法确认、覆盖状态。队列有上限，容量不足停止接收/分派并显示错误；不能用无界内存队列吞掉积压。

同一计划/周期生成同一个作业 ID。每次真正调用公共模块，都使用从作业 ID 派生的同一个请求 ID。首次调用前持久化 intent、预算和新数据占用；回执丢失后按同 ID 读取/重试，让 M16/M17/M18/M19 恢复原操作。模型未知调用由源模块阻止自动重放，训练也不以新请求 ID 重开昂贵 worker。这里不声称分布式任意副作用的绝对 exactly-once。

临时服务错误按有界指数退避，默认最多 3 次失败；权利/数据/范围不合格直接 attention。未知编程/协议错误进入 attention，不能无穷重试。停机保留未决 lease；重启只在到期后重新领取，保持原上游 ID。M18 仍检查旧 worker 确认停止和有效 checkpoint，不会因协调器重启就自动开始另一份训练。

前台优先使用 Agent 的全局活动聚合计数，覆盖不同项目与身份的活跃/排队运行，不读取或公开其他身份内容。后台 review/数据/训练在前台繁忙时不新分派；监控/指定撤权优先处理。已有后台训练在前台到来、窗口关闭或授权失效后经 M18 cancel 接口确认停止并保存可用 checkpoint。只有计划最初明确设置 `allow_checkpoint_resume=true`、当前计划/数据仍合格、窗口开放、前台空闲且源模块确认可恢复，才自动 resume 原作业；否则保持暂停，用户去训练页面审查恢复。

具体作业的“暂停”会停止其受管训练 worker；对 review，已进入的源模块操作可以完成，暂停阻止后续调度，不伪称能撤销发出的网络请求。宿主 disabled 防止新分派；若不运行循环，仍需人工执行一次对账/取消来停止此前的未决工作。停止/未知效果无法确认时，保留 attention，不假装资源已经释放。

这是应用层准入与有界停止策略。CPU/RAM/GPU 硬隔离和前台资源预留由最终部署环境设置 Docker/cgroups 等限制；当前开发机上未声称测量过目标环境的抢占延迟、吞吐或 GPU 互不干扰。

## 持续训练门槛

每个自动训练作业必须有当前 ready 的非 probe 训练计划，以及当前有效、明确授权的 train artifact。对监督样本的 kind、规范化输入和规范化目标计算稳定键，至少需要 20 个未被此前后台训练占用的新监督样本。计划改名、artifact 改名或重复导出同样文本不能取得新的额度。首次分派前占用样本；失败/不确定操作也保留占用，防止绕过故障状态重复昂贵训练。

训练原有 train/validation/replay/anchor 独立性、真实基础模型 manifest、足够独立组、数据权利和 worker 停止确认仍由 M18/M19 再次验证。运行漂移只触发独立复核告警，不授予新的数据权利、训练资格或发布权；当前自动训练采取“足够新数据且计划合格”这一保守门槛，不以未证实的漂移替代数据。

## 监控、告警和保留

成本按实际 run、独立 evaluator request ID、review stage request ID 去重汇总；重复采样不重复计入模型调用。未知成本、未决模型请求及未知工具结果单列，不只看成功率。runtime/test 来源分别统计，不能将 fixture 通过计入生产收益。

运行通过率为当前有效 runtime 报告的描述性统计。至少 20 份报告时冻结初始监控基线，较基线下降超过阈值（默认 0.2）标记 drift advisory；它不是统计显著性结论、因果训练收益或金标质量。长期需要结合 M13/M19/M20 独立证据，而不是凭 dashboard 颜色上线。

同一个告警代码只有 active/resolved 状态变化才记录新版本和审计事件；相同状态的周期采样不反复告警。包括未知用量/效果、复核积压、数据使用权变化、作业 attention、运行表现下降。后台循环异常通过 status.last_error 明示，不向主对话刷日志。

监控采样每项目最多 1000 条（可配置），retention 任务按保留天数物理删除指定身份/项目的旧采样行。它不删除训练输入、原始 trajectory、checkpoint、模型、审批和不可变作业回执；需要撤回数据使用权时，单独登记精确 withdraw 任务，撤权立即沿既有来源检查阻断后续导出/使用。物理删除原始业务数据、备份的组织保留政策不由此样本清理接口暗中扩大。

调度回执与作业历史保留以防重放，默认最多 100,000 个不可变版本；达到上限会停下并显示容量错误，需要审查/归档迁移。高频计划应按目标环境容量设置周期与限额，不声称进程可以在无限数据增长下永久运行。

## 备份恢复演练

备份覆盖当前身份的 operations 历史/heads/幂等回执、监控采样与告警/基线，存放在受忽略、权限受限的本地目录；API 只返回 ID、SHA、字节数、记录数和配置 digest，不把文件或其他身份记录暴露给浏览器。它不是全项目备份，不包含上游 kernel、授权、数据、训练产物、模型或 `.env`。

1. 在目标环境先停止原协调进程，保留原目录；完成 M02/M09/M17/M18 等上游状态的协调备份/恢复。不得同时启动两个不同状态目录来共享同一个 kernel 和身份。
2. 通过 backups API 生成私有 JSON 和 manifest，保存精确 SHA。复制文件时保留私有权限，不放进 GitHub；若临时文件或备份损坏，保留故障现场，使用新的请求 ID 重新备份。
3. 在空目标、兼容配置、相同身份和已经恢复的项目下，放置该身份对应的备份文件，提交 RestoreCommand，确认 `confirm_empty_target=true`。错误 SHA、来源不匹配、配置不相容、未知 schema、结构/版本/digest 不一致和非空目标均拒绝，禁止覆盖现有数据。
4. 原始历史和上游稳定 ID 被保留。恢复的新 heads 会超过 kernel 中已存在的同文档审计版本，避免旧备份的后续写入撞上历史记录。恢复事务同时写入当前身份 paused=true，不会在半恢复状态自动分派。审计扫描最多 1,000,000 条事件，超出需离线审查迁移。
5. 核对外部作业状态和未知效果，再逐项恢复身份/计划。重启不重复创建已完成训练，也不取得发布权。故障注入测试包含损坏备份、旧审计仍存、过期 worker、回执丢失、前台抢占及人工 checkpoint 恢复。

跨环境迁移涉及完整上游存储、原身份密钥与真实训练镜像/模型的备份恢复，需要最终部署演练；当前工程测试不能替代这项验收。

## 已有真实历史的只读检查

`make operations-smoke` 使用既有 `.auton_local/evolution-smoke` 原身份/业务记录，在专用 observer-only 状态目录创建一次性监控和调度状态备份。脚本在启动前拒绝该观察命名空间里的非监控计划，不重做付费 Agent 任务、不下载模型、不训练、不发布。缺少先前的真实记录时会明确失败，不偷偷生成替代“真实历史”。

真实训练效果、金标质量、live shadow、目标 GPU 隔离、跨机恢复和周/月尺度收益仍待最终部署环境。M21 当前交付的是通用、可验证、失败时保持关闭的工程流程。
