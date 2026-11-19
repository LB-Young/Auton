# 配置参数完整参考

由 `scripts/export_user_docs.py` 从 ApplicationConfig 生成。不要手改参数表；使用说明见 [配置指南](../configuration.md)。默认值来自代码，不读取 .env、环境密钥或本机硬件。

配置文件为 TOML。根字段对应 ApplicationConfig；模块字段置于同名 `[module]` 表。数组对象使用 `[[module.field]]`；下方类型链接列出嵌套对象。数字约束与跨字段校验同时生效，见配置指南。

<a id="applicationconfig"></a>
### ApplicationConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `operations` | [OperationsConfig](#operationsconfig) | 否 | 见对应类型字段 |  |
| `release` | [ReleaseConfig](#releaseconfig) | 否 | 见对应类型字段 |  |
| `decision_training` | [DecisionTrainingConfig](#decisiontrainingconfig) | 否 | 见对应类型字段 |  |
| `training` | [TrainingConfig](#trainingconfig) | 否 | 见对应类型字段 |  |
| `datasets` | [DatasetConfig](#datasetconfig) | 否 | 见对应类型字段 |  |
| `decision_review` | [DecisionReviewConfig](#decisionreviewconfig) | 否 | 见对应类型字段 |  |
| `evolve` | [EvolutionConfig](#evolutionconfig) | 否 | 见对应类型字段 |  |
| `delegation` | [DelegationConfig](#delegationconfig) | 否 | 见对应类型字段 |  |
| `assess` | [AssessConfig](#assessconfig) | 否 | 见对应类型字段 |  |
| `server` | [ServerSettings](#serversettings) | 否 | 见对应类型字段 |  |
| `experience` | [ExperienceConfig](#experienceconfig) | 否 | 见对应类型字段 |  |
| `agent` | [AgentConfig](#agentconfig) | 否 | 见对应类型字段 |  |
| `constitution` | [ConstitutionConfig](#constitutionconfig) | 否 | 见对应类型字段 |  |
| `context` | [ContextConfig](#contextconfig) | 否 | 见对应类型字段 |  |
| `genome` | [GenomeConfig](#genomeconfig) | 否 | 见对应类型字段 |  |
| `tools` | [ToolConfig](#toolconfig) | 否 | 见对应类型字段 |  |
| `judgment` | [JudgmentConfig](#judgmentconfig) | 否 | 见对应类型字段 |  |
| `models` | [ModelConfig](#modelconfig) | 否 | 见对应类型字段 |  |
| `kernel` | [KernelConfig](#kernelconfig) | 否 | 见对应类型字段 |  |
| `profile` | `"demo"`, `"test"`, `"dev"`, `"production"` | 否 | `"demo"` |  |
| `implementation` | string | 否 | `"scripted"` |  |
| `chunk_delay_seconds` | number | 否 | `0.035` | ≥ 0; ≤ 2 |
| `allowed_origins` | array&lt;string&gt; | 否 | `["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8000", "http://localhost:8000"]` |  |

<a id="agentconfig"></a>
### AgentConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `judgment_wait_seconds` | number | 否 | `120.0` | ≥ 1; ≤ 180 |
| `max_steps` | integer | 否 | `8` | ≥ 1; ≤ 20 |
| `max_tokens` | integer | 否 | `16000` | ≥ 512; ≤ 100000 |
| `max_cost_microusd` | integer | 否 | `10000` | ≥ 1; ≤ 1000000 |
| `max_tool_calls` | integer | 否 | `8` | ≥ 1; ≤ 30 |
| `max_active_runs` | integer | 否 | `2` | ≥ 1; ≤ 4 |
| `max_output_tokens` | integer | 否 | `512` | ≥ 32; ≤ 1024 |
| `directory` | string | 否 | `".auton_local/agent"` |  |

<a id="assessconfig"></a>
### AssessConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `directory` | string | 否 | `".auton_local/assess"` | 类型格式 path |
| `judge_model` | string | 否 | `"deepseek-v4-pro"` |  |
| `rubric_revision` | `"assess-rubric-v1"` | 否 | `"assess-rubric-v1"` |  |
| `min_calibration_samples` | integer | 否 | `30` | ≥ 30; ≤ 1000 |
| `min_calibration_lower` | number | 否 | `0.8` | ≥ 0.8; ≤ 1 |
| `max_cases` | integer | 否 | `500` | ≥ 1; ≤ 10000 |
| `max_documents` | integer | 否 | `10000` | ≥ 100; ≤ 100000 |
| `max_active_jobs` | integer | 否 | `2` | ≥ 1; ≤ 4 |
| `max_window_uses` | integer | 否 | `1` | ≥ 1; ≤ 3 |
| `max_calibration_calls` | integer | 否 | `128` | ≥ 60; ≤ 2048 |
| `checker_revision` | `"deterministic-checks-v2"` | 否 | `"deterministic-checks-v2"` |  |
| `statistics_revision` | `"family-wilson-kappa-v1"` | 否 | `"family-wilson-kappa-v1"` |  |

<a id="basemodelspec"></a>
### BaseModelSpec

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | — | 格式 ^[a-zA-Z0-9_-]{1,80}$ |
| `directory` | string | 是 | — | 类型格式 path |
| `architecture` | `"causal_lm"`, `"encoder_choice"` | 否 | `"causal_lm"` |  |
| `repository` | string | 是 | — | 最短 1; 最长 200 |
| `revision` | string | 是 | — | 格式 ^[a-f0-9]{40}$ |
| `license_reference` | string | 是 | — | 最短 10; 最长 1000 |
| `files` | map&lt;string&gt; | 是 | — | 最少属性 2; 最多属性 100 |
| `tool_parser` | `"tagged_json"`, `"json"` | 否 | `"tagged_json"` |  |
| `template_sha256` | string | 是 | — | 格式 ^[a-f0-9]{64}$ |

<a id="constitutionconfig"></a>
### ConstitutionConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `allowed_actions` | array&lt;`"demo.start"`, `"demo.stop"`, `"model.generate"`, `"judgment.evaluate"`, `"tool.read"`, `"tool.write"`, `"dataset.read"`, `"model.train"`, `"asset.read"`, `"asset.publish"`, `"asset.propose"`, `"release.activate"`&gt; | 否 | `["demo.start", "demo.stop", "model.generate", "judgment.evaluate", "tool.read", "tool.write", "dataset.read", "model.train", "asset.read", "asset.publish", "asset.propose", "release.activate"]` |  |
| `remote_providers` | array&lt;`"deepseek"`, `"typesafe"`&gt; | 否 | `[]` |  |
| `approval_actions` | array&lt;`"demo.start"`, `"demo.stop"`, `"model.generate"`, `"judgment.evaluate"`, `"tool.read"`, `"tool.write"`, `"dataset.read"`, `"model.train"`, `"asset.read"`, `"asset.publish"`, `"asset.propose"`, `"release.activate"`&gt; | 否 | `["tool.write", "release.activate"]` |  |
| `autonomy_max` | integer | 否 | `1` | ≥ 0; ≤ 3 |
| `budget` | [Usage](#usage) | 否 | `{"tokens": 100000, "cost_microusd": 5000000, "tool_calls": 100}` |  |
| `max_concurrent` | integer | 否 | `4` | ≥ 1; ≤ 32 |
| `authorization_ttl_seconds` | integer | 否 | `300` | ≥ 1; ≤ 3600 |

<a id="contextconfig"></a>
### ContextConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `tokenizer_directory` | string | 否 | `"weights/context-tokenizers"` | 类型格式 path |
| `max_evidence` | integer | 否 | `6` | ≥ 0; ≤ 12 |
| `chunk_characters` | integer | 否 | `1800` | ≥ 200; ≤ 4000 |
| `hosted_overhead_tokens` | integer | 否 | `512` | ≥ 256; ≤ 2048 |

<a id="datasetconfig"></a>
### DatasetConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `directory` | string | 否 | `".auton_local/datasets"` | 类型格式 path |
| `max_documents` | integer | 否 | `10000` | ≥ 100; ≤ 100000 |
| `max_sources` | integer | 否 | `100` | ≥ 1; ≤ 200 |
| `max_examples` | integer | 否 | `1000` | ≥ 1; ≤ 5000 |
| `max_example_bytes` | integer | 否 | `64000` | ≥ 2000; ≤ 256000 |
| `max_snapshot_bytes` | integer | 否 | `16000000` | ≥ 10000; ≤ 64000000 |
| `max_export_bytes` | integer | 否 | `8000000` | ≥ 10000; ≤ 32000000 |
| `source_revision` | `"trajectory-datasets-v1"` | 否 | `"trajectory-datasets-v1"` |  |

<a id="decisionreviewconfig"></a>
### DecisionReviewConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `directory` | string | 否 | `".auton_local/decision-review"` | 类型格式 path |
| `reviewer_model` | string | 否 | `"deepseek-v4-pro"` |  |
| `max_documents` | integer | 否 | `10000` | ≥ 100; ≤ 100000 |
| `max_active_jobs` | integer | 否 | `1` | ≥ 1; ≤ 2 |
| `max_stage_cost_microusd` | integer | 否 | `20000` | ≥ 1; ≤ 50000 |
| `max_input_bytes` | integer | 否 | `14000` | ≥ 1000; ≤ 20000 |
| `min_meta_families` | integer | 否 | `100` | ≥ 100; ≤ 1000 |
| `min_meta_per_verdict` | integer | 否 | `30` | ≥ 30; ≤ 200 |
| `max_keep_contamination_upper` | number | 否 | `0.01` | > 0; ≤ 0.01 |
| `min_meta_coverage` | number | 否 | `0.9` | ≥ 0.9; ≤ 1 |
| `min_meta_kappa` | number | 否 | `0.6` | ≥ 0.6; ≤ 1 |
| `rubric_revision` | `"decision-review-v1"` | 否 | `"decision-review-v1"` |  |

<a id="decisiontrainingconfig"></a>
### DecisionTrainingConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `workload` | `"executor"`, `"decision"` | 否 | `"decision"` |  |
| `directory` | string | 否 | `".auton_local/decision-training"` | 类型格式 path |
| `backend` | `"disabled"`, `"docker"` | 否 | `"disabled"` |  |
| `image` | string | 否 | `""` | 最长 300 |
| `base_models` | array&lt;[BaseModelSpec](#basemodelspec)&gt; | 否 | `[]` |  |
| `device` | `"auto"`, `"cpu"`, `"cuda"` | 否 | `"auto"` |  |
| `max_documents` | integer | 否 | `10000` | ≥ 100; ≤ 100000 |
| `max_steps` | integer | 否 | `1000` | ≥ 1; ≤ 100000 |
| `max_wall_seconds` | integer | 否 | `3600` | ≥ 10; ≤ 86400 |
| `memory_mb` | integer | 否 | `8192` | ≥ 512; ≤ 1048576 |
| `cpus` | integer | 否 | `4` | ≥ 1; ≤ 256 |
| `max_output_bytes` | integer | 否 | `536870912` | ≥ 1048576; ≤ 8589934592 |
| `min_free_bytes` | integer | 否 | `1073741824` | ≥ 1048576 |
| `max_active_jobs` | integer | 否 | `1` | ≥ 1; ≤ 8 |

<a id="delegationconfig"></a>
### DelegationConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `directory` | string | 否 | `".auton_local/delegation"` | 类型格式 path |
| `max_active_parents` | integer | 否 | `2` | ≥ 1; ≤ 4 |
| `max_children` | integer | 否 | `6` | ≥ 1; ≤ 8 |
| `max_parallel` | integer | 否 | `2` | ≥ 1; ≤ 4 |
| `max_parents` | integer | 否 | `100` | ≥ 1; ≤ 1000 |
| `child_timeout_seconds` | number | 否 | `600.0` | ≥ 1; ≤ 3600 |

<a id="evolutionconfig"></a>
### EvolutionConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `directory` | string | 否 | `".auton_local/evolve"` | 类型格式 path |
| `reflection_model` | string | 否 | `"deepseek-v4-pro"` |  |
| `max_active_jobs` | integer | 否 | `1` | ≥ 1; ≤ 2 |
| `max_documents` | integer | 否 | `10000` | ≥ 100; ≤ 100000 |
| `max_patch_characters` | integer | 否 | `1500` | ≥ 100; ≤ 3000 |
| `max_changed_fraction` | number | 否 | `0.5` | ≥ 0.05; ≤ 0.5 |
| `max_failed_attempts` | integer | 否 | `3` | ≥ 1; ≤ 3 |
| `min_development_families` | integer | 否 | `3` | ≥ 3; ≤ 9 |
| `min_repeats` | integer | 否 | `3` | ≥ 3; ≤ 5 |
| `max_arena_runs` | integer | 否 | `72` | ≥ 3; ≤ 180 |
| `max_arena_model_calls` | integer | 否 | `240` | ≥ 3; ≤ 600 |
| `max_arena_tokens` | integer | 否 | `600000` | ≥ 1536; ≤ 2000000 |
| `max_arena_cost_microusd` | integer | 否 | `300000` | ≥ 1; ≤ 1000000 |
| `max_arena_tool_calls` | integer | 否 | `72` | ≥ 3; ≤ 200 |
| `arena_timeout_seconds` | number | 否 | `1200.0` | ≥ 1; ≤ 3600 |
| `max_reflection_cost_microusd` | integer | 否 | `20000` | ≥ 1; ≤ 50000 |
| `gate_revision` | `"skill-gates-v1"` | 否 | `"skill-gates-v1"` |  |

<a id="experienceconfig"></a>
### ExperienceConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `directory` | string | 否 | `".auton_local/experience"` | 类型格式 path |
| `batch_size` | integer | 否 | `200` | ≥ 1; ≤ 1000 |
| `max_catchup_events` | integer | 否 | `20000` | ≥ 100; ≤ 100000 |
| `max_trace_events` | integer | 否 | `2000` | ≥ 100; ≤ 5000 |

<a id="genomeconfig"></a>
### GenomeConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `directory` | string | 否 | `".auton_local/genome"` | 类型格式 path |

<a id="judgmentconfig"></a>
### JudgmentConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `backend` | `"laya"`, `"mock"` | 否 | `"laya"` |  |
| `directory` | string | 否 | `"weights/laya-multilingual"` | 类型格式 path |
| `revision` | `"e333cb7c823cd1787276228260f56d02fbf5180b"` | 否 | `"e333cb7c823cd1787276228260f56d02fbf5180b"` |  |
| `application_enabled` | boolean | 否 | `false` |  |
| `device` | `"cpu"`, `"mps"` | 否 | `"cpu"` |  |
| `max_tokens` | integer | 否 | `1024` | ≥ 128; ≤ 1024 |
| `timeout_seconds` | number | 否 | `90.0` | > 0; ≤ 180 |
| `load_timeout_seconds` | number | 否 | `120.0` | > 0; ≤ 300 |

<a id="kernelconfig"></a>
### KernelConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `backend` | `"sqlite"`, `"memory"` | 否 | `"sqlite"` |  |
| `data_directory` | string | 否 | `".auton_local"` | 类型格式 path |
| `busy_timeout_ms` | integer | 否 | `1000` | ≥ 0; ≤ 30000 |

<a id="modelconfig"></a>
### ModelConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `backend` | `"deepseek"`, `"mock"` | 否 | `"deepseek"` |  |
| `local_targets` | array&lt;[ModelSpec](#modelspec)&gt; | 否 | `[]` |  |
| `fixture_scenario` | `"baseline"`, `"agent_acceptance"` | 否 | `"baseline"` |  |
| `secret_reference` | string | 否 | `"DEEPSEEK_API_KEY"` | 格式 ^[A-Z][A-Z0-9_]{2,99}$ |
| `timeout_seconds` | number | 否 | `45.0` | > 0; ≤ 120 |
| `max_parallel` | integer | 否 | `4` | ≥ 1; ≤ 16 |

<a id="modelspec"></a>
### ModelSpec

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | — |  |
| `provider` | `"deepseek"`, `"mock"`, `"local"` | 是 | — |  |
| `location` | `"local"`, `"remote"` | 是 | — |  |
| `declared_revision` | string | 是 | — |  |
| `executor_tier` | `"small_2b"`, `"small_7b"`, `"strong"`, `"test_fixture"` | 否 | `"strong"` |  |
| `base_revision` | string / null | 否 | `null` |  |
| `adapter_revision` | string / null | 否 | `null` |  |
| `template_revision` | string / null | 否 | `null` |  |
| `runtime_revision` | string | 否 | `"deepseek-http-sse-v2"` |  |
| `quantization` | string / null | 否 | `null` |  |
| `context_tokens` | integer | 否 | `8192` |  |
| `declared_context_tokens` | integer | 否 | `1048576` |  |
| `max_output_tokens` | integer | 否 | `2048` |  |
| `capabilities` | array&lt;`"text"`, `"tools"`, `"json"`&gt; | 否 | `["text", "tools", "json"]` |  |
| `input_microusd_per_million` | integer | 否 | `0` |  |
| `output_microusd_per_million` | integer | 否 | `0` |  |
| `price_revision` | string | 否 | `"2026-11-17-peak"` |  |
| `revision_is_pinned` | boolean | 否 | `false` |  |
| `endpoint` | string / null | 否 | `null` |  |
| `expected_fingerprint` | string / null | 否 | `null` |  |
| `local_secret_reference` | string / null | 否 | `null` |  |
| `base_manifest_digest` | string / null | 否 | `null` |  |
| `local_tool_parser` | `"tagged_json"`, `"json"` | 否 | `"tagged_json"` |  |
| `local_lora_rank` | integer | 否 | `8` | ≥ 1; ≤ 128 |

<a id="operationsconfig"></a>
### OperationsConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `directory` | string | 否 | `".auton_local/operations"` | 类型格式 path |
| `enabled` | boolean | 否 | `false` |  |
| `observer_only` | boolean | 否 | `false` |  |
| `poll_seconds` | number | 否 | `5.0` | ≥ 1; ≤ 60 |
| `lease_seconds` | integer | 否 | `120` | ≥ 60; ≤ 3600 |
| `dispatch_timeout_seconds` | integer | 否 | `30` | ≥ 1; ≤ 50 |
| `max_jobs_per_tick` | integer | 否 | `2` | ≥ 1; ≤ 8 |
| `max_queued_jobs` | integer | 否 | `200` | ≥ 10; ≤ 1000 |
| `max_documents` | integer | 否 | `100000` | ≥ 1000; ≤ 1000000 |
| `max_attempts` | integer | 否 | `3` | ≥ 1; ≤ 5 |
| `backoff_seconds` | integer | 否 | `30` | ≥ 1; ≤ 600 |
| `owner_budget_microusd` | integer | 否 | `1000000` | ≥ 0; ≤ 100000000 |
| `min_new_training_examples` | integer | 否 | `20` | ≥ 20; ≤ 10000 |
| `preempt_training` | boolean | 否 | `true` |  |
| `sample_retention_days` | integer | 否 | `30` | ≥ 1; ≤ 365 |
| `max_samples` | integer | 否 | `1000` | ≥ 20; ≤ 10000 |
| `drift_delta` | number | 否 | `0.2` | ≥ 0.1; ≤ 1 |
| `backlog_alert` | integer | 否 | `20` | ≥ 1; ≤ 1000 |

<a id="releaseconfig"></a>
### ReleaseConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `directory` | string | 否 | `".auton_local/release"` | 类型格式 path |
| `max_documents` | integer | 否 | `10000` | ≥ 100; ≤ 100000 |
| `min_independent_families` | integer | 否 | `30` | ≥ 20; ≤ 1000 |
| `min_quality_lower` | number | 否 | `0.9` | ≥ 0.8; ≤ 1 |
| `max_observations` | integer | 否 | `500` | ≥ 20; ≤ 5000 |
| `max_initial_percentage` | integer | 否 | `5` | ≥ 1; ≤ 10 |
| `schema_revision` | `"release-control-v1"` | 否 | `"release-control-v1"` |  |

<a id="serversettings"></a>
### ServerSettings

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `directory` | string | 否 | `".auton_local/server"` | 类型格式 path |
| `identity_backend` | `"sqlite"`, `"memory"` | 否 | `"sqlite"` |  |
| `identity_ttl_seconds` | integer | 否 | `2592000` | ≥ 60; ≤ 31536000 |
| `max_identities` | integer | 否 | `1000` | ≥ 1; ≤ 10000 |
| `max_upload_bytes` | integer | 否 | `131072` | ≥ 1024; ≤ 1048576 |
| `upload_ttl_seconds` | integer | 否 | `600` | ≥ 1; ≤ 3600 |
| `stream_page_size` | integer | 否 | `32` | ≥ 1; ≤ 100 |
| `stream_send_timeout` | number | 否 | `5.0` | ≥ 0.1; ≤ 30 |

<a id="toolconfig"></a>
### ToolConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `directory` | string | 否 | `".auton_local/tools"` | 类型格式 path |
| `read_only` | boolean | 否 | `false` |  |
| `max_file_bytes` | integer | 否 | `131072` | ≥ 1024; ≤ 262144 |
| `max_output_bytes` | integer | 否 | `16384` | ≥ 1024; ≤ 65536 |
| `process_timeout_seconds` | number | 否 | `5.0` | > 0; ≤ 30 |
| `mcp_enabled` | boolean | 否 | `true` |  |

<a id="trainingconfig"></a>
### TrainingConfig

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `workload` | `"executor"`, `"decision"` | 否 | `"executor"` |  |
| `directory` | string | 否 | `".auton_local/training"` | 类型格式 path |
| `backend` | `"disabled"`, `"docker"` | 否 | `"disabled"` |  |
| `image` | string | 否 | `""` | 最长 300 |
| `base_models` | array&lt;[BaseModelSpec](#basemodelspec)&gt; | 否 | `[]` |  |
| `device` | `"auto"`, `"cpu"`, `"cuda"` | 否 | `"auto"` |  |
| `max_documents` | integer | 否 | `10000` | ≥ 100; ≤ 100000 |
| `max_steps` | integer | 否 | `1000` | ≥ 1; ≤ 100000 |
| `max_wall_seconds` | integer | 否 | `3600` | ≥ 10; ≤ 86400 |
| `memory_mb` | integer | 否 | `8192` | ≥ 512; ≤ 1048576 |
| `cpus` | integer | 否 | `4` | ≥ 1; ≤ 256 |
| `max_output_bytes` | integer | 否 | `536870912` | ≥ 1048576; ≤ 8589934592 |
| `min_free_bytes` | integer | 否 | `1073741824` | ≥ 1048576 |
| `max_active_jobs` | integer | 否 | `1` | ≥ 1; ≤ 8 |

<a id="usage"></a>
### Usage

| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |
| --- | --- | --- | --- | --- |
| `tokens` | integer | 否 | `0` | ≥ 0 |
| `cost_microusd` | integer | 否 | `0` | ≥ 0 |
| `tool_calls` | integer | 否 | `0` | ≥ 0 |
