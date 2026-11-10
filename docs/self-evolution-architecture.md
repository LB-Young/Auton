# Auton 架构设计：自进化 Agent（Greenfield 版）

> 状态：设计稿 v0.2（2026-11-10），从零构建，不考虑现有代码兼容
> 取代 v0.1（基于现有代码的重构方案）

---

## 0. 目标与定义

**Auton 是一个会随使用变强的个人 Agent。** 它每完成一个任务，都会留下可归因的经验；经验被评估和反思后，变成对自身"基因组"的候选修改；候选修改在隔离环境中验证通过后才上线，上线后持续监测，变差就回滚。

衡量"自进化是否有效"的北极星指标（可在 `/evolve report` 中查看）：

| 指标 | 含义 |
|---|---|
| 任务成功率（滚动 30 天） | Outcome = success 的 episode 占比，应持续上升 |
| 用户纠正率 | 需要用户纠正/重问的 episode 占比，应下降 |
| 单任务成本 | tokens / 工具调用 / 耗时，同类任务应下降 |
| 进化有效率 | 已发布变更中，上线后指标确实改善的比例 |
| 回滚率 | 应低且稳定；过高说明验证门禁不够强 |

---

## 1. 设计原则

1. **代码固定，能力是数据。** Agent = 模型（外部）+ Harness（代码，稳定）+ Genome（声明式资产，可进化）。进化只修改 Genome，不修改 Harness 代码。这让进化可审查、可 diff、可回滚，也避免自修改代码带来的不可控性。
2. **事件溯源。** 唯一事实来源是 append-only 事件日志。会话、episode、指标、记忆索引都是日志的投影（projection），因此可以重放、重算、追溯。
3. **归因优先。** 每个 episode 都记录用了哪些资产的哪个版本。没有归因，就没有进化。
4. **评估者独立于被评估者。** 评估规则（Constitution）在 Genome 之外，进化流程无权修改，防止 Agent 通过改标准来"变好"。
5. **先验证再发布，发布后仍可回滚。** 所有变更都走统一管道：提案 → 验证 → 灰度 → 发布 → 监测。
6. **常驻进程。** Auton 以本地守护进程运行。前台处理会话，空闲时在后台进化。CLI、Web、IM 都只是客户端。
7. **人类可读。** Genome 是一个 git 仓库中的 Markdown/YAML 文件，用户可以直接阅读、编辑、回退。

---

## 2. 系统全景

```
 ┌──────────── Clients ─────────────┐
 │  CLI     Web     Slack/飞书/...   │
 └──────────────┬───────────────────┘
                │  本地 API（HTTP + WebSocket 流）
 ┌──────────────▼──────────────────────────────────────────────────────┐
 │ autond（守护进程）                                                    │
 │                                                                      │
 │  ┌────────────── 前台：Runtime ───────────────┐                      │
 │  │ Session → Agent Loop → Model / Tools       │                      │
 │  │        ↑ Context Engine（从 Genome 装配）   │                      │
 │  └───────────────┬────────────────────────────┘                      │
 │                  │ events                                            │
 │  ┌───────────────▼───────────────┐   ┌───────────────────────────┐   │
 │  │ Event Log（SQLite, append-only）│──▶│ Projections               │   │
 │  └───────────────────────────────┘   │ sessions / episodes /     │   │
 │                                      │ asset usage / metrics     │   │
 │                                      └────────────┬──────────────┘   │
 │  ┌────────────── 后台：Evolution Engine ──────────▼──────────────┐   │
 │  │ Assess → Reflect → Propose → Verify(Arena) → Release → Monitor│   │
 │  └───────────────────────────────────────┬───────────────────────┘   │
 │                                          │ git commit / branch       │
 │  ┌───────────────────────────────────────▼───────────────────────┐   │
 │  │ Genome（git 仓库）  skills · knowledge · insights · prompts ·   │   │
 │  │                    roles · tools · policies                     │   │
 │  └────────────────────────────────────────────────────────────────┘   │
 │  Constitution（只读）：安全规则 · 评估 rubric · 进化边界               │
 └──────────────────────────────────────────────────────────────────────┘
```

---

## 3. 进化闭环

```
        ┌─────────────────────────────────────────────────────────┐
        ▼                                                         │
   ① RESOLVE        为本次会话选定每个资产的版本（含灰度分流）      │
        ▼                                                         │
   ② ACT            执行任务，产生事件                             │
        ▼                                                         │
   ③ RECORD         事件 → episode，记录 assets_used               │
        ▼                                                         │
   ④ ASSESS         信号 → Outcome → 回写各资产版本的 fitness       │
        ▼                                                         │
   ⑤ REFLECT        批量分析 episode：失败模式 / 成功模式 / 能力缺口 │
        ▼                                                         │
   ⑥ PROPOSE        Mutator 生成候选修改（git 分支）                │
        ▼                                                         │
   ⑦ VERIFY         Arena 中回放对比 + 回归测试 + 规则检查           │
        ▼                                                         │
   ⑧ RELEASE        灰度 → 合并到 main（或人工审批）               │
        ▼                                                         │
   ⑨ MONITOR        上线后持续比较；劣于父版本则自动 revert ─────────┘
```

### 3.1 三种节奏

| 回路 | 时机 | 做什么 | 门禁 |
|---|---|---|---|
| **快回路** | 会话内，每轮 | 记录用户偏好/事实、工具失败后写"教训"到会话工作区 | 去重 + 冲突检测 |
| **中回路** | 会话结束 | 切分 episode、评估、更新 fitness、沉淀记忆、产出 reflection | 自动 |
| **慢回路** | 空闲 / 每日 / 累计阈值 | 重写或新建 skill、调整 prompt 片段和参数、清理冗余 | Arena 验证 + 灰度（+ 人工） |

---

## 4. Genome：可进化的一切

### 4.1 资产类型

按"知识的种类"划分，而不是按实现划分：

| Kind | 知识类型 | 例子 | 典型来源 |
|---|---|---|---|
| `knowledge` | 陈述性：事实、偏好 | "用户偏好 pnpm"、"项目 X 的部署在周五冻结" | 快回路 |
| `skill` | 程序性：怎么做某类任务 | `github-pr/SKILL.md`（步骤、坑、检查清单） | 慢回路 |
| `insight` | 元认知：跨任务的策略/教训 | "修改配置文件前先读完整文件"、"测试失败先看最早的报错" | 中/慢回路 |
| `prompt` | 身份与行为片段 | 回复风格、规划习惯（只有标记为 evolvable 的片段） | 慢回路 |
| `role` | 子 Agent 定义 | `reviewer.md`：职责、可用工具、提示词 | 慢回路 |
| `tool` | 可执行组合工具 | 在沙箱中运行的脚本 + schema（如 `release-notes.py`） | 慢回路，必须人工审批 |
| `policy` | 数值/规则参数 | 上下文压缩阈值、重试次数、并行度、检索 top-k | 慢回路 |

每个资产都是一个目录或文件，带 frontmatter：

```markdown
---
id: skill/github-pr
kind: skill
scope: global            # global | project:<hash>
origin: evolved          # builtin | user | evolved
evolvable: true
triggers: ["create PR", "pull request", "提 PR"]
requires_tools: [bash, git]
---
# 创建 Pull Request
1. 先确认当前分支与 base 分支 ...
```

### 4.2 存储：直接用 git

```
~/.auton/genome/                 # 一个 git 仓库
├── knowledge/
├── skills/<name>/SKILL.md
├── insights/
├── prompts/
├── roles/
├── tools/<name>/{tool.yaml, main.py}
├── policies/*.yaml
└── projects/<project-hash>/     # 项目级 overlay，同结构，优先级高于全局
```

映射关系：

| 进化概念 | git 实现 |
|---|---|
| 资产版本 | 文件在某个 commit 中的 blob hash |
| Genome 快照 | commit hash |
| 提案 | 分支 `proposal/<id>`，commit message 写 rationale + 证据 episode |
| 发布 | merge 到 `main` |
| 回滚 | `git revert` |
| 谱系 / 审计 | `git log` |
| 用户手改 | 用户直接 commit，`origin=user` 的文件受保护 |

fitness 等运行统计**不进 git**（频繁变化），存在 SQLite，按 `(asset_id, blob_hash)` 索引。

### 4.3 Resolve：为会话选版本

`GenomeResolver` 在会话开始时生成 `Snapshot`：

1. 以 `main` 为基础，叠加项目 overlay。
2. 对处于灰度中的资产，用 **Thompson sampling** 在"当前版本 / 候选版本"间选择（按两者 fitness 的 Beta 分布采样）。好的候选自然获得更多流量，差的自然被淘汰，同时得到在线 A/B 数据。
3. 产出 `Snapshot{id, base_commit, overrides: {asset_id: blob_hash}}`，写入事件日志。

---

## 5. Runtime

### 5.1 组件

| 组件 | 职责 |
|---|---|
| **Model Gateway** | 统一的 provider 接口（Anthropic / OpenAI 兼容 / 本地）；流式；重试；按角色路由模型（主模型、便宜模型、judge 模型） |
| **Tool Host** | 内置工具（read/write/edit/bash/grep/glob/web）、MCP 客户端、Genome 中的 `tool` 资产；统一权限检查与沙箱 |
| **Context Engine** | 每轮装配上下文：Constitution 核心 + prompt 片段 + 相关 skills / insights / knowledge（检索）+ 会话历史（含压缩） |
| **Agent Loop** | 最小循环：装配上下文 → 调模型 → 执行工具 → 判断继续/压缩/结束。只发事件，不含任何学习逻辑 |
| **Roles / Delegation** | 子 Agent = 用 `role` 资产配置的另一个 Agent Loop 实例；规划、审查、调试都是 role，不是硬编码类 |

### 5.2 Context Engine 的检索

资产按需加载（渐进披露），不一次塞进 system prompt：

- **常驻**：Constitution 核心、`prompt` 片段、skill/role 的一行目录。
- **按需**：根据当前任务检索 top-k 的 knowledge、insight，以及匹配的完整 SKILL.md。
- 检索使用 SQLite FTS5（BM25）+ 可选 embedding（sqlite-vec），无需额外的向量数据库。
- **每次注入都发 `AssetUsed` 事件**，这是归因的数据来源。

### 5.3 事件模型

所有事件都有 `id, ts, session_id, episode_id?, type, payload`。

| 事件 | 关键字段 |
|---|---|
| `SessionStarted` | snapshot_id, client, project |
| `UserMessage` / `AssistantMessage` | 内容引用 |
| `ModelCall` | model, tokens_in/out, latency |
| `ToolCall` / `ToolResult` | tool, args 摘要, ok, error, duration |
| `AssetUsed` | asset_id, blob_hash, how（injected / retrieved / invoked） |
| `ContextCompacted` | before / after tokens |
| `Feedback` | 显式反馈（👍👎、文字） |
| `SessionEnded` | reason |
| `Evolution.*` | Proposal 创建、验证结果、发布、回滚（进化流程自身也被记录） |

---

## 6. Experience 与 Assess

### 6.1 Episode

一个 episode = 一个用户意图从提出到结束。切分规则：新的用户消息若被小模型判断为"新任务"则开新 episode，否则（追问、纠正、继续）归入当前 episode。

```python
@dataclass
class Episode:
    id: str
    session_id: str
    snapshot_id: str
    intent: str                      # 小模型归纳的一句话任务描述
    task_type: str                   # 聚类得到的类别，用于同类对比
    event_range: tuple[int, int]
    assets_used: dict[str, AssetUse] # asset_id -> (blob_hash, how, count)
    metrics: Metrics                 # turns, tool_calls, tool_errors, tokens, duration
    outcome: Outcome | None
```

### 6.2 信号

| 来源 | 信号 | 成本 |
|---|---|---|
| 工具 | 错误率、重试、非零退出、测试结果 | 零 |
| 行为 | 用户纠正、重问、中断、放弃、"谢谢/好的" | 小模型分类 |
| 显式 | 👍👎、`/feedback` | 零 |
| 结果 | 产物检查：测试是否通过、文件是否按要求生成 | 视任务 |
| Judge | 按 Constitution 中固定 rubric 打分（抽样） | 中 |

聚合为 `Outcome{score ∈ [-1,1], confidence, label}`。置信度取决于信号的种类和数量，低置信度的 episode 在进化中权重低。

### 6.3 Credit Assignment（功劳分配）

Outcome 按以下方式分配给 `assets_used`：

- `invoked`（如执行了某 skill 的流程）权重最高，`injected`（常驻）权重最低。
- 用 **同类任务的基线** 计算增量：`credit = outcome − baseline(task_type)`，避免"简单任务里用到的资产都显得很好"。
- 每个 `(asset, blob_hash)` 维护 Beta 分布形式的 fitness，供 Resolver 采样和 Monitor 比较。

---

## 7. Evolution Engine

### 7.1 Reflect

定期（或累计 N 个新 episode 后）批量运行：

- **失败聚类**：同类任务中 Outcome 低的 episode 聚类，LLM 总结共同原因并定位可疑资产 → `Diagnosis(kind=failure_mode)`。
- **成功模式**：同一类任务多次成功、步骤相似但没有对应 skill → `Diagnosis(kind=gap)`。
- **低效**：成功但成本显著高于同类 → `Diagnosis(kind=inefficiency)`。
- **冗余/冲突**：从未被使用、或内容互相矛盾的资产 → `Diagnosis(kind=redundancy)`。

### 7.2 Mutators

```python
class Mutator(Protocol):
    name: str
    kinds: set[AssetKind]
    cadence: Cadence                        # fast | medium | slow
    def accepts(self, d: Diagnosis) -> bool: ...
    async def propose(self, d: Diagnosis, ctx: EvolveContext) -> list[Proposal]: ...
```

| Mutator | 输入 | 输出 |
|---|---|---|
| `KnowledgeCurator` | 会话中的事实/偏好 | 新增/合并/废弃 knowledge |
| `InsightDistiller` | failure_mode / inefficiency | 新增或修订 insight |
| `SkillRefiner` | 某 skill 的失败 episode | skill 的修订版 |
| `SkillMiner` | gap（多次相似成功轨迹） | 新 skill |
| `RoleTuner` | 子 Agent 表现 | role 定义修订 |
| `PolicyTuner` | 指标与参数的关系 | policy 数值调整 |
| `ToolSmith` | 反复出现的多步机械操作 | 新 tool（必须人工审批） |
| `Gardener` | redundancy | 合并、废弃、删除资产，控制 Genome 规模 |

```python
@dataclass
class Proposal:
    id: str
    diagnosis_id: str
    branch: str                  # proposal/<id>
    changes: list[AssetChange]   # create / modify / retire
    rationale: str
    evidence: list[str]          # episode ids
    risk: Risk                   # low / medium / high（由 Guard 判定，不由 Mutator 自报）
    eval_plan: EvalPlan
```

### 7.3 Verify：Arena

Arena 是离线评测环境，比较"候选 Genome"与"当前 Genome"在同一批任务上的表现。

- **任务集**
  - 目标集：Diagnosis 的证据 episode（候选必须在这些上变好）。
  - 回归集：同类高分 episode + 内置 benchmark（候选不能在这些上变差）。
- **隔离执行**：每个任务在临时工作区（目录副本或 git worktree）中运行；只读工具真实执行；外部副作用（网络写、发消息）用记录的结果 stub。
- **对比**：硬指标（测试通过、工具错误、tokens）+ judge 盲评两两对比（随机左右位置）。
- **判定**：目标集显著改善且回归集不显著变差 → `verified`。
- **成本控制**：按风险等级决定样本量；低风险资产只做规则检查。

### 7.4 Release 与 Monitor

| 风险 | 例子 | 流程 |
|---|---|---|
| low | knowledge、insight 小修 | 规则检查 → 直接合并 |
| medium | skill 修订、policy 调整 | Arena → 灰度（Thompson sampling）→ 合并 |
| high | 新 skill、prompt 片段、role、user 资产 | Arena → **人工审批** → 灰度 → 合并 |
| critical | 新 tool | Arena + 代码审查 → **人工审批** → 合并 |

Monitor：合并后在线比较新旧版本的 fitness，若在足够样本下显著变差，则自动 `git revert` 并把该 Diagnosis 标记为"已尝试"，避免反复提出同样的修改。

---

## 8. Constitution 与 Guard（不可进化区）

**Constitution**（随代码发布，Genome 之外，只读）：

- 安全规则：危险命令、路径边界、密钥处理、外部副作用需确认。
- 评估 rubric 与信号权重。
- 进化边界：哪些资产类型可进化、各类型风险等级、预算上限。
- 核心身份与诚实性要求。

**Guard**（代码实现，拦截所有 Proposal）：

- 拒绝修改 Constitution、拒绝放宽权限、拒绝修改 `origin=user` 的资产（只能以建议形式提出）。
- 判定风险等级（不信任 Mutator 的自报）。
- 预算：每日进化 token 上限、每资产每日最多一次发布、并发灰度数上限。
- 规模：skill / knowledge / insight 数量上限，超出时优先触发 `Gardener`。
- 内容扫描：防止把密钥、个人敏感信息写进 Genome。

---

## 9. 用户控制面

| 命令 | 作用 |
|---|---|
| `/feedback [+/-] [说明]` | 显式反馈当前 episode |
| `/evolve status` | 进行中的提案、灰度、最近发布与回滚 |
| `/evolve show <proposal>` | diff + rationale + 证据 + Arena 结果 |
| `/evolve approve / reject <proposal>` | 人工审批 |
| `/evolve rollback <asset>` | 立即回滚 |
| `/evolve pause / resume` | 暂停/恢复进化 |
| `/evolve report` | 北极星指标趋势 |
| `/genome ls / show / edit` | 浏览和手动编辑资产 |

配置 `evolution.autonomy`：`off`（只记录）/ `suggest`（只提案）/ `auto-low`（默认，低风险自动）/ `auto`（中风险也自动）。

---

## 10. 工程结构

### 10.1 技术栈

- Python 3.12、asyncio、Pydantic v2
- 存储：SQLite（WAL）存事件日志、投影、fitness、FTS 索引；git（pygit2 或 CLI）存 Genome
- 服务：Starlette/FastAPI + WebSocket；CLI 用 Typer + Rich
- 沙箱：首期用子进程 + 工作目录隔离 + 命令白名单；后期可选容器
- 质量：ruff、mypy --strict、pytest、import-linter

### 10.2 目录

```
auton/
├── kernel/          # 核心类型、事件定义、EventLog、配置、ID、时钟。不依赖任何其他包
├── constitution/    # 只读规则、rubric、进化边界（数据 + 加载器）
├── model/           # Model Gateway 与 providers
├── tools/           # Tool Host、内置工具、MCP、权限、沙箱
├── genome/          # git 存储、资产类型、Resolver、fitness 存储
├── context/         # Context Engine：装配、检索、压缩
├── agent/           # Agent Loop、Session、Roles/Delegation
├── experience/      # 投影：sessions、episodes、asset usage、metrics
├── assess/          # 信号、judge、Outcome、credit assignment
├── evolve/          # reflect、mutators/、proposal、arena、release、monitor、guard、scheduler
├── server/          # autond：API、会话管理、后台任务调度
└── clients/         # cli/、web/、im/（slack、feishu …）
```

### 10.3 依赖规则（CI 强制）

```
clients → server → evolve → assess → experience → agent → context → genome/tools/model → kernel
                                                               constitution → kernel
```

- `agent` 及以下不得 import `experience / assess / evolve`。学习只能通过订阅事件发生。
- `assess` 不得 import `evolve`（评估独立于进化）。
- 只有 `evolve.release` 能写 Genome 的 `main` 分支。

---

## 11. 端到端示例

1. 用户多次让 Auton 创建 PR。没有专门 skill，Agent 每次都要摸索，且有两次漏指定 base 分支，被用户纠正。
2. **Record/Assess**：这几个 episode 被归为 `task_type=create-pr`；有纠正信号的 Outcome 为 partial。
3. **Reflect**：发现 `gap`（5 次相似的成功/部分成功轨迹，无对应 skill）和 `failure_mode`（漏 base 分支）。
4. **Propose**：`SkillMiner` 从成功轨迹中提炼出 `skills/github-pr/SKILL.md`，把"确认 base 分支"作为第一步；提交到 `proposal/0042`。
5. **Guard**：新 skill → 风险 high。
6. **Verify**：Arena 回放这 5 个任务和 20 个回归任务；目标集纠正率 2/5 → 0/5、平均 turns 下降 30%，回归集无变差。
7. **Release**：`/evolve status` 提示待审批；用户查看 diff 后 approve；进入灰度，Thompson sampling 很快把流量导向新 skill；合并到 main。
8. **Monitor**：两周后，create-pr 任务成功率稳定提升；`/evolve report` 中可见。若变差，则自动 revert。

---

## 12. 实施路线

| 里程碑 | 内容 | 完成标志 |
|---|---|---|
| **M1 能用的 Agent** | kernel、model、tools、context（无检索）、agent loop、CLI、EventLog | 能在 CLI 完成编程任务，全部事件入库 |
| **M2 Genome** | git 存储、资产类型、Resolver、按需检索、`/genome` 命令、AssetUsed 事件 | 手写的 skill/knowledge 能被正确检索使用并记录归因 |
| **M3 经验与评估** | episode 切分、信号、Outcome、credit、fitness、`/feedback` | 每个 episode 有分数，每个资产有 fitness |
| **M4 闭环 v1（低风险）** | Reflect、KnowledgeCurator、InsightDistiller、Guard、Release、Monitor | knowledge/insight 能自动沉淀并在劣化时回滚 |
| **M5 Arena** | 任务回放、隔离工作区、judge 对比、内置 benchmark | 能对任意 Proposal 给出可信的对比报告 |
| **M6 闭环 v2（中/高风险）** | SkillRefiner、SkillMiner、PolicyTuner、灰度、人工审批、`/evolve` 全套 | 完成第 11 节的端到端示例 |
| **M7 扩展** | autond 常驻 + Web/IM 客户端、Roles、ToolSmith、Gardener、`/evolve report` | 多客户端共享一个持续进化的 Genome |

M1 到 M3 先打好"可观测、可归因"的地基；M4 起闭环开始真正运转。

---

## 13. 待决策问题

1. **默认自治级别**：建议 `auto-low`。
2. **Judge 与辅助模型**：建议主模型之外单独配置一个便宜模型，负责意图归纳、信号分类、judge；可选本地模型。
3. **Genome 共享**：是否需要导出/导入，或在多台设备间同步（git remote 天然支持）？
4. **内置 benchmark**：首期覆盖哪些任务类型（建议编程任务为主：改 bug、写测试、提 PR、重构）？
5. **沙箱强度**：首期接受"子进程 + 目录隔离"，还是一开始就上容器？
