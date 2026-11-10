# Auton 重构设计：以 Agent Self-Evolution 为核心的架构闭环

> 状态：设计稿（v0.1，2026-11-10）
> 范围：整体架构重构方案，不含具体代码实现

---

## 0. 一句话目标

**让 Auton 的每一次运行都留下可归因的经验，经验被评估、反思后转化为对"可进化资产"的候选修改，候选修改经过验证才上线，上线后持续监测、劣化自动回滚。**

自进化不是一个功能模块，而是整个架构的主轴：运行时（Runtime）只是闭环中的 "Act" 一环。

---

## 1. 现状诊断（为什么要重构）

现有代码里其实已经有不少自进化"零件"，但它们**各自为战、没有闭环**：

| 已有零件 | 位置 | 缺什么 |
|---|---|---|
| Skill 性能追踪 | `skills/perf_tracker.py` | 只统计 success/turns，信号单一；与具体 skill 版本无关联 |
| Skill 自动优化 | `skills/optimizer.py` | LLM 改完**直接覆盖 SKILL.md**，无验证、无版本、无回滚 |
| 检索命中分析 | `memory/retrieval_analytics.py` | 只服务于摘要质量，不是通用信号 |
| 摘要改进 | `memory/compression_improver.py` | 生成改进 prompt，但改进后效果是否变好无人检验 |
| 记忆遗忘 / 冲突 | `memory/forgetting.py`、`conflict_resolver.py` | 规则驱动，与任务结果无关 |
| 事件总线 | `core/events.py`、`core/event_types.py` | `SessionProcessor` 在 emit，但**几乎没有订阅者** |
| 触发 | `agent/agent.py::_trigger_pending_skill_optimizations` | 硬编码在主循环里，导致主循环 1158 行 |

结构性问题（见上一轮架构评审）：`Message`/`LLMContext` 放在 `agent/` 导致 `llm/memory/compress/skills → agent` 反向依赖；`cron/heartbeat/plugins/context_aware/api` 为空壳；planner/task/workflow 多套重叠。

**结论**：重构的关键不是加新功能，而是建立统一的「经验 → 评估 → 变异 → 验证 → 发布」管道，把现有零件都改造成管道上的插件。

---

## 2. 核心闭环

```
            ┌──────────────────────────────────────────────────────────┐
            │                      GENOME（可进化资产，带版本）           │
            │  prompt片段 · skills · memory · subagents · workflows ·    │
            │  compaction策略 · tool使用策略                             │
            └───────▲───────────────────────────────────┬──────────────┘
                    │ ⑥ Promote / Rollback              │ ① Assemble（按版本快照装配）
                    │                                   ▼
   ┌────────────────┴───────┐                 ┌─────────────────────┐
   │ ⑤ VERIFY（门禁）        │                 │ ② ACT（Runtime）     │
   │ 回放评测 · 金样例回归    │                 │ Agent loop / tools   │
   │ canary · 安全约束检查    │                 │ 只负责执行 + 发事件   │
   └────────▲───────────────┘                 └──────────┬──────────┘
            │                                            │ events
   ┌────────┴───────────────┐                 ┌──────────▼──────────┐
   │ ④ MUTATE（提案）        │                 │ ③ OBSERVE           │
   │ SkillRefiner · SkillMiner│◀── Reflect ─── │ Trace → Episode      │
   │ MemoryCurator · Prompt..│   （诊断归因）   │ + Signals → Outcome  │
   └────────────────────────┘                 └─────────────────────┘
```

六个阶段，对应六个一等公民概念：

| 阶段 | 概念 | 一句话 |
|---|---|---|
| ① Assemble | `GenomeSnapshot` | 本次会话用了哪些资产的哪个版本 |
| ② Act | `Runtime` | 执行任务，只发事件，不做学习 |
| ③ Observe | `Episode` + `Signal` + `Outcome` | 一个任务的完整轨迹 + 打分 |
| ④ Reflect/Mutate | `Diagnosis` + `Proposal` | 为什么好/坏 → 对哪个资产做什么修改 |
| ⑤ Verify | `Gate` + `EvalReport` | 候选版本是否比当前版本好且安全 |
| ⑥ Promote | `AssetVersion` 状态机 | 发布 / 灰度 / 回滚，保留谱系 |

**闭环的关键是归因**：`Episode` 必须记录 `GenomeSnapshot` 和 `assets_touched`，否则信号无法回流到具体资产的具体版本。这是当前代码最缺的一环。

---

## 3. 三种进化速度

不同资产的风险和反馈周期不同，不能用同一个节奏：

| 回路 | 触发时机 | 典型动作 | 门禁强度 | 承载者 |
|---|---|---|---|---|
| **快回路**（in-session） | 每轮 / 工具失败后 | 写入工作记忆、记录"教训"笔记、本会话内纠正 | 轻量（去重、冲突检测） | Runtime 订阅者 |
| **中回路**（session end） | 会话结束 / compact | 生成摘要、整合记忆、更新资产 fitness、产出 Diagnosis | 自动 | `EvolutionScheduler` |
| **慢回路**（idle / 定时） | 空闲、每日、累计阈值 | Skill 重写、新 Skill 挖掘、prompt 片段调整、压缩策略调参 | 强（回放评测 + canary） | `EvolutionScheduler`（复用 cron/heartbeat） |

这也给空壳模块 `cron/`、`heartbeat/` 找到了真正的职责：**它们是慢回路的时钟**。

---

## 4. 分层架构

依赖只能自上而下，用 import-linter 在 CI 中强制。

```
┌─────────────────────────────────────────────────────────────┐
│ L5  interfaces/   adapters(cli/web/slack/...) · gateway · commands │
├─────────────────────────────────────────────────────────────┤
│ L4  evolution/    reflect · mutators · verify · promote · scheduler │
├─────────────────────────────────────────────────────────────┤
│ L3  evaluation/   signals · judges · outcome · benchmarks           │
├─────────────────────────────────────────────────────────────┤
│ L2  experience/   trace recorder · episode builder · store          │
├─────────────────────────────────────────────────────────────┤
│ L1  runtime/      loop · llm · tools · context(compress) · prompt   │
│     genome/       asset store · versions · loaders(skill/memory/..) │
├─────────────────────────────────────────────────────────────┤
│ L0  kernel/       types(Message, LLMContext...) · events · config   │
│                   paths · errors · logging · storage primitives     │
└─────────────────────────────────────────────────────────────┘
```

规则：

1. `runtime` 不依赖 `experience/evaluation/evolution`。学习逻辑全部通过 **订阅 EventBus** 挂载，主循环里不再出现 skill 追踪、优化触发等代码。
2. `genome` 与 `runtime` 同层：runtime 只读 genome（读取 *active* 版本），只有 `evolution.promote` 能写 genome。
3. `evaluation` 不依赖 `evolution`：评估器必须独立于被评估者（防止"自己给自己打分"被一起进化掉）。
4. `security/` 作为 kernel 旁路的横切模块，**不属于 genome，不可被进化**。

### 4.1 目录结构

```
auton/
├── kernel/          # 原 core/ + 下沉的 Message / LLMContext / Part 等核心类型
├── runtime/
│   ├── loop.py      # 精简后的 SessionProcessor（目标 < 400 行）
│   ├── llm/         # 原 llm/（去掉对 agent/gateway 的依赖）
│   ├── tools/       # 原 tools/
│   ├── context/     # 原 compress/ + token 管理
│   └── prompt/      # system prompt 装配器：从 GenomeSnapshot 渲染
├── genome/
│   ├── store.py     # AssetStore：版本化存储（文件 + manifest）
│   ├── types.py     # Asset / AssetVersion / GenomeSnapshot
│   └── kinds/       # 每类资产的 loader + schema + diff/patch
│       ├── skill.py
│       ├── memory.py
│       ├── prompt_fragment.py
│       ├── subagent.py
│       ├── workflow.py
│       └── policy.py      # compaction 阈值、tool 选择偏好等参数型资产
├── experience/
│   ├── recorder.py  # EventBus 订阅者 → trace
│   ├── episode.py   # 把 trace 切分成 Episode（一个用户任务）
│   └── store.py     # 统一 session_store（append-only jsonl）+ episode 索引
├── evaluation/
│   ├── signals/     # explicit / implicit / tool / retrieval / judge
│   ├── outcome.py   # Signal 聚合为 Outcome，回写资产 fitness
│   ├── judges.py    # LLM-as-judge（rubric 固定，不可被进化）
│   └── bench/       # 金样例集、回放 harness
├── evolution/
│   ├── reflect.py   # Diagnosis：失败/成功模式 + 归因到资产
│   ├── mutators/    # 每类资产的变异器（插件）
│   ├── proposal.py  # Proposal 数据结构 + 队列
│   ├── verify.py    # Gate：静态检查 → 回放评测 → canary
│   ├── promote.py   # 发布 / 回滚 / 谱系
│   ├── scheduler.py # 三速回路调度（吸收 cron/heartbeat）
│   └── guard.py     # 预算、频率、不可变区域、人工审批
├── orchestration/   # 合并 planner/ + task/ + workflow/ + subagents/delegator
├── memory/          # 检索服务（runtime 调用）；记忆内容本身是 genome 资产
├── security/
└── interfaces/
    ├── gateway/
    ├── commands/
    └── adapters/
```

---

## 5. 关键数据模型

### 5.1 Genome：可进化资产

```python
class AssetKind(StrEnum):
    SKILL = "skill"
    MEMORY = "memory"                 # 长期记忆条目 / 主题文件
    PROMPT_FRAGMENT = "prompt_fragment"
    SUBAGENT = "subagent"
    WORKFLOW = "workflow"
    POLICY = "policy"                 # 数值/规则型参数

class VersionState(StrEnum):
    CANDIDATE = "candidate"   # 提案产出，未验证
    VERIFIED = "verified"     # 通过离线门禁
    CANARY = "canary"         # 灰度中
    ACTIVE = "active"         # 当前生效（每个 asset 至多一个）
    RETIRED = "retired"       # 被替代
    REJECTED = "rejected"     # 门禁失败 / 被回滚

@dataclass
class AssetVersion:
    asset_id: str             # e.g. "skill:git-workflow"
    version: str              # 内容哈希前 12 位
    parent: str | None        # 谱系
    content_ref: Path         # 实际内容位置
    state: VersionState
    origin: Literal["builtin", "user", "evolved"]
    proposal_id: str | None
    fitness: Fitness          # 滚动统计（n, mean, ci, 最近窗口）
    created_at: datetime

@dataclass
class GenomeSnapshot:
    id: str
    versions: dict[str, str]  # asset_id -> version
```

存储方式（保持对用户可读、可 git 管理）：

```
~/.auton/genome/
├── manifest.json                     # asset_id -> active/canary 版本指针
└── skill/git-workflow/
    ├── versions/<ver>/SKILL.md
    ├── versions/<ver>/meta.json      # parent / origin / proposal / fitness
    └── lineage.jsonl
```

`origin=user` 的资产默认受保护：进化只能产出"建议版本"，需用户确认才能 ACTIVE。

### 5.2 Experience：Episode

```python
@dataclass
class Episode:
    id: str
    session_id: str
    snapshot_id: str                    # GenomeSnapshot
    user_intent: str                    # 首条用户消息 / 归纳出的任务
    span: tuple[str, str]               # 起止 msg_id（指向 session jsonl，不复制）
    assets_touched: dict[str, str]      # 实际用到的资产 -> 版本（调用的 skill、读到的记忆…）
    metrics: EpisodeMetrics             # turns, tool_calls, tool_errors, tokens, duration
    signals: list[Signal]
    outcome: Outcome | None
```

Episode 边界：一个用户任务 = 从用户提出新意图到任务完成/切换话题/会话结束。初版用"每条用户消息开始一个 episode，被识别为追问/纠正时合并"的简单规则。

### 5.3 Evaluation：Signal → Outcome

```python
@dataclass
class Signal:
    source: Literal["explicit", "implicit", "tool", "retrieval", "judge"]
    name: str          # "thumbs_down", "user_correction", "tool_error", "jsonl_fallback"...
    value: float       # 归一化到 [-1, 1]
    weight: float
    evidence: str      # msg_id / 片段引用

@dataclass
class Outcome:
    score: float       # 加权聚合
    confidence: float  # 信号越少 / 越隐式，置信度越低
    label: Literal["success", "partial", "failure", "unknown"]
```

信号来源（从便宜到贵）：

| 类别 | 信号 | 已有基础 |
|---|---|---|
| tool | 工具错误率、重试次数、命令非零退出 | `ToolErrorEvent` |
| retrieval | 记忆命中层级（memory/summary/jsonl） | `retrieval_analytics.py` |
| implicit | 用户纠正 / 重问 / 中断 / 放弃（下一轮 LLM 小模型分类） | 新增 |
| explicit | `/feedback`、Web 👍👎 | 新增 |
| judge | 会话结束后按固定 rubric 打分（便宜模型，抽样） | 新增 |

Outcome 回写：对 `assets_touched` 中每个资产版本更新 fitness。这是现有 `SKILL_PERF.json` 的泛化版本。

### 5.4 Evolution：Diagnosis → Proposal

```python
@dataclass
class Diagnosis:
    episodes: list[str]
    pattern: str            # "skill:github 在 PR 创建场景反复漏掉 base 分支参数"
    suspected_assets: list[str]
    kind: Literal["failure_mode", "success_pattern", "gap", "redundancy"]

@dataclass
class Proposal:
    id: str
    target: str             # asset_id；新建资产时为 "skill:<new-name>"
    op: Literal["create", "patch", "replace", "retire", "tune"]
    base_version: str | None
    candidate_version: str
    rationale: str          # 来自 Diagnosis，写入谱系，便于人审
    risk: Literal["low", "medium", "high"]
    eval_plan: EvalPlan     # 用哪些 episode 回放、什么指标、阈值
```

### 5.5 Mutator 插件接口

```python
class Mutator(Protocol):
    kind: AssetKind
    cadence: Literal["fast", "medium", "slow"]

    def wants(self, diagnosis: Diagnosis) -> bool: ...
    async def propose(self, diagnosis: Diagnosis, ctx: EvolutionContext) -> list[Proposal]: ...
```

首批 Mutator（大部分是现有代码的改造）：

| Mutator | 回路 | 来源 | 作用 |
|---|---|---|---|
| `MemoryCurator` | 快/中 | `memory_generator` + `conflict_resolver` + `forgetting` | 写入、去重、冲突合并、按 **fitness × 衰减** 遗忘 |
| `SummaryTuner` | 中 | `compression_improver` | 调整摘要/压缩 prompt（POLICY / PROMPT_FRAGMENT 资产） |
| `SkillRefiner` | 慢 | `skills/optimizer` | 基于失败 episode 修改 SKILL.md → **产出候选版本而非覆盖** |
| `SkillMiner` | 慢 | 新增（复用 skill-creator） | 从多个相似的成功轨迹中抽取新 skill |
| `PromptFragmentTuner` | 慢 | 新增 | 只允许修改标记为 evolvable 的 system prompt 片段 |
| `PolicyTuner` | 慢 | `perf_tracker.calibrate_thresholds` | 调 compact 阈值、重试次数等数值参数 |
| `Pruner` | 慢 | 新增 | 退役长期未使用或 fitness 低的 evolved 资产，防膨胀 |

---

## 6. 验证与发布（闭环中最重要的一环）

没有验证的自进化就是自我漂移。门禁分三级，按 `Proposal.risk` 选用：

```
Proposal ──▶ L1 静态门禁 ──▶ L2 离线回放 ──▶ L3 在线灰度 ──▶ ACTIVE
              schema/长度        金样例 + 相关     按比例分流        │
              不可变区检查       失败 episode       对比 fitness      │
              安全规则扫描       pairwise judge     CI 不重叠才晋升    ▼
                                                              持续监测
                                                    劣于 parent ──▶ 自动回滚
```

| 风险 | 典型资产 | 门禁 |
|---|---|---|
| low | 记忆条目、摘要措辞 | L1 → 直接 ACTIVE（可回滚） |
| medium | evolved skill 修改、policy 参数 | L1 → L2 → L3 canary |
| high | 新建 skill、prompt 片段、user-origin 资产 | L1 → L2 → **人工确认** → L3 |

**回放 harness（`evaluation/bench/`）**：

- 金样例集来源：高 Outcome 的真实 episode 自动沉淀 + 用户手动标记 + 内置 benchmark 任务。
- 回放时工具在沙箱/dry-run 模式下运行（只读工具真实执行，写操作在临时副本上），`providers/mock.py` 可用于确定性单元测试。
- 对比方式：候选 vs 当前 ACTIVE，同一输入 pairwise judge + 硬指标（tool errors、turns、tokens）。
- 必须同时满足：目标 episode 改善 **且** 金样例不回退（regression guard）。

**发布与回滚**：`promote.py` 只改 `manifest.json` 指针；每个版本保留 parent，回滚 = 指针回退。所有状态变化写审计日志（复用 `security/audit.py`）。

---

## 7. 安全与治理（`evolution/guard.py`）

1. **不可变区（Constitution）**：安全规则、权限模式、评估 rubric、guard 自身、核心身份 prompt 不属于 genome，任何 Mutator 不可修改。防止奖励作弊（Agent 改评估标准来"变好"）。
2. **预算**：每日进化 token 上限、每资产每日最多 1 次晋升、并行 canary 数上限。
3. **膨胀控制**：skill 数上限、memory 容量上限，由 `Pruner` 维护。
4. **可解释**：每个 evolved 版本都有 rationale + 证据 episode，`/evolve log` 可查看。
5. **用户可控**：`/evolve status | diff <asset> | approve | reject | rollback | pause`；配置项 `evolution.autonomy = off | suggest | auto-low | auto`，默认 `auto-low`。
6. **隐私**：轨迹仅存本地；judge 调用可配置为本地模型或关闭。

---

## 8. 运行时改造要点

精简后的 `SessionProcessor`（`runtime/loop.py`）只做：取上下文 → 调 LLM → 执行工具 → 判断继续/压缩/停止 → 发事件。

需要新增/规范的事件（`kernel/events`）：

| 事件 | 用途 |
|---|---|
| `SessionStartEvent(snapshot_id)` | 绑定 GenomeSnapshot |
| `AssetUsedEvent(asset_id, version, how)` | skill 注入、记忆被读、subagent 调用 → `assets_touched` |
| `UserTurnEvent` / `AssistantTurnEvent` | episode 切分 |
| `ToolCallEvent` / `ToolResultEvent` / `ToolErrorEvent` | 已有 |
| `FeedbackEvent` | 显式反馈 |
| `SessionEndEvent(reason)` | 触发中回路 |

从主循环移出的逻辑：

- `_record_skill_turn_start/end`、`_trigger_pending_skill_optimizations`、`_optimize_skill_async` → `experience.recorder` + `evolution.scheduler`
- `memory_read_hook` → 改为发 `AssetUsedEvent`，由 recorder 统一记录
- system prompt 拼装（目前散落在 `session_factory._inject_*`） → `runtime/prompt`，输入只有 `GenomeSnapshot`

---

## 9. 现有模块迁移映射

| 现有 | 去向 | 说明 |
|---|---|---|
| `core/` | `kernel/` | + 下沉 `agent/message.py`、`agent/types.py` 中的核心类型 |
| `agent/agent.py` | `runtime/loop.py` | 拆掉学习相关代码 |
| `agent/system_prompt.py` + `gateway/session_factory._inject_*` | `runtime/prompt/` | 片段化，片段可声明 `evolvable: true` |
| `agent/session_store.py` | `experience/store.py` | 与 episode 索引合并 |
| `llm/` | `runtime/llm/` | 删除 `prompt.py` 兼容层、`factory.py` 对 gateway 的反向依赖 |
| `compress/` | `runtime/context/` | 压缩参数变成 POLICY 资产 |
| `skills/loader,registry,frontmatter` | `genome/kinds/skill.py` | |
| `skills/perf_tracker.py` | `evaluation/outcome.py`（泛化为资产 fitness） | `SKILL_PERF.json` 迁移为 version meta |
| `skills/optimizer.py` | `evolution/mutators/skill_refiner.py` | 改为产出候选版本 |
| `memory/retrieval_analytics, memory_read_hook` | `evaluation/signals/retrieval.py` | |
| `memory/compression_improver` | `evolution/mutators/summary_tuner.py` | |
| `memory/forgetting, conflict_resolver, memory_generator` | `evolution/mutators/memory_curator.py` | 检索部分留在 `memory/` |
| `planner/`, `task/`, `workflow/`, `subagents/delegator` | `orchestration/` | 合并为一套 |
| `subagents/*` | `genome/kinds/subagent.py` + 内置定义改为 `.md` | 规则型 `_execute` 占位实现删除 |
| `cron/`, `heartbeat/` | `evolution/scheduler.py` | 慢回路时钟 |
| `plugins/`, `context_aware/`, `api/` | 删除（需要时再建） | |
| `gateway/`, `commands/`, `adapters/` | `interfaces/` | 新增 `/evolve`、`/feedback` 命令 |

---

## 10. 分阶段实施计划

每一阶段结束都可运行、可发布；后一阶段不阻塞前一阶段的价值。

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **P0 清理** | 修 `pyproject` 包发现、删 `tmp.json` 与空壳模块、补 pytest 依赖 | `pip install .` 后 `auton --help` 可用；测试可运行 |
| **P1 Kernel 下沉** | 核心类型移入 `kernel/`；消除 llm/memory/compress/skills → agent 的反向依赖；加 import-linter | 无循环依赖；lint 规则进 CI |
| **P2 事件化 Runtime** | 补齐事件；学习代码移出主循环改为订阅者；prompt 装配独立 | `loop.py` < 400 行；行为与重构前一致（e2e 测试） |
| **P3 Experience** | Recorder + Episode 切分 + `assets_touched` | 每个会话产出 episode 索引，可按资产查询 |
| **P4 Genome** | 版本化 AssetStore；skill / memory / prompt 片段 / policy 迁移；`/evolve status/diff/rollback` | 任一资产可回滚到任意历史版本 |
| **P5 Evaluation** | tool / retrieval / implicit / explicit 信号 + 抽样 judge；fitness 回写 | 每个 episode 有 Outcome；资产 fitness 可见 |
| **P6 闭环 v1** | Reflect + 改造后的 `MemoryCurator`、`SkillRefiner`、`SummaryTuner`；L1/L2 门禁；scheduler | 一个劣化 skill 能被自动发现 → 提案 → 回放验证 → 发布 → 指标改善，全过程有审计 |
| **P7 闭环 v2** | `SkillMiner`、`PromptFragmentTuner`、`PolicyTuner`、canary、自动回滚、Pruner | 新 skill 从轨迹中自动产生并经人工确认上线 |

建议 P0–P2 先做（纯工程重构，风险低，为后续铺路）；P3–P4 是闭环的数据基础；P5–P6 才真正"活起来"。

---

## 11. 待决策问题

1. **自治级别默认值**：建议 `auto-low`（只有低风险的记忆/摘要自动生效，其余需确认）。是否接受？
2. **Judge 模型**：使用与主 Agent 相同的 provider 的便宜模型，还是允许单独配置（含本地模型）？
3. **兼容性**：重构期间是否需要保持 `~/.auton/` 现有目录结构与命令兼容，还是允许一次性迁移（提供 `auton migrate`）？
4. **金样例冷启动**：初期真实 episode 少，是否接受先内置一小套编程任务 benchmark？
5. **多用户 / 多项目**：genome 是全局一份，还是 全局 + 项目级 overlay（项目内的 skill/记忆覆盖全局）？建议 overlay。
