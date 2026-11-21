# 新对话自动整理为训练数据

新建对话会自动登记到后端学习队列。后台发现每一轮的 AgentRun，冻结检查点，调用独立评测，记录决策复核结果，构建数据快照并导出合格 JSONL。执行模型与决策模型使用不同监督格式。这个过程不会启动训练、切换在线模型或发布候选。

前端仍只保留对话、项目路径与模型选择。后台策略、授权和资格可通过 API 管理。所有接口沿用当前身份 Cookie；浏览器和 CLI 默认是不同身份，详见 [API 身份约定](api.md)。

## 默认行为与一次性配置

默认启用队列发现，默认没有数据使用授权，也没有付费复核额度。因此可以先积累轨迹，状态是 `collected`。重启不会清空队列。已有对话在列出或打开时登记；新对话创建时立即登记。首次采集覆盖登记会话的已有各轮，以及后续新增各轮。

`GET /api/v1/learning` 返回当前身份的策略、案例、预留复核次数、拒绝原因、报告/快照/导出 ID。`PUT /api/v1/learning/policy` 设置一次当前身份的持续策略，之后无需每轮手动创建 grant/build/export。范围是该身份登记的全部会话，包括本地项目内容和历史消息；不要为不打算训练的数据开启此策略。

策略例子（字段值须由数据所有者填写，示例本身不构成提供商条款或授权）：

```json
{
  "expected_version": null,
  "enabled": true,
  "local_training_authorized": true,
  "data_license_reference": "填写数据来源和你拥有训练使用权的依据",
  "teacher_uses": [
    {
      "model_id": "填写 /api/v1/models 中的 id",
      "declared_revision": "填写同一条记录的 declared_revision",
      "terms_reference": "填写该模型版本允许训练使用输出的实际条款依据",
      "training_use_confirmed_by_user": true
    }
  ],
  "external_asset_uses": [],
  "allow_local_only_data": false,
  "allow_remote_review": true,
  "max_review_calls": 100,
  "review_decisions": true
}
```

首次 `expected_version=null`，修改时传 GET 返回的策略 `version`。更新策略不能清零已经预留的调用次数。历史回复若来自其他模型版本，也必须在 `teacher_uses` 中覆盖。外部资产沿用 datasets 的精确资产 ID/内容 SHA/授权规则。字段完整定义见 [配置和 API 参数参考](reference/api-schemas.md)。

在当前浏览器页面的开发者控制台，可用当前身份提交自己填写的 `policy` 对象：

```javascript
await fetch('/api/v1/learning/policy', {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json', 'X-Auton-Client': 'web' },
  body: JSON.stringify(policy)
}).then(r => r.json());
```

`allow_remote_review` 是独立复核的额外授权开关，不改变原始数据域。`local-only` 任务仍只能交给满足本地数据策略的评测模型，不会因为这个开关就被改成 public。`allow_local_only_data` 单独控制是否允许纳入本地训练。没有用户声明的数据/教师使用权，不会自动填成 true。

## 处理链与资格

| 环节 | 行为 |
| --- | --- |
| 发现 | 每轮一个持久案例；运行中、待审批、暂停或阻塞的任务暂不冻结 |
| 历史来源 | 新轮保存前序 run ID/版本；核对真实目标、回复、项目、工作区、顺序与检查点；未证明的历史不入库 |
| 复核额度 | 每轮语义评测先预留 2 次；每个实际采用的决策答案先预留 2 次；总额度包含重试与结果未知的调用 |
| 执行评测 | 固定 run/version，重复两次语义判断，要求校准、独立身份、证据有效、环境可核对；非空回复不算正确 |
| 决策复核 | 当时合理性与后续贡献分开审查；保留 DROP/HOLD 原因；只有当前合格 KEEP 可转成正监督 |
| 授权与排除 | 原始输入/输出/工具关联匹配；教师/资产授权有效；凭据特征内容拒绝导出；测试来源、保留评测、reviewer meta、进化实验排除 |
| 划分 | 会话 ID 的稳定哈希约 90% train、10% validation；同一会话所有轮与两类监督保持同一划分，前序 run 参与谱系；已有去重/划分锁继续生效 |
| 导出 | 合格快照自动导出 canonical JSONL，记录 artifact/来源/检查点/授权；重复调用复用不可变 ID，重复正样本不再次导出 |

普通问答和只读项目分析新增了 `response` 转换：保留最后一次真实模型调用的原始输入、完整工具协议以及最终回复，**只给最后的 assistant 目标计算 loss**。前序历史、工具结果和系统约束均是输入。目标必须与真实完成的最终回复完全一致，不能截断或用事后改写替换。

评测输入包含历史文本、任务边界和实际工具结果。超过评测器输入上限会明确保留 unknown，不静默截断后判合格。校准题库现在支持 `kind=response`；仍需真实独立人工 meta 标签及对应语言/长度/风险分组的校准资格，具体流程见 [独立评估 M13](milestones/evidence/M13.md)。测试里的模拟通过不能替代生产校准。

发生 `file.write` 的对话回复暂保留 `dataset_code_execution_verification_required`：文字审稿不能证明代码改动满足需求。这类任务仍保留完整轨迹和拒绝原因；独立文件目标验收继续使用原有 file 数据转换。失败、取消、结果未知和未确认副作用不被转换成成功执行样本。

当前 Laya 默认只是影子建议，`adopted=false`。自动记录 `HOLD:shadow_answer_not_eligible`，不浪费两阶段付费复核，也不把后续成功归因给未采用的建议。实际采用的决策才进入现有独立贡献/因果/校准门禁。没有这些证据就继续 HOLD，而非自动生成 KEEP。

## 状态、恢复和撤权

- `collected`：已发现；策略关闭或任务仍未完成。无自动付费调用。
- `assessing` / `reviewing` / `building`：已保存处理意图，正在独立复核或建库。
- `ready`：对应产物通过资格检查并已导出；读取状态时还会检查资格是否仍有效。
- `hold`：缺少授权、额度、校准、来源证明、执行验收等；原因在 `reasons`，决策原因在 `decision_outcomes`。
- `rejected`：执行任务失败/取消，不收为成功执行样本，保留审计记录。

关闭策略：提交新版本并设置 `enabled=false`，阻止后续自动处理。它不等同于撤销已导出的授权。撤销已有样本请调用原有 `POST /api/v1/datasets/withdraw`，指定项目和 run/grant；后续下载、训练读取和学习清单会重新检查，失效数据不会继续显示为 ready。已经复制到应用之外的文件无法由接口追回。

结果未知的付费请求不会在重启后自动重发。已完成报告可按原 ID 恢复；找不到最终证据则 HOLD。修正授权/校准/故障后，可以显式重试：

```text
POST /api/v1/learning/cases/{case_id}/retry
{"expected_version": 当前案例版本}
```

重试生成新处理 attempt，历史保留、复核额度累计。它不是续费授权；额度不足仍会停止。策略变更后中断的任务也要求明确重试。旧版本中只保存文字而没有前序检查点引用的历史不会被自动猜测为可信来源，必要时使用新会话积累完整链路。

## 取得训练输入

`GET /api/v1/learning/manifest` 按 `executor/decision` 和 `train/validation` 列出当前 ready 产物 ID，只返回当前身份拥有且仍可读取的产物。每组最多 200 个，超出时要求选择有界训练批次；训练清单与整个历史库不是同一个概念。可用原有 datasets artifact 下载接口取得 JSONL 和 manifest，不要直接抓 SQLite 表充当训练集。

每个会话拥有独立项目，因此多个会话的数据使用训练计划新增的批量字段：

```json
{
  "project_id": "训练输出所属的已有项目",
  "train_artifact_id": "清单中第一个训练产物",
  "additional_train_artifact_ids": ["同类的其他训练产物"],
  "validation_artifact_id": "清单中第一个验证产物",
  "additional_validation_artifact_ids": ["同类的其他验证产物"],
  "allow_cross_project_sources": true
}
```

以上是数据相关字段，完整训练计划还需 request/base model/优化参数等，见 [通用训练流程](usage.md)。默认禁止跨项目；明确允许时仍只能读取当前身份的合格产物，逐个检查授权、撤回、监督类型、哈希和组间独立性。每个角色合并后最多 32 MB，单角色不能有重复样本，训练/验证/回放/锚点不能重叠。两类模型的数据始终分别读取。

同一会话不会同时提供训练和验证数据。刚开始样本少、尚无独立验证会话时，应继续收集，不能拆散同一段历史来凑验证集。数据合格也不等于模型变好；训练、留出评估、灰度、批准上线仍走既有训练与发布流程。

## 宿主配置和维护

`[learning]` 可配置 `directory`（默认 `.auton_local/learning`）、`background`（默认 true）、`poll_seconds`（默认 5）、`max_cases_per_tick`（默认 4）、`max_documents`（默认 30000）。完整上下界见 [配置参考](reference/configuration.md)。

存储复用带文件独占锁、版本校验和审计摘要的 SQLite 文档仓库，目录 0700、文件 0600；不会进入 Git。备份/恢复要同时保留 learning、原始事件、datasets、assess、decision-review 等证据目录，只复制学习队列不能恢复来源资格。容量达到上限时停止新增，不自动删除审计记录。

`POST /api/v1/learning/tick` 手动运行一轮，用于维护和测试；后台启用时无需定时调用。所有队列控制都在后端，执行器、教师模型和工具不能自行开启学习、增加额度、训练或发布。
