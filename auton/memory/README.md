# Memory — 记忆系统

四类记忆分层：会话 / 项目 / 全局 / 长期。**存储与检索完全分离。**

## 目录结构

| 文件 | 职责 | 状态 |
|------|------|------|
| `types.py` | 记忆类型定义：type = user / feedback / project / reference | ✅ |
| `project_memory.py` | ★ 项目记忆（Claude Code 格式）：MEMORY.md 索引 + 主题文件 + SUMMARY.md | ✅ |
| `global_memory.py` | ★ 全局记忆（OpenClaw 格式）：按日期目录，闲聊模式启动时加载当日+昨日 | ✅ |
| `memory_manager.py` | ★ 统一检索入口：模式判断 + 加载优先级 + MEMORY.md 蒸馏触发 | ✅ |
| `session_summarizer.py` | ★ 会话摘要生成器：jsonl → 分段详细摘要（block 逐行，含意图/决策/文件/待办） | ✅ |
| `memory_md.py` | ★ MEMORY.md 管理器：从 SUMMARY.md 蒸馏高价值条目写入 MEMORY.md | ✅ |
| `auton_md.py` | ★ auton.md 加载器：三位置取并集 + 优先级合并 + 闲聊模式全局记忆加载 | ✅ |
| `conflict_resolver.py` | ★ 冲突管理：写入冲突检测（语义指纹）+ 召回冲突裁决 + 去重 | ✅ |
| `long_term_memory.py` | 长期记忆：向量检索 top-k（**M7 实现**） | 📋 |
| `embedding_store.py` | 向量嵌入存储：ChromaDB/Qdrant 封装（**M7 实现**） | 📋 |
| `chunker.py` | 长期记忆分块器：语义分块策略（**M7 实现**） | 📋 |

✅ = 已完成    📋 = 待实现

## 核心设计

### 存储与检索分离
- `SessionStore` 只管 append jsonl，不管检索
- `MemoryManager` 只管读 jsonl，按需加载到 context
- 两者通过 jsonl 文件解耦

### 三层检索架构
```
query → MEMORY.md（顶层索引）
       → SUMMARY.md（分段详细摘要，jsonl 文件名 + block 序号）
           → execution/*.jsonl（按 block 序号读取原文）
```

### SUMMARY.md 格式
- 每个日期（全局）或每个项目一个 SUMMARY.md
- 文件内每个 block 一行，格式：`block_序号: <详细总结>`
- 总结包含：意图、涉及文件/模块、关键决策/结论、待跟进事项
- 足够详细，让 LLM 仅凭 SUMMARY.md 判断相关性

### auton.md 三位置优先级
- `~/.auton/auton.md`（高）> `{项目根}/.auton/auton.md`（中）> `{auton源码}/.auton/auton.md`（低）
- 取并集，同键冲突高优先级覆盖低优先级

### 打开模式
- **项目模式**：检索仅当前项目 jsonl，加载项目 MEMORY.md + 长期记忆 top-k
- **无项目模式**：检索全部项目 + 全部日期，加载当日+昨日 global MEMORY.md + 近 2 天有变动的项目 MEMORY.md

## 存储结构（~/.auton/）

```
~/.auton/
├── config.yaml              # 用户配置文件
├── memory/                  # 记忆数据
│   ├── execution/            # append-only jsonl 会话记录
│   │   ├── <session_id>.jsonl
│   │   └── index.jsonl
│   ├── memory_<date>.md     # 每日长期记忆（L1 索引）
│   ├── summary_<date>.md    # 每日分段摘要（L2，详细）
│   └── vector_db/            # Chroma 向量数据库（M7）
├── logs/                     # 日志
├── cron/                     # 定时任务
└── credentials/              # 敏感凭据（可选加密）
```

项目级记忆（放在项目根目录 `.auton/`）：
```
{项目根}/.auton/
  MEMORY.md               # 项目记忆顶层索引
  SUMMARY.md              # 本项目所有 jsonl 的 block 逐行详细摘要
  user_role.md            # 用户偏好（type: user）
  feedback_*.md            # 行为规则（type: feedback）
  project_*.md             # 项目背景（type: project）
  reference_*.md           # 外部引用（type: reference）
  execution/               # append-only jsonl
    <session_id>.jsonl
```

## 快速使用

```python
from auton.memory import MemoryManager, MemoryMode

mm = MemoryManager()

# 检测模式
mode = mm.detect_mode()
print(f"模式: {mode.mode}")

# 获取注入上下文
ctx = mm.get_context(mode)
print(ctx[:200])

# 三层检索
results = mm.retrieve("auth 模块重构", mode, top_k=5)
for r in results:
    print(f"  [{r.source}] {r.content[:80]}")

# 会话蒸馏（会话结束时调用）
mm.distill_session("session-2026-04-07-001")
```
