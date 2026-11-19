# 通用本地模型运行与独立发布

训练与服务运行在最终部署环境。项目不检测当前开发电脑的显存，不下载指定尺寸模型，不在开发电脑启动训练或推理。M18/M19 负责离线候选；M20 的独立发布模块负责审查与实际激活，训练模块没有发布依赖或写权限。

## 部署工件

执行模型候选先通过 M18 的通用 Docker 工作流生成不可变 bundle。部署方自行选择已许可的基础模型，冻结完整文件 SHA、基础 revision、工具模板、解析器和运行依赖。`config/training.example.toml` 是通用训练配置。不要把密钥写入配置文件、训练输入、adapter 或镜像。

M20 提供 `python -m auton.model.runtime_worker --config /runtime/config.json --port 8091` 作为可选的 HF/PEFT 服务实现。重型依赖只安装到目标服务环境；容器配方在 `containers/local-runtime`，从仓库根目录构建。基础镜像必须显式提供已审核的 Python 3.12 镜像 digest，构建后的环境也应固定到镜像 digest。当前参考实现仅支持 CPU/CUDA、未量化 `none` 的 causal LM + LoRA；量化、其他模型输出语法和生产并发容量需要独立 adapter 与目标环境验收。

配置 JSON 结构：

```json
{
  "spec": {
    "id": "local-approved-executor",
    "provider": "local",
    "location": "local",
    "declared_revision": "<训练 bundle ID>",
    "adapter_revision": "<adapter.safetensors SHA256>",
    "base_revision": "<基础模型完整 revision>",
    "base_manifest_digest": "<TrainingPlan.base_manifest_digest>",
    "template_revision": "<真实 chat_template SHA256>",
    "runtime_revision": "auton-hf-json-v1",
    "quantization": "none",
    "local_tool_parser": "tagged_json",
    "local_lora_rank": 8,
    "revision_is_pinned": true,
    "endpoint": "http://127.0.0.1:8091",
    "expected_fingerprint": "<部署环境计算的 fingerprint>",
    "local_secret_reference": "AUTON_LOCAL_MODEL_EXECUTOR"
  },
  "base_directory": "/models/base",
  "adapter_directory": "/models/adapter",
  "base_manifest": "此处实际填入 BaseModelSpec 去掉 directory 字段后的对象",
  "base_files": {"config.json": "<SHA256>", "其他每一个文件": "<SHA256>"},
  "adapter_files": {"adapter.safetensors": "<SHA256>"},
  "device": "cuda"
}
```

以上是结构示意，尖括号和说明字符串不能直接用于部署。目录必须与 manifest 完全一致，不接受未列出的文件或符号链接。`base_manifest.files` 与 `base_files` 相同，去掉目录后的 canonical digest 必须匹配训练计划。服务按 M18 训练计划中的 rank 重建同一个 all-linear LoRA 配方，再载入 adapter.safetensors，严格核对 tensor 名称与形状；不假定训练 checkpoint 已是 PEFT save_pretrained 目录。当前参考运行时使用 float32。运行时 SHA 绑定实际脚本、依赖版本、设备、模板、解析器、基础文件与 adapter 文件；初次提供占位 fingerprint 时服务在加载模型之前拒绝启动并给出计算值。审核真实部署配置后固定此值，应用 `models.local_targets` 配置填入同一个 `spec`。仅更改 endpoint 不能替换获准工件，运行时变化必须重新评测。

服务只监听 loopback，要求独立的至少 32 字符 bearer 密钥；应用和服务各自通过 `AUTON_LOCAL_MODEL_…` 环境引用读取。它不会接收 DeepSeek 云端密钥。生产应由操作员监督运行，配置/基础/adapter 只读、非 root、撤销特权、限 CPU/内存/进程/输出并阻止外部网络。Linux 容器如使用 host 网络才能访问其 loopback，须另行验证网络隔离；不把该配置默认为跨平台隔离保证。

## 输入、输出与相容性

服务使用训练相同的 HF chat template、tools、`enable_thinking=False`、`add_generation_prompt=True`。`tagged_json` 解析 `<tool_call>{"name":"…","arguments":{…}}</tool_call>`；`json` 解析单个工具 JSON 对象。普通回答按文本返回。工具名、参数 schema、finish reason、用量及预算由应用继续校验。不同模板的工具语法不能假定兼容，需要实现专用解析器并重新评测。

`GET /auton/manifest` 必须鉴权、真实加载基础/adapter 并完成一次 tensor 预热后才返回 ready。`POST /auton/token-count` 和 `/auton/generate` 都绑定完整 ModelRequest digest 和 fingerprint；token-count 使用实际 tokenizer，不用字符数伪装。generate 只返回结果，不执行工具。应用关闭代理继承与重定向，预热失败不会切换运行指针。

该协议与常规 OpenAI-compatible API 不等价。已有服务若没有这三个接口，需要实现并验证 adapter；不能仅写一个“active”记录就声称运行链路已生效。当前工程测试使用 HTTP 协议替身，未在本机加载或训练真实基础模型。

## 发布与验证步骤

1. 创建 `POST /api/v1/releases`：冻结项目、来源、模式、比例、基线、语言/数据范围和报告 ID。默认模式 offline；canary 上限默认 5%。同 request ID 的命令不可修改。
2. 执行模型先提交一份证据不足的计划，再调用 `/{id}/validation` 真实预热并创建隔离验证授权。该授权只允许经 `/{id}/validation/runs` 创建的专用工作区任务，绝不设置项目默认指针。任务输入包含 `request_id`、`goal`、独立文件验收 `acceptance` 和 `data_domain`。仅允许受控文件读写；写操作仍需用户审批。未授权普通任务不能使用该本地候选。
3. 在独立评测模块开放一次性 release 窗口，用完整受保护 test 批次评测。新建最终发布计划引用报告与成对基线报告。初始计划不可原地替换报告，避免批准对象变化。报告需要当前、runtime 来源、独立质量资格、完整用量、严格匹配实际 bundle/模板/runtime/fingerprint；资产报告需要实际输入快照含候选内容。测试替身不能获得发布资格。
4. 以 case family 与 origin ancestry 的连通分量统计独立数量，默认至少 30，且质量 Wilson 下界至少 0.9；全部通过时通常还需至少 35 个分量。执行模型另要求相同任务、工具、验收、资产、资源条件下的完整成对基线，在独立分量上建立模型延迟改善的置信下界。这是模型调用延迟指标，不能声称已证明总任务成本或长期收益。语言按真实输入任务识别；数据范围必须有对应评测覆盖。当前只支持 general 的运行任务域，其他域因缺少运行分类器阻断发布。
5. 用户核对报告 digest、范围和风险，提交 `/{id}/approvals`（`risks_reviewed` 默认 false），然后 `/{id}/commands` 的 activate。前端 `?view=release` 提供检查、批准、激活、暂停、回滚及证据状态。不存在自动批准。
6. 模型通过任务页面显式选择“项目批准的灰度策略”才采用项目 profile；原有手选模型继续按用户选择执行。灰度由 owner/project/goal 的稳定哈希分组，任务固定模型和资产快照。暂停停止新分配，已有任务保持版本；回滚撤销后续执行权，取消受影响任务并保留未知工具结果，待安全对账后重试回滚以完成状态。
7. 提交 `/{id}/observations` 引用真实候选 cohort 的独立评测。严重失败或未知工具副作用按工件身份记录 incident 并请求回滚。同一工件换 job/计划名不能绕过；源码/数据授权撤回也会阻断后续本地模型请求。人工后续资产变更不得被回滚覆盖，冲突会明确失败，需人工合并。

## 决策模型的边界

当前用户授权的决策流程仍为教师唯一执行。M19 学生可离线训练、描述性回放和四层评估；M20 仅登记 offline 候选。`decision_model` 的 canary/active 会阻断。没有通过真实金标、live shadow、完整隔离 Agent 和部署验证，不能用历史 KEEP 一致率替代上线效果。当前实现不提供生产 student/teacher 双写、动态路由或伪造 live shadow；未来接手必须有新的明确授权及实证。

## 回滚和故障恢复

发布状态使用私有 SQLite WAL、CAS、不可变版本与审计回执；模型 profile 单次事务切换，资产正式写入使用 Git revision CAS。先写入“activating”再执行效果，恢复时显式重试同一发布；独立后端以相同发布/命令回执识别已完成切换。失败不自动重发模型调用或重放工具。资产 100% 写入保留原始父版本及回执，回滚只恢复完全相同的目标资产，保留其他资产。

回滚开始先撤销 profile，然后取消受影响运行；若 actor 尚未终止，发布显示 rollback_pending。未知副作用不会被报告成成功撤销，需沿 M09 的安全检查点对账，随后重试 rollback。远程基线回退对 local-only 数据仍拒绝外发；不以“恢复可用性”为理由绕过隐私。

当前没有真实训练后的可部署模型，也没有完整的新鲜受保护质量批次。因此这套控制面的实现不代表已批准任何模型上线。目标部署环境仍需验证真实 GPU/CPU 推理、隔离、量化、性能、并发、质量及长周期退化；缺少证据时保持 blocked。
