# HTTP 路由完整目录

由 `contracts/openapi.json` 生成；所有路径、方法、查询/路径参数、请求类型和响应状态如下。鉴权、写请求头、WebSocket 和 curl 示例见 [API 指南](../api.md)。参数类型详见 [请求/响应参考](api-schemas.md)。

## GET /api/v1/agent/history

Run History

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |
| `after` | query | 否 | integer | 0 | ≥ 0; < 9223372036854775808 |
| `limit` | query | 否 | integer | 10 | ≥ 1; ≤ 20 |
| `search` | query | 否 | string | "" | 最长 100 |

- `200` Successful Response：[RunPage](api-schemas.md#runpage)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/agent/runs

Agent Runs

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[AgentRun](api-schemas.md#agentrun)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/agent/runs

Create Agent Run

请求体 `application/json`：[CreateRun-Input](api-schemas.md#createrun-input)

- `200` Successful Response：[AgentRun](api-schemas.md#agentrun)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/agent/runs/{run_id}

Agent Run

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `run_id` | path | 是 | string | — |  |

- `200` Successful Response：[AgentRun](api-schemas.md#agentrun)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/agent/runs/{run_id}/commands

Agent Command

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `run_id` | path | 是 | string | — |  |

请求体 `application/json`：[RunCommand](api-schemas.md#runcommand)

- `200` Successful Response：[AgentRun](api-schemas.md#agentrun)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/agent/runs/{run_id}/feedback

Run Feedback

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `run_id` | path | 是 | string | — |  |

请求体 `application/json`：[FeedbackCommand](api-schemas.md#feedbackcommand)

- `200` Successful Response：[FeedbackReceipt](api-schemas.md#feedbackreceipt)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/agent/runs/{run_id}/report

Agent Report

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `run_id` | path | 是 | string | — |  |

- `200` Successful Response：object
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/agent/runs/{run_id}/snapshot

Run Snapshot

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `run_id` | path | 是 | string | — |  |

- `200` Successful Response：[RunSnapshot](api-schemas.md#runsnapshot)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/assessment/aggregate

Assessment Aggregate

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：[Aggregate](api-schemas.md#aggregate)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/assessment/bank

Assessment Bank

- `200` Successful Response：[CaseBank](api-schemas.md#casebank)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/assessment/bank

Import Assessment Cases

请求体 `application/json`：[ImportCases](api-schemas.md#importcases)

- `200` Successful Response：[CaseBank](api-schemas.md#casebank)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/assessment/batches

Assessment Batch

请求体 `application/json`：[BatchEvaluation](api-schemas.md#batchevaluation)

- `200` Successful Response：[BatchResult](api-schemas.md#batchresult)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/assessment/calibrations

Assessment Calibrations

- `200` Successful Response：array&lt;[CalibrationReport](api-schemas.md#calibrationreport)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/assessment/calibrations

Calibrate Judge

请求体 `application/json`：[CalibrationCommand](api-schemas.md#calibrationcommand)

- `200` Successful Response：[CalibrationReport](api-schemas.md#calibrationreport)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/assessment/compare

Compare Assessment

请求体 `application/json`：[CompareCommand](api-schemas.md#comparecommand)

- `200` Successful Response：[Comparison](api-schemas.md#comparison)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/assessment/jobs

Evaluate Run

请求体 `application/json`：[EvaluateCommand-Input](api-schemas.md#evaluatecommand-input)

- `200` Successful Response：[EvalJob](api-schemas.md#evaljob)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/assessment/jobs/{job_id}

Assessment Job

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | 是 | string | — |  |

- `200` Successful Response：[EvalJob](api-schemas.md#evaljob)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/assessment/reports

Assessment Reports

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[EvalReport](api-schemas.md#evalreport)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/assessment/reports/{report_id}

Assessment Report

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `report_id` | path | 是 | string | — |  |

- `200` Successful Response：[EvalReport](api-schemas.md#evalreport)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/assessment/seed

Seed Assessment Cases

请求体 `application/json`：[SeedCommand](api-schemas.md#seedcommand)

- `200` Successful Response：[CaseBank](api-schemas.md#casebank)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/assessment/status

Assessment Status

- `200` Successful Response：[AssessmentStatus](api-schemas.md#assessmentstatus)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/assessment/train-cases

Assessment Training Cases

- `200` Successful Response：array&lt;[EvalCase-Output](api-schemas.md#evalcase-output)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/assessment/windows

Assessment Windows

- `200` Successful Response：array&lt;[WindowView](api-schemas.md#windowview)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/assessment/windows

Assessment Window

请求体 `application/json`：[BlindWindowCommand](api-schemas.md#blindwindowcommand)

- `200` Successful Response：[BlindWindow](api-schemas.md#blindwindow)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/bootstrap

Bootstrap

- `200` Successful Response：[BootstrapResponse](api-schemas.md#bootstrapresponse)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/capabilities

Capabilities

- `200` Successful Response：array&lt;object&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/contracts/session-event

Event Contract

- `200` Successful Response：object
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/conversations

Conversations

- `200` Successful Response：array&lt;[WorkspaceConversation](api-schemas.md#workspaceconversation)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/conversations

Create Conversation

请求体 `application/json`：[ConversationCreate](api-schemas.md#conversationcreate)

- `200` Successful Response：[WorkspaceConversation](api-schemas.md#workspaceconversation)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/conversations/{identity}

Conversation View

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `identity` | path | 是 | string | — |  |

- `200` Successful Response：[ConversationView](api-schemas.md#conversationview)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/conversations/{identity}/history-export

Conversation History Export

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `identity` | path | 是 | string | — |  |

- `200` Successful Response：[ConversationHistoryPath](api-schemas.md#conversationhistorypath)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/conversations/{identity}/turns

Conversation Turn

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `identity` | path | 是 | string | — |  |

请求体 `application/json`：[ConversationTurn](api-schemas.md#conversationturn)

- `200` Successful Response：[AgentRun](api-schemas.md#agentrun)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/datasets/artifacts/{artifact_id}

Read Dataset Artifact

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `artifact_id` | path | 是 | string | — |  |

- `200` Successful Response：object
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/datasets/grants

Dataset Grants

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[DataGrant](api-schemas.md#datagrant)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/datasets/grants

Dataset Grant

请求体 `application/json`：[DataGrantCommand-Input](api-schemas.md#datagrantcommand-input)

- `201` Successful Response：[DataGrant](api-schemas.md#datagrant)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/datasets/snapshots

Dataset Snapshots

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[DatasetSnapshot](api-schemas.md#datasetsnapshot)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/datasets/snapshots

Build Dataset

请求体 `application/json`：[DatasetBuild-Input](api-schemas.md#datasetbuild-input)

- `201` Successful Response：[DatasetSnapshot](api-schemas.md#datasetsnapshot)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/datasets/snapshots/{snapshot_id}

Dataset Snapshot

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `snapshot_id` | path | 是 | string | — |  |

- `200` Successful Response：[DatasetSnapshot](api-schemas.md#datasetsnapshot)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/datasets/snapshots/{snapshot_id}/exports

Export Dataset

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `snapshot_id` | path | 是 | string | — |  |

请求体 `application/json`：[ExportCommand-Input](api-schemas.md#exportcommand-input)

- `201` Successful Response：[DatasetArtifact](api-schemas.md#datasetartifact)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/datasets/status

Dataset Status

- `200` Successful Response：[DatasetStatus](api-schemas.md#datasetstatus)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/datasets/withdrawals

Withdraw Dataset Source

请求体 `application/json`：[DatasetWithdrawal-Input](api-schemas.md#datasetwithdrawal-input)

- `200` Successful Response：array&lt;string&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/decision-review/calibrations

Decision Review Calibrations

- `200` Successful Response：array&lt;[CalibrationView](api-schemas.md#calibrationview)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/decision-review/eligible

Decision Review Eligible

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[ReviewExport](api-schemas.md#reviewexport)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/decision-review/jobs

Review Decision

请求体 `application/json`：[ReviewCommand-Input](api-schemas.md#reviewcommand-input)

- `201` Successful Response：[ReviewRecord](api-schemas.md#reviewrecord)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/decision-review/meta

Decision Review Meta

请求体 `application/json`：[MetaCaseCommand](api-schemas.md#metacasecommand)

- `200` Successful Response：[CalibrationView](api-schemas.md#calibrationview)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/decision-review/reviews

Decision Reviews

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[ReviewRecord](api-schemas.md#reviewrecord)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/decision-review/reviews/{review_id}

Decision Review

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `review_id` | path | 是 | string | — |  |

- `200` Successful Response：[ReviewRecord](api-schemas.md#reviewrecord)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/decision-review/reviews/{review_id}/revisions

Revise Decision Review

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `review_id` | path | 是 | string | — |  |

请求体 `application/json`：[HumanRevision-Input](api-schemas.md#humanrevision-input)

- `200` Successful Response：[ReviewRecord](api-schemas.md#reviewrecord)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/decision-review/status

Decision Review Status

- `200` Successful Response：[ReviewStatus](api-schemas.md#reviewstatus)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/decision-training/bundles

Decision Training Bundles

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[TrainingBundle](api-schemas.md#trainingbundle)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/decision-training/bundles/{bundle_id}/shadow-replay

Decision Training Shadow

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `bundle_id` | path | 是 | string | — |  |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：[ShadowEvaluation](api-schemas.md#shadowevaluation)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/decision-training/evaluations

Decision Training Evaluations

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[DecisionEvaluation](api-schemas.md#decisionevaluation)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/decision-training/evaluations

Decision Training Evaluate

请求体 `application/json`：[DecisionEvaluationCommand-Input](api-schemas.md#decisionevaluationcommand-input)

- `201` Successful Response：[DecisionEvaluation](api-schemas.md#decisionevaluation)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/decision-training/jobs

Decision Training Jobs

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[TrainingJob](api-schemas.md#trainingjob)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/decision-training/jobs

Decision Training Create

请求体 `application/json`：[TrainingJobCommand](api-schemas.md#trainingjobcommand)

- `201` Successful Response：[TrainingJob](api-schemas.md#trainingjob)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/decision-training/jobs/{job_id}

Decision Training Job

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | 是 | string | — |  |

- `200` Successful Response：[TrainingJob](api-schemas.md#trainingjob)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/decision-training/jobs/{job_id}/commands

Decision Training Control

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | 是 | string | — |  |

请求体 `application/json`：[TrainingControl](api-schemas.md#trainingcontrol)

- `200` Successful Response：[TrainingJob](api-schemas.md#trainingjob)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/decision-training/plans

Decision Training Plans

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[TrainingPlan](api-schemas.md#trainingplan)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/decision-training/plans

Decision Training Plan

请求体 `application/json`：[TrainingPlanCommand-Input](api-schemas.md#trainingplancommand-input)

- `201` Successful Response：[TrainingPlan](api-schemas.md#trainingplan)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/decision-training/status

Decision Training Status

- `200` Successful Response：[TrainingStatus](api-schemas.md#trainingstatus)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/delegation

List Supervisors

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[DelegationView](api-schemas.md#delegationview)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/delegation

Create Supervisor

请求体 `application/json`：[DelegationCreate-Input](api-schemas.md#delegationcreate-input)

- `201` Successful Response：[DelegationView](api-schemas.md#delegationview)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/delegation/status

Supervisor Status

- `200` Successful Response：[DelegationStatus](api-schemas.md#delegationstatus)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/delegation/{parent_id}

Get Supervisor

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `parent_id` | path | 是 | string | — |  |

- `200` Successful Response：[DelegationView](api-schemas.md#delegationview)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/delegation/{parent_id}/commands

Control Supervisor

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `parent_id` | path | 是 | string | — |  |

请求体 `application/json`：[DelegationCommand](api-schemas.md#delegationcommand)

- `200` Successful Response：[DelegationView](api-schemas.md#delegationview)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/delegation/{parent_id}/contrast

Contrast Supervisor

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `parent_id` | path | 是 | string | — |  |

请求体 `application/json`：[ContrastCommand](api-schemas.md#contrastcommand)

- `200` Successful Response：[SingleMultiContrast](api-schemas.md#singlemulticontrast)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/evolution/arenas

Evolution Arenas

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[ArenaView](api-schemas.md#arenaview)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/evolution/arenas

Evolution Create Arena

请求体 `application/json`：[ArenaCommand-Input](api-schemas.md#arenacommand-input)

- `201` Successful Response：[ArenaView](api-schemas.md#arenaview)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/evolution/arenas/{arena_id}

Evolution Arena

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `arena_id` | path | 是 | string | — |  |

- `200` Successful Response：[ArenaView](api-schemas.md#arenaview)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/evolution/arenas/{arena_id}/commands

Evolution Control

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `arena_id` | path | 是 | string | — |  |

请求体 `application/json`：[ArenaControl](api-schemas.md#arenacontrol)

- `200` Successful Response：[ArenaView](api-schemas.md#arenaview)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/evolution/diagnoses

Evolution Diagnose

请求体 `application/json`：[DiagnoseCommand](api-schemas.md#diagnosecommand)

- `200` Successful Response：[Diagnosis](api-schemas.md#diagnosis)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/evolution/generations

Evolution Generations

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[GenerationRecord](api-schemas.md#generationrecord)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/evolution/playbook

Evolution Playbook

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[PlaybookEntry](api-schemas.md#playbookentry)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/evolution/proposals

Evolution Proposals

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[Proposal](api-schemas.md#proposal)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/evolution/proposals

Evolution Propose

请求体 `application/json`：[ProposalCommand](api-schemas.md#proposalcommand)

- `201` Successful Response：[Proposal](api-schemas.md#proposal)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/evolution/proposals/{proposal_id}

Evolution Proposal

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `proposal_id` | path | 是 | string | — |  |

- `200` Successful Response：[Proposal](api-schemas.md#proposal)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/evolution/proposals/{proposal_id}/submit

Evolution Submit

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `proposal_id` | path | 是 | string | — |  |

请求体 `application/json`：[SubmitProposal](api-schemas.md#submitproposal)

- `200` Successful Response：[Proposal](api-schemas.md#proposal)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/evolution/reflections

Evolution Reflect

请求体 `application/json`：[ReflectCommand-Input](api-schemas.md#reflectcommand-input)

- `201` Successful Response：[Proposal](api-schemas.md#proposal)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/evolution/status

Evolution Status

- `200` Successful Response：[EvolutionStatus](api-schemas.md#evolutionstatus)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/health

Health

- `200` Successful Response：[HealthResponse](api-schemas.md#healthresponse)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/identity/adopt-legacy

Adopt Legacy Identity

请求体 `application/json`：[LegacyIdentityCommand](api-schemas.md#legacyidentitycommand)

- `200` Successful Response：[IdentityInfo](api-schemas.md#identityinfo)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/identity/reset

Reset Identity

请求体 `application/json`：[ModelProbe](api-schemas.md#modelprobe)

- `200` Successful Response：[IdentityInfo](api-schemas.md#identityinfo)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/judgment

Judgment Info

- `200` Successful Response：[JudgmentInfo](api-schemas.md#judgmentinfo)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/judgment/preview

Judgment Preview

请求体 `application/json`：[JudgmentPreview](api-schemas.md#judgmentpreview)

- `200` Successful Response：[JudgmentResult](api-schemas.md#judgmentresult)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/learning

Learning Status

- `200` Successful Response：[LearningStatus](api-schemas.md#learningstatus)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/learning/cases/{identity}/retry

Learning Retry

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `identity` | path | 是 | string | — |  |

请求体 `application/json`：[LearningRetry](api-schemas.md#learningretry)

- `200` Successful Response：[LearningCase](api-schemas.md#learningcase)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/learning/manifest

Learning Manifest

- `200` Successful Response：[LearningManifest](api-schemas.md#learningmanifest)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## PUT /api/v1/learning/policy

Learning Policy

请求体 `application/json`：[LearningPolicyCommand-Input](api-schemas.md#learningpolicycommand-input)

- `200` Successful Response：[LearningPolicy](api-schemas.md#learningpolicy)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/learning/tick

Learning Tick

- `200` Successful Response：[LearningStatus](api-schemas.md#learningstatus)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/local/directories

Local Directories

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `path` | query | 否 | string / null | — |  |

- `200` Successful Response：[LocalDirectories](api-schemas.md#localdirectories)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/models

Models

- `200` Successful Response：array&lt;[ModelInfo](api-schemas.md#modelinfo)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/models/{model_id}/probe

Probe Model

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `model_id` | path | 是 | string | — |  |

请求体 `application/json`：[ModelProbe](api-schemas.md#modelprobe)

- `200` Successful Response：[ModelResult](api-schemas.md#modelresult)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/operations/alerts

Operations Alerts

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[OperationsAlert](api-schemas.md#operationsalert)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/operations/backups

Operations Backup

请求体 `application/json`：[BackupCommand](api-schemas.md#backupcommand)

- `201` Successful Response：[BackupManifest](api-schemas.md#backupmanifest)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/operations/control

Operations Control

请求体 `application/json`：[OwnerPause](api-schemas.md#ownerpause)

- `200` Successful Response：boolean
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/operations/jobs

Operations Jobs

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[BackgroundJob](api-schemas.md#backgroundjob)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/operations/jobs/{job_id}/commands

Operations Job Control

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | 是 | string | — |  |

请求体 `application/json`：[OperationsControl](api-schemas.md#operationscontrol)

- `200` Successful Response：[BackgroundJob](api-schemas.md#backgroundjob)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/operations/restores

Operations Restore

请求体 `application/json`：[RestoreCommand](api-schemas.md#restorecommand)

- `200` Successful Response：[BackupManifest](api-schemas.md#backupmanifest)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/operations/samples

Operations Samples

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[TelemetrySample](api-schemas.md#telemetrysample)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/operations/schedules

Operations Schedules

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[Schedule](api-schemas.md#schedule)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/operations/schedules

Operations Schedule

请求体 `application/json`：[ScheduleCommand-Input](api-schemas.md#schedulecommand-input)

- `201` Successful Response：[Schedule](api-schemas.md#schedule)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/operations/schedules/{schedule_id}/commands

Operations Schedule Control

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `schedule_id` | path | 是 | string | — |  |

请求体 `application/json`：[OperationsControl](api-schemas.md#operationscontrol)

- `200` Successful Response：[Schedule](api-schemas.md#schedule)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/operations/status

Operations Status

- `200` Successful Response：[OperationsStatus](api-schemas.md#operationsstatus)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/operations/tick

Operations Tick

- `200` Successful Response：array&lt;[BackgroundJob](api-schemas.md#backgroundjob)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/policy

Public Policy

- `200` Successful Response：[PublicPolicy](api-schemas.md#publicpolicy)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/policy/preview

Preview Policy

请求体 `application/json`：[ActionRequest](api-schemas.md#actionrequest)

- `200` Successful Response：[PolicyDecision](api-schemas.md#policydecision)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/policy/revisions

Revise Policy

请求体 `application/json`：[PolicyRevision](api-schemas.md#policyrevision)

- `200` Successful Response：[PublicPolicy](api-schemas.md#publicpolicy)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/projects

Projects

- `200` Successful Response：array&lt;[Project-Output](api-schemas.md#project-output)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/projects

Create Project

请求体 `application/json`：[Project-Input](api-schemas.md#project-input)

- `201` Successful Response：[Revision](api-schemas.md#revision)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/projects/{project_id}/assets

Asset Catalog

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | 是 | string | — |  |

- `200` Successful Response：[Revision](api-schemas.md#revision)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/projects/{project_id}/assets/{asset_id}/diff

Asset Diff

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | 是 | string | — |  |
| `asset_id` | path | 是 | string | — |  |
| `revision` | query | 是 | string | — |  |

- `200` Successful Response：string
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/projects/{project_id}/assets/{asset_id}/history

Asset History

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | 是 | string | — |  |
| `asset_id` | path | 是 | string | — |  |

- `200` Successful Response：array&lt;[VersionInfo](api-schemas.md#versioninfo)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/projects/{project_id}/assets/{asset_id}/promote

Promote Asset

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | 是 | string | — |  |
| `asset_id` | path | 是 | string | — |  |

请求体 `application/json`：[AssetPublishCommand](api-schemas.md#assetpublishcommand)

- `200` Successful Response：[Revision](api-schemas.md#revision)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/projects/{project_id}/assets/{asset_id}/revoke

Revoke Asset

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | 是 | string | — |  |
| `asset_id` | path | 是 | string | — |  |

请求体 `application/json`：[AssetRevisionCommand](api-schemas.md#assetrevisioncommand)

- `200` Successful Response：[Revision](api-schemas.md#revision)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/projects/{project_id}/assets/{asset_id}/rollback

Rollback Asset

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | 是 | string | — |  |
| `asset_id` | path | 是 | string | — |  |

请求体 `application/json`：[AssetRevisionCommand](api-schemas.md#assetrevisioncommand)

- `200` Successful Response：[Revision](api-schemas.md#revision)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/projects/{project_id}/candidates

Propose Asset

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | 是 | string | — |  |

请求体 `application/json`：[AssetProposalCommand](api-schemas.md#assetproposalcommand)

- `200` Successful Response：[Revision](api-schemas.md#revision)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/projects/{project_id}/context

Prepare Context

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | 是 | string | — |  |

请求体 `application/json`：[ContextPreviewCommand](api-schemas.md#contextpreviewcommand)

- `200` Successful Response：[ContextSnapshot](api-schemas.md#contextsnapshot)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/projects/{project_id}/context/{snapshot_id}

Get Context

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | 是 | string | — |  |
| `snapshot_id` | path | 是 | string | — |  |

- `200` Successful Response：[ContextSnapshot](api-schemas.md#contextsnapshot)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/projects/{project_id}/runs/{run_id}/recover

Recover

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | 是 | string | — |  |
| `run_id` | path | 是 | string | — |  |

请求体 `application/json`：[RecoveryCommand](api-schemas.md#recoverycommand)

- `200` Successful Response：[AgentRun](api-schemas.md#agentrun)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/projects/{project_id}/runs/{run_id}/trajectory

Trajectory

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | 是 | string | — |  |
| `run_id` | path | 是 | string | — |  |
| `purpose` | query | 否 | `"inspect"`, `"recovery"` | "inspect" |  |

- `200` Successful Response：[Trajectory](api-schemas.md#trajectory)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/projects/{project_id}/snapshots

Resolve Assets

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | 是 | string | — |  |

- `200` Successful Response：[Snapshot](api-schemas.md#snapshot)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/projects/{project_id}/snapshots/{snapshot_id}

Get Asset Snapshot

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | path | 是 | string | — |  |
| `snapshot_id` | path | 是 | string | — |  |

- `200` Successful Response：[Snapshot](api-schemas.md#snapshot)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/releases

Releases

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[ReleaseRecord](api-schemas.md#releaserecord)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/releases

Release Plan

请求体 `application/json`：[ReleasePlanCommand-Input](api-schemas.md#releaseplancommand-input)

- `201` Successful Response：[ReleaseRecord](api-schemas.md#releaserecord)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/releases/status

Release Status

- `200` Successful Response：[ReleaseStatus](api-schemas.md#releasestatus)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/releases/{release_id}

Release Get

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `release_id` | path | 是 | string | — |  |

- `200` Successful Response：[ReleaseRecord](api-schemas.md#releaserecord)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/releases/{release_id}/approvals

Release Approve

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `release_id` | path | 是 | string | — |  |

请求体 `application/json`：[ReleaseApproval](api-schemas.md#releaseapproval)

- `200` Successful Response：[ReleaseRecord](api-schemas.md#releaserecord)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/releases/{release_id}/commands

Release Control

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `release_id` | path | 是 | string | — |  |

请求体 `application/json`：[ReleaseControl](api-schemas.md#releasecontrol)

- `200` Successful Response：[ReleaseRecord](api-schemas.md#releaserecord)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/releases/{release_id}/observations

Release Observe

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `release_id` | path | 是 | string | — |  |

请求体 `application/json`：[ReleaseObservation](api-schemas.md#releaseobservation)

- `200` Successful Response：[ReleaseRecord](api-schemas.md#releaserecord)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/releases/{release_id}/validation

Release Validate

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `release_id` | path | 是 | string | — |  |

- `200` Successful Response：[ReleaseRecord](api-schemas.md#releaserecord)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/releases/{release_id}/validation/runs

Release Validation Run

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `release_id` | path | 是 | string | — |  |

请求体 `application/json`：[ReleaseValidationRun](api-schemas.md#releasevalidationrun)

- `201` Successful Response：[AgentRun](api-schemas.md#agentrun)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/sessions

Sessions

- `200` Successful Response：array&lt;[Session](api-schemas.md#session)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/sessions

Create Session

请求体 `application/json`：[CreateSession](api-schemas.md#createsession)

- `201` Successful Response：[Session](api-schemas.md#session)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/sessions/{session_id}

Get Session

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `session_id` | path | 是 | string | — |  |

- `200` Successful Response：[Session](api-schemas.md#session)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/sessions/{session_id}/messages

Send

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `session_id` | path | 是 | string | — |  |

请求体 `application/json`：[SendMessage](api-schemas.md#sendmessage)

- `202` Successful Response：[Session](api-schemas.md#session)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/sessions/{session_id}/stop

Stop

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `session_id` | path | 是 | string | — |  |

请求体 `application/json`：[StopRun](api-schemas.md#stoprun)

- `200` Successful Response：[Session](api-schemas.md#session)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/tools

Tools Catalog

- `200` Successful Response：array&lt;[ToolDescriptor](api-schemas.md#tooldescriptor)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/tools/operations

Prepare Tool

请求体 `application/json`：[ToolPrepareCommand](api-schemas.md#toolpreparecommand)

- `200` Successful Response：[ToolPlan](api-schemas.md#toolplan)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/tools/operations/{operation_id}

Tool Receipt

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `operation_id` | path | 是 | string | — |  |

- `200` Successful Response：[ToolReceipt](api-schemas.md#toolreceipt)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/tools/operations/{operation_id}/approve

Approve Tool

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `operation_id` | path | 是 | string | — |  |

- `200` Successful Response：[ToolApproval](api-schemas.md#toolapproval)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/tools/operations/{operation_id}/artifact

Tool Artifact

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `operation_id` | path | 是 | string | — |  |

- `200` Successful Response：object
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/tools/operations/{operation_id}/execute

Execute Tool

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `operation_id` | path | 是 | string | — |  |

请求体 `application/json`：[ToolExecuteCommand](api-schemas.md#toolexecutecommand)

- `200` Successful Response：[ToolReceipt](api-schemas.md#toolreceipt)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/tools/operations/{operation_id}/reconcile

Reconcile Tool

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `operation_id` | path | 是 | string | — |  |

- `200` Successful Response：[ToolReceipt](api-schemas.md#toolreceipt)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/tools/workspaces

Tool Workspaces

- `200` Successful Response：array&lt;[WorkspaceView](api-schemas.md#workspaceview)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/tools/workspaces

Create Tool Workspace

请求体 `application/json`：[ToolWorkspaceCommand](api-schemas.md#toolworkspacecommand)

- `201` Successful Response：[WorkspaceView](api-schemas.md#workspaceview)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/training/bundles

Training Bundles

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[TrainingBundle](api-schemas.md#trainingbundle)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/training/jobs

Training Jobs

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[TrainingJob](api-schemas.md#trainingjob)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/training/jobs

Training Create

请求体 `application/json`：[TrainingJobCommand](api-schemas.md#trainingjobcommand)

- `201` Successful Response：[TrainingJob](api-schemas.md#trainingjob)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/training/jobs/{job_id}

Training Job

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | 是 | string | — |  |

- `200` Successful Response：[TrainingJob](api-schemas.md#trainingjob)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/training/jobs/{job_id}/commands

Training Control

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | 是 | string | — |  |

请求体 `application/json`：[TrainingControl](api-schemas.md#trainingcontrol)

- `200` Successful Response：[TrainingJob](api-schemas.md#trainingjob)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/training/plans

Training Plans

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `project_id` | query | 是 | string | — |  |

- `200` Successful Response：array&lt;[TrainingPlan](api-schemas.md#trainingplan)&gt;
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/training/plans

Training Plan

请求体 `application/json`：[TrainingPlanCommand-Input](api-schemas.md#trainingplancommand-input)

- `201` Successful Response：[TrainingPlan](api-schemas.md#trainingplan)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## GET /api/v1/training/status

Training Status

- `200` Successful Response：[TrainingStatus](api-schemas.md#trainingstatus)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/uploads

Prepare Upload

请求体 `application/json`：[UploadCommand](api-schemas.md#uploadcommand)

- `200` Successful Response：[UploadIntent](api-schemas.md#uploadintent)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)

## POST /api/v1/uploads/{upload_id}/content

Complete Upload

| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- | --- | --- |
| `upload_id` | path | 是 | string | — |  |

请求体 `application/octet-stream`：string

- `200` Successful Response：[UploadReceipt](api-schemas.md#uploadreceipt)
- `401` Unauthorized：[ErrorBody](api-schemas.md#errorbody)
- `403` Forbidden：[ErrorBody](api-schemas.md#errorbody)
- `404` Not Found：[ErrorBody](api-schemas.md#errorbody)
- `409` Conflict：[ErrorBody](api-schemas.md#errorbody)
- `410` Gone：[ErrorBody](api-schemas.md#errorbody)
- `413` Request Entity Too Large：[ErrorBody](api-schemas.md#errorbody)
- `422` Unprocessable Entity：[ErrorBody](api-schemas.md#errorbody)
- `429` Too Many Requests：[ErrorBody](api-schemas.md#errorbody)
- `501` Not Implemented：[ErrorBody](api-schemas.md#errorbody)
- `503` Service Unavailable：[ErrorBody](api-schemas.md#errorbody)
