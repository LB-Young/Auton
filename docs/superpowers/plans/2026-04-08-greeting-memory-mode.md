# Greeting Memory Mode Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Auton 在启动时先基于本地近两天记忆收集上下文，再由模型生成带回顾概要的问候语，并按“已有项目历史优先”决定是否直接进入项目模式。

**Architecture:** 启动链路拆成三层：本地模式判定、本地记忆收集、模型问候生成。`SessionStore` 负责“当前目录是否已有项目历史”和 `project_modify.md` 增量维护，`GlobalMemory` 负责近两天日期记忆与项目变更索引读取，`cli/main.py` 只负责串联启动流程与用户交互，避免继续堆砌分支逻辑。

**Tech Stack:** Python, Typer, Rich, 现有 `LLMProvider` 抽象, `SessionStore`, `GlobalMemory`, `ProjectMemory`

---

## Chunk 1: 启动模式判定与索引能力

### Task 1: 为项目历史判定补测试

**Files:**
- Test: `tests/agent/test_session_store.py`
- Modify: `auton/agent/session_store.py`

- [ ] **Step 1: 写失败测试，覆盖“已有项目历史则进入项目模式候选”**

```python
def test_has_existing_project_history_when_project_folder_exists(tmp_path):
    storage_dir = tmp_path / "memory"
    project_dir = storage_dir / "projects" / "Auton"
    project_dir.mkdir(parents=True)

    store = SessionStore(storage_dir=storage_dir, project_root=None)

    assert store.has_existing_project_history(Path("/work/Auton")) is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/agent/test_session_store.py -v`
Expected: FAIL，提示 `SessionStore` 缺少 `has_existing_project_history`

- [ ] **Step 3: 实现最小判定逻辑**

```python
def has_existing_project_history(self, cwd: Path) -> bool:
    project_base = self.storage_dir / "projects" / cwd.name
    return project_base.exists() and project_base.is_dir()
```

- [ ] **Step 4: 补充“无历史时返回 False”的测试并跑绿**

Run: `pytest tests/agent/test_session_store.py -v`
Expected: PASS


### Task 2: 为 `project_modify.md` 读写补测试

**Files:**
- Test: `tests/memory/test_global_memory.py`
- Modify: `auton/memory/global_memory.py`

- [ ] **Step 1: 写失败测试，覆盖项目 session 路径登记与近两天读取**

```python
def test_project_modify_tracks_recent_project_sessions(tmp_path):
    gm = GlobalMemory(tmp_path / "memory")
    session_path = "~/.auton/memory/projects/Auton/sessions/abc.jsonl"

    gm.record_project_session_path(date.today(), session_path)
    paths = gm.read_recent_project_session_paths()

    assert session_path in paths
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/memory/test_global_memory.py -v`
Expected: FAIL，提示缺少 `record_project_session_path`

- [ ] **Step 3: 最小实现 `project_modify.md` 读写接口**

```python
def project_modify_path(self) -> Path: ...
def record_project_session_path(self, d: date, session_path: str) -> None: ...
def read_recent_project_session_paths(self) -> list[str]: ...
```

- [ ] **Step 4: 增加去重与只保留今天/昨天分组的测试**

Run: `pytest tests/memory/test_global_memory.py -v`
Expected: PASS


### Task 3: 在 session 归档时更新项目变更索引

**Files:**
- Test: `tests/agent/test_session_store.py`
- Modify: `auton/agent/session_store.py`
- Modify: `auton/memory/global_memory.py`

- [ ] **Step 1: 写失败测试，覆盖项目模式归档时写入 `project_modify.md`**

```python
def test_archive_project_session_updates_project_modify(tmp_path):
    storage_dir = tmp_path / "memory"
    project_root = tmp_path / "workspace" / "Auton"
    store = SessionStore(storage_dir=storage_dir, project_root=project_root)

    store.archive_session("sid", "start", "end", 0)

    content = (storage_dir / "project_modify.md").read_text(encoding="utf-8")
    assert "projects/Auton/sessions/sid.jsonl" in content
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/agent/test_session_store.py::test_archive_project_session_updates_project_modify -v`
Expected: FAIL

- [ ] **Step 3: 在 `archive_session()` 内按项目模式增量更新 `project_modify.md`**

- [ ] **Step 4: 跑该测试与相关测试**

Run: `pytest tests/agent/test_session_store.py tests/memory/test_global_memory.py -v`
Expected: PASS

---

## Chunk 2: 启动问候上下文收集

### Task 4: 抽离启动上下文收集器

**Files:**
- Create: `auton/cli/greeting_context.py`
- Test: `tests/cli/test_greeting_context.py`
- Modify: `auton/cli/main.py`

- [ ] **Step 1: 写失败测试，覆盖以下场景**
- [ ] 有项目历史：返回 `mode_candidate="project"`，且 `should_ask_project_mode=False`
- [ ] 无项目历史但近两天有 dates 记忆：返回回顾片段
- [ ] 无项目历史但近两天有项目活动：返回项目摘要片段
- [ ] 两天都无内容：返回空回顾并要求通用问候

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/cli/test_greeting_context.py -v`
Expected: FAIL，缺少模块或函数

- [ ] **Step 3: 实现最小收集器**

```python
@dataclass
class GreetingContext:
    cwd: str
    today: str
    yesterday: str
    mode_candidate: Literal["project", "date"]
    should_ask_project_mode: bool
    date_memory_snippets: list[str]
    recent_project_summaries: list[str]
```

- [ ] **Step 4: 从今天/昨天 `dates/*/memory/MEMORY.md` 提取片段**

- [ ] **Step 5: 从 `project_modify.md` 解析近两天项目 session 路径，再聚合项目 `memory/MEMORY.md` 片段**

- [ ] **Step 6: 跑绿**

Run: `pytest tests/cli/test_greeting_context.py -v`
Expected: PASS


### Task 5: 统一“无内容则通用问候”的退化规则

**Files:**
- Test: `tests/cli/test_greeting_context.py`
- Modify: `auton/cli/greeting_context.py`

- [ ] **Step 1: 写失败测试，覆盖“无项目、无近两天事务时仅走通用问候”**

```python
def test_greeting_context_falls_back_to_generic_when_no_recent_content(...):
    ctx = collect_greeting_context(...)
    assert ctx.date_memory_snippets == []
    assert ctx.recent_project_summaries == []
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 实现退化规则，不在收集层拼问候文案，只提供结构化空结果**

- [ ] **Step 4: 跑绿**

Run: `pytest tests/cli/test_greeting_context.py -v`
Expected: PASS

---

## Chunk 3: 模型生成问候语

### Task 6: 为问候生成器补测试

**Files:**
- Create: `auton/cli/greeting_generator.py`
- Test: `tests/cli/test_greeting_generator.py`
- Modify: `auton/cli/main.py`

- [ ] **Step 1: 写失败测试，覆盖 prompt 组装**

```python
def test_build_greeting_prompt_includes_recent_memory_and_question_flag():
    ctx = GreetingContext(
        cwd="/work/Auton",
        today="2026-04-08",
        yesterday="2026-04-07",
        mode_candidate="date",
        should_ask_project_mode=True,
        date_memory_snippets=["今天处理了记忆系统设计"],
        recent_project_summaries=["Auton 项目最近修改过启动逻辑"],
    )

    prompt = build_greeting_prompt(ctx)

    assert "是否按项目模式开启" in prompt
    assert "今天处理了记忆系统设计" in prompt
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/cli/test_greeting_generator.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 prompt 构建函数**

要求：
- 明确说明这是“启动问候生成”任务
- 限制输出篇幅
- 若无回顾内容，要求输出简短通用问候
- 若 `should_ask_project_mode=True`，要求自然询问是否按项目模式开启

- [ ] **Step 4: 为 `generate_greeting()` 增加 provider 交互测试**

可以用一个 fake provider 返回固定文本，验证 `main.py` 采用模型结果而不再直接拼固定字符串。

- [ ] **Step 5: 跑绿**

Run: `pytest tests/cli/test_greeting_generator.py -v`
Expected: PASS


### Task 7: 替换 `main.py` 中固定问候逻辑

**Files:**
- Modify: `auton/cli/main.py`
- Test: `tests/cli/test_main_greeting_flow.py`

- [ ] **Step 1: 写失败测试，覆盖启动流程**
- [ ] 当前目录已有项目历史时，直接切项目模式并生成带项目回顾的问候
- [ ] 无项目历史时，不切模式，只生成带询问的问候
- [ ] 无任何近两天记忆时，输出通用问候

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/cli/test_main_greeting_flow.py -v`
Expected: FAIL

- [ ] **Step 3: 删除 `_run_repl()` 中当前“`.git`/标记文件自动判项目”的逻辑**

- [ ] **Step 4: 以新流程替换**

顺序固定为：
1. `has_existing_project_history(cwd)`
2. 组装 `GreetingContext`
3. 调用模型生成问候
4. 写入 assistant opening message
5. 若需要询问项目模式，则等待后续用户明确答复再切换

- [ ] **Step 5: 跑绿**

Run: `pytest tests/cli/test_main_greeting_flow.py -v`
Expected: PASS

---

## Chunk 4: 项目模式确认与会话切换

### Task 8: 为“用户确认切项目模式”补测试

**Files:**
- Create: `auton/cli/project_mode_intent.py`
- Test: `tests/cli/test_project_mode_intent.py`
- Modify: `auton/cli/main.py`

- [ ] **Step 1: 写失败测试**

```python
def test_recognizes_positive_project_mode_confirmation():
    assert parse_project_mode_reply("是，按项目模式开启") is True

def test_recognizes_negative_project_mode_confirmation():
    assert parse_project_mode_reply("不用，就按普通模式") is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/cli/test_project_mode_intent.py -v`
Expected: FAIL

- [ ] **Step 3: 实现最小解析器**

只覆盖少量高置信表达：
- 正向：`是`、`好的`、`按项目模式`、`切到项目模式`
- 反向：`否`、`不用`、`普通模式`、`闲聊模式`
- 其余返回 `None`

- [ ] **Step 4: 在 REPL 输入循环里接入**

当 `should_ask_project_mode=True` 且尚未决策时：
- 用户明确确认 -> `store.set_project_root(cwd)`
- 用户明确拒绝 -> 保持 date 模式
- 不明确 -> 按普通消息继续

- [ ] **Step 5: 跑绿**

Run: `pytest tests/cli/test_project_mode_intent.py tests/cli/test_main_greeting_flow.py -v`
Expected: PASS

---

## Chunk 5: 回归验证

### Task 9: 验证启动链路与现有 session 存储兼容

**Files:**
- Test: `tests/cli/test_main_greeting_flow.py`
- Test: `tests/agent/test_session_store.py`
- Test: `tests/memory/test_global_memory.py`

- [ ] **Step 1: 运行聚合测试**

Run: `pytest tests/cli/test_main_greeting_flow.py tests/cli/test_greeting_context.py tests/cli/test_greeting_generator.py tests/cli/test_project_mode_intent.py tests/agent/test_session_store.py tests/memory/test_global_memory.py -v`
Expected: PASS

- [ ] **Step 2: 补一个手工验证清单**

1. 在一个已有 `projects/<cwd.name>/` 历史的目录启动，确认直接进入项目模式且问候带项目回顾。
2. 在一个没有项目历史但有近两天 dates 记忆的目录启动，确认问候带近两天回顾并询问是否用项目模式。
3. 在完全空白目录启动，确认只出现简短通用问候。
4. 在无项目历史目录里回答“按项目模式开启”，确认后续 session 保存到 `projects/<cwd.name>/sessions/`。
5. 结束项目模式 session 后，确认 `project_modify.md` 记录了该 session 路径。

- [ ] **Step 3: 如有现成命令，运行相关 CLI smoke test**

Run: `python -m auton --help`
Expected: CLI 正常启动，无 import 错误

