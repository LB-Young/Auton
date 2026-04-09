# Auton 个人 Agent 助手 - 功能规格

> 参考了 Claude Code v2.1.88 和 OpenCode 的架构设计，采纳了经过验证的核心模式。

## 1. 核心定位

**Auton** 是一个个人自主 Agent 助手，旨在帮助用户完成复杂任务、记忆个人偏好、管理项目上下文、并与外部工具链深度集成。它是用户意志的延伸——理解目标、规划路径、执行动作、汇报结果。

**核心设计理念**：**以 SessionProcessor 为执行核心，以事件总线为数据血液，以工具为能力插件。**（源自 OpenCode/Claude Code 共同验证的最佳实践）

---

## 2. 功能模块

### 2.1 对话交互（Conversation）

用户与 Auton 之间的基础交互层。

- **自然语言理解**：解析用户指令中的意图、实体、时间、上下文
- **多轮对话管理**：支持复杂任务的多轮澄清和迭代
- **主动询问**：任务不明确时主动询问，而非盲目猜测
- **回复风格控制**：用户可指定回复的详细程度、语言风格（简洁/详细）
- **多语言支持**：中文、英文双语自由切换

### 2.2 命令系统（Command System）

斜杠命令（`/xxx`）是第一公民的统一交互接口，与自然语言对话并列。

- **命令注册表**：所有命令统一注册，SessionProcessor 统一调度
- **动态启用/禁用**：命令可根据上下文状态动态开启/关闭
- **结构化输出**：命令结果有标准格式，便于 UI 渲染和自动化脚本
- **命令覆盖命令**：模型在推理过程中可主动调用命令（如调用 `/plan` 进入计划模式）

**标准命令集**：`/help` `/model` `/memory` `/tasks` `/compact` `/plan` `/config` `/session` `/workflow` `/mcp`

### 2.3 任务管理（Task Management）

对复杂任务进行分解、执行与追踪。

#### 2.3.1 任务状态机

```
pending → running → completed
                   ↘ failed
                   ↘ killed
```

任务状态不可逆单向转移，`is_terminal(status())` 作为边界守卫，防止向已终止任务注入消息。

#### 2.3.2 功能

- **任务分解**：将高层目标自动拆解为可执行的子任务步骤
- **进度追踪**：实时显示任务进度，支持暂停、恢复、取消
- **任务依赖**：识别子任务间的依赖关系，按序或并行执行
- **子代理委托**：将子任务委托给专门的 Agent 并行处理
- **任务历史**：记录所有任务执行历史，支持回顾和复盘
- **优先级排序**：根据用户指定或推断的优先级调度任务
- **输出持久化**：任务输出写入磁盘文件，支持增量读取和断点续执

### 2.4 记忆系统（Memory System）

持久化存储用户偏好、项目上下文和会话历史。系统支持**项目模式**与**无项目模式**两种打开方式，记忆的组织与加载策略不同。

#### 2.4.1 核心原则：存与用完全分离

存储（Store）与检索（Use）是两个完全独立的子系统，各自职责清晰：

| 子系统 | 模块 | 职责 |
|--------|------|------|
| **存储** | `session_store.py` | 将会话中所有事件**只追加**写入 jsonl，存储本身不做任何压缩/过滤 |
| **检索** | `memory_manager.py` | 从 jsonl 中读取和检索，按模式限定范围，按需加载到 context |

两者通过 jsonl 文件解耦：存储只管 append，检索只管读，互不感知对方内部逻辑。

#### 2.4.2 会话日志存储（Append-only）

会话执行过程中，**每发生一个事件就 append 一行到 jsonl**，永不覆盖。参考 Claude Code 的 append-only 原则：

- 每个会话对应一个 `session_{timestamp}.jsonl` 文件
- jsonl 中每行是一个完整的结构化事件（user-message / text-delta / tool-call / tool-result / step-* 等）
- 压缩（compact）时，**原始消息和压缩摘要同时 append 到同一个 jsonl**，不在原位置修改：
  ```
  {"type": "user-message", "content": "帮我重构 auth 模块"}
  {"type": "tool-call", "tool": "edit", "file": "src/auth/token.py", "old": "...", "new": "..."}
  {"type": "compact", "before_count": 28, "summary": "保留首尾消息，中间28条压缩为摘要"}
  {"type": "user-message", "content": "继续添加单元测试"}
  ...
  ```
- **原始消息永远保留**：压缩后，原始行仍然在 jsonl 中，可完整回放，不丢失任何信息

会话结束后，session jsonl 写入对应文件夹的 `sessions/` 目录，然后触发蒸馏更新 `memory/`。

#### 2.4.3 打开模式

| 模式 | 触发条件 | 记忆加载策略 | session 记录检索范围 |
|------|----------|-------------|---------------------|
| **项目模式** | 在项目目录（包含 `.auton/`）中启动 | 项目记忆整块加载 + 长期记忆按相关度检索 | **当前项目**的 `projects/{project}/sessions/*.jsonl` |
| **无项目模式** | 在非项目目录中启动 | 全局记忆按日期加载 + 长期记忆按相关度检索 | **当前日期**的 `dates/{YYYY-MM-DD}/sessions/*.jsonl` |

- **项目目录判定**：当前工作目录或其任意父目录存在 `.auton/` 目录
- **session 记录**：指会话的 jsonl 日志文件，按项目或日期隔离存放
- 两种模式共享底层存储结构，区别在于检索范围不同

#### 2.4.4 记忆层级与存储结构

Auton 采用**双轨制**记忆存储：按项目隔离（项目模式）和按日期组织（无项目模式）。

**顶层目录结构**：
```
~/.auton/
├── auton.md              # 跨项目用户偏好（最高优先级加载）
├── projects/              # ★ 项目模式：每个项目一个文件夹
│   └── {project-name}/
│       ├── sessions/     # 项目所有 session 的 jsonl 日志
│       │   ├── session_2024-01-15T10-00-00.jsonl
│       │   └── session_2024-01-20T14-30-00.jsonl
│       └── memory/       # ★ 项目沉淀的长期记忆
│           ├── MEMORY.md       # ★ 记忆索引（顶层入口）
│           ├── SUMMARY.md      # session 分段摘要
│           ├── user_role.md    # 用户身份与偏好
│           ├── feedback_*.md   # 行为规则
│           └── project_*.md    # 项目背景与决策
├── dates/                # ★ 无项目模式：按日期组织
│   └── {YYYY-MM-DD}/
│       ├── sessions/     # 当日所有 session 的 jsonl 日志
│       │   ├── session_2024-01-15T10-00-00.jsonl
│       │   └── session_2024-01-15T14-30-00.jsonl
│       └── memory/       # ★ 当日沉淀的长期记忆
│           ├── MEMORY.md       # ★ 记忆索引（顶层入口）
│           ├── SUMMARY.md      # session 分段摘要
│           └── user_*.md       # 用户相关内容
└── vector_db/            # 跨项目长期记忆向量库（ChromaDB）
```

**五类记忆**：

| 层级 | 存储位置 | 生命周期 | 组织方式 | 加载策略 |
|------|----------|----------|----------|----------|
| **会话记忆** | `AppState.messages` | 会话级，随会话结束消失 | 消息历史 | 直接存入上下文 |
| **项目记忆** | `projects/{project}/` | 项目级，同一项目所有 Session 共享 | **按项目隔离**，sessions + memory 分开 | 项目模式下整块加载 memory/ |
| **全局记忆** | `dates/{YYYY-MM-DD}/` | 日期级，当日所有会话 | **按日期组织**，sessions + memory 分开 | 无项目模式加载当日 memory/ |
| **跨项目记忆** | `vector_db/` | 用户级，跨项目共享 | **向量检索**，ChromaDB | 按 query 相关度加载 top-k 块 |
| **工作空间** | `workspace/` | 任务级，临时 | 临时文件，不进入 AI context | 不加载 |

#### 2.4.5 跨项目长期记忆（向量库）

跨项目长期记忆（用户画像、偏好、跨项目知识）不能一次性全量加载到系统提示词，采用**向量检索 + 按需分块**策略：

- **分块规则**：按语义单元分块（一个主题/一类知识 = 一个 chunk），而非按日期或文件边界
- **检索流程**：`query embedding` → 向量相似度检索 top-k 块 → 加载到 context
- **向量库结构**：
  ```
  ~/.auton/vector_db/                  # Chroma 向量数据库
  ├── chunks/                          # 向量数据
  └── metadata.jsonl                   # chunk 元数据
  ```
- **chunk metadata**（存入 metadata.jsonl）：
  ```json
  {"id": "chunk_001", "tags": ["偏好", "技术栈"], "summary": "Go/Python+React技术栈偏好", "updated_at": "2024-01-15"}
  ```

#### 2.4.6 项目记忆

项目模式下，记忆存储在 `~/.auton/projects/{project}/` 目录下，**严格分离 session 记录和沉淀记忆**：

**目录结构**：
```
~/.auton/projects/{project-name}/
├── sessions/                    # ★ 项目所有 session 的原始 jsonl 日志
│   ├── session_2024-01-15T10-00-00.jsonl
│   └── session_2024-01-20T14-30-00.jsonl
└── memory/                      # ★ 项目沉淀的长期记忆（session 结束后蒸馏生成）
    ├── MEMORY.md                # ★ 记忆索引（顶层入口，无 frontmatter）
    ├── SUMMARY.md               # 所有 session 的 block 逐行摘要
    ├── user_role.md             # 用户身份、偏好（type: user）
    ├── feedback_testing.md      # 测试策略行为规则（type: feedback）
    ├── project_context.md       # 项目背景与关键决策（type: project）
    └── reference_runbook.md     # 外部引用指针（type: reference）
```

**`MEMORY.md`（索引）**：无 frontmatter，一行一个入口，最多 200 行。
```markdown
本文档是项目记忆顶层索引，详细的会话分段总结见 [memory/SUMMARY.md](memory/SUMMARY.md)。

- [用户角色与偏好](memory/user_role.md) — 后端工程师，偏好最小可运行解先迭代。
- [测试策略偏好](memory/feedback_testing.md) — 涉及数据库必须真实集成测试。
- [项目会话分段总结](memory/SUMMARY.md) — 记录了本项目所有 session 的详细分段总结。
```

**主题文件格式**（带 YAML frontmatter）：
```markdown
---
name: 用户角色与交互偏好
description: 记录用户技术背景与沟通偏好
type: user
---

用户关注点：可维护性、可验证性、边界条件覆盖。
执行偏好：未经确认不提交，不执行高风险命令。
```

#### 2.4.7 全局记忆与闲聊模式加载策略

无项目模式下，全局记忆存储在 `~/.auton/dates/{YYYY-MM-DD}/` 目录下，**严格分离 session 记录和沉淀记忆**：

**目录结构**：
```
~/.auton/dates/{YYYY-MM-DD}/
├── sessions/                    # ★ 当日所有 session 的原始 jsonl 日志
│   ├── session_2024-01-15T10-00-00.jsonl
│   └── session_2024-01-15T14-30-00.jsonl
└── memory/                      # ★ 当日沉淀的长期记忆
    ├── MEMORY.md                # ★ 记忆索引（顶层入口）
    ├── SUMMARY.md               # 当日所有 session 的 block 逐行摘要
    └── user_*.md               # 当日用户相关内容
```

**闲聊模式（无项目）启动时，加载策略如下**：

| 加载内容 | 说明 |
|---------|------|
| **当日日期文件夹的 memory/MEMORY.md** | `~/.auton/dates/{今天}/memory/MEMORY.md`，必加载 |
| **昨日日期文件夹的 memory/MEMORY.md** | `~/.auton/dates/{昨天}/memory/MEMORY.md`，必加载 |
| **近 2 天有变动的项目 memory/MEMORY.md** | 扫描所有 `~/.auton/projects/*/memory/MEMORY.md`，只加载 mtime 在 48 小时内的 |

**加载示例**（今天是 2024-01-20）：
```
已加载：
  - ~/.auton/dates/2024-01-20/memory/MEMORY.md    # 当日
  - ~/.auton/dates/2024-01-19/memory/MEMORY.md    # 昨日
  - ~/.auton/projects/project-A/memory/MEMORY.md   # 项目A 今日修改过
  - ~/.auton/projects/project-B/memory/MEMORY.md   # 项目B 昨日修改过

未加载（超过48小时未修改）：
  - project-C 的 memory/MEMORY.md（最后修改于 2024-01-10）
  - project-D 的 memory/MEMORY.md（最后修改于 2024-01-15）
```

> **注意**：项目 MEMORY.md 扫描 `~/.auton/projects/*/memory/` 目录，跨所有项目扫描以复用近期上下文。

#### 2.4.8 `auton.md`：跨项目用户偏好（auton 专属）

`auton.md` 存放跨项目通用的用户偏好，文件名固定为 `auton.md`，可在三处出现：

| 位置 | 说明 | 优先级 |
|------|------|--------|
| `~/.auton/auton.md` | 用户全局偏好 | 高 |
| `{项目根}/.auton/auton.md` | 当前项目偏好覆盖 | 中 |
| `{auton源码}/.auton/auton.md` | Auton 内置默认偏好 | 低 |

**加载规则：取并集，同键冲突时高优先级覆盖低优先级**

#### 2.4.9 指针文件机制

记忆以指针文件而非直接内容存储——SUMMARY.md 中只存摘要和路径，LLM 在需要时才加载完整内容。**这是 Claude Code 记忆系统的核心设计哲学：失败尝试不记记忆（防止坏习惯沉淀）。**

#### 2.4.10 记忆生成时机

| 时机 | 动作 |
|------|------|
| **compaction 时** | 追加 `compact` 事件到 jsonl，同时触发蒸馏：提取值得沉淀的信息，追加到当前模式下的 `memory/MEMORY.md` + 主题文件 |
| **每日首次启动时** | 扫描昨日对应文件夹（项目或日期）的 session jsonl，提取主题，更新 `memory/MEMORY.md` |
| **会话结束时** | 将 session jsonl 写入当前对应文件夹的 `sessions/` 目录，然后触发蒸馏更新 `memory/` |
| **用户显式要求** | 用户说"记住..."时，直接追加/编辑对应模式下的 `memory/MEMORY.md` 或主题文件 |
| **compaction 前 flush** | compaction 前先 silent turn 提醒 agent 保存重要上下文 |

#### 2.4.11 记忆类型（参考 Claude Code）

| type | 用途 | 典型文件名 |
|------|------|-----------|
| `user` | 用户身份、偏好、沟通风格 | `user_role.md` |
| `feedback` | 用户反馈与行为规则 | `feedback_testing.md` |
| `project` | 项目背景、关键决策、约束 | `project_auth_context.md` |
| `reference` | 外部资源指针（链接、文档） | `reference_runbook.md` |

#### 2.4.12 三层检索架构：jsonl → SUMMARY.md → MEMORY.md

jsonl 中的对话内容通过**两层摘要**逐步提炼，最终汇入 MEMORY.md。检索时逆向逐层定位：

**项目模式检索路径**：
```
query → projects/{project}/memory/MEMORY.md（顶层索引）
       → projects/{project}/memory/SUMMARY.md（分段详细摘要，找到 block 序号）
           → projects/{project}/sessions/*.jsonl（按 block 序号读取原始段落）
```

**无项目模式检索路径**：
```
query → dates/{YYYY-MM-DD}/memory/MEMORY.md（顶层索引）
       → dates/{YYYY-MM-DD}/memory/SUMMARY.md（分段详细摘要，找到 block 序号）
           → dates/{YYYY-MM-DD}/sessions/*.jsonl（按 block 序号读取原始段落）
```

**第一层：SUMMARY.md（每日/每项目一个，记录所有 jsonl 的分段详细摘要）**

会话结束后，对该日期/项目下的所有 jsonl，逐个 jsonl、逐个 block 生成详细总结，合并为一个 SUMMARY.md：

**SUMMARY.md 格式**（每天/每个项目一个，记录该文件夹下所有对话的分段总结）：
```markdown
# 摘要索引：2024-01-15（全局记忆）

本文档记录当日所有对话的分段总结，每个 block 对应 jsonl 中一个完整的话题/任务段，
包含该段的参与者意图、关键决策、主要结论和待跟进事项，供后续检索和上下文复用。

## session_2024-01-15T10-00-00.jsonl
- block_001: 用户要求重构 auth 模块（token 刷新逻辑），Agent 分析后决定替换 token.py 中的过期刷新机制，
  涉及 src/auth/token.py、src/auth/client.py、src/config.py 共 3 个文件，修改前先确认了向后兼容需求。
- block_002: 在重构完成后，Agent 主动提出添加单元测试，用户同意，测试覆盖了 token 刷新的正常流程、token 过期、
  刷新失败重试、网络异常 4 个分支，使用 unittest.mock 模拟外部依赖。
- block_003: Agent review 了同事提交的 PR #42（改动 src/api/user.py），提出 3 条改进意见：
  1) 建议将 validate_user_input 改为类型注解而非断言；2) 建议对 /user/:id 返回 404 而非 403；
  3) 指出缺少对空字符串 user_id 的边界条件处理。

## session_2024-01-15T14-30-00.jsonl
- block_001: 用户闲聊讨论 Python 类型提示取舍，涉及 Protocol vs ABC vs duck typing 的工程实践差异，
  用户明确倾向使用 Protocol 代替 ABC，认为可维护性更好，Agent 给出了具体代码示例对比。
- block_002: 用户提到最近在学习 Rust，通过写小工具（如文件批量重命名、JSON 美化工具）来学习，
  表达了对 Rust 所有权的理解困惑，Agent 用 Python 的引用计数做了类比解释。
```

**每行格式**：`block_序号: <详细总结>`
- `block_序号` 与 jsonl 中的 block 编号一一对应
- 总结应包含：该 block 的参与者意图、关键决策/结论、涉及的具体文件/模块、待跟进事项
- 足够详细，让 LLM 仅凭 SUMMARY.md 就能判断该 block 是否与当前 query 相关

**第二层：MEMORY.md 索引（从 SUMMARY.md 进一步提炼）**

MEMORY.md 从 SUMMARY.md 中提取高价值条目，按主题聚合，注明 SUMMARY.md 的性质：
```markdown
- [auth 模块重构（2024-01-15）](SUMMARY.md#session_2024-01-15T10-00-00:block_001) — 替换 token.py 刷新逻辑，涉及 token.py/client.py/config.py，向后兼容。
- [token 单元测试（2024-01-15）](SUMMARY.md#session_2024-01-15T10-00-00:block_002) — 添加单元测试，覆盖 4 个分支，mock 外部依赖。
- [Python 类型提示讨论（2024-01-15）](SUMMARY.md#session_2024-01-15T14-30-00:block_001) — 倾向 Protocol 代替 ABC，可维护性更优。
```

**完整检索流程**：

```
用户 query
  → 检索 MEMORY.md（一级匹配，找到相关条目）
  → 读取对应 SUMMARY.md（二级匹配，找到 jsonl_range）
  → 读取 jsonl 指定行范围（三级，精确定位原始内容）
  → 将 jsonl 原文片段追加到 context
```

**为什么需要中间层**：
- jsonl 行数多、噪声高，不适合直接做语义检索
- SUMMARY.md 浓缩了每段的语义，去掉了工具调用噪声
- MEMORY.md 只保留高价值结论，容量极小但可能缺细节
- 中间层弥合了两者的粒度差异，支持"索引粗定位 → 细节精读取"

#### 2.4.13 记忆冲突、召回去重与过载管理

##### 一、auton.md 写入冲突管理

三处 `auton.md`（`~/.auton/auton.md`、`{项目根}/.auton/auton.md`、`{auton源码}/.auton/auton.md`）采用**写时冲突检测**机制：

**写入流程**：
```
1. 读取目标 auton.md 当前内容
2. 计算内容语义指纹（semantic fingerprint，按 section 分段）
3. 检测写入内容是否与已有内容冲突：
   - 相同 section + 相同语义 → 静默跳过（避免重复）
   - 相同 section + 语义矛盾 → 标记为冲突，追加冲突标记，不直接覆盖
   - 不同 section → 正常追加
4. 写入时记录来源标记（source: ~/.auton / 项目 / 内置）
```

**auton.md 内容格式（带来源与时间戳）**：
```markdown
# 用户偏好（跨项目通用）

## 编码规范
<!-- source: ~/.auton/auton.md | updated: 2024-01-15 -->
- 优先使用类型提示，不接受 bare `Any`

## 执行约束
<!-- source: project-X/.auton/auton.md | updated: 2024-01-16 -->
- 项目X禁止使用 `eval`
<!-- conflict: 与内置规则冲突（source: 内置 | updated: 2024-01-10）
     内置规则: 允许 eval，但必须记录日志 -->
```

**冲突处理策略**：

| 冲突类型 | 处理方式 |
|---------|---------|
| 相同语义重复写入 | 静默跳过，不重复追加 |
| 同一 section 语义矛盾 | 追加冲突标记，保留双方，提示用户确认 |
| 新 section 追加 | 正常追加，无冲突 |
| 用户偏好 vs 内置默认 | 用户偏好优先（高优先级覆盖低优先级） |

##### 二、query 召回去重（同一来源）

当多层检索命中同一内容时（常见于 SUMMARY 和 jsonl 都命中了同一语义段），使用**语义指纹去重**：

```
召回结果列表
  → 计算每个结果的 semantic_hash（基于核心语义，非行号/时间戳）
  → 相同 hash 只保留一个（保留相关性最高的一个）
  → 保留结果附带来历标记（来自 MEMORY.md / SUMMARY.md / jsonl）
```

##### 三、query 召回冲突处理（跨来源）

跨来源（不同项目 / 不同日期 / 不同层级）命中**语义矛盾**的内容时：

```
发现矛盾结果
  → 标记为 conflict
  → 按以下优先级裁决：
     1. 时间：新结论 > 旧结论（近期的记忆覆盖早期的）
     2. 来源：用户显式指定 > 自动生成（用户偏好 > agent 总结）
     3. 粒度：详细 > 简略（原文片段 > 摘要）
  → 裁决后附加上下文标记（`[resolved: newer]` / `[resolved: user_pref]`）
  → 用户可见结果中标注：`⚠ 与某条记录冲突，已采用较新/用户偏好版本`
```

##### 四、query 召回过载筛选

当召回内容超过 context 预算时，分三阶段截断：

**第一阶段：相关性硬过滤**
```
所有召回结果按相关性得分排序
  → 丢弃相关性得分 < threshold（默认 0.3）的结果
  → 剩余结果进入预算分配
```

**第二阶段：内容多样性过滤**
```
在余量预算内，优先保证多样性（同主题只保留 top-1）
  → 按主题聚类
  → 每类只保留相关性最高的条目
  → 超出预算则丢弃整类
```

**第三阶段：预算截断**
```
按相关性排序逐一加入 context
  → 加入后总 token 接近预算上限时停止
  → 最后一条做截断而非丢弃（保留部分内容）
  → 告知用户"因 token 限制已截断，完整内容可通过 /memory get 查看"
```

**整体筛选策略总结**：

| 阶段 | 策略 | 目的 |
|------|------|------|
| 硬过滤 | 相关性得分 < 0.3 丢弃 | 去除明显无关内容 |
| 多样性 | 同主题只留 top-1 | 避免单一主题占满 context |
| 预算截断 | 逐一加入，超限截断尾部 | 控制 context 长度 |

### 2.5 定时任务与心跳机制（参考 OpenClaw）

参考 OpenClaw 的 heartbeat 和 cron 设计，Auton 支持后台自动化任务，保持"常驻感知"。

#### 2.5.1 心跳机制（Heartbeat）

**核心思想**：在主会话中周期性插入一个轻量 turn，读取检查清单并响应，让 Auton 在闲置时仍能感知环境变化。

**与主会话的关系**：

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| **main-session**（默认） | 主会话周期性被打断，执行心跳 turn，然后恢复等待 | 常规感知，如检查邮件、监控状态 |
| **isolated** | 每次心跳是独立的 session turn，不影响主会话上下文 | 降低 token 消耗，隔绝干扰 |

**心跳配置项**（`~/.auton/config.yaml`）：

```yaml
heartbeat:
  enabled: true
  every: "30m"              # 间隔（默认 30 分钟，支持 5m / 1h / 2h / 自定义）
  active_hours: "9:00-18:00"  # 仅在此时段生效（可选，默认全天）
  session_mode: "main"      # main | isolated
  light_context: true       # 是否使用轻量上下文（isolated 模式建议开启）
  target: "main"            # main | isolated | current（默认 main）
```

**心跳契约（HEARTBEAT.md 检查清单）**：

Auton 在 `~/.auton/heartbeat/HEARTBEAT.md` 中维护检查清单，每次心跳读取并响应：

```markdown
# Heartbeat Checklist

## 待处理任务
- [ ] review PR #42
- [ ] 确认部署时间

## 待确认决策
- [ ] auth 模块是否采用 JWT？

## 提醒
- [ ] 周五下午 3 点周会

---
# HEARTBEAT_OK
timestamp: 2024-01-15T15:30:00
issues_responded: 2
issues_raised: 0
```

- Auton 读取 HEARTBEAT.md，找到所有 `-[ ]` 未完成条目
- 对每个条目做出响应（执行动作 / 更新状态 / 标记完成 / 提新问题）
- 响应完成后写入 `HEARTBEAT_OK` 块，表示本次心跳正常完成
- 如果有问题需要用户确认，写入 `HEARTBEAT_ASK` 并附上具体问题

**light_context 模式**（isolated + light_context）：
- 不加载完整 memory，仅携带 auton.md 和 HEARTBEAT.md
- token 消耗大幅降低，适合高频心跳（如每 5 分钟一次）

#### 2.5.2 Cron 定时任务（Cron Jobs）

**核心思想**：精确时间点的独立自动化任务，与心跳互补。

**执行模式**：

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| **main-session** | 作为主会话的系统事件触发，下次心跳时执行 | 与主会话上下文相关的周期性任务 |
| **isolated** | 独立 agent turn，完全隔离上下文 | 定时报告、数据采集、纯自动化任务 |

**调度类型**：

| 类型 | 格式 | 示例 |
|------|------|------|
| **at**（一次性） | `at YYYY-MM-DD HH:MM` | `at 2024-01-20 09:00` |
| **every**（间隔） | `every <duration>` | `every 1h`, `every 30m`, `every 1d` |
| **cron**（Cron 表达式） | 标准 5 字段 | `0 9 * * 1-5`（工作日 9 点）|

**Cron Job 配置结构**：

```yaml
jobs:
  - name: "daily-report"
    schedule: "0 9 * * *"           # 每天早上 9 点
    session: "isolated"              # 隔离会话
    light_context: true              # 轻量上下文
    delivery: "announce"             # announce | webhook | none
    webhook_url: "https://..."       # delivery=webhook 时填写
    enabled: true
    description: "生成每日开发报告"
    retry:
      max_attempts: 3
      backoff: "exponential"        # 30s → 1m → 5m → 15m → 60m

  - name: "deploy-check"
    schedule: "every 1h"
    session: "main"                 # 主会话上下文相关
    delivery: "announce"
    enabled: false                  # 可手动禁用
```

**交付模式（delivery）**：

| 模式 | 说明 |
|------|------|
| **announce**（默认） | 在主会话 announce 结果，类似 `/cron run` 输出 |
| **webhook** | POST 结果到指定 URL |
| **none** | 仅记录日志，不输出不通知 |

**重试策略**：
- 定时任务执行失败时，使用**指数退避重试**
- 默认退避序列：30s → 1m → 5m → 15m → 60m
- 连续失败 N 次后暂停任务，等待用户手动确认后恢复

**与心跳的关系**（参考 OpenClaw cron-vs-heartbeat.md）：

```
┌─────────────────────────────────────────────────────────┐
│  Heartbeat = 周期性感知，维持"活跃在场"状态              │
│  - 按固定间隔（默认 30m）                              │
│  - 读取 HEARTBEAT.md 检查清单                         │
│  - 上下文感知，依赖主会话状态                          │
│  - 适合：监控、提醒、持续感知                          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Cron = 精确时间，独立的自动化执行                      │
│  - cron 表达式或 every 间隔                            │
│  - 可选 isolated 完全隔离                              │
│  - 精确时机 + 不同模型/配置                             │
│  - 适合：定时报告、数据采集、精确调度                   │
└─────────────────────────────────────────────────────────┘

两者组合：心跳维持感知，cron 处理精确时机任务
```

#### 2.5.3 命令接口

```
/cron list                  # 列出所有定时任务
/cron add <name> <schedule> # 添加定时任务
/cron edit <name> ...       # 编辑任务配置
/cron remove <name>         # 删除任务
/cron run <name>            # 立即执行（跳过调度）
/cron enable/disable <name> # 启用/禁用任务
/cron logs <name>           # 查看任务执行日志
```

#### 2.5.4 存储结构

```
~/.auton/
  heartbeat/
    HEARTBEAT.md             # 心跳检查清单
    HEARTBEAT_OK.log         # 历史心跳记录
  cron/
    jobs.yaml                # 定时任务配置
    logs/                    # 执行日志
      daily-report/
        2024-01-15T09-00-00.jsonl
        2024-01-16T09-00-00.jsonl
      deploy-check/
        ...
```

---

### 2.6 上下文感知（Context Awareness）

理解当前工作环境，主动提供相关帮助。

- **项目类型检测**：自动识别当前项目类型（Web/App/后端/数据科学等）
- **项目结构理解**：解析项目目录、依赖配置、主要模块
- **最近工作感知**：记录并理解用户最近编辑的文件和操作
- **主动建议**：基于上下文主动提供下一步行动建议

### 2.7 规划引擎（Planning Engine）

将复杂目标转化为可执行计划。

- **目标分解**：将模糊目标（如"帮我优化这个性能问题"）分解为具体步骤
- **多方案生成**：为同一目标生成多种执行方案并比较优劣
- **风险识别**：识别计划中的风险点、瓶颈、依赖项
- **计划调整**：执行中遇到障碍时动态调整计划
- **计划可视化**：以流程图展示任务分解和依赖关系

### 2.8 工具集成（Tool Integration）

Auton 执行任务所依赖的能力扩展。

#### 2.7.1 工具自包含模块

每个工具独立目录，结构一致：

```
tools/<ToolName>/
  tool.py           # 工具逻辑（输入验证、执行、输出）
  schema.py         # 工具输入 Schema（Pydantic 验证）
```

**内置工具清单**：

| 类别 | 工具 | 描述 |
|------|------|------|
| 文件操作 | `read` | 读取文件 |
| | `write` | 创建/覆写文件 |
| | `edit` | 字符串替换编辑（幂等） |
| | `glob` | 文件路径模式匹配 |
| | `grep` | 正则内容搜索 |
| Shell | `bash` | Shell 命令执行（含 7 层安全校验） |
| 网络 | `web_search` | 网页搜索 |
| | `web_fetch` | URL 内容抓取 |
| 代码管理 | `git` | Git 操作 |
| HTTP | `http` | HTTP API 请求 |
| 任务 | `task_create` | 创建后台任务 |
| | `task_get` | 查询任务状态 |
| | `task_list` | 列出所有任务 |
| | `task_stop` | 停止任务 |
| 扩展 | `mcp` | MCP 协议工具适配器 |

#### 2.7.2 BashTool 安全防线（7 层）

1. **路径校验**（`pathValidator.py`）：防路径遍历（`../`）、Unicode 标准化攻击（全角字符）
2. **危险命令过滤**（`security.py`）：黑名单命令拦截（`rm -rf /`、`curl | sh`）
3. **sed 特殊解析**：防止利用 sed 隐蔽修改
4. **读写语义分类**：告知用户命令的读写副作用
5. **沙箱隔离**（`sandbox.py`）：Linux namespaces / macOS sandbox
6. **Permission 检查**：按权限模式决定是否放行
7. **只读模式验证**：yolo 模式下自动拒绝所有写操作

#### 2.7.3 外部工具扩展

- **MCP 协议支持**：通过 MCP 连接外部工具服务
- **插件工具**：从插件系统动态加载工具
- **统一注册表**：内置工具 + MCP 工具 + 插件工具统一合并，SessionProcessor 无感知差异

### 2.9 执行闭环（SessionProcessor）

#### 2.9.1 主循环

SessionProcessor 是 Auton 的唯一执行核心，职责单一（约 200 行）。

**三态返回值**：

| 状态 | 含义 | 触发条件 |
|------|------|----------|
| `continue` | 继续下一轮 LLM 调用 | 正常流程，有工具结果 |
| `compact` | 上下文压缩后继续 | Token 接近上限 / 历史过长 |
| `stop` | 终止回到 idle | 用户中断 / 不可重试错误 / 权限拒绝 |

#### 2.9.2 Part 化消息

消息不是裸字符串，而是由多种 Part 组成：

- **TextPart**：模型回复正文（支持流式增量更新）
- **ReasoningPart**：思考过程（不暴露给用户，但保留在 context 中）
- **ToolPart**：工具状态机（pending → running → completed / error）
- **StepPart**：单步边界（用于成本/流程可观测）

#### 2.9.3 结构化事件

每步操作产生结构化事件，供 UI、日志、审计订阅：

```
text-start / text-delta / text-finish
reasoning-start / reasoning-delta / reasoning-finish
tool-call / tool-result / tool-error
step-start / step-finish（含 files_changed）
audit-event / session-compact
```

**工程价值**：每一段输出、每一次工具调用、每一个文件改动都有事件轨迹，可回放、调试、审计、重试。

### 2.10 快照与 Patch 系统

每步执行前后记录快照，产出 patch 文件清单：

- **可解释**：知道"哪一步改了哪些文件"
- **可审计**：便于回放与分享
- **可恢复**：失败后容易定位回滚/重试边界
- **Step 边界**：每个 `step-finish` 事件携带 `files_changed` 列表

### 2.11 工作流自动化（Workflow Automation）

将重复性工作封装为可复用工作流。

- **工作流定义**：用户通过自然语言或 DSL 定义工作流
- **条件分支**：支持 if/else、循环、并行分支等控制流
- **断点续执**：工作流中断后可从断点恢复
- **执行日志**：完整记录每步操作的输入输出

### 2.12 安全与权限（Security & Permissions）

确保 Agent 行为在用户可控范围内。

#### 2.12.1 四级权限模式

| 模式 | 描述 | 触发条件 |
|------|------|----------|
| `default` | 交互式确认（每次写操作询问） | 默认模式 |
| `auto` | ML 分类器自动审批低风险操作 | `--auto` 标志 |
| `bypass` | 跳过所有权限检查（危险） | 明确 opt-in |
| `yolo` | 全部自动拒绝（只读模式） | 安全研究场景 |

#### 2.12.2 其他安全措施

- **操作审计日志**：记录所有操作的时间、内容、结果
- **数据隔离**：多项目间数据严格隔离
- **密钥管理**：不存储明文密钥，从 env / Keychain 读取
- **Prompt Injection 防护**：工具结果中的特殊字符转义，用户内容与系统消息隔离

### 2.13 技能系统（Skills System）

**核心认知（源自 OpenClaw）**：Skill 就是一个带 YAML frontmatter 的 Markdown 文件，**不是可执行代码**。

Skill 的本质是**知识文档**，作用是：当用户请求涉及某个领域时，Auton 把对应 Skill 的完整内容注入 LLM 上下文，让 LLM 知道"在这个场景下应该用哪些工具、怎么用"。

#### 2.13.1 Skill 目录结构

每个 Skill 是独立目录，支持可选的打包资源：

```
skills/<SkillName>/
├── SKILL.md          # ★ 必需：YAML frontmatter + Markdown 知识文档
├── scripts/          # 可选：可执行脚本（Python/Bash），直接运行不入 context
├── references/       # 可选：参考文档，按需加载（表结构、API 文档、公司规范）
├── assets/           # 可选：输出资产（模板、图片、样板代码），不加载入 context
└── experiences/      # 可选：使用经验记录，提高后续执行的稳定性和效率
    └── README.md     # experiences 文件夹说明 + 经验条目列表
```

**`experiences/` 文件夹**：记录该 skill 在实际使用过程中积累的经验、教训和最佳实践。
当 skill 被调用时，Auton 会将 `experiences/README.md` 的内容注入 context（按需加载），
帮助 LLM 避免重复犯错、复用成功路径。具体格式见下方 SKILL.md `experiences` 引用字段。

#### 2.13.2 SKILL.md 格式

```yaml
---
name: github
description: "GitHub operations via `gh` CLI. Use when: (1) checking PR
  status or CI, (2) creating/commenting on issues, (3) listing/filtering
  PRs. NOT for: local git operations, non-GitHub repos."
disable-model-invocation: false
user-invocable: true
load-experiences: true          # 是否自动加载 experiences/README.md
metadata:
  openclaw:
    emoji: "🐙"
    requires:
      bins: ["gh"]
    install:
      - kind: brew
        formula: gh
---

# GitHub Skill

## When to Use

✅ **USE when:** Checking PR status, CI runs, creating issues
❌ **DON'T use when:** Local git → use `git` directly

## Commands

gh pr list --repo owner/repo
gh issue create --title "Bug" --body "..."
```

**`experiences/README.md` 格式**（使用经验记录，Skill 触发时按需加载）：

```markdown
# PostgreSQL Manager 使用经验

本文档记录本 skill 在实际使用中积累的经验和教训，每次使用后可选择追加新条目。
LLM 在执行本 skill 时读取此文件，避免重复犯错、复用成功路径。

## 经验条目

### 2024-01-15: 大表迁移必须用事务包裹
- **场景**：迁移超过 10 万行的表时，直接 ALTER TABLE 导致锁表超时。
- **教训**：大表迁移必须用 `BEGIN` / `COMMIT` 包裹分批 UPDATE，或使用 pg_repack。
- **标签**：#migration #performance

### 2024-01-20: JSONB 字段查询加索引
- **场景**：对 jsonb 字段做 WHERE 条件查询时，全表扫描严重（500ms+）。
- **教训**：对频繁查询的 JSON key 创建表达式索引：`CREATE INDEX ON table ((data->>'key'))`。
- **标签**：#jsonb #performance #index

### 2024-02-01: 连接池大小不要超过 100
- **场景**：高并发时数据库连接数暴涨，导致 PostgreSQL `too many connections` 错误。
- **教训**：PgBouncer pool_size 设置为 CPU 核数的 2-3 倍，绝对值不超过 100。
- **标签**：#connection-pool #production
```

**experiences 条目格式**：
- `### 日期: 简短标题` — 经验名称
- `**场景**：` — 在什么情况下遇到问题
- `**教训/最佳实践**：` — 如何解决或应该怎么做
- **`标签**：` — 便于检索的标签（#topic 格式）

| 层级 | 内容 | 何时加载 | 容量 |
|------|------|----------|------|
| **元数据** | name + description + load-experiences | 始终在 context | ~100 words |
| **SKILL.md body** | 工作流、工具说明、示例 | Skill 触发后 | <500 lines |
| **experiences/** | 使用经验、教训、最佳实践 | Skill 触发后（load-experiences=true 时） | 无限制 |
| **references/** | 详细文档、表结构、API 规范 | 按需（LLM 决定） | 无限制 |
| **scripts/** | 可执行脚本 | 直接运行 | 无限制 |

#### 2.13.3 Frontmatter Schema

| 字段 | 说明 |
|------|------|
| `name` | 技能名称（唯一标识，小写+连字符） |
| `description` | **最重要字段**：描述何时使用/何时不用，LLM 据此判断是否注入 |
| `disable-model-invocation` | 是否禁止 LLM 自动调用（默认 false） |
| `user-invocable` | 是否允许用户手动触发（默认 true） |
| `load-experiences` | Skill 触发时是否自动加载 `experiences/README.md`（默认 false） |
| `metadata.openclaw.emoji` | 展示 emoji |
| `metadata.openclaw.requires.bins` | 依赖的二进制命令 |
| `metadata.openclaw.install` | 安装说明（brew/apt/npm 等） |

#### 2.13.4 技能来源与加载优先级

| 优先级 | 来源 | 路径 |
|--------|------|------|
| 1（最高） | **工作区技能** | `.auton/skills/`（当前目录） |
| 2 | **项目技能** | `.auton/skills/`（项目根） |
| 3 | **用户技能** | `~/.auton/skills/` |
| 4 | **内置技能** | `src/skills/`（随 Auton 分发） |

同名技能高优先级覆盖低优先级。

#### 2.13.5 技能创建流程（skill-creator）

内置 `skill-creator` 技能，让用户用自然语言构建新技能：

```
用户: "我想建一个 skill，用来管理我们的 PostgreSQL 数据库"
  → skill-creator 技能被触发
  → Auton 与用户对话，理解具体场景
     "你会用这个 skill 做什么？创建表？查数据？迁移？"
  → 确定 skill 结构（SKILL.md / scripts/ / references/ / experiences/）
  → 生成技能目录到 ~/.auton/skills/postgres-manager/
  → 编写 SKILL.md 知识文档
  → 创建 experiences/README.md（经验记录说明文档）
  → 验证并打包（可选）
  → 通知用户新技能已就绪
```

**skill-creator 的标准构建流程**：
1. **理解场景**：通过对话收集具体使用示例
2. **规划内容**：确定需要 scripts/ / references/ / assets/ / experiences/ 哪些资源
3. **初始化目录**：创建 `~/.auton/skills/<skill-name>/`
4. **编辑内容**：编写 SKILL.md 和资源文件
5. **创建 experiences/README.md**：写入文件夹说明模板（说明文件用途和条目格式），设置 `load-experiences: true`
6. **验证打包**：检查格式完整性，生成可分发包（可选）

#### 2.13.6 技能注入机制

```
用户输入
  → 对所有 SKILL.md 的 description 做 embedding 语义检索
  → 选取 top-k 最相关的 Skill（description 最相关者）
  → 将对应 SKILL.md 全文注入 system prompt
  → LLM 根据注入的知识决定调用哪些工具（bash / read / gh...）
```

- 注入时机：**每次请求前**，根据用户输入动态选择
- 注入上限：最多 10 个 Skill（超出按相关度截断）
- references/ 按需单独加载，不占用固定 token 预算

#### 2.13.7 内置技能清单

| 技能 | 何时使用 | 资源 |
|------|----------|------|
| `skill-creator` | 用户要新建或改进一个 skill | 内置（Meta 技能） |
| `github` | 检查 PR 状态、CI 运行、管理 issues | 内置 |
| `git-workflow` | 标准化 commit、branch、PR 提交流程 | 内置 |
| `web-search` | 网页搜索、内容抓取 | 内置 |
| `code-review` | 代码审查、安全检查 | 内置 |
| `debugging` | 系统性调试日志分析 | 内置 |
| `planning` | 任务分解、多方案比较 | 内置 |
| `tdd` | 测试驱动开发流程 | 内置 |

#### 2.13.8 技能管理命令

| 命令 | 功能 |
|------|------|
| `/skill list` | 列出所有可用技能（含来源） |
| `/skill info <name>` | 查看指定技能的完整内容 |
| `/skill create` | 触发 skill-creator，引导创建新技能 |
| `/skill delete <name>` | 删除用户/项目级技能（内置不可删） |
| `/skill edit <name>` | 编辑指定技能内容 |
| `/skill check` | 检查所有技能的依赖（bins/权限）是否满足 |
| `/skill install <file>` | 从 .skill 包文件安装技能 |

> 用户的自定义技能存储在 `~/.auton/skills/`，项目级技能在 `.auton/skills/`。skill-creator 生产的技能默认写入 `~/.auton/skills/`。

### 2.14 可扩展性（Extensibility）

- **插件系统**：编写插件扩展 Agent 底层能力，支持热加载
- **工作流 DSL**：自定义领域特定语言定义高级工作流
- **规则引擎**：通过配置文件定义 Agent 行为规则
- **记忆模板**：预定义记忆结构，快速初始化新项目
- **多 Agent 协作**：支持将复杂任务委托给多个专业子 Agent 并行处理

### 2.15 持久化与恢复（Persistence & Recovery）

- **状态快照**：定期保存 Agent 状态快照
- **会话恢复**：Agent 重启后可恢复之前的会话和任务上下文
- **失败恢复**：任务失败后自动重试或回退到安全状态
- **数据导出/导入**：导出全部记忆和配置，方便迁移

---

## 3. 非功能性需求

### 3.1 性能

- 首次响应延迟 < 2 秒（简单查询）
- 复杂任务规划 < 30 秒
- 支持至少 5 个并行子任务

### 3.2 可用性

- CLI 为主，API 为可选扩展
- 错误信息清晰、可操作
- 支持离线基础功能（记忆检索、简单任务）

### 3.3 可观测性

- **结构化事件**：所有操作通过事件总线广播
- **结构化日志**：JSON + Console 双输出
- **Snapshot + Patch**：每步操作可追踪
- **执行链路可追踪**：每步有 step-id，含 summary 和 files_changed

---

## 4. 用户旅程示例

### 场景 1：新项目初始化

```
用户: "帮我搭建一个新的 Python FastAPI 项目"
Auton:
  1. /plan 自动触发（检测到项目初始化意图）
  2. 询问项目名称、是否需要数据库、是否需要认证等关键信息
  3. 生成包含 4 种方案的比较分析
  4. 用户选择方案后，创建重构计划
  5. SessionProcessor 执行：生成项目结构 → 初始化依赖文件 → 生成骨架代码 → Git 首次提交
  6. 每步 step-finish 事件记录 files_changed
  7. 完成后写入 .auton/memory/project_knowledge.json（指针文件）
```

### 场景 2：带权限控制的复杂任务

```
用户: "帮我删除 tests/ 目录下所有 __pycache__"

Auton:
  1. 识别到 rm 类危险命令
  2. BashTool 7 层校验触发
  3. default 模式：弹出确认对话框
     "将删除 23 个 __pycache__ 目录，确认？"
  4. 用户确认 → 执行 → audit log 记录
  5. step-finish 事件：files_changed = ["tests/a/__pycache__", ...]
```

### 场景 3：上下文压缩与恢复

```
用户: （长对话进行中）

Auton:
  1. Token 预算接近上限
  2. SessionProcessor 返回 "compact"
  3. 压缩历史：保留首尾消息，中间以摘要替代
  4. 释放的 token 用于继续对话
  5. 用户无感知，可继续工作
```

---

## 5. 里程碑计划

> 参考 Claude Code 和 OpenCode 的演进路径，先实现核心执行闭环，再逐步扩展。

| 阶段 | 内容 | 优先级 | 核心交付 |
|------|------|--------|----------|
| **M1 - Core** ✅ | CLI 入口、SessionProcessor 执行闭环、Part 化消息、事件总线、内置 8 工具、MiniMax 支持、append-only JSONL 存储 | P0 | 可运行的最小 Agent |
| **M2 - Tools** ✅ | 工具注册表、read/write/edit/bash/glob/grep 工具、BashTool 7 层安全校验、MCP 协议适配器 | P0 | 可执行真实任务的 Agent |
| **M3 - Commands** ✅ | 命令系统（斜杠命令）、命令注册表、Command 接口 | P0 | 命令行界面就绪 |
| **M4 - Memory** ✅ | 会话记忆、项目记忆（指针文件）、SessionSummarizer、/memory 命令 | P0 | 有上下文的 Agent |
| **M5 - Security** ✅ | 四级权限模式、AuditLog、PromptInjection 防护、KeyManager、/security 命令 | P0 | 可安全使用的 Agent |
| **M6 - Skills** ✅ | 技能系统（SKILL.md + scripts/ + references/ + 渐进式披露）、skill-creator 内置技能、/skill 管理命令 | P0 | 可注入领域知识 + 用户可自建技能的 Agent |
| **M7 - Long-term Memory** ✅ | 长期记忆（BM25 关键词检索）、遗忘策略、/memory 命令（edit/delete/gc/reindex/stats） | P1 | 有持久记忆的 Agent |
| **M8 - Planning** ✅ | 规划引擎、任务分解、风险分析、多方案比较、/plan 命令（confirm/list/show/modify/cancel） | P1 | 可自主规划的 Agent |
| **M9 - Tasks** ✅ | 后台任务系统、任务状态机、task_create/get/list/stop 工具、/tasks 命令（list/get/stop/retry/stats） | P1 | 支持异步并行的 Agent |
| **M10 - Workflow** ✅ | 工作流引擎、DSL、断点续执 | P2 | 可自动化的 Agent |
| **M11 - Extensibility** ✅ | MCP 集成（CLI + /mcp 管理命令）、插件系统 | P2 | 可深度扩展的 Agent |
| **M12 - Multi-Agent** ✅ | 子代理委托、多 Agent 协作 | P3 | 多 Agent 协作 |
