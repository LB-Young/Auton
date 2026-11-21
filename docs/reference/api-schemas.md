# HTTP 请求与响应参数完整参考

由已提交的 OpenAPI 契约生成。入口和错误处理见 [API 使用指南](../api.md)，接口目录见 [HTTP 路由](api-endpoints.md)。`-Input` 为输入格式，`-Output` 为返回格式；不要将响应中的 owner/role/内部状态自行拼进请求。

表中必填以具体 HTTP schema 为准，含显式 null 的响应字段可能仍为必填。未显示默认值的字段不代表存在隐式授权。字段间业务约束还受服务端校验和当前状态门禁限制。

<a id="acceptance-input"></a>
### Acceptance-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `kind` | `"file"`, `"research"`, `"response"` | 是 | — |  |
| `min_sources` | integer | 否 | `1` | ≥ 1.0; ≤ 6.0 |
| `path` | string / null | 否 | — |  |
| `sha256` | string / null | 否 | — |  |

<a id="acceptance-output"></a>
### Acceptance-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `kind` | `"file"`, `"research"`, `"response"` | 是 | — |  |
| `min_sources` | integer | 是 | `1` | ≥ 1.0; ≤ 6.0 |
| `path` | string / null | 是 | — |  |
| `sha256` | string / null | 是 | — |  |

<a id="acceptancecheck"></a>
### AcceptanceCheck

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `checker` | `"file-sha256-v1"`, `"retrieval-citations-v1"`, `"response-present-v1"` | 是 | — |  |
| `evidence` | array&lt;string&gt; | 是 | — |  |
| `outcome` | `"passed"`, `"failed"`, `"unknown"` | 是 | — |  |
| `semantic_quality_verified` | `false` | 是 | `false` |  |

<a id="actionrequest"></a>
### ActionRequest

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `action` | string | 是 | — | 最短 1; 最长 100 |
| `autonomy` | integer | 否 | `0` | ≥ 0.0; ≤ 3.0 |
| `data_domain` | `"public"`, `"local-only"`, `"secret"` | 否 | `"local-only"` |  |
| `destination` | `"local"`, `"remote"` | 否 | `"local"` |  |
| `goal_id` | string | 是 | — | 最短 1; 最长 200 |
| `goal_revision` | integer | 是 | — | ≥ 1.0 |
| `input_digest` | string | 否 | `"0000000000000000000000000000000000000000000000000000000000000000"` | 格式 ^[a-f0-9]{64}$ |
| `operation_id` | string | 否 | `"preview"` | 最短 1; 最长 200 |
| `principal` | [Principal](#principal) | 是 | — |  |
| `provider` | string / null | 否 | — |  |

<a id="agentdecisionpair"></a>
### AgentDecisionPair

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `candidate_report_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `reference_report_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |

<a id="agentrun"></a>
### AgentRun

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `approvals` | map&lt;string&gt; | 是 | — |  |
| `budget_limits` | map&lt;integer&gt; | 是 | — |  |
| `check` | [AcceptanceCheck](#acceptancecheck) / null | 是 | — |  |
| `command` | [CreateRun-Output](#createrun-output) | 是 | — |  |
| `context_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `cost_microusd` | integer | 是 | `0` |  |
| `decision_candidate_catalog` | array&lt;map&lt;[JsonValue](#jsonvalue)&gt;&gt; | 是 | `[]` |  |
| `decision_catalog_cutoff` | integer / null | 是 | — |  |
| `decision_catalog_goal_revision` | integer / null | 是 | — |  |
| `executor_selection` | `"user-explicit"` | 是 | `"user-explicit"` |  |
| `executor_spec` | map&lt;[JsonValue](#jsonvalue)&gt; | 是 | — |  |
| `final_text` | string | 是 | `""` |  |
| `goal_revision` | integer | 是 | `1` |  |
| `history` | array&lt;[ModelMessage-Output](#modelmessage-output)&gt; | 是 | `[]` |  |
| `id` | string | 是 | — |  |
| `input_asset_release_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `input_asset_snapshot_id` | string / null | 是 | — |  |
| `input_cutoff_unit` | `"run-checkpoint-version"` | 是 | `"run-checkpoint-version"` |  |
| `judgment_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `judgments` | array&lt;[JudgmentResult](#judgmentresult)&gt; | 是 | `[]` |  |
| `model_assignment_purpose` | `"operational"`, `"evaluation"` | 是 | `"operational"` |  |
| `model_release_id` | string / null | 是 | — |  |
| `model_request_id` | string / null | 是 | — |  |
| `model_results` | array&lt;[ModelResult](#modelresult)&gt; | 是 | `[]` |  |
| `pending_calls` | array&lt;[ToolCall](#toolcall)&gt; | 是 | `[]` |  |
| `pending_goal` | string / null | 是 | — |  |
| `phase` | `"idle"`, `"judgment"`, `"context"`, `"model"`, `"tool"`, `"acceptance"` | 是 | `"idle"` |  |
| `plans` | array&lt;[ToolPlan](#toolplan)&gt; | 是 | `[]` |  |
| `reason` | string | 是 | `"queued"` |  |
| `receipts` | array&lt;[ToolReceipt](#toolreceipt)&gt; | 是 | `[]` |  |
| `resolved_model_id` | string / null | 是 | — |  |
| `runtime_revision` | `"single-agent-v1"`, `"single-agent-v2"`, `"single-agent-v3"` | 是 | `"single-agent-v3"` |  |
| `session_id` | string | 是 | `""` |  |
| `source` | `"runtime"`, `"test"` | 是 | — |  |
| `status` | `"queued"`, `"running"`, `"waiting_approval"`, `"blocked"`, `"pausing"`, `"paused"`, `"cancelling"`, `"cancelled"`, `"succeeded"`, `"failed"` | 是 | `"queued"` |  |
| `steps` | integer | 是 | `0` |  |
| `stop_requested` | boolean | 是 | `false` |  |
| `tokens_used` | integer | 是 | `0` |  |
| `undispatched_model_request_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `version` | integer | 是 | `0` |  |

<a id="aggregate"></a>
### Aggregate

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `cost_microusd` | integer | 是 | — |  |
| `critical_failures` | integer | 是 | — |  |
| `environment_errors` | integer | 是 | — |  |
| `evaluation_cost_microusd` | integer | 是 | — |  |
| `evaluation_unknown_calls` | integer | 是 | — |  |
| `failed` | integer | 是 | — |  |
| `groups` | map&lt;map&lt;integer&gt;&gt; | 是 | — |  |
| `incomplete` | integer | 是 | — |  |
| `known_denominator` | integer | 是 | — |  |
| `pass_rate` | number / null | 是 | — |  |
| `passed` | integer | 是 | — |  |
| `release_eligible` | integer | 是 | — |  |
| `scope` | `"descriptive-only"` | 是 | `"descriptive-only"` |  |
| `source_counts` | map&lt;integer&gt; | 是 | — |  |
| `split_counts` | map&lt;integer&gt; | 是 | — |  |
| `tokens` | integer | 是 | — |  |
| `total` | integer | 是 | — |  |
| `unknown` | integer | 是 | — |  |
| `wilson_lower` | number / null | 是 | — |  |
| `wilson_upper` | number / null | 是 | — |  |

<a id="answer"></a>
### Answer

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `confidence` | number / null | 是 | — |  |
| `expected_score` | number / null | 是 | — |  |
| `probabilities` | map&lt;number&gt; | 是 | — |  |
| `question_id` | string | 是 | — |  |
| `reason` | string / null | 是 | — |  |
| `selected_id` | string / null | 是 | — |  |
| `status` | `"answered"`, `"abstained"`, `"failed"` | 是 | — |  |
| `type` | `"choice"`, `"boolean"`, `"score"` | 是 | — |  |

<a id="arenacommand-input"></a>
### ArenaCommand-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `bank_revision` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `checkpoints` | array&lt;[ToolCheckpoint-Input](#toolcheckpoint-input)&gt; | 是 | — | 最少项 1; 最多项 4 |
| `development_cases` | array&lt;string&gt; | 是 | — | 最少项 1; 最多项 9 |
| `expected_proposal_version` | integer | 是 | — | ≥ 0.0 |
| `limits` | [RunLimits-Input](#runlimits-input) | 是 | — |  |
| `model_id` | string | 是 | — | 最短 1; 最长 100 |
| `proposal_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `public` | boolean | 否 | `false` |  |
| `repeats` | integer | 否 | `3` | ≥ 1.0; ≤ 5.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `train_cases` | array&lt;string&gt; | 是 | — | 最少项 1; 最多项 3 |

<a id="arenacommand-output"></a>
### ArenaCommand-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `bank_revision` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `checkpoints` | array&lt;[ToolCheckpoint-Output](#toolcheckpoint-output)&gt; | 是 | — | 最少项 1; 最多项 4 |
| `development_cases` | array&lt;string&gt; | 是 | — | 最少项 1; 最多项 9 |
| `expected_proposal_version` | integer | 是 | — | ≥ 0.0 |
| `limits` | [RunLimits-Output](#runlimits-output) | 是 | — |  |
| `model_id` | string | 是 | — | 最短 1; 最长 100 |
| `proposal_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `public` | boolean | 是 | `false` |  |
| `repeats` | integer | 是 | `3` | ≥ 1.0; ≤ 5.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `train_cases` | array&lt;string&gt; | 是 | — | 最少项 1; 最多项 3 |

<a id="arenacontrol"></a>
### ArenaControl

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `action` | `"start"`, `"resume"`, `"approve_current"`, `"cancel"` | 是 | — |  |
| `expected_version` | integer | 是 | — | ≥ 0.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="arenatrial"></a>
### ArenaTrial

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `case_id` | string | 是 | — |  |
| `case_source` | `"human_seed"`, `"benchmark"`, `"episode"`, `"test_fixture"` | 是 | `"test_fixture"` |  |
| `checkpoints_followed` | boolean | 是 | `false` |  |
| `comparison_signature` | string / null | 是 | — |  |
| `confirmed_calls` | integer | 是 | `0` |  |
| `cost_microusd` | integer | 是 | `0` |  |
| `critical` | boolean | 是 | `false` |  |
| `environment_verified` | boolean | 是 | `false` |  |
| `executor_signature` | string / null | 是 | — |  |
| `family` | string | 是 | — |  |
| `id` | string | 是 | — |  |
| `independence_group` | string / null | 是 | — |  |
| `outcome` | `"pass"`, `"fail"`, `"unknown"`, `"environment_error"`, `"incomplete"` | 是 | `"incomplete"` |  |
| `pending_preview` | string / null | 是 | — |  |
| `reasons` | array&lt;string&gt; | 是 | `[]` |  |
| `repeat` | integer | 是 | — | ≥ 0.0; ≤ 4.0 |
| `report_id` | string / null | 是 | — |  |
| `run_id` | string / null | 是 | — |  |
| `run_version` | integer / null | 是 | — |  |
| `snapshot_id` | string | 是 | — |  |
| `source` | `"runtime"`, `"test"` | 是 | `"test"` |  |
| `split` | `"train"`, `"development"` | 是 | — |  |
| `status` | string | 是 | `"pending"` |  |
| `target_retained` | boolean | 是 | `false` |  |
| `tokens` | integer | 是 | `0` |  |
| `tool_calls` | integer | 是 | `0` |  |
| `unknown_calls` | integer | 是 | `0` |  |
| `variant` | `"baseline"`, `"candidate"`, `"ablation"` | 是 | — |  |
| `workspace_id` | string | 是 | — |  |

<a id="arenaview"></a>
### ArenaView

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `approval_command_id` | string / null | 是 | — |  |
| `assessment_config_digest` | string | 是 | `""` |  |
| `command` | [ArenaCommand-Output](#arenacommand-output) | 是 | — |  |
| `config_digest` | string | 是 | — |  |
| `created_at` | number | 是 | — |  |
| `current_trial` | string / null | 是 | — |  |
| `frozen_tasks` | array&lt;[OptimizationTask](#optimizationtask)&gt; | 是 | `[]` |  |
| `gates` | array&lt;[GateSignal](#gatesignal)&gt; | 是 | `[]` |  |
| `id` | string | 是 | — |  |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `ready_for_release` | boolean | 是 | `false` |  |
| `reason` | string | 是 | — |  |
| `resume_command_id` | string / null | 是 | — |  |
| `source` | `"runtime"`, `"test"` | 是 | — |  |
| `status` | `"draft"`, `"running"`, `"waiting_approval"`, `"complete"`, `"blocked"`, `"cancelling"`, `"cancelled"` | 是 | `"draft"` |  |
| `total_cost_microusd` | integer | 是 | `0` |  |
| `total_model_calls` | integer | 是 | `0` |  |
| `total_tokens` | integer | 是 | `0` |  |
| `total_tool_calls` | integer | 是 | `0` |  |
| `trials` | array&lt;[ArenaTrial](#arenatrial)&gt; | 是 | — |  |
| `unknown_model_calls` | integer | 是 | `0` |  |
| `version` | integer | 是 | `0` |  |

<a id="artifact"></a>
### Artifact

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `content` | string | 是 | — |  |
| `filename` | string | 是 | — |  |
| `id` | string | 是 | — |  |
| `source` | `"demo"` | 是 | `"demo"` |  |
| `title` | string | 是 | — |  |

<a id="assessmentstatus"></a>
### AssessmentStatus

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `active_jobs` | integer | 是 | — |  |
| `config_digest` | string | 是 | — |  |
| `judge_model` | string | 是 | — |  |
| `max_calibration_calls` | integer | 是 | — |  |
| `min_calibration_lower` | number | 是 | — |  |
| `min_calibration_samples` | integer | 是 | — |  |
| `private_judge_journal` | boolean | 是 | `true` |  |
| `rubric_revision` | string | 是 | — |  |

<a id="asset-input"></a>
### Asset-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `content` | string | 是 | — | 最短 1; 最长 32000 |
| `expires_at` | string / null | 否 | — |  |
| `id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `kind` | `"skill"`, `"prompt"`, `"role"`, `"knowledge"`, `"document"`, `"memory"` | 是 | — |  |
| `name` | string | 是 | — | 最短 1; 最长 100 |
| `origin` | `"user_explicit"`, `"inferred"`, `"external"` | 是 | — |  |
| `parents` | array&lt;string&gt; | 否 | `[]` | 最多项 20 |
| `source` | string | 是 | — | 最短 1; 最长 1000 |
| `untrusted` | `true` | 否 | `true` |  |

<a id="asset-output"></a>
### Asset-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `content` | string | 是 | — | 最短 1; 最长 32000 |
| `expires_at` | string / null | 是 | — |  |
| `id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `kind` | `"skill"`, `"prompt"`, `"role"`, `"knowledge"`, `"document"`, `"memory"` | 是 | — |  |
| `name` | string | 是 | — | 最短 1; 最长 100 |
| `origin` | `"user_explicit"`, `"inferred"`, `"external"` | 是 | — |  |
| `parents` | array&lt;string&gt; | 是 | `[]` | 最多项 20 |
| `source` | string | 是 | — | 最短 1; 最长 1000 |
| `untrusted` | `true` | 是 | `true` |  |

<a id="assetproposalcommand"></a>
### AssetProposalCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `asset` | [Asset-Input](#asset-input) | 是 | — |  |
| `expected` | string / null | 否 | — |  |

<a id="assetpublishcommand"></a>
### AssetPublishCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `candidates_revision` | string | 是 | — | 格式 ^[a-f0-9]{40}$ |
| `expected` | string | 是 | — | 格式 ^[a-f0-9]{40}$ |

<a id="assetrecord"></a>
### AssetRecord

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `asset` | [Asset-Output](#asset-output) | 是 | — |  |
| `promoted_from` | string / null | 是 | — |  |
| `status` | `"active"`, `"candidate"`, `"revoked"` | 是 | — |  |

<a id="assetrevisioncommand"></a>
### AssetRevisionCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `expected` | string | 是 | — | 格式 ^[a-f0-9]{40}$ |
| `revision` | string / null | 否 | — |  |

<a id="assetuse-input"></a>
### AssetUse-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `content_sha256` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `license_reference` | string | 是 | — | 最短 10; 最长 1000 |
| `training_use_confirmed_by_user` | boolean | 否 | `false` |  |

<a id="assetuse-output"></a>
### AssetUse-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `content_sha256` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `license_reference` | string | 是 | — | 最短 10; 最长 1000 |
| `training_use_confirmed_by_user` | boolean | 是 | `false` |  |

<a id="backgroundjob"></a>
### BackgroundJob

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `actual_cost_microusd` | integer / null | 是 | `0` |  |
| `attempts` | integer | 是 | `0` |  |
| `created_at` | number | 是 | — |  |
| `cycle` | integer | 是 | — |  |
| `dispatched` | boolean | 是 | `false` |  |
| `external_id` | string / null | 是 | — |  |
| `failures` | integer | 是 | `0` |  |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `lease_token` | string / null | 是 | — |  |
| `lease_until` | number | 是 | `0` |  |
| `next_due` | number | 是 | — |  |
| `operation` | [ReviewOperation-Output](#reviewoperation-output) / [DatasetOperation-Output](#datasetoperation-output) / [ExportOperation-Output](#exportoperation-output) / [WithdrawOperation-Output](#withdrawoperation-output) / [TrainingOperation-Output](#trainingoperation-output) / [MaintenanceOperation](#maintenanceoperation) | 是 | — |  |
| `project_id` | string | 是 | — |  |
| `reason` | string | 是 | `"queued"` |  |
| `reserved_cost_microusd` | integer | 是 | `0` |  |
| `result_digest` | string / null | 是 | — |  |
| `sample_keys` | array&lt;string&gt; | 是 | `[]` |  |
| `schedule_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `status` | `"queued"`, `"leased"`, `"waiting"`, `"paused"`, `"succeeded"`, `"failed"`, `"cancelled"`, `"attention"` | 是 | `"queued"` |  |
| `version` | integer | 是 | `0` |  |

<a id="backupcommand"></a>
### BackupCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="backupmanifest"></a>
### BackupManifest

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `bytes` | integer | 是 | — |  |
| `config_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `created_at` | number | 是 | — |  |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `records` | integer | 是 | — |  |
| `scope` | `"owned_operations_state_only"` | 是 | `"owned_operations_state_only"` |  |
| `sha256` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |

<a id="batchevaluation"></a>
### BatchEvaluation

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `bank_revision` | string | 是 | — |  |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `repeats` | integer | 否 | `1` | ≥ 1.0; ≤ 3.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |
| `runs` | array&lt;[CaseRunBinding](#caserunbinding)&gt; | 是 | — | 最少项 1; 最多项 100 |
| `semantic` | boolean | 否 | `false` |  |
| `window_id` | string | 是 | — |  |

<a id="batchresult"></a>
### BatchResult

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `aggregate` | [Aggregate](#aggregate) | 是 | — |  |
| `bank_revision` | string | 是 | — |  |
| `blocked_cases` | array&lt;string&gt; | 是 | — |  |
| `complete` | boolean | 是 | — |  |
| `expected_cases` | integer | 是 | — |  |
| `id` | string | 是 | — |  |
| `reports` | array&lt;[EvalReport](#evalreport)&gt; | 是 | — |  |
| `window_id` | string | 是 | — |  |

<a id="blindwindow"></a>
### BlindWindow

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `bank_revision` | string | 是 | — |  |
| `candidate_revision` | string | 是 | — |  |
| `id` | string | 是 | — |  |
| `max_uses` | integer | 是 | — |  |
| `purpose` | string | 是 | — |  |
| `split` | `"test"`, `"meta"` | 是 | — |  |
| `split_digest` | string | 是 | — |  |

<a id="blindwindowcommand"></a>
### BlindWindowCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `bank_revision` | string | 是 | — |  |
| `candidate_revision` | string | 是 | — | 最短 1; 最长 100 |
| `purpose` | `"release"`, `"calibration"` | 是 | — |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |
| `split` | `"test"`, `"meta"` | 是 | — |  |

<a id="bootstrapresponse"></a>
### BootstrapResponse

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `demo` | boolean | 是 | — |  |
| `event_storage` | [StorageInfo](#storageinfo) | 是 | — |  |
| `identity` | [IdentityInfo](#identityinfo) | 是 | — |  |
| `implementation` | string | 是 | — |  |
| `modules` | array&lt;[ModuleDescriptor](#moduledescriptor)&gt; | 是 | — |  |
| `persistence` | `"memory-only"` | 否 | `"memory-only"` |  |
| `policy` | [PublicPolicy](#publicpolicy) | 是 | — |  |
| `profile` | string | 是 | — |  |

<a id="calibrationcommand"></a>
### CalibrationCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `bank_revision` | string | 是 | — |  |
| `confirm_public` | boolean | 否 | `false` |  |
| `repeats` | integer | 否 | `2` | ≥ 2.0; ≤ 3.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |
| `window_id` | string | 是 | — |  |

<a id="calibrationreport"></a>
### CalibrationReport

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `agreement` | number / null | 是 | — |  |
| `bank_revision` | string | 是 | — |  |
| `configuration_digest` | string | 是 | — |  |
| `confirmed_judge_cost_microusd` | integer | 是 | — |  |
| `confirmed_judge_tokens` | integer | 是 | — |  |
| `coverage` | number | 是 | — |  |
| `critical_errors` | integer | 是 | — |  |
| `critical_missing` | integer | 是 | — |  |
| `critical_samples` | integer | 是 | — |  |
| `families` | integer | 是 | — |  |
| `groups` | map&lt;[GroupCalibration](#groupcalibration)&gt; | 是 | — |  |
| `id` | string | 是 | — |  |
| `judge_calls` | integer | 是 | — |  |
| `judge_identity` | string / null | 是 | — |  |
| `kappa` | number / null | 是 | — |  |
| `known` | integer | 是 | — |  |
| `meta_digest` | string | 是 | — |  |
| `negative_gold` | integer | 是 | — |  |
| `passed` | boolean | 是 | — |  |
| `positive_gold` | integer | 是 | — |  |
| `reasons` | array&lt;string&gt; | 是 | — |  |
| `repeat_disagreements` | integer | 是 | — |  |
| `rubric_revision` | string | 是 | — |  |
| `samples` | integer | 是 | — |  |
| `source_qualified` | boolean | 是 | — |  |
| `supported_groups` | array&lt;string&gt; | 是 | — |  |
| `unknown_judge_calls` | integer | 是 | — |  |
| `wilson_lower` | number / null | 是 | — |  |

<a id="calibrationview"></a>
### CalibrationView

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `config_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `coverage` | number | 是 | `0` |  |
| `eligible` | boolean | 是 | `false` |  |
| `independent_families` | integer | 是 | `0` |  |
| `kappa` | number / null | 是 | — |  |
| `keep_contamination_upper` | number / null | 是 | — |  |
| `keep_errors` | integer | 是 | `0` |  |
| `per_verdict` | map&lt;integer&gt; | 是 | — |  |
| `predicted_keep` | integer | 是 | `0` |  |
| `protected_review_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `reasons` | array&lt;string&gt; | 是 | — |  |
| `reviewer_signature` | string / null | 是 | — |  |

<a id="casebank"></a>
### CaseBank

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `cases` | array&lt;[CaseInfo](#caseinfo)&gt; | 是 | — |  |
| `counts` | map&lt;integer&gt; | 是 | — |  |
| `revision` | string | 是 | — |  |

<a id="caseinfo"></a>
### CaseInfo

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `critical` | boolean | 是 | — |  |
| `digest` | string | 是 | — |  |
| `family` | string | 是 | — |  |
| `id` | string | 是 | — |  |
| `kind` | string | 是 | — |  |
| `origin_group` | string | 是 | `""` |  |
| `split` | `"train"`, `"development"`, `"test"`, `"meta"` | 是 | — |  |

<a id="caserunbinding"></a>
### CaseRunBinding

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `case_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `expected_version` | integer | 是 | — | ≥ 0.0; ≤ 65535.0 |
| `run_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |

<a id="checkpointreference"></a>
### CheckpointReference

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `cursor` | integer | 是 | — |  |
| `digest` | string | 是 | — |  |
| `event_id` | string | 是 | — |  |
| `goal_id` | string | 是 | `""` |  |
| `project_id` | string | 是 | `""` |  |
| `run_id` | string | 是 | — |  |
| `runtime_revision` | string | 是 | — |  |
| `session_id` | string | 是 | `""` |  |
| `version` | integer | 是 | — |  |

<a id="childspec-input"></a>
### ChildSpec-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `acceptance` | [Acceptance-Input](#acceptance-input) | 是 | — |  |
| `allowed_tools` | array&lt;`"file.read"`, `"file.write"`, `"mcp.sha256"`&gt; | 是 | — |  |
| `depends_on` | array&lt;string&gt; | 否 | `[]` | 最多项 8 |
| `goal` | string | 是 | — | 最短 1; 最长 3000 |
| `id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,64}$ |
| `limits` | [RunLimits-Input](#runlimits-input) | 是 | — |  |
| `model_id` | string | 是 | — | 最短 1; 最长 100 |
| `role` | `"worker"`, `"researcher"` | 否 | `"worker"` |  |

<a id="childspec-output"></a>
### ChildSpec-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `acceptance` | [Acceptance-Output](#acceptance-output) | 是 | — |  |
| `allowed_tools` | array&lt;`"file.read"`, `"file.write"`, `"mcp.sha256"`&gt; | 是 | — |  |
| `depends_on` | array&lt;string&gt; | 是 | `[]` | 最多项 8 |
| `goal` | string | 是 | — | 最短 1; 最长 3000 |
| `id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,64}$ |
| `limits` | [RunLimits-Output](#runlimits-output) | 是 | — |  |
| `model_id` | string | 是 | — | 最短 1; 最长 100 |
| `role` | `"worker"`, `"researcher"` | 是 | `"worker"` |  |

<a id="childstate"></a>
### ChildState

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `approval_command_id` | string / null | 是 | — |  |
| `command` | [CreateRun-Output](#createrun-output) / null | 是 | — |  |
| `cost_microusd` | integer | 是 | `0` |  |
| `id` | string | 是 | — |  |
| `pending_operation_id` | string / null | 是 | — |  |
| `pending_preview` | string / null | 是 | — |  |
| `reason` | string | 是 | `"dependency_not_ready"` |  |
| `report_id` | string / null | 是 | — |  |
| `run_id` | string / null | 是 | — |  |
| `started_at` | number / null | 是 | — |  |
| `status` | `"queued"`, `"running"`, `"waiting_approval"`, `"blocked"`, `"pausing"`, `"paused"`, `"cancelling"`, `"cancelled"`, `"succeeded"`, `"failed"` / `"pending"`, `"verified"`, `"dispatch_intent"` | 是 | `"pending"` |  |
| `tokens` | integer | 是 | `0` |  |
| `tool_calls` | integer | 是 | `0` |  |
| `unknown_calls` | integer | 是 | `0` |  |
| `unknown_tools` | integer | 是 | `0` |  |
| `version` | integer / null | 是 | — |  |

<a id="comparecommand"></a>
### CompareCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `baseline` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `candidate` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |

<a id="comparison"></a>
### Comparison

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `baseline` | string | 是 | — |  |
| `candidate` | string | 是 | — |  |
| `comparable` | boolean | 是 | — |  |
| `cost_delta_microusd` | integer | 是 | — |  |
| `outcome_changed` | boolean | 是 | — |  |
| `reasons` | array&lt;string&gt; | 是 | — |  |
| `token_delta` | integer | 是 | — |  |

<a id="constitutionconfig"></a>
### ConstitutionConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `allowed_actions` | array&lt;`"demo.start"`, `"demo.stop"`, `"model.generate"`, `"judgment.evaluate"`, `"tool.read"`, `"tool.write"`, `"dataset.read"`, `"model.train"`, `"asset.read"`, `"asset.publish"`, `"asset.propose"`, `"release.activate"`&gt; | 否 | `["demo.start", "demo.stop", "model.generate", "judgment.evaluate", "tool.read", "tool.write", "dataset.read", "model.train", "asset.read", "asset.publish", "asset.propose", "release.activate"]` |  |
| `approval_actions` | array&lt;`"demo.start"`, `"demo.stop"`, `"model.generate"`, `"judgment.evaluate"`, `"tool.read"`, `"tool.write"`, `"dataset.read"`, `"model.train"`, `"asset.read"`, `"asset.publish"`, `"asset.propose"`, `"release.activate"`&gt; | 否 | `["tool.write", "release.activate"]` |  |
| `authorization_ttl_seconds` | integer | 否 | `300` | ≥ 1.0; ≤ 3600.0 |
| `autonomy_max` | integer | 否 | `1` | ≥ 0.0; ≤ 3.0 |
| `budget` | [Usage](#usage) | 否 | — |  |
| `max_concurrent` | integer | 否 | `4` | ≥ 1.0; ≤ 32.0 |
| `remote_providers` | array&lt;`"deepseek"`, `"typesafe"`&gt; | 否 | `[]` |  |

<a id="contextpreviewcommand"></a>
### ContextPreviewCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `history` | array&lt;[ModelMessage-Input](#modelmessage-input)&gt; | 否 | `[]` | 最多项 300 |
| `model_id` | string | 是 | — | 最短 1; 最长 100 |
| `public` | boolean | 否 | `false` |  |
| `request_id` | string | 是 | — | 最短 1; 最长 100 |
| `state` | [TaskState](#taskstate) | 是 | — |  |

<a id="contextsnapshot"></a>
### ContextSnapshot

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `admission_tokens` | integer / null | 是 | — |  |
| `asset_snapshot_id` | string | 是 | — |  |
| `checkpoint_modified` | `false` | 是 | `false` |  |
| `compression_revision` | `"whole-turn-retention-v1"` | 是 | `"whole-turn-retention-v1"` |  |
| `configuration_digest` | string | 是 | — |  |
| `context_limit` | integer | 是 | — |  |
| `counter_source` | `"official-local"`, `"test-fixture"`, `"unavailable"` | 是 | — |  |
| `data_domain` | `"public"`, `"local-only"` | 是 | — |  |
| `declared_model_revision` | string | 是 | — |  |
| `dropped_history_groups` | integer | 是 | — |  |
| `evidence` | array&lt;[Evidence](#evidence)&gt; | 是 | — |  |
| `excluded_evidence` | array&lt;string&gt; | 是 | — |  |
| `goal_id` | string | 是 | — |  |
| `goal_revision` | integer | 是 | — |  |
| `id` | string | 是 | — |  |
| `input_tokens` | integer / null | 是 | — |  |
| `instructions_revision` | `"context-system-v1"` | 是 | `"context-system-v1"` |  |
| `messages` | array&lt;[ModelMessage-Output](#modelmessage-output)&gt; | 是 | — |  |
| `model_id` | string | 是 | — |  |
| `output_reserved` | integer | 是 | — |  |
| `policy_version` | string | 是 | — |  |
| `project_id` | string | 是 | — |  |
| `reasons` | array&lt;string&gt; | 是 | — |  |
| `receipt_digests` | map&lt;string&gt; | 是 | — |  |
| `remaining_tokens` | integer / null | 是 | — |  |
| `request_digest` | string | 是 | — |  |
| `retrieval_revision` | `"lexical-bigram-v1"` | 是 | `"lexical-bigram-v1"` |  |
| `state_cutoff` | integer | 是 | — |  |
| `status` | `"ready"`, `"blocked"` | 是 | — |  |
| `tokenizer_revision` | string | 是 | — |  |
| `tools` | array&lt;[ToolSpec](#toolspec)&gt; | 是 | — |  |

<a id="contrastcommand"></a>
### ContrastCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `baseline_run_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `expected_version` | integer | 是 | — | ≥ 0.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,64}$ |

<a id="contribution"></a>
### Contribution

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `causal_support` | `"controlled"`, `"corrective_chain"`, `"observational"`, `"none"` | 是 | — |  |
| `efficiency` | `"beneficial"`, `"avoidable_detour"`, `"necessary_exploration"`, `"unknown"` | 是 | — |  |
| `evidence_refs` | array&lt;string&gt; | 是 | — | 最少项 0; 最多项 16 |
| `explanation` | string | 是 | — | 最短 1; 最长 1500 |
| `verdict` | `"beneficial"`, `"harmful"`, `"environment_only"`, `"unknown"` | 是 | — |  |

<a id="conversationcreate"></a>
### ConversationCreate

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `project_path` | string / null | 否 | — |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |
| `title` | string | 是 | — | 最短 1; 最长 100 |

<a id="conversationhistorypath"></a>
### ConversationHistoryPath

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `conversation_id` | string | 是 | — |  |
| `exported_at` | string | 是 | — |  |
| `format` | string | 是 | `"json"` |  |
| `path` | string | 是 | — |  |
| `size_bytes` | integer | 是 | — |  |
| `snapshot` | boolean | 是 | `true` |  |

<a id="conversationturn"></a>
### ConversationTurn

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `allow_remote` | boolean | 否 | `false` |  |
| `expected_turns` | integer | 是 | — | ≥ 0.0; < 40.0 |
| `model_id` | string | 是 | — | 最短 1; 最长 100 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |
| `text` | string | 是 | — | 最短 1; 最长 4000 |

<a id="conversationview"></a>
### ConversationView

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `conversation` | [WorkspaceConversation](#workspaceconversation) | 是 | — |  |
| `turns` | array&lt;[AgentRun](#agentrun)&gt; | 是 | `[]` |  |

<a id="createrun-input"></a>
### CreateRun-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `acceptance` | [Acceptance-Input](#acceptance-input) | 是 | — |  |
| `allowed_tools` | array&lt;`"file.read"`, `"file.list"`, `"file.write"`, `"process.run"`, `"mcp.sha256"`&gt; | 否 | `["file.read", "mcp.sha256"]` | 最多项 4 |
| `asset_snapshot_id` | string / null | 否 | — |  |
| `boundaries` | array&lt;string&gt; | 否 | `[]` | 最多项 16 |
| `data_domain` | `"public"`, `"local-only"` | 否 | `"local-only"` |  |
| `goal` | string | 是 | — | 最短 1; 最长 4000 |
| `limits` | [RunLimits-Input](#runlimits-input) / null | 否 | — |  |
| `model_id` | string | 是 | — | 最短 1; 最长 100 |
| `prior_messages` | array&lt;[ModelMessage-Input](#modelmessage-input)&gt; | 否 | `[]` | 最多项 78 |
| `prior_runs` | array&lt;[PriorRun](#priorrun)&gt; | 否 | `[]` | 最多项 39 |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |
| `workspace_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="createrun-output"></a>
### CreateRun-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `acceptance` | [Acceptance-Output](#acceptance-output) | 是 | — |  |
| `allowed_tools` | array&lt;`"file.read"`, `"file.list"`, `"file.write"`, `"process.run"`, `"mcp.sha256"`&gt; | 是 | `["file.read", "mcp.sha256"]` | 最多项 4 |
| `asset_snapshot_id` | string / null | 是 | — |  |
| `boundaries` | array&lt;string&gt; | 是 | `[]` | 最多项 16 |
| `data_domain` | `"public"`, `"local-only"` | 是 | `"local-only"` |  |
| `goal` | string | 是 | — | 最短 1; 最长 4000 |
| `limits` | [RunLimits-Output](#runlimits-output) / null | 是 | — |  |
| `model_id` | string | 是 | — | 最短 1; 最长 100 |
| `prior_messages` | array&lt;[ModelMessage-Output](#modelmessage-output)&gt; | 是 | `[]` | 最多项 78 |
| `prior_runs` | array&lt;[PriorRun](#priorrun)&gt; | 是 | `[]` | 最多项 39 |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |
| `workspace_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="createsession"></a>
### CreateSession

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `request_id` | string | 是 | — | 最短 1; 最长 100 |

<a id="datagrant"></a>
### DataGrant

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `command` | [DataGrantCommand-Output](#datagrantcommand-output) | 是 | — |  |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `license_truth` | `"user_attestation_not_legal_verification"` | 是 | `"user_attestation_not_legal_verification"` |  |
| `revoked` | boolean | 是 | `false` |  |
| `source_scope` | `"owner_project_local_training"` | 是 | `"owner_project_local_training"` |  |
| `version` | integer | 是 | `0` |  |

<a id="datagrantcommand-input"></a>
### DataGrantCommand-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `allow_local_only_data` | boolean | 否 | `false` |  |
| `data_license_reference` | string | 是 | — | 最短 10; 最长 1000 |
| `external_asset_uses` | array&lt;[AssetUse-Input](#assetuse-input)&gt; | 否 | `[]` | 最多项 100 |
| `local_training_authorized` | boolean | 否 | `false` |  |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `purposes` | array&lt;`"executor"`, `"router"`, `"decision"`&gt; | 是 | — | 最少项 1; 最多项 3 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `run_ids` | array&lt;string&gt; | 是 | — | 最少项 1; 最多项 200 |
| `teacher_uses` | array&lt;[TeacherUse-Input](#teacheruse-input)&gt; | 否 | `[]` | 最多项 20 |

<a id="datagrantcommand-output"></a>
### DataGrantCommand-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `allow_local_only_data` | boolean | 是 | `false` |  |
| `data_license_reference` | string | 是 | — | 最短 10; 最长 1000 |
| `external_asset_uses` | array&lt;[AssetUse-Output](#assetuse-output)&gt; | 是 | `[]` | 最多项 100 |
| `local_training_authorized` | boolean | 是 | `false` |  |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `purposes` | array&lt;`"executor"`, `"router"`, `"decision"`&gt; | 是 | — | 最少项 1; 最多项 3 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `run_ids` | array&lt;string&gt; | 是 | — | 最少项 1; 最多项 200 |
| `teacher_uses` | array&lt;[TeacherUse-Output](#teacheruse-output)&gt; | 是 | `[]` | 最多项 20 |

<a id="datasetartifact"></a>
### DatasetArtifact

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `command` | [ExportCommand-Output](#exportcommand-output) | 是 | — |  |
| `example_count` | integer | 是 | — |  |
| `format` | `"auton-local-learning-jsonl-v1"` | 是 | `"auton-local-learning-jsonl-v1"` |  |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `manifest_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `sha256` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `size` | integer | 是 | — |  |
| `snapshot_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `version` | integer | 是 | `0` |  |

<a id="datasetbuild-input"></a>
### DatasetBuild-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `grant_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `kind` | `"executor"`, `"router"`, `"decision"` | 是 | — |  |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `router_pairs` | array&lt;[RouterPair](#routerpair)&gt; | 否 | `[]` | 最多项 100 |
| `subjects` | array&lt;[SubjectRef-Input](#subjectref-input)&gt; | 是 | — | 最少项 1; 最多项 200 |

<a id="datasetbuild-output"></a>
### DatasetBuild-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `grant_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `kind` | `"executor"`, `"router"`, `"decision"` | 是 | — |  |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `router_pairs` | array&lt;[RouterPair](#routerpair)&gt; | 是 | `[]` | 最多项 100 |
| `subjects` | array&lt;[SubjectRef-Output](#subjectref-output)&gt; | 是 | — | 最少项 1; 最多项 200 |

<a id="datasetoperation-input"></a>
### DatasetOperation-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `command` | [DatasetBuild-Input](#datasetbuild-input) | 是 | — |  |
| `kind` | `"dataset"` | 是 | — |  |

<a id="datasetoperation-output"></a>
### DatasetOperation-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `command` | [DatasetBuild-Output](#datasetbuild-output) | 是 | — |  |
| `kind` | `"dataset"` | 是 | — |  |

<a id="datasetsnapshot"></a>
### DatasetSnapshot

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `activation` | `"no_training_started"` | 是 | `"no_training_started"` |  |
| `command` | [DatasetBuild-Output](#datasetbuild-output) | 是 | — |  |
| `config_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `content_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `created_at` | number | 是 | — |  |
| `current_evidence_valid` | boolean | 是 | `true` |  |
| `examples` | array&lt;[TrainingExample](#trainingexample)&gt; | 是 | `[]` |  |
| `grant_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `invalidation_reasons` | array&lt;string&gt; | 是 | `[]` |  |
| `rejected` | array&lt;[RejectedSubject](#rejectedsubject)&gt; | 是 | `[]` |  |
| `source_groups` | integer | 是 | `0` |  |
| `status` | `"ready"`, `"blocked"`, `"engineering_only"` | 是 | `"blocked"` |  |
| `training_ready` | boolean | 是 | `false` |  |
| `version` | integer | 是 | `0` |  |

<a id="datasetstatus"></a>
### DatasetStatus

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `config_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `max_sources` | integer | 是 | — |  |
| `protected_splits` | array&lt;string&gt; | 是 | `["test", "meta", "reviewer_meta", "optimization_arena"]` |  |
| `source_revision` | string | 是 | — |  |
| `training` | `"separate_worker_capability"` | 是 | `"separate_worker_capability"` |  |

<a id="datasetwithdrawal-input"></a>
### DatasetWithdrawal-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `grant_id` | string / null | 否 | — |  |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `reason` | string | 是 | — | 最短 10; 最长 2000 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `run_id` | string / null | 否 | — |  |

<a id="datasetwithdrawal-output"></a>
### DatasetWithdrawal-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `grant_id` | string / null | 是 | — |  |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `reason` | string | 是 | — | 最短 10; 最长 2000 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `run_id` | string / null | 是 | — |  |

<a id="decisionevaluation"></a>
### DecisionEvaluation

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `activation` | `"teacher_only_no_student_route"` | 是 | `"teacher_only_no_student_route"` |  |
| `actual_agent_pairs` | integer | 是 | `0` |  |
| `blockers` | array&lt;string&gt; | 是 | — |  |
| `bundle_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `command` | [DecisionEvaluationCommand-Output](#decisionevaluationcommand-output) | 是 | — |  |
| `current_evidence_valid` | boolean | 是 | `true` |  |
| `evidence_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `independent_agent_families` | integer | 是 | `0` |  |
| `layers` | map&lt;`"observed"`, `"missing"`, `"stale"`, `"descriptive_only"`&gt; | 是 | — |  |
| `release_eligible` | `false` | 是 | `false` |  |
| `status` | `"HOLD"` | 是 | `"HOLD"` |  |
| `version` | integer | 是 | `0` |  |

<a id="decisionevaluationcommand-input"></a>
### DecisionEvaluationCommand-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `agent_pairs` | array&lt;[AgentDecisionPair](#agentdecisionpair)&gt; | 否 | `[]` | 最多项 30 |
| `bundle_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `champion_bundle_id` | string / null | 否 | — |  |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="decisionevaluationcommand-output"></a>
### DecisionEvaluationCommand-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `agent_pairs` | array&lt;[AgentDecisionPair](#agentdecisionpair)&gt; | 是 | `[]` | 最多项 30 |
| `bundle_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `champion_bundle_id` | string / null | 是 | — |  |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="decisionsource"></a>
### DecisionSource

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `device` | string | 是 | — |  |
| `max_tokens` | integer | 是 | — |  |
| `provider` | `"laya"`, `"mock"` | 是 | — |  |
| `repository` | string | 是 | — |  |
| `revision` | string | 是 | — |  |
| `runtime_version` | string | 是 | — |  |
| `source` | `"local"`, `"test"` | 是 | — |  |
| `subfolder` | string | 是 | — |  |

<a id="delegationcommand"></a>
### DelegationCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `action` | `"start"`, `"resume"`, `"cancel"`, `"approve_child"`, `"approve_integration"` | 是 | — |  |
| `child_id` | string / null | 否 | — |  |
| `expected_version` | integer | 是 | — | ≥ 0.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,64}$ |

<a id="delegationcreate-input"></a>
### DelegationCreate-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `acceptance` | [Acceptance-Input](#acceptance-input) | 是 | — |  |
| `boundaries` | array&lt;string&gt; | 否 | `[]` | 最多项 12 |
| `children` | array&lt;[ChildSpec-Input](#childspec-input)&gt; | 是 | — | 最少项 1; 最多项 8 |
| `expected_previous_sha256` | string / null | 否 | — |  |
| `goal` | string | 是 | — | 最短 1; 最长 4000 |
| `limits` | [RunLimits-Input](#runlimits-input) | 是 | — |  |
| `merge_order` | array&lt;string&gt; | 是 | — | 最少项 1; 最多项 8 |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,64}$ |
| `public` | boolean | 否 | `false` |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,64}$ |
| `separator` | string | 否 | `""` | 最长 200 |
| `workspace_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,64}$ |

<a id="delegationcreate-output"></a>
### DelegationCreate-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `acceptance` | [Acceptance-Output](#acceptance-output) | 是 | — |  |
| `boundaries` | array&lt;string&gt; | 是 | `[]` | 最多项 12 |
| `children` | array&lt;[ChildSpec-Output](#childspec-output)&gt; | 是 | — | 最少项 1; 最多项 8 |
| `expected_previous_sha256` | string / null | 是 | — |  |
| `goal` | string | 是 | — | 最短 1; 最长 4000 |
| `limits` | [RunLimits-Output](#runlimits-output) | 是 | — |  |
| `merge_order` | array&lt;string&gt; | 是 | — | 最少项 1; 最多项 8 |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,64}$ |
| `public` | boolean | 是 | `false` |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,64}$ |
| `separator` | string | 是 | `""` | 最长 200 |
| `workspace_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,64}$ |

<a id="delegationstatus"></a>
### DelegationStatus

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `child_timeout_seconds` | number | 是 | — |  |
| `host_limits` | [RunLimits-Output](#runlimits-output) | 是 | — |  |
| `max_children` | integer | 是 | — |  |
| `max_parallel` | integer | 是 | — |  |
| `mode` | `"user-authored-file-supervisor"` | 是 | `"user-authored-file-supervisor"` |  |

<a id="delegationview"></a>
### DelegationView

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `approved_integration` | boolean | 是 | `false` |  |
| `attribution` | `"interaction-group-only"` | 是 | `"interaction-group-only"` |  |
| `benefit_claim` | `"not_established"` | 是 | `"not_established"` |  |
| `children` | array&lt;[ChildState](#childstate)&gt; | 是 | — |  |
| `command` | [DelegationCreate-Output](#delegationcreate-output) | 是 | — |  |
| `created_at` | number | 是 | — |  |
| `goal_revision` | integer | 是 | `1` |  |
| `id` | string | 是 | — |  |
| `input_snapshot_id` | string | 是 | — |  |
| `integration` | [ToolPlan](#toolplan) / null | 是 | — |  |
| `integration_receipt` | [ToolReceipt](#toolreceipt) / null | 是 | — |  |
| `interaction_group` | array&lt;string&gt; | 是 | — |  |
| `reason` | string | 是 | `"user_authored_dag_ready"` |  |
| `source` | `"runtime"`, `"test"` | 是 | — |  |
| `status` | `"draft"`, `"running"`, `"waiting_approval"`, `"integrating"`, `"integrated"`, `"blocked"`, `"cancelling"`, `"cancelled"` | 是 | `"draft"` |  |
| `total_cost_microusd` | integer | 是 | `0` |  |
| `total_tokens` | integer | 是 | `0` |  |
| `total_tool_calls` | integer | 是 | `0` |  |
| `unknown_calls` | integer | 是 | `0` |  |
| `unknown_tools` | integer | 是 | `0` |  |
| `updated_at` | number | 是 | — |  |
| `version` | integer | 是 | `0` |  |

<a id="diagnosecommand"></a>
### DiagnoseCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `report_ids` | array&lt;string&gt; | 是 | — | 最少项 1; 最多项 12 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="diagnosis"></a>
### Diagnosis

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | string | 是 | — |  |
| `category` | `"asset_hypothesis"`, `"tool_environment"`, `"execution_capability"`, `"missing_information"`, `"mixed"`, `"unknown"` | 是 | — |  |
| `conclusion_scope` | `"diagnostic-hypothesis-only"` | 是 | `"diagnostic-hypothesis-only"` |  |
| `id` | string | 是 | — |  |
| `project_id` | string | 是 | — |  |
| `reasons` | array&lt;string&gt; | 是 | — |  |
| `report_ids` | array&lt;string&gt; | 是 | — |  |
| `suggested_action` | `"inspect_tools"`, `"inspect_executor"`, `"collect_evidence"`, `"review_local_patch"` | 是 | — |  |
| `usable_train_reports` | array&lt;string&gt; | 是 | — |  |

<a id="episodesummary"></a>
### EpisodeSummary

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `context_ids` | array&lt;string&gt; | 是 | — |  |
| `estimated_cost_microusd` | integer | 是 | — |  |
| `first_cursor` | integer | 是 | — |  |
| `goal_id` | string | 是 | — |  |
| `goal_revision` | integer | 是 | — |  |
| `id` | string | 是 | — |  |
| `last_cursor` | integer | 是 | — |  |
| `model_request_ids` | array&lt;string&gt; | 是 | — |  |
| `observed_tokens` | integer | 是 | — |  |
| `operation_ids` | array&lt;string&gt; | 是 | — |  |
| `parent_run_id` | string / null | 是 | — |  |
| `run_id` | string | 是 | — |  |
| `session_id` | string | 是 | — |  |

<a id="errorbody"></a>
### ErrorBody

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `code` | string | 是 | — |  |
| `message` | string | 是 | — |  |

<a id="evalcase-input"></a>
### EvalCase-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `critical` | boolean | 否 | `false` |  |
| `data_domain` | `"public"`, `"local-only"` | 否 | `"local-only"` |  |
| `domain` | string | 否 | `"general"` | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `evidence_text` | map&lt;string&gt; | 否 | — | 最多属性 12 |
| `expected_sha256` | string / null | 否 | — |  |
| `family` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `human_answer` | string / null | 否 | — |  |
| `human_verdict` | `"pass"`, `"fail"`, `"unknown"` | 否 | `"unknown"` |  |
| `id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `kind` | `"file"`, `"research"`, `"response"` | 是 | — |  |
| `origin_group` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |
| `prompt` | string | 是 | — | 最短 1; 最长 4000 |
| `source` | `"human_seed"`, `"benchmark"`, `"episode"`, `"test_fixture"` | 是 | — |  |
| `split` | `"train"`, `"development"`, `"test"`, `"meta"` | 是 | — |  |
| `tags` | array&lt;string&gt; | 否 | `[]` | 最多项 8 |
| `target_path` | string / null | 否 | — |  |

<a id="evalcase-output"></a>
### EvalCase-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `critical` | boolean | 是 | `false` |  |
| `data_domain` | `"public"`, `"local-only"` | 是 | `"local-only"` |  |
| `domain` | string | 是 | `"general"` | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `evidence_text` | map&lt;string&gt; | 是 | — | 最多属性 12 |
| `expected_sha256` | string / null | 是 | — |  |
| `family` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `human_answer` | string / null | 是 | — |  |
| `human_verdict` | `"pass"`, `"fail"`, `"unknown"` | 是 | `"unknown"` |  |
| `id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `kind` | `"file"`, `"research"`, `"response"` | 是 | — |  |
| `origin_group` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |
| `prompt` | string | 是 | — | 最短 1; 最长 4000 |
| `source` | `"human_seed"`, `"benchmark"`, `"episode"`, `"test_fixture"` | 是 | — |  |
| `split` | `"train"`, `"development"`, `"test"`, `"meta"` | 是 | — |  |
| `tags` | array&lt;string&gt; | 是 | `[]` | 最多项 8 |
| `target_path` | string / null | 是 | — |  |

<a id="evaljob"></a>
### EvalJob

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `command` | [EvaluateCommand-Output](#evaluatecommand-output) | 是 | — |  |
| `id` | string | 是 | — |  |
| `reason` | string | 是 | — |  |
| `report` | [EvalReport](#evalreport) / null | 是 | — |  |
| `status` | `"running"`, `"complete"`, `"blocked"` | 是 | — |  |

<a id="evalreport"></a>
### EvalReport

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `bank_revision` | string / null | 是 | — |  |
| `candidate_revision` | string | 是 | — |  |
| `case_id` | string / null | 是 | — |  |
| `checkpoint_digest` | string | 是 | — |  |
| `checkpoint_event_id` | string | 是 | — |  |
| `checkpoint_version` | integer | 是 | — |  |
| `conditions_digest` | string | 是 | — |  |
| `config_digest` | string | 是 | — |  |
| `current_evidence_valid` | boolean | 是 | `true` |  |
| `environment_verified` | boolean | 是 | `false` |  |
| `evaluation_cost_microusd` | integer / null | 是 | — |  |
| `evaluation_unknown_calls` | integer | 是 | — |  |
| `family` | string | 是 | — |  |
| `goal_revision` | integer | 是 | — |  |
| `groups` | array&lt;string&gt; | 是 | — |  |
| `id` | string | 是 | — |  |
| `judges` | array&lt;[JudgeObservation](#judgeobservation)&gt; | 是 | — |  |
| `metrics` | [Metrics](#metrics) | 是 | — |  |
| `outcome` | `"pass"`, `"fail"`, `"unknown"`, `"environment_error"`, `"incomplete"` | 是 | — |  |
| `project_id` | string | 是 | — |  |
| `quality_release_eligible` | boolean | 是 | `false` |  |
| `reasons` | array&lt;string&gt; | 是 | — |  |
| `request_id` | string | 是 | — |  |
| `rubric_revision` | string | 是 | — |  |
| `run_id` | string | 是 | — |  |
| `semantic_verdict` | `"pass"`, `"fail"`, `"unknown"` | 是 | — |  |
| `signals` | array&lt;[Signal](#signal)&gt; | 是 | — |  |
| `source` | `"runtime"`, `"test"` | 是 | — |  |
| `split` | `"operational"`, `"train"`, `"development"`, `"test"`, `"meta"` | 是 | — |  |
| `split_digest` | string / null | 是 | — |  |
| `status` | `"complete"`, `"blocked"` | 是 | — |  |

<a id="evaluatecommand-input"></a>
### EvaluateCommand-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `bank_revision` | string / null | 否 | — |  |
| `case_id` | string / null | 否 | — |  |
| `expected_version` | integer | 是 | — | ≥ 0.0; ≤ 65535.0 |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `repeats` | integer | 否 | `1` | ≥ 1.0; ≤ 3.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |
| `run_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `semantic` | boolean | 否 | `false` |  |
| `window_id` | string / null | 否 | — |  |

<a id="evaluatecommand-output"></a>
### EvaluateCommand-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `bank_revision` | string / null | 是 | — |  |
| `case_id` | string / null | 是 | — |  |
| `expected_version` | integer | 是 | — | ≥ 0.0; ≤ 65535.0 |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `repeats` | integer | 是 | `1` | ≥ 1.0; ≤ 3.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |
| `run_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `semantic` | boolean | 是 | `false` |  |
| `window_id` | string / null | 是 | — |  |

<a id="evidence"></a>
### Evidence

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `asset_ids` | array&lt;string&gt; | 是 | — |  |
| `content_digest` | string | 是 | — |  |
| `end_character` | integer | 是 | — |  |
| `locations` | array&lt;[SourceLocation](#sourcelocation)&gt; | 是 | — |  |
| `score` | number | 是 | — |  |
| `source_references` | array&lt;string&gt; | 是 | — |  |
| `start_character` | integer | 是 | — |  |
| `text` | string | 是 | — |  |
| `trust` | `"untrusted"` | 是 | `"untrusted"` |  |

<a id="evidencefact"></a>
### EvidenceFact

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `cursor` | integer | 是 | — |  |
| `digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `id` | string | 是 | — |  |
| `kind` | string | 是 | — |  |
| `text` | string | 是 | — | 最长 1000 |

<a id="evolutionstatus"></a>
### EvolutionStatus

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `activation` | `"release_control_only"` | 是 | `"release_control_only"` |  |
| `config_digest` | string | 是 | — |  |
| `gate_revision` | string | 是 | — |  |
| `max_arena_model_calls` | integer | 是 | — |  |
| `min_development_families` | integer | 是 | — |  |
| `min_repeats` | integer | 是 | — |  |
| `reflection_model` | string | 是 | — |  |

<a id="exportcommand-input"></a>
### ExportCommand-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `expected_content_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `purpose` | `"local_training"`, `"local_validation"` | 是 | — |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `split` | `"train"`, `"validation"` | 否 | `"train"` |  |

<a id="exportcommand-output"></a>
### ExportCommand-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `expected_content_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `purpose` | `"local_training"`, `"local_validation"` | 是 | — |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `split` | `"train"`, `"validation"` | 是 | `"train"` |  |

<a id="exportoperation-input"></a>
### ExportOperation-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `command` | [ExportCommand-Input](#exportcommand-input) | 是 | — |  |
| `kind` | `"export"` | 是 | — |  |
| `snapshot_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |

<a id="exportoperation-output"></a>
### ExportOperation-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `command` | [ExportCommand-Output](#exportcommand-output) | 是 | — |  |
| `kind` | `"export"` | 是 | — |  |
| `snapshot_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |

<a id="feedbackcommand"></a>
### FeedbackCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `category` | `"delivery"`, `"approval"` | 否 | `"delivery"` |  |
| `checkpoint_version` | integer | 是 | — | ≥ 0.0; ≤ 65535.0 |
| `expected_goal_revision` | integer | 是 | — | ≥ 1.0 |
| `note` | string | 否 | `""` | 最长 2000 |
| `rating` | `"helpful"`, `"unhelpful"` | 是 | — |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |

<a id="feedbackreceipt"></a>
### FeedbackReceipt

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `checkpoint_event_id` | string | 是 | — |  |
| `event_id` | string | 是 | — |  |
| `label_source` | `"human-feedback"` | 是 | `"human-feedback"` |  |
| `run_id` | string | 是 | — |  |
| `verified_quality` | `false` | 是 | `false` |  |

<a id="gatesignal"></a>
### GateSignal

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `evidence` | array&lt;string&gt; | 是 | `[]` |  |
| `name` | string | 是 | — |  |
| `reasons` | array&lt;string&gt; | 是 | — |  |
| `verdict` | `"pass"`, `"fail"`, `"hold"` | 是 | — |  |

<a id="generationreceipt"></a>
### GenerationReceipt

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `cost_microusd` | integer / null | 是 | — |  |
| `dispatch` | `"confirmed"`, `"not_dispatched"`, `"unknown"` | 是 | — |  |
| `fingerprint` | string / null | 是 | — |  |
| `reason` | string | 是 | — |  |
| `reported_model` | string / null | 是 | — |  |
| `request_id` | string | 是 | — |  |
| `source` | `"remote"`, `"test"`, `"unavailable"` | 是 | — |  |
| `tokens` | integer / null | 是 | — |  |

<a id="generationrecord"></a>
### GenerationRecord

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `command` | [ReflectCommand-Output](#reflectcommand-output) | 是 | — |  |
| `config_digest` | string | 是 | — |  |
| `id` | string | 是 | — |  |
| `proposal_id` | string / null | 是 | — |  |
| `reason` | string | 是 | — |  |
| `receipt` | [GenerationReceipt](#generationreceipt) / null | 是 | — |  |
| `status` | `"running"`, `"complete"`, `"rejected"`, `"blocked"` | 是 | — |  |
| `version` | integer | 是 | `0` |  |

<a id="groupcalibration"></a>
### GroupCalibration

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `correct` | integer | 是 | — |  |
| `families` | integer | 是 | — |  |
| `known` | integer | 是 | — |  |
| `qualified` | boolean | 是 | — |  |
| `samples` | integer | 是 | — |  |
| `wilson_lower` | number / null | 是 | — |  |

<a id="healthresponse"></a>
### HealthResponse

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `profile` | string | 是 | — |  |
| `status` | `"ready"`, `"starting"`, `"stopped"` | 是 | — |  |

<a id="humanrevision-input"></a>
### HumanRevision-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `evidence_refs` | array&lt;string&gt; | 是 | — | 最少项 1; 最多项 20 |
| `expected_version` | integer | 是 | — | ≥ 0.0 |
| `proposed_verdict` | `"KEEP"`, `"DROP"`, `"HOLD"` | 是 | — |  |
| `reason` | string | 是 | — | 最短 10; 最长 2000 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `source` | `"user_observation"` | 否 | `"user_observation"` |  |

<a id="humanrevision-output"></a>
### HumanRevision-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `evidence_refs` | array&lt;string&gt; | 是 | — | 最少项 1; 最多项 20 |
| `expected_version` | integer | 是 | — | ≥ 0.0 |
| `proposed_verdict` | `"KEEP"`, `"DROP"`, `"HOLD"` | 是 | — |  |
| `reason` | string | 是 | — | 最短 10; 最长 2000 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `source` | `"user_observation"` | 是 | `"user_observation"` |  |

<a id="identityinfo"></a>
### IdentityInfo

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `expires_at` | number | 是 | — |  |
| `identity_id` | string | 是 | — |  |
| `persistent` | boolean | 是 | — |  |
| `remaining_seconds` | integer | 是 | — |  |

<a id="importcases"></a>
### ImportCases

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `cases` | array&lt;[EvalCase-Input](#evalcase-input)&gt; | 是 | — | 最少项 1; 最多项 100 |
| `expected_revision` | string | 是 | — |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |

<a id="jsonvalue"></a>
### JsonValue

object

<a id="judgeobservation"></a>
### JudgeObservation

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `configuration_digest` | string | 是 | — |  |
| `cost_microusd` | integer / null | 是 | `0` |  |
| `dispatch_outcome` | `"not_dispatched"`, `"confirmed"`, `"unknown"` | 是 | `"not_dispatched"` |  |
| `evidence` | array&lt;string&gt; | 是 | `[]` |  |
| `fingerprint` | string / null | 是 | — |  |
| `reason` | string | 是 | — |  |
| `reported_confidence` | number / null | 是 | — |  |
| `reported_model` | string / null | 是 | — |  |
| `request_id` | string | 是 | — |  |
| `rubric_revision` | string | 是 | — |  |
| `self_eval_bias` | boolean | 是 | `false` |  |
| `source` | `"remote"`, `"test"`, `"unavailable"` | 是 | — |  |
| `tokens` | integer / null | 是 | `0` |  |
| `verdict` | `"pass"`, `"fail"`, `"unknown"` | 是 | — |  |

<a id="judgmentinfo"></a>
### JudgmentInfo

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `application_enabled` | boolean | 是 | `false` |  |
| `backend` | string | 是 | — |  |
| `checkpoint` | string | 是 | — |  |
| `decision_points` | array&lt;string&gt; | 是 | — |  |
| `health` | `"not_loaded"`, `"available"`, `"weights_missing"`, `"unavailable"`, `"test_fixture"` | 是 | — |  |
| `primary_only` | `true` | 是 | `true` |  |
| `revision` | string | 是 | — |  |

<a id="judgmentpreview"></a>
### JudgmentPreview

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `public` | boolean | 否 | `false` |  |
| `request_id` | string | 是 | — | 最短 1; 最长 100; 格式 ^[a-zA-Z0-9_-]+$ |
| `state` | string | 是 | — | 最短 1; 最长 12000 |

<a id="judgmentrequest"></a>
### JudgmentRequest

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `data_domain` | `"public"`, `"local-only"`, `"secret"` | 是 | `"local-only"` |  |
| `goal_id` | string | 是 | — | 最短 1; 最长 200 |
| `goal_revision` | integer | 是 | `1` | ≥ 1.0 |
| `principal` | [Principal](#principal) | 是 | — |  |
| `questions` | array&lt;[Question](#question)&gt; | 是 | — | 最少项 1; 最多项 8 |
| `request_id` | string | 是 | — | 最短 1; 最长 100; 格式 ^[a-zA-Z0-9_-]+$ |
| `required_capabilities` | array&lt;`"text"`, `"tools"`, `"json"`&gt; | 是 | `["text"]` |  |
| `required_context_tokens` | integer | 是 | `0` | ≥ 0.0; ≤ 1048576.0 |
| `state` | string | 是 | — | 最短 1; 最长 12000 |
| `state_cutoff` | integer | 是 | `0` | ≥ 0.0 |

<a id="judgmentresult"></a>
### JudgmentResult

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `adopted` | boolean | 是 | `false` |  |
| `answers` | array&lt;[Answer](#answer)&gt; | 是 | — |  |
| `goal_id` | string | 是 | — |  |
| `goal_revision` | integer | 是 | — |  |
| `latency_ms` | integer | 是 | — |  |
| `raw_event_id` | string | 是 | — |  |
| `request_digest` | string | 是 | — |  |
| `request_id` | string | 是 | — |  |
| `route` | [RouteDecision](#routedecision) | 是 | — |  |
| `source` | [DecisionSource](#decisionsource) | 是 | — |  |
| `state_cutoff` | integer | 是 | — |  |

<a id="learningcase"></a>
### LearningCase

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `artifact_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `assessment_id` | string / null | 是 | — |  |
| `attempt` | integer | 是 | `0` |  |
| `conversation_id` | string | 是 | — |  |
| `dataset_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `decision_outcomes` | map&lt;string&gt; | 是 | — |  |
| `example_keys` | array&lt;string&gt; | 是 | `[]` |  |
| `id` | string | 是 | — |  |
| `policy_version` | integer / null | 是 | — |  |
| `project_id` | string | 是 | — |  |
| `reasons` | array&lt;string&gt; | 是 | `[]` |  |
| `reserved_review_calls` | integer | 是 | `0` |  |
| `review_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `run_id` | string | 是 | — |  |
| `run_version` | integer / null | 是 | — |  |
| `split` | `"train"`, `"validation"` | 是 | `"train"` |  |
| `stage` | `"collected"`, `"assessing"`, `"reviewing"`, `"building"`, `"ready"`, `"hold"`, `"rejected"` | 是 | `"collected"` |  |
| `version` | integer | 是 | `0` |  |

<a id="learningmanifest"></a>
### LearningManifest

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `activation` | `"no_training_started"` | 是 | `"no_training_started"` |  |
| `decision_train_artifact_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `decision_validation_artifact_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `executor_train_artifact_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `executor_validation_artifact_ids` | array&lt;string&gt; | 是 | `[]` |  |

<a id="learningpolicy"></a>
### LearningPolicy

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `command` | [LearningPolicyCommand-Output](#learningpolicycommand-output) | 是 | — |  |
| `version` | integer | 是 | `0` |  |

<a id="learningpolicycommand-input"></a>
### LearningPolicyCommand-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `allow_local_only_data` | boolean | 否 | `false` |  |
| `allow_remote_review` | boolean | 否 | `false` |  |
| `data_license_reference` | string | 否 | `""` | 最长 1000 |
| `enabled` | boolean | 否 | `false` |  |
| `expected_version` | integer / null | 否 | — |  |
| `external_asset_uses` | array&lt;[AssetUse-Input](#assetuse-input)&gt; | 否 | `[]` | 最多项 100 |
| `local_training_authorized` | boolean | 否 | `false` |  |
| `max_review_calls` | integer | 否 | `0` | ≥ 0.0; ≤ 100000.0 |
| `review_decisions` | boolean | 否 | `true` |  |
| `teacher_uses` | array&lt;[TeacherUse-Input](#teacheruse-input)&gt; | 否 | `[]` | 最多项 20 |

<a id="learningpolicycommand-output"></a>
### LearningPolicyCommand-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `allow_local_only_data` | boolean | 是 | `false` |  |
| `allow_remote_review` | boolean | 是 | `false` |  |
| `data_license_reference` | string | 是 | `""` | 最长 1000 |
| `enabled` | boolean | 是 | `false` |  |
| `expected_version` | integer / null | 是 | — |  |
| `external_asset_uses` | array&lt;[AssetUse-Output](#assetuse-output)&gt; | 是 | `[]` | 最多项 100 |
| `local_training_authorized` | boolean | 是 | `false` |  |
| `max_review_calls` | integer | 是 | `0` | ≥ 0.0; ≤ 100000.0 |
| `review_decisions` | boolean | 是 | `true` |  |
| `teacher_uses` | array&lt;[TeacherUse-Output](#teacheruse-output)&gt; | 是 | `[]` | 最多项 20 |

<a id="learningretry"></a>
### LearningRetry

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `expected_version` | integer | 是 | — | ≥ 0.0 |

<a id="learningstatus"></a>
### LearningStatus

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `activation` | `"no_training_started"` | 是 | `"no_training_started"` |  |
| `cases` | array&lt;[LearningCase](#learningcase)&gt; | 是 | — |  |
| `policy` | [LearningPolicy](#learningpolicy) / null | 是 | — |  |
| `reserved_review_calls` | integer | 是 | — |  |

<a id="legacyidentitycommand"></a>
### LegacyIdentityCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="localdirectories"></a>
### LocalDirectories

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `directories` | array&lt;string&gt; | 是 | — |  |
| `parent` | string / null | 是 | — |  |
| `path` | string | 是 | — |  |
| `truncated` | boolean | 是 | `false` |  |

<a id="maintenanceoperation"></a>
### MaintenanceOperation

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `kind` | `"telemetry"`, `"retention"` | 是 | — |  |

<a id="message"></a>
### Message

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `content` | string | 是 | — |  |
| `id` | string | 是 | — |  |
| `role` | `"user"`, `"assistant"` | 是 | — |  |

<a id="metacasecommand"></a>
### MetaCaseCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `confirm_independent_human_annotation` | boolean | 否 | `false` |  |
| `evidence_refs` | array&lt;string&gt; | 是 | — | 最少项 1; 最多项 20 |
| `expected_review_version` | integer | 是 | — | ≥ 0.0 |
| `explanation` | string | 是 | — | 最短 20; 最长 2000 |
| `family` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `gold` | `"KEEP"`, `"DROP"`, `"HOLD"` | 是 | — |  |
| `label_source` | `"human_annotation"` | 否 | `"human_annotation"` |  |
| `origin_group` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `review_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |

<a id="metrics"></a>
### Metrics

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `confirmed_model_calls` | integer | 是 | — |  |
| `cost_microusd` | integer | 是 | — |  |
| `extra_model_calls` | integer | 是 | — |  |
| `failed_tools` | integer | 是 | — |  |
| `model_latency_ms` | integer | 是 | — |  |
| `scope` | `"run-lifetime"` | 是 | `"run-lifetime"` |  |
| `tokens` | integer | 是 | — |  |
| `tool_attempts` | integer | 是 | — |  |
| `unconfirmed_model_calls` | integer | 是 | — |  |
| `unknown_tools` | integer | 是 | — |  |
| `usage_complete` | boolean | 是 | — |  |

<a id="modelinfo"></a>
### ModelInfo

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `adapter_revision` | string / null | 是 | — |  |
| `base_revision` | string / null | 是 | — |  |
| `capabilities` | array&lt;string&gt; | 是 | — |  |
| `capability_source` | `"provider-declared"`, `"test-fixture"` | 是 | — |  |
| `context_tokens` | integer | 是 | — |  |
| `declared_context_tokens` | integer | 是 | — |  |
| `declared_revision` | string | 是 | — |  |
| `executor_tier` | `"small_2b"`, `"small_7b"`, `"strong"`, `"test_fixture"` | 是 | `"strong"` |  |
| `health` | `"not_checked"`, `"available"`, `"unavailable"`, `"credential_missing"`, `"test_fixture"` | 是 | — |  |
| `id` | string | 是 | — |  |
| `input_microusd_per_million` | integer | 是 | — |  |
| `location` | `"local"`, `"remote"` | 是 | — |  |
| `max_output_tokens` | integer | 是 | — |  |
| `output_microusd_per_million` | integer | 是 | — |  |
| `price_revision` | string | 是 | — |  |
| `provider` | string | 是 | — |  |
| `quantization` | string / null | 是 | — |  |
| `revision_is_pinned` | boolean | 是 | — |  |
| `runtime_revision` | string | 是 | `"deepseek-http-sse-v2"` |  |
| `template_revision` | string / null | 是 | — |  |

<a id="modelmessage-input"></a>
### ModelMessage-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `content` | string / null | 否 | — |  |
| `role` | `"system"`, `"user"`, `"assistant"`, `"tool"` | 是 | — |  |
| `tool_call_id` | string / null | 否 | — |  |
| `tool_calls` | array&lt;[ToolCall](#toolcall)&gt; | 否 | `[]` |  |

<a id="modelmessage-output"></a>
### ModelMessage-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `content` | string / null | 是 | — |  |
| `role` | `"system"`, `"user"`, `"assistant"`, `"tool"` | 是 | — |  |
| `tool_call_id` | string / null | 是 | — |  |
| `tool_calls` | array&lt;[ToolCall](#toolcall)&gt; | 是 | `[]` |  |

<a id="modelprobe"></a>
### ModelProbe

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `request_id` | string | 是 | — | 最短 1; 最长 100; 格式 ^[a-zA-Z0-9_-]+$ |

<a id="modelresult"></a>
### ModelResult

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `content` | string | 是 | — |  |
| `finish_reason` | `"stop"`, `"tool_calls"`, `"length"` | 是 | — |  |
| `latency_ms` | integer | 是 | — |  |
| `model_id` | string | 是 | — |  |
| `redacted` | boolean | 是 | `false` |  |
| `reported_model` | string | 是 | — |  |
| `request_id` | string | 是 | — |  |
| `source` | `"remote"`, `"local"`, `"test"` | 是 | — |  |
| `system_fingerprint` | string / null | 是 | — |  |
| `tool_calls` | array&lt;[ToolCall](#toolcall)&gt; | 是 | `[]` |  |
| `usage` | [ModelUsage](#modelusage) | 是 | — |  |

<a id="modelusage"></a>
### ModelUsage

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `cost_is_estimate` | `true` | 是 | `true` |  |
| `estimated_cost_microusd` | integer | 是 | `0` | ≥ 0.0 |
| `input_tokens` | integer | 是 | — | ≥ 0.0 |
| `output_tokens` | integer | 是 | — | ≥ 0.0 |

<a id="moduledescriptor"></a>
### ModuleDescriptor

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `config_schema` | string / null | 否 | — |  |
| `factory_entry` | string / null | 否 | — |  |
| `id` | string | 是 | — |  |
| `milestone` | string | 是 | — |  |
| `provides` | array&lt;string&gt; | 否 | `[]` |  |
| `requires` | array&lt;string&gt; | 否 | `[]` |  |
| `scope` | `"application"`, `"session"`, `"run"` | 否 | `"application"` |  |
| `status` | `"ready"`, `"planned"`, `"disabled"` | 是 | — |  |
| `title` | string | 是 | — |  |
| `version` | string | 否 | `"1"` |  |

<a id="operationsalert"></a>
### OperationsAlert

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `active` | boolean | 是 | — |  |
| `changed_at` | number | 是 | — |  |
| `code` | string | 是 | — |  |
| `delivery` | `"local_control_panel_only"` | 是 | `"local_control_panel_only"` |  |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `project_id` | string | 是 | — |  |
| `sample_id` | string / null | 是 | — |  |
| `version` | integer | 是 | `0` |  |

<a id="operationscontrol"></a>
### OperationsControl

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `action` | `"pause"`, `"resume"`, `"cancel"` | 是 | — |  |
| `expected_version` | integer | 是 | — | ≥ 0.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="operationsstatus"></a>
### OperationsStatus

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `config_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `coordinator` | `"single_process_fenced_leases"` | 是 | `"single_process_fenced_leases"` |  |
| `enabled` | boolean | 是 | — |  |
| `last_error` | string | 是 | `""` |  |
| `observer_only` | boolean | 是 | `false` |  |
| `owner_paused` | boolean | 是 | `false` |  |
| `publication_authority` | `false` | 是 | `false` |  |

<a id="optimizationtask"></a>
### OptimizationTask

Executable train/dev input, with no meta human answer or calibration label.

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `case_id` | string | 是 | — |  |
| `critical` | boolean | 是 | — |  |
| `data_domain` | `"public"`, `"local-only"` | 是 | — |  |
| `family` | string | 是 | — |  |
| `origin_group` | string | 是 | — |  |
| `path` | string | 是 | — |  |
| `prompt` | string | 是 | — |  |
| `sha256` | string | 是 | — |  |
| `source` | `"human_seed"`, `"benchmark"`, `"episode"`, `"test_fixture"` | 是 | — |  |
| `split` | `"train"`, `"development"` | 是 | — |  |

<a id="option"></a>
### Option

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `description` | string | 是 | — | 最短 1; 最长 300 |
| `id` | string | 是 | — | 格式 ^[a-z][a-z0-9_]{0,49}$ |

<a id="ownerpause"></a>
### OwnerPause

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `paused` | boolean | 是 | — |  |

<a id="pendingoperation"></a>
### PendingOperation

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `operation_id` | string | 是 | — | 最短 1; 最长 200 |
| `receipt_digest` | string / null | 否 | — |  |
| `status` | `"unknown"`, `"awaiting_approval"`, `"completed"`, `"failed"` | 是 | — |  |

<a id="playbookentry"></a>
### PlaybookEntry

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | string | 是 | — |  |
| `direction` | string | 是 | — |  |
| `evidence` | array&lt;string&gt; | 是 | — |  |
| `id` | string | 是 | — |  |
| `outcome` | `"proposed"`, `"rejected"`, `"blocked"`, `"review_queue"`, `"ready_for_release"` | 是 | — |  |
| `parent_sha256` | string | 是 | — |  |
| `project_id` | string | 是 | — |  |
| `proposal_id` | string | 是 | — |  |
| `reasons` | array&lt;string&gt; | 是 | — |  |
| `version` | integer | 是 | `0` |  |

<a id="policydecision"></a>
### PolicyDecision

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `outcome` | `"allow"`, `"deny"`, `"approval_required"` | 是 | — |  |
| `policy_version` | string | 是 | — |  |
| `reason_codes` | array&lt;string&gt; | 是 | — |  |

<a id="policyrevision"></a>
### PolicyRevision

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `config` | [ConstitutionConfig](#constitutionconfig) | 是 | — |  |
| `expected_version` | string | 是 | — |  |

<a id="principal"></a>
### Principal

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `owner` | string | 是 | — | 最短 1; 最长 200 |
| `role` | `"user"`, `"runtime"`, `"training"`, `"evolution"` | 否 | `"runtime"` |  |

<a id="priorrun"></a>
### PriorRun

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `version` | integer | 是 | — | ≥ 0.0; ≤ 65535.0 |

<a id="project-input"></a>
### Project-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `instructions` | string | 否 | `""` | 最长 10000 |
| `title` | string | 是 | — | 最短 1; 最长 100 |

<a id="project-output"></a>
### Project-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `instructions` | string | 是 | `""` | 最长 10000 |
| `title` | string | 是 | — | 最短 1; 最长 100 |

<a id="proposal"></a>
### Proposal

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `activation` | `"not_activated"` | 是 | `"not_activated"` |  |
| `candidate_content` | string | 是 | — |  |
| `candidate_sha256` | string | 是 | — |  |
| `command` | [ProposalCommand](#proposalcommand) | 是 | — |  |
| `config_digest` | string | 是 | — |  |
| `current_arena_id` | string / null | 是 | — |  |
| `diff` | string | 是 | — |  |
| `gates` | array&lt;[GateSignal](#gatesignal)&gt; | 是 | `[]` |  |
| `generation` | [GenerationReceipt](#generationreceipt) / null | 是 | — |  |
| `id` | string | 是 | — |  |
| `learning_revision` | string / null | 是 | — |  |
| `parent_blob_sha256` | string | 是 | — |  |
| `reasons` | array&lt;string&gt; | 是 | — |  |
| `source` | `"human-proposal"`, `"model-proposal"`, `"test"` | 是 | — |  |
| `status` | `"proposed"`, `"rejected"`, `"evaluating"`, `"blocked"`, `"review_queue"`, `"ready_for_release"` | 是 | — |  |
| `version` | integer | 是 | `0` |  |

<a id="proposalcommand"></a>
### ProposalCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `base_snapshot_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `diagnosis_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `direction` | string | 是 | — | 最短 1; 最长 300 |
| `expected_content_sha256` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `patch` | [SectionPatch](#sectionpatch) | 是 | — |  |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `rationale` | string | 是 | — | 最短 1; 最长 2000 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="publicpolicy"></a>
### PublicPolicy

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `allowed_actions` | array&lt;string&gt; | 是 | — |  |
| `approval_actions` | array&lt;string&gt; | 是 | — |  |
| `autonomy_max` | integer | 是 | — |  |
| `budget_per_goal` | [Usage](#usage) | 是 | — |  |
| `max_concurrent` | integer | 是 | — |  |
| `remote_data_domains` | array&lt;`"public"`&gt; | 否 | `["public"]` |  |
| `remote_providers` | array&lt;string&gt; | 是 | — |  |
| `version` | string | 是 | — |  |

<a id="question"></a>
### Question

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | — | 格式 ^[a-z][a-z0-9_]{0,49}$ |
| `instructions` | string | 是 | — | 最短 1; 最长 600 |
| `options` | array&lt;[Option](#option)&gt; | 是 | `[]` | 最多项 6 |
| `point` | `"information_sufficiency"`, `"executor_tier"`, `"tool_domain"`, `"skill_match"` | 是 | — |  |
| `revision` | string | 是 | `"auton-question-v1"` |  |
| `type` | `"choice"`, `"boolean"`, `"score"` | 是 | `"choice"` |  |

<a id="reasonableness"></a>
### Reasonableness

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `evidence_refs` | array&lt;string&gt; | 是 | — | 最少项 0; 最多项 12 |
| `explanation` | string | 是 | — | 最短 1; 最长 1500 |
| `knowledge_at_time` | `"sufficient"`, `"insufficient"`, `"unknown"` | 是 | — |  |
| `verdict` | `"supported"`, `"unreasonable"`, `"unknown"` | 是 | — |  |

<a id="recoverycommand"></a>
### RecoveryCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `checkpoint_event_id` | string | 是 | — | 最短 1; 最长 200 |
| `expected_goal_revision` | integer | 是 | — | ≥ 1.0 |
| `expected_version` | integer | 是 | — | ≥ 0.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |

<a id="reflectcommand-input"></a>
### ReflectCommand-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `base_snapshot_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `diagnosis_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `direction` | string | 是 | — | 最短 1; 最长 300 |
| `expected_content_sha256` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `heading` | string | 是 | — | 格式 ^#{1,6} [^\n]{1,100}$ |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `public` | boolean | 否 | `false` |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="reflectcommand-output"></a>
### ReflectCommand-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `base_snapshot_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `diagnosis_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `direction` | string | 是 | — | 最短 1; 最长 300 |
| `expected_content_sha256` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `heading` | string | 是 | — | 格式 ^#{1,6} [^\n]{1,100}$ |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `public` | boolean | 是 | `false` |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="rejectedsubject"></a>
### RejectedSubject

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `reasons` | array&lt;string&gt; | 是 | — |  |
| `run_id` | string | 是 | — |  |

<a id="releaseapproval"></a>
### ReleaseApproval

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `expected_evidence_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `expected_version` | integer | 是 | — | ≥ 0.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `risks_reviewed` | boolean | 否 | `false` |  |

<a id="releasecontrol"></a>
### ReleaseControl

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `action` | `"activate"`, `"pause"`, `"rollback"` | 是 | — |  |
| `expected_version` | integer | 是 | — | ≥ 0.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="releaseevidence"></a>
### ReleaseEvidence

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `blockers` | array&lt;string&gt; | 是 | — |  |
| `eligible` | boolean | 是 | — |  |
| `evidence_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `independent_families` | integer | 是 | `0` |  |
| `quality_lower` | number / null | 是 | — |  |
| `report_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `source_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `target_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |

<a id="releaseobservation"></a>
### ReleaseObservation

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `expected_version` | integer | 是 | — | ≥ 0.0 |
| `report_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="releaseplancommand-input"></a>
### ReleasePlanCommand-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `baseline_model_id` | string | 否 | `"deepseek-v4-pro"` | 最长 100 |
| `baseline_report_ids` | array&lt;string&gt; | 否 | `[]` | 最多项 100 |
| `decision_evaluation_id` | string / null | 否 | — |  |
| `kind` | `"genome"`, `"executor_model"`, `"decision_model"` | 是 | — |  |
| `mode` | `"offline"`, `"canary"`, `"active"` | 否 | `"offline"` |  |
| `percentage` | integer | 否 | `5` | ≥ 1.0; ≤ 100.0 |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `report_ids` | array&lt;string&gt; | 否 | `[]` | 最多项 100 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `scope` | [ReleaseScope-Input](#releasescope-input) | 否 | — |  |
| `source_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `target_model_id` | string / null | 否 | — |  |

<a id="releaseplancommand-output"></a>
### ReleasePlanCommand-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `baseline_model_id` | string | 是 | `"deepseek-v4-pro"` | 最长 100 |
| `baseline_report_ids` | array&lt;string&gt; | 是 | `[]` | 最多项 100 |
| `decision_evaluation_id` | string / null | 是 | — |  |
| `kind` | `"genome"`, `"executor_model"`, `"decision_model"` | 是 | — |  |
| `mode` | `"offline"`, `"canary"`, `"active"` | 是 | `"offline"` |  |
| `percentage` | integer | 是 | `5` | ≥ 1.0; ≤ 100.0 |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `report_ids` | array&lt;string&gt; | 是 | `[]` | 最多项 100 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `scope` | [ReleaseScope-Output](#releasescope-output) | 是 | — |  |
| `source_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `target_model_id` | string / null | 是 | — |  |

<a id="releaserecord"></a>
### ReleaseRecord

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `affected_run_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `approval_event_id` | string / null | 是 | — |  |
| `command` | [ReleasePlanCommand-Output](#releaseplancommand-output) | 是 | — |  |
| `config_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `created_at` | number | 是 | — |  |
| `current_evidence_valid` | boolean | 是 | `true` |  |
| `effect_version` | integer / null | 是 | — |  |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `observation_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `reason` | string | 是 | `""` |  |
| `report` | [ReleaseEvidence](#releaseevidence) | 是 | — |  |
| `status` | `"blocked"`, `"ready"`, `"approved"`, `"activating"`, `"active"`, `"offline_registered"`, `"paused"`, `"rollback_pending"`, `"rolled_back"`, `"failed"` | 是 | — |  |
| `validation_event_id` | string / null | 是 | — |  |
| `version` | integer | 是 | `0` |  |

<a id="releasescope-input"></a>
### ReleaseScope-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `data_domains` | array&lt;`"public"`, `"local-only"`&gt; | 否 | `["public"]` |  |
| `decision_points` | array&lt;`"information_sufficiency"`, `"executor_tier"`, `"tool_domain"`, `"skill_match"`&gt; | 否 | `[]` |  |
| `domains` | array&lt;string&gt; | 否 | `["general"]` | 最少项 1; 最多项 8 |
| `languages` | array&lt;`"zh"`, `"en"`, `"mixed"`, `"other"`&gt; | 否 | `["zh", "en"]` |  |

<a id="releasescope-output"></a>
### ReleaseScope-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `data_domains` | array&lt;`"public"`, `"local-only"`&gt; | 是 | `["public"]` |  |
| `decision_points` | array&lt;`"information_sufficiency"`, `"executor_tier"`, `"tool_domain"`, `"skill_match"`&gt; | 是 | `[]` |  |
| `domains` | array&lt;string&gt; | 是 | `["general"]` | 最少项 1; 最多项 8 |
| `languages` | array&lt;`"zh"`, `"en"`, `"mixed"`, `"other"`&gt; | 是 | `["zh", "en"]` |  |

<a id="releasestatus"></a>
### ReleaseStatus

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `auto_approval` | `false` | 是 | `false` |  |
| `decision_online_routing` | `"teacher_only"` | 是 | `"teacher_only"` |  |
| `min_independent_families` | integer | 是 | — |  |
| `policy_revision` | string | 是 | — |  |

<a id="releasevalidationrun"></a>
### ReleaseValidationRun

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `acceptance` | [Acceptance-Input](#acceptance-input) | 是 | — |  |
| `data_domain` | `"public"`, `"local-only"` | 否 | `"local-only"` |  |
| `goal` | string | 是 | — | 最短 1; 最长 4000 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="resourcewindow-input"></a>
### ResourceWindow-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `end_hour_utc` | integer | 否 | `24` | ≥ 1.0; ≤ 24.0 |
| `start_hour_utc` | integer | 否 | `0` | ≥ 0.0; ≤ 23.0 |

<a id="resourcewindow-output"></a>
### ResourceWindow-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `end_hour_utc` | integer | 是 | `24` | ≥ 1.0; ≤ 24.0 |
| `start_hour_utc` | integer | 是 | `0` | ≥ 0.0; ≤ 23.0 |

<a id="restorecommand"></a>
### RestoreCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `backup_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `confirm_empty_target` | boolean | 否 | `false` |  |
| `expected_sha256` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |

<a id="reviewcommand-input"></a>
### ReviewCommand-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `assessment_report_id` | string / null | 否 | — |  |
| `expected_run_version` | integer | 是 | — | ≥ 0.0 |
| `judgment_id` | string | 是 | — | 最短 1; 最长 100 |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `public` | boolean | 否 | `false` |  |
| `question_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `run_id` | string | 是 | — | 最短 1; 最长 200 |

<a id="reviewcommand-output"></a>
### ReviewCommand-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `assessment_report_id` | string / null | 是 | — |  |
| `expected_run_version` | integer | 是 | — | ≥ 0.0 |
| `judgment_id` | string | 是 | — | 最短 1; 最长 100 |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `public` | boolean | 是 | `false` |  |
| `question_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `run_id` | string | 是 | — | 最短 1; 最长 200 |

<a id="reviewexport"></a>
### ReviewExport

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | — |  |
| `input` | map&lt;[JsonValue](#jsonvalue)&gt; | 是 | — |  |
| `qualification_signature` | string | 是 | — |  |
| `source_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `target` | map&lt;[JsonValue](#jsonvalue)&gt; | 是 | — |  |
| `verdict` | `"KEEP"` | 是 | `"KEEP"` |  |
| `version` | integer | 是 | — |  |

<a id="reviewoperation-input"></a>
### ReviewOperation-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `command` | [ReviewCommand-Input](#reviewcommand-input) | 是 | — |  |
| `kind` | `"review"` | 是 | — |  |

<a id="reviewoperation-output"></a>
### ReviewOperation-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `command` | [ReviewCommand-Output](#reviewcommand-output) | 是 | — |  |
| `kind` | `"review"` | 是 | — |  |

<a id="reviewrecord"></a>
### ReviewRecord

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `audit_retained` | `true` | 是 | `true` |  |
| `command` | [ReviewCommand-Output](#reviewcommand-output) | 是 | — |  |
| `config_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `evidence_current` | boolean | 是 | `true` |  |
| `human_revisions` | array&lt;[HumanRevision-Output](#humanrevision-output)&gt; | 是 | `[]` |  |
| `id` | string | 是 | — |  |
| `positive_training_eligible` | boolean | 是 | `false` |  |
| `proposed_verdict` | `"KEEP"`, `"DROP"`, `"HOLD"` | 是 | `"HOLD"` |  |
| `qualification_signature` | string / null | 是 | — |  |
| `reason_codes` | array&lt;string&gt; | 是 | `[]` |  |
| `stage_a` | [StageReceipt](#stagereceipt) / null | 是 | — |  |
| `stage_b` | [StageReceipt](#stagereceipt) / null | 是 | — |  |
| `status` | `"pending"`, `"stage_a"`, `"stage_b"`, `"complete"`, `"blocked"` | 是 | `"pending"` |  |
| `subject` | [ReviewSubject](#reviewsubject) | 是 | — |  |
| `verdict` | `"KEEP"`, `"DROP"`, `"HOLD"` | 是 | `"HOLD"` |  |
| `version` | integer | 是 | `0` |  |

<a id="reviewstatus"></a>
### ReviewStatus

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `automatic_admission` | `"requires_human_meta_calibration"` | 是 | `"requires_human_meta_calibration"` |  |
| `config_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `online_adoption` | `"unchanged"` | 是 | `"unchanged"` |  |
| `positive_rule` | `"current_calibrated_adopted_beneficial_KEEP_only"` | 是 | `"current_calibrated_adopted_beneficial_KEEP_only"` |  |
| `reviewer_model` | string | 是 | — |  |
| `rubric_revision` | string | 是 | — |  |

<a id="reviewsubject"></a>
### ReviewSubject

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `actual_fingerprints` | array&lt;string&gt; | 是 | `[]` |  |
| `actual_model_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `after_evidence` | array&lt;[EvidenceFact](#evidencefact)&gt; | 是 | — |  |
| `answer` | [Answer](#answer) | 是 | — |  |
| `assessment_current` | boolean | 是 | `false` |  |
| `assessment_passed` | boolean | 是 | `false` |  |
| `assessment_report_id` | string / null | 是 | — |  |
| `before_evidence` | array&lt;[EvidenceFact](#evidencefact)&gt; | 是 | — |  |
| `blockers` | array&lt;string&gt; | 是 | — |  |
| `causal_link_verified` | boolean | 是 | `false` |  |
| `checkpoint_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `checkpoint_id` | string | 是 | — |  |
| `decision` | [JudgmentResult](#judgmentresult) | 是 | — |  |
| `efficiency_comparison_verified` | boolean | 是 | `false` |  |
| `environment_failure` | boolean | 是 | `false` |  |
| `goal_changed` | boolean | 是 | `false` |  |
| `goal_revision` | integer | 是 | — |  |
| `interaction_group` | string / null | 是 | — |  |
| `request` | [JudgmentRequest](#judgmentrequest) | 是 | — |  |
| `run_version` | integer | 是 | — |  |
| `source` | `"runtime"`, `"test"` | 是 | — |  |
| `source_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |

<a id="revision"></a>
### Revision

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `assets` | array&lt;[AssetRecord](#assetrecord)&gt; | 是 | — |  |
| `candidates` | array&lt;[AssetRecord](#assetrecord)&gt; | 是 | — |  |
| `candidates_revision` | string / null | 是 | — |  |
| `excluded` | map&lt;string&gt; | 是 | — |  |
| `project` | [Project-Output](#project-output) | 是 | — |  |
| `revision` | string / null | 是 | — |  |

<a id="routedecision"></a>
### RouteDecision

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `excluded` | map&lt;string&gt; | 是 | — |  |
| `model_id` | string / null | 是 | — |  |
| `policy_version` | string | 是 | — |  |
| `reason_codes` | array&lt;string&gt; | 是 | `[]` |  |
| `requested_tier` | string / null | 是 | — |  |
| `status` | `"proposed"`, `"blocked"`, `"not_requested"`, `"stale"` | 是 | — |  |

<a id="routerpair"></a>
### RouterPair

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `left_run_id` | string | 是 | — | 最短 1; 最长 200 |
| `right_run_id` | string | 是 | — | 最短 1; 最长 200 |

<a id="runcommand"></a>
### RunCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `action` | `"pause"`, `"cancel"`, `"resume"`, `"approve"`, `"reconcile"`, `"revise"` | 是 | — |  |
| `expected_goal_revision` | integer | 是 | — | ≥ 1.0 |
| `expected_version` | integer / null | 否 | — |  |
| `goal` | string / null | 否 | — |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |

<a id="runframe"></a>
### RunFrame

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `cursor` | integer | 是 | — | ≥ 0 |
| `goal_revision` | integer | 是 | — |  |
| `kind` | `"snapshot"`, `"checkpoint"`, `"delta"`, `"heartbeat"`, `"reset_required"` | 是 | — |  |
| `persisted` | boolean | 是 | — |  |
| `progress` | [TransientProgress](#transientprogress) / null | 是 | `null` |  |
| `reason` | string / null | 是 | `null` |  |
| `run_id` | string | 是 | — |  |
| `schema_version` | `1` | 是 | `1` |  |
| `version` | integer | 是 | — |  |

<a id="runlimits-input"></a>
### RunLimits-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `max_cost_microusd` | integer | 是 | — | ≥ 1.0; ≤ 1000000.0 |
| `max_output_tokens` | integer | 否 | `512` | ≥ 32.0; ≤ 2048.0 |
| `max_steps` | integer | 是 | — | ≥ 1.0; ≤ 100.0 |
| `max_tokens` | integer | 是 | — | ≥ 512.0; ≤ 100000.0 |
| `max_tool_calls` | integer | 是 | — | ≥ 1.0; ≤ 200.0 |

<a id="runlimits-output"></a>
### RunLimits-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `max_cost_microusd` | integer | 是 | — | ≥ 1.0; ≤ 1000000.0 |
| `max_output_tokens` | integer | 是 | `512` | ≥ 32.0; ≤ 2048.0 |
| `max_steps` | integer | 是 | — | ≥ 1.0; ≤ 100.0 |
| `max_tokens` | integer | 是 | — | ≥ 512.0; ≤ 100000.0 |
| `max_tool_calls` | integer | 是 | — | ≥ 1.0; ≤ 200.0 |

<a id="runpage"></a>
### RunPage

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `items` | array&lt;[AgentRun](#agentrun)&gt; | 是 | — |  |
| `next_cursor` | integer / null | 是 | — |  |

<a id="runsnapshot"></a>
### RunSnapshot

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `checkpoint_event_id` | string | 是 | — |  |
| `cursor` | integer | 是 | — |  |
| `run` | [AgentRun](#agentrun) | 是 | — |  |
| `transient` | [TransientProgress](#transientprogress) / null | 是 | — |  |

<a id="schedule"></a>
### Schedule

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `command` | [ScheduleCommand-Output](#schedulecommand-output) | 是 | — |  |
| `config_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `cycle` | integer | 是 | `0` |  |
| `enabled` | boolean | 是 | — |  |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `next_due` | number | 是 | — |  |
| `project_id` | string | 是 | — |  |
| `reason` | string | 是 | `"user_disabled"` |  |
| `version` | integer | 是 | `0` |  |

<a id="schedulecommand-input"></a>
### ScheduleCommand-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `budget_microusd` | integer | 否 | `0` | ≥ 0.0; ≤ 100000000.0 |
| `confirm_background_actions` | boolean | 否 | `false` |  |
| `depends_on` | array&lt;string&gt; | 否 | `[]` | 最多项 8 |
| `enabled` | boolean | 否 | `false` |  |
| `expires_at` | number | 是 | — | > 0.0 |
| `interval_seconds` | integer | 否 | `3600` | ≥ 30.0; ≤ 604800.0 |
| `operation` | [ReviewOperation-Input](#reviewoperation-input) / [DatasetOperation-Input](#datasetoperation-input) / [ExportOperation-Input](#exportoperation-input) / [WithdrawOperation-Input](#withdrawoperation-input) / [TrainingOperation-Input](#trainingoperation-input) / [MaintenanceOperation](#maintenanceoperation) | 是 | — |  |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `repeat` | boolean | 否 | `false` |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `window` | [ResourceWindow-Input](#resourcewindow-input) | 否 | — |  |

<a id="schedulecommand-output"></a>
### ScheduleCommand-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `budget_microusd` | integer | 是 | `0` | ≥ 0.0; ≤ 100000000.0 |
| `confirm_background_actions` | boolean | 是 | `false` |  |
| `depends_on` | array&lt;string&gt; | 是 | `[]` | 最多项 8 |
| `enabled` | boolean | 是 | `false` |  |
| `expires_at` | number | 是 | — | > 0.0 |
| `interval_seconds` | integer | 是 | `3600` | ≥ 30.0; ≤ 604800.0 |
| `operation` | [ReviewOperation-Output](#reviewoperation-output) / [DatasetOperation-Output](#datasetoperation-output) / [ExportOperation-Output](#exportoperation-output) / [WithdrawOperation-Output](#withdrawoperation-output) / [TrainingOperation-Output](#trainingoperation-output) / [MaintenanceOperation](#maintenanceoperation) | 是 | — |  |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `repeat` | boolean | 是 | `false` |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `window` | [ResourceWindow-Output](#resourcewindow-output) | 是 | — |  |

<a id="sectionpatch"></a>
### SectionPatch

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `after` | string | 是 | — | 最短 1; 最长 12000 |
| `before` | string | 是 | — | 最短 1; 最长 12000 |
| `heading` | string | 是 | — | 格式 ^#{1,6} [^\n]{1,100}$ |

<a id="seedcommand"></a>
### SeedCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `expected_revision` | string | 是 | — |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |

<a id="sendmessage"></a>
### SendMessage

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `content` | string | 是 | — | 最短 1; 最长 8000 |
| `request_id` | string | 是 | — | 最短 1; 最长 100 |

<a id="session"></a>
### Session

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `artifacts` | array&lt;[Artifact](#artifact)&gt; | 是 | — |  |
| `created_at` | string | 是 | — |  |
| `goal_id` | string / null | 是 | `null` |  |
| `goal_revision` | integer | 是 | `1` |  |
| `id` | string | 是 | — |  |
| `messages` | array&lt;[Message](#message)&gt; | 是 | — |  |
| `run_id` | string / null | 是 | `null` |  |
| `sequence` | integer | 是 | `0` |  |
| `source` | `"demo"` | 是 | `"demo"` |  |
| `status` | `"idle"`, `"running"`, `"stopping"`, `"stopped"`, `"completed"` | 是 | `"idle"` |  |
| `title` | string | 是 | `"新对话"` |  |

<a id="sessionevent"></a>
### SessionEvent

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `event_id` | string | 是 | — |  |
| `goal_id` | string / null | 是 | — |  |
| `goal_revision` | integer | 是 | — |  |
| `kind` | `"session.updated"` | 是 | `"session.updated"` |  |
| `payload` | [Session](#session) | 是 | — |  |
| `run_id` | string / null | 是 | — |  |
| `schema_version` | `"1"` | 是 | `"1"` |  |
| `sequence` | integer | 是 | — |  |
| `session_id` | string | 是 | — |  |
| `timestamp` | string | 是 | — |  |

<a id="shadowevaluation"></a>
### ShadowEvaluation

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `agent_benefit_verified` | `false` | 是 | `false` |  |
| `live_distribution_verified` | `false` | 是 | `false` |  |
| `predictions` | array&lt;[ShadowPrediction](#shadowprediction)&gt; | 是 | — |  |
| `protocol` | `"decision-shadow-replay-v1"` | 是 | `"decision-shadow-replay-v1"` |  |
| `source` | `"historical_validation_not_live_shadow"` | 是 | `"historical_validation_not_live_shadow"` |  |

<a id="shadowprediction"></a>
### ShadowPrediction

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `adopted` | `false` | 是 | `false` |  |
| `observed_state_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `option_ids` | array&lt;string&gt; | 是 | — |  |
| `point` | string | 是 | — |  |
| `probabilities` | map&lt;number&gt; | 是 | — |  |
| `sample_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `selected_id` | string / null | 是 | — |  |
| `teacher_selected_id` | string / null | 是 | — |  |

<a id="signal"></a>
### Signal

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `critical` | boolean | 是 | `false` |  |
| `evidence` | array&lt;string&gt; | 是 | `[]` |  |
| `name` | string | 是 | — |  |
| `reason` | string | 是 | — |  |
| `source` | `"deterministic"`, `"model-judge"`, `"human"`, `"unverified-self-report"` | 是 | — |  |
| `verdict` | `"pass"`, `"fail"`, `"unknown"` | 是 | — |  |

<a id="singlemulticontrast"></a>
### SingleMultiContrast

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `baseline_calls` | integer | 是 | — |  |
| `baseline_cost_microusd` | integer | 是 | — |  |
| `baseline_outcome` | string | 是 | — |  |
| `baseline_run_id` | string | 是 | — |  |
| `baseline_tokens` | integer | 是 | — |  |
| `comparable` | boolean | 是 | — |  |
| `cost_delta_microusd` | integer | 是 | — |  |
| `evidence_scope` | `"one-paired-workflow-only"` | 是 | `"one-paired-workflow-only"` |  |
| `improvement_established` | `false` | 是 | `false` |  |
| `multi_outcome` | string | 是 | — |  |
| `reasons` | array&lt;string&gt; | 是 | — |  |
| `source` | `"runtime"`, `"test"` | 是 | — |  |
| `supervisor_id` | string | 是 | — |  |
| `worker_calls` | integer | 是 | — |  |
| `worker_cost_microusd` | integer | 是 | — |  |
| `worker_tokens` | integer | 是 | — |  |

<a id="snapshot"></a>
### Snapshot

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `arena_asset_id` | string / null | 是 | — |  |
| `arena_mode` | `"patch"`, `"ablation"` / null | 是 | — |  |
| `assets` | array&lt;[Asset-Output](#asset-output)&gt; | 是 | — |  |
| `id` | string | 是 | — |  |
| `instructions` | string | 是 | — |  |
| `parent_snapshot_id` | string / null | 是 | — |  |
| `project_id` | string | 是 | — |  |
| `purpose` | `"runtime"`, `"optimization_arena"` | 是 | `"runtime"` |  |
| `release_ids` | array&lt;string&gt; | 是 | `[]` |  |
| `revision` | string | 是 | — |  |
| `scope` | `"project"` | 是 | `"project"` |  |
| `untrusted` | `true` | 是 | `true` |  |

<a id="sourcelocation"></a>
### SourceLocation

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | string | 是 | — |  |
| `end_character` | integer | 是 | — |  |
| `source` | string | 是 | — |  |
| `start_character` | integer | 是 | — |  |

<a id="sourceproof"></a>
### SourceProof

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `assessment_report_id` | string / null | 是 | — |  |
| `checkpoint_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `checkpoint_id` | string | 是 | — |  |
| `declared_model` | map&lt;[JsonValue](#jsonvalue)&gt; | 是 | — |  |
| `event_refs` | array&lt;string&gt; | 是 | `[]` |  |
| `goal_revision` | integer | 是 | — |  |
| `input_snapshot_id` | string | 是 | — |  |
| `review_id` | string / null | 是 | — |  |
| `review_version` | integer / null | 是 | — |  |
| `run_id` | string | 是 | — |  |
| `source` | `"runtime"`, `"test"` | 是 | — |  |
| `source_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `version` | integer | 是 | — |  |

<a id="stagereceipt"></a>
### StageReceipt

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `cost_microusd` | integer / null | 是 | `0` |  |
| `dispatch` | `"confirmed"`, `"not_dispatched"`, `"unknown"` | 是 | `"not_dispatched"` |  |
| `evidence_refs` | array&lt;string&gt; | 是 | `[]` |  |
| `fingerprint` | string / null | 是 | — |  |
| `input_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `model_declaration_digest` | string / null | 是 | — |  |
| `reason` | string | 是 | — |  |
| `reported_model` | string / null | 是 | — |  |
| `request_id` | string | 是 | — |  |
| `source` | `"runtime"`, `"test"`, `"unavailable"` | 是 | `"unavailable"` |  |
| `tokens` | integer / null | 是 | `0` |  |
| `verdict` | [Reasonableness](#reasonableness) / [Contribution](#contribution) / null | 是 | — |  |

<a id="stoprun"></a>
### StopRun

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `request_id` | string | 是 | — | 最短 1; 最长 100 |
| `run_id` | string | 是 | — |  |

<a id="storageinfo"></a>
### StorageInfo

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `backend` | `"sqlite"`, `"memory"` | 是 | — |  |
| `durable` | boolean | 是 | — |  |
| `journal_mode` | string | 是 | — |  |
| `ready` | boolean | 是 | — |  |
| `schema_version` | integer | 是 | — |  |
| `sqlite_version` | string / null | 否 | — |  |
| `synchronous` | string | 是 | — |  |

<a id="subjectref-input"></a>
### SubjectRef-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `assessment_report_id` | string / null | 否 | — |  |
| `expected_version` | integer | 是 | — | ≥ 0.0 |
| `family` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `origin_group` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `review_id` | string / null | 否 | — |  |
| `run_id` | string | 是 | — | 最短 1; 最长 200 |
| `split` | `"train"`, `"validation"` | 否 | `"train"` |  |

<a id="subjectref-output"></a>
### SubjectRef-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `assessment_report_id` | string / null | 是 | — |  |
| `expected_version` | integer | 是 | — | ≥ 0.0 |
| `family` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `origin_group` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `review_id` | string / null | 是 | — |  |
| `run_id` | string | 是 | — | 最短 1; 最长 200 |
| `split` | `"train"`, `"validation"` | 是 | `"train"` |  |

<a id="submitproposal"></a>
### SubmitProposal

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `arena_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `direction_reviewed` | boolean | 否 | `false` |  |
| `expected_learning_revision` | string / null | 是 | — |  |
| `expected_version` | integer | 是 | — | ≥ 0.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="taskstate"></a>
### TaskState

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `boundaries` | array&lt;string&gt; | 否 | `[]` | 最多项 20 |
| `delivery` | map&lt;[JsonValue](#jsonvalue)&gt; | 否 | — |  |
| `goal` | string | 是 | — | 最短 1; 最长 4000 |
| `pending` | array&lt;[PendingOperation](#pendingoperation)&gt; | 否 | `[]` | 最多项 200 |

<a id="teacheruse-input"></a>
### TeacherUse-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `declared_revision` | string | 是 | — | 最短 1; 最长 200 |
| `model_id` | string | 是 | — | 最短 1; 最长 200 |
| `terms_reference` | string | 是 | — | 最短 10; 最长 1000 |
| `training_use_confirmed_by_user` | boolean | 否 | `false` |  |

<a id="teacheruse-output"></a>
### TeacherUse-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `declared_revision` | string | 是 | — | 最短 1; 最长 200 |
| `model_id` | string | 是 | — | 最短 1; 最长 200 |
| `terms_reference` | string | 是 | — | 最短 10; 最长 1000 |
| `training_use_confirmed_by_user` | boolean | 是 | `false` |  |

<a id="telemetrysample"></a>
### TelemetrySample

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `causal_benefit_verified` | `false` | 是 | `false` |  |
| `created_at` | number | 是 | — |  |
| `drift_advisory` | boolean | 是 | `false` |  |
| `failed` | integer | 是 | — |  |
| `foreground_active` | integer | 是 | — |  |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `known_cost_microusd` | integer | 是 | — |  |
| `operational_pass_rate` | number / null | 是 | — |  |
| `passed` | integer | 是 | — |  |
| `project_id` | string | 是 | — |  |
| `queue_states` | map&lt;integer&gt; | 是 | — |  |
| `review_backlog` | integer | 是 | — |  |
| `runs` | integer | 是 | — |  |
| `source_counts` | map&lt;integer&gt; | 是 | — |  |
| `training_states` | map&lt;integer&gt; | 是 | — |  |
| `unknown_charges` | integer | 是 | — |  |
| `withdrawn_datasets` | integer | 是 | — |  |

<a id="toolapproval"></a>
### ToolApproval

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `expires_at` | number | 是 | — |  |
| `id` | string | 是 | — |  |
| `operation_id` | string | 是 | — |  |

<a id="toolartifact"></a>
### ToolArtifact

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | — |  |
| `media_type` | `"text/plain"` | 是 | `"text/plain"` |  |
| `path` | string | 是 | — |  |
| `sha256` | string | 是 | — |  |
| `size_bytes` | integer | 是 | — |  |

<a id="toolcall"></a>
### ToolCall

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `arguments` | map&lt;[JsonValue](#jsonvalue)&gt; | 是 | — |  |
| `id` | string | 是 | — |  |
| `name` | string | 是 | — |  |

<a id="toolcheckpoint-input"></a>
### ToolCheckpoint-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `name` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `require_absent_or_null_old_digest` | boolean | 否 | `true` |  |
| `tool` | `"file_write"` | 否 | `"file_write"` |  |

<a id="toolcheckpoint-output"></a>
### ToolCheckpoint-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `name` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `require_absent_or_null_old_digest` | boolean | 是 | `true` |  |
| `tool` | `"file_write"` | 是 | `"file_write"` |  |

<a id="tooldescriptor"></a>
### ToolDescriptor

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `approval_required` | boolean | 是 | — |  |
| `effect` | `"read"`, `"write"`, `"process"` | 是 | — |  |
| `id` | `"file.read"`, `"file.list"`, `"file.write"`, `"process.run"`, `"mcp.sha256"` | 是 | — |  |
| `input_schema` | map&lt;[JsonValue](#jsonvalue)&gt; | 是 | — |  |
| `isolation` | string | 是 | — |  |
| `title` | string | 是 | — |  |

<a id="toolexecutecommand"></a>
### ToolExecuteCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `approval_id` | string / null | 否 | — |  |

<a id="toolplan"></a>
### ToolPlan

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `operation_id` | string | 是 | — |  |
| `policy_version` | string | 是 | — |  |
| `preview` | string | 是 | — |  |
| `request_digest` | string | 是 | — |  |
| `requires_approval` | boolean | 是 | — |  |
| `status` | `"prepared"` | 是 | `"prepared"` |  |
| `title` | string | 是 | — |  |
| `tool` | `"file.read"`, `"file.list"`, `"file.write"`, `"process.run"`, `"mcp.sha256"` | 是 | — |  |
| `workspace_id` | string | 是 | — |  |

<a id="toolpreparecommand"></a>
### ToolPrepareCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `arguments` | map&lt;[JsonValue](#jsonvalue)&gt; | 是 | — |  |
| `operation_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |
| `tool` | `"file.read"`, `"file.list"`, `"file.write"`, `"process.run"`, `"mcp.sha256"` | 是 | — |  |
| `workspace_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="toolreceipt"></a>
### ToolReceipt

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `artifact` | [ToolArtifact](#toolartifact) / null | 是 | — |  |
| `attempt` | integer | 是 | `1` |  |
| `code` | string | 是 | — |  |
| `evidence` | string | 是 | — |  |
| `exit_code` | integer / null | 是 | — |  |
| `operation_id` | string | 是 | — |  |
| `outcome` | `"succeeded"`, `"failed"`, `"unknown"` | 是 | — |  |
| `output` | string | 是 | — |  |
| `reconciled` | boolean | 是 | `false` |  |
| `request_digest` | string | 是 | — |  |
| `source` | `"local"` | 是 | `"local"` |  |
| `tool` | `"file.read"`, `"file.list"`, `"file.write"`, `"process.run"`, `"mcp.sha256"` | 是 | — |  |
| `untrusted` | `true` | 是 | `true` |  |
| `workspace_id` | string | 是 | — |  |

<a id="toolspec"></a>
### ToolSpec

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `description` | string | 是 | `""` | 最长 1000 |
| `name` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,64}$ |
| `parameters` | map&lt;[JsonValue](#jsonvalue)&gt; | 是 | — |  |

<a id="toolworkspacecommand"></a>
### ToolWorkspaceCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `read_only` | boolean | 否 | `true` |  |
| `title` | string | 是 | — | 最短 1; 最长 100 |

<a id="traceedge"></a>
### TraceEdge

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `relation` | `"checkpoint"`, `"input"`, `"decision"`, `"authorization"`, `"receipt"`, `"verification"`, `"parent"` | 是 | — |  |
| `source` | string | 是 | — |  |
| `target` | string | 是 | — |  |

<a id="tracenode"></a>
### TraceNode

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `cursor` | integer | 是 | — |  |
| `details` | map&lt;[JsonValue](#jsonvalue)&gt; | 是 | — |  |
| `event_time` | string | 是 | — |  |
| `goal_revision` | integer | 是 | — |  |
| `id` | string | 是 | — |  |
| `kind` | string | 是 | — |  |
| `late_revision_result` | boolean | 是 | `false` |  |
| `processed_at` | string | 是 | — |  |
| `source` | string | 是 | — |  |

<a id="trainingbundle"></a>
### TrainingBundle

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `activation` | `"offline_candidate"` | 是 | `"offline_candidate"` |  |
| `auxiliary_files` | map&lt;string&gt; | 是 | — |  |
| `files` | map&lt;string&gt; | 是 | — |  |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `job_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `kind` | `"executor"`, `"decision"` | 是 | `"executor"` |  |
| `lineage_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `metrics` | map&lt;[JsonValue](#jsonvalue)&gt; | 是 | — |  |
| `plan_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `project_id` | string | 是 | — |  |
| `quality_release_eligible` | `false` | 是 | `false` |  |
| `release_blockers` | array&lt;string&gt; | 是 | `["independent_deployment_evaluation_required"]` |  |
| `source` | `"runtime"`, `"test"` | 是 | — |  |
| `source_current` | boolean | 是 | `true` |  |
| `version` | integer | 是 | `0` |  |

<a id="trainingcheckpoint"></a>
### TrainingCheckpoint

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `files` | map&lt;string&gt; | 是 | — |  |
| `manifest_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `step` | integer | 是 | — | ≥ 0.0 |

<a id="trainingcontrol"></a>
### TrainingControl

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `action` | `"cancel"`, `"resume"` | 是 | — |  |
| `expected_version` | integer | 是 | — | ≥ 0.0 |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="trainingexample"></a>
### TrainingExample

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `engineering_only` | boolean | 是 | `false` |  |
| `family` | string | 是 | — |  |
| `following_tool_results` | array&lt;[ModelMessage-Output](#modelmessage-output)&gt; | 是 | `[]` |  |
| `group_id` | string | 是 | `""` |  |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `input_fingerprints` | array&lt;string&gt; | 是 | — |  |
| `input_messages` | array&lt;[ModelMessage-Output](#modelmessage-output)&gt; | 是 | `[]` |  |
| `kind` | `"executor"`, `"router"`, `"decision"` | 是 | — |  |
| `lineage_tokens` | array&lt;string&gt; | 是 | `[]` |  |
| `loss_message_indices` | array&lt;integer&gt; | 是 | `[]` |  |
| `normalized_input` | string | 是 | — |  |
| `normalized_target` | string | 是 | — |  |
| `origin_group` | string | 是 | — |  |
| `proofs` | array&lt;[SourceProof](#sourceproof)&gt; | 是 | — |  |
| `split` | `"train"`, `"validation"` | 是 | — |  |
| `structured_input` | map&lt;[JsonValue](#jsonvalue)&gt; | 是 | — |  |
| `structured_target` | map&lt;[JsonValue](#jsonvalue)&gt; | 是 | — |  |
| `target_message` | [ModelMessage-Output](#modelmessage-output) / null | 是 | — |  |
| `tools` | array&lt;[ToolSpec](#toolspec)&gt; | 是 | `[]` |  |

<a id="trainingjob"></a>
### TrainingJob

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `attempt` | integer | 是 | `0` |  |
| `bundle_id` | string / null | 是 | — |  |
| `checkpoint` | [TrainingCheckpoint](#trainingcheckpoint) / null | 是 | — |  |
| `command` | [TrainingJobCommand](#trainingjobcommand) | 是 | — |  |
| `completed_steps` | integer | 是 | `0` |  |
| `created_at` | number | 是 | — |  |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `metrics` | map&lt;[JsonValue](#jsonvalue)&gt; | 是 | — |  |
| `plan_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `project_id` | string | 是 | — |  |
| `reason` | string | 是 | `""` |  |
| `started_at` | number / null | 是 | — |  |
| `status` | `"queued"`, `"running"`, `"succeeded"`, `"failed"`, `"cancelled"`, `"interrupted"`, `"blocked"` | 是 | — |  |
| `version` | integer | 是 | `0` |  |

<a id="trainingjobcommand"></a>
### TrainingJobCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `expected_plan_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `plan_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |

<a id="trainingoperation-input"></a>
### TrainingOperation-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `allow_checkpoint_resume` | boolean | 否 | `false` |  |
| `command` | [TrainingJobCommand](#trainingjobcommand) | 是 | — |  |
| `kind` | `"executor_training"`, `"decision_training"` | 是 | — |  |

<a id="trainingoperation-output"></a>
### TrainingOperation-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `allow_checkpoint_resume` | boolean | 是 | `false` |  |
| `command` | [TrainingJobCommand](#trainingjobcommand) | 是 | — |  |
| `kind` | `"executor_training"`, `"decision_training"` | 是 | — |  |

<a id="trainingplan"></a>
### TrainingPlan

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `activation` | `"candidate_only"` | 是 | `"candidate_only"` |  |
| `base_manifest_digest` | string / null | 是 | — |  |
| `blockers` | array&lt;string&gt; | 是 | `[]` |  |
| `command` | [TrainingPlanCommand-Output](#trainingplancommand-output) | 是 | — |  |
| `config_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `current_evidence_valid` | boolean | 是 | `true` |  |
| `dataset_manifests` | map&lt;string&gt; | 是 | — |  |
| `examples` | map&lt;integer&gt; | 是 | — |  |
| `groups` | map&lt;integer&gt; | 是 | — |  |
| `id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `manifest_digest` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `status` | `"ready"`, `"blocked"` | 是 | `"blocked"` |  |
| `version` | integer | 是 | `0` |  |

<a id="trainingplancommand-input"></a>
### TrainingPlanCommand-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `abstention_threshold` | number | 否 | `0.7` | ≥ 0.5; ≤ 0.99 |
| `additional_train_artifact_ids` | array&lt;string&gt; | 否 | `[]` | 最多项 199 |
| `additional_validation_artifact_ids` | array&lt;string&gt; | 否 | `[]` | 最多项 199 |
| `allow_cross_project_sources` | boolean | 否 | `false` |  |
| `anchor_artifact_id` | string / null | 否 | — |  |
| `base_model_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `engineering_probe` | boolean | 否 | `false` |  |
| `learning_rate` | number | 否 | `0.0001` | > 0.0; ≤ 0.01 |
| `max_sequence_length` | integer | 否 | `2048` | ≥ 64.0; ≤ 32768.0 |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `rank` | integer | 否 | `8` | ≥ 1.0; ≤ 128.0 |
| `replay_artifact_id` | string / null | 否 | — |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `seed` | integer | 否 | `42` | ≥ 0.0; ≤ 2147483647.0 |
| `steps` | integer | 否 | `100` | ≥ 1.0; ≤ 100000.0 |
| `train_artifact_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `validation_artifact_id` | string / null | 否 | — |  |

<a id="trainingplancommand-output"></a>
### TrainingPlanCommand-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `abstention_threshold` | number | 是 | `0.7` | ≥ 0.5; ≤ 0.99 |
| `additional_train_artifact_ids` | array&lt;string&gt; | 是 | `[]` | 最多项 199 |
| `additional_validation_artifact_ids` | array&lt;string&gt; | 是 | `[]` | 最多项 199 |
| `allow_cross_project_sources` | boolean | 是 | `false` |  |
| `anchor_artifact_id` | string / null | 是 | — |  |
| `base_model_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `engineering_probe` | boolean | 是 | `false` |  |
| `learning_rate` | number | 是 | `0.0001` | > 0.0; ≤ 0.01 |
| `max_sequence_length` | integer | 是 | `2048` | ≥ 64.0; ≤ 32768.0 |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `rank` | integer | 是 | `8` | ≥ 1.0; ≤ 128.0 |
| `replay_artifact_id` | string / null | 是 | — |  |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `seed` | integer | 是 | `42` | ≥ 0.0; ≤ 2147483647.0 |
| `steps` | integer | 是 | `100` | ≥ 1.0; ≤ 100000.0 |
| `train_artifact_id` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `validation_artifact_id` | string / null | 是 | — |  |

<a id="trainingstatus"></a>
### TrainingStatus

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `backend` | string | 是 | — |  |
| `configured` | boolean | 是 | — |  |
| `lifecycle` | `"manual_start_candidate_only"` | 是 | `"manual_start_candidate_only"` |  |
| `model_ids` | array&lt;string&gt; | 是 | — |  |
| `worker_protocol` | `"auton-training-worker-v1"` | 是 | `"auton-training-worker-v1"` |  |
| `workload` | `"executor"`, `"decision"` | 是 | `"executor"` |  |

<a id="trajectory"></a>
### Trajectory

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `caught_up` | boolean | 是 | — |  |
| `checkpoint` | [CheckpointReference](#checkpointreference) / null | 是 | — |  |
| `checkpoint_state` | map&lt;[JsonValue](#jsonvalue)&gt; | 是 | — |  |
| `cost_microusd` | integer / null | 是 | — |  |
| `edges` | array&lt;[TraceEdge](#traceedge)&gt; | 是 | — |  |
| `episodes` | array&lt;[EpisodeSummary](#episodesummary)&gt; | 是 | `[]` |  |
| `missing_references` | array&lt;string&gt; | 是 | — |  |
| `nodes` | array&lt;[TraceNode](#tracenode)&gt; | 是 | — |  |
| `processing_cursor` | integer | 是 | — |  |
| `project_id` | string | 是 | — |  |
| `projection_schema` | `2` | 是 | `2` |  |
| `purpose` | `"inspect"`, `"recovery"` | 是 | — |  |
| `recovery_available` | boolean | 是 | — |  |
| `recovery_reasons` | array&lt;string&gt; | 是 | — |  |
| `run_id` | string | 是 | — |  |
| `schema_version` | `1` | 是 | `1` |  |
| `semantic_quality_verified` | `false` | 是 | `false` |  |
| `tokens_used` | integer / null | 是 | — |  |
| `usage_complete` | boolean | 是 | — |  |

<a id="transientprogress"></a>
### TransientProgress

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `goal_revision` | integer | 是 | — |  |
| `persisted` | `false` | 是 | `false` |  |
| `request_id` | string | 是 | — |  |
| `sequence` | integer | 是 | — |  |
| `text` | string | 是 | — |  |
| `version` | integer | 是 | — |  |

<a id="uploadcommand"></a>
### UploadCommand

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `filename` | string | 是 | — | 最短 1; 最长 128; 格式 ^[^/\\\x00-\x1f]+$ |
| `project_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `request_id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,100}$ |
| `sha256` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |
| `size_bytes` | integer | 是 | — | ≥ 1.0; ≤ 1048576.0 |

<a id="uploadintent"></a>
### UploadIntent

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `expires_at` | number | 是 | — |  |
| `filename` | string | 是 | — |  |
| `id` | string | 是 | — |  |
| `project_id` | string | 是 | — |  |
| `receipt` | [UploadReceipt](#uploadreceipt) / null | 是 | — |  |
| `sha256` | string | 是 | — |  |
| `size_bytes` | integer | 是 | — |  |

<a id="uploadreceipt"></a>
### UploadReceipt

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `asset_id` | string | 是 | — |  |
| `candidates_revision` | string / null | 是 | — |  |
| `id` | string | 是 | — |  |
| `project_id` | string | 是 | — |  |
| `sha256` | string | 是 | — |  |
| `size_bytes` | integer | 是 | — |  |
| `status` | `"candidate"` | 是 | `"candidate"` |  |

<a id="usage"></a>
### Usage

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `cost_microusd` | integer | 否 | `0` | ≥ 0.0 |
| `tokens` | integer | 否 | `0` | ≥ 0.0 |
| `tool_calls` | integer | 否 | `0` | ≥ 0.0 |

<a id="versioninfo"></a>
### VersionInfo

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `digest` | string | 是 | — |  |
| `name` | string | 是 | — |  |
| `origin` | string | 是 | — |  |
| `revision` | string | 是 | — |  |
| `status` | string | 是 | — |  |

<a id="windowview"></a>
### WindowView

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `current` | boolean | 是 | — |  |
| `used` | integer | 是 | — |  |
| `window` | [BlindWindow](#blindwindow) | 是 | — |  |

<a id="withdrawoperation-input"></a>
### WithdrawOperation-Input

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `command` | [DatasetWithdrawal-Input](#datasetwithdrawal-input) | 是 | — |  |
| `kind` | `"withdraw"` | 是 | — |  |

<a id="withdrawoperation-output"></a>
### WithdrawOperation-Output

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `command` | [DatasetWithdrawal-Output](#datasetwithdrawal-output) | 是 | — |  |
| `kind` | `"withdraw"` | 是 | — |  |

<a id="workspaceconversation"></a>
### WorkspaceConversation

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | — |  |
| `project_id` | string | 是 | — |  |
| `project_path` | string / null | 是 | — |  |
| `title` | string | 是 | — |  |
| `workspace_id` | string | 是 | — |  |

<a id="workspaceview"></a>
### WorkspaceView

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | — |  |
| `read_only` | boolean | 是 | — |  |
| `revision` | integer | 是 | — |  |
| `title` | string | 是 | — |  |
