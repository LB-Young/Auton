# Plan: Skill 自动优化触发逻辑

## Context

`sSkillPerfTracker._check_alert()` 在每次 Skill 调用结束时设置 `alert_triggered=true` 到 `SKILL_PERF.json`，但没有任何地方读取这个标志并调用 `SkillOptimizer.optimize()`。目前只有 `/skill tune <name>` 能手动触发优化。

目标：在会话结束时（`archive_session`）**后台异步**触发已标记的 skill 优化，不阻塞主进程。

---

## 设计决策

1. **触发时机**：`SessionProcessor._do_stop()` — 会话结束时，且已有 `self.llm`
2. **后台方式**：`asyncio.create_task()` fire-and-forget（已在 `workflow_cmd.py`、`slack/adapter.py` 中使用）
3. **扫描范围**：扫描 `~/.auton/skill/` 下所有 skill 的 `SKILL_PERF.json`，对 `alert_triggered==true` 的触发优化
4. **去重**：同一 session 内同一种 skill 只触发一次（`alert_count` 已是去重计数器）

---

## 实现步骤

### Step 1: `auton/skills/perf_tracker.py` — 新增 `get_skills_with_pending_alerts()`

在 `SkillPerfTracker` 中新增一个模块级函数，扫描 skills 目录找所有 `alert_triggered=true` 的 skill：

```python
def get_skills_with_pending_alerts(skills_dir: Path) -> list[SkillPerfTracker]:
    """扫描 skills_dir 下所有 skill，返回 alert_triggered=true 的 SkillPerfTracker 列表。"""
```

实现：
- 遍历 `skills_dir/<name>/SKILL_PERF.json`
- 读取 `window_7d.alert_triggered`，为 `True` 的 skill 创建 `SkillPerfTracker`
- 返回列表（为空则直接返回）

### Step 2: `auton/agent/agent.py` — `SessionProcessor._do_stop()` 新增后台优化

修改 `_do_stop()`，在 `archive_session()` 后：

```python
async def _do_stop(self, reason: str) -> None:
    # ... 现有逻辑 ...
    self.session_store.archive_session(...)

    # 后台：触发已标记的 skill 优化（不阻塞主进程）
    self._trigger_pending_skill_optimizations()
```

新增私有方法 `_trigger_pending_skill_optimizations()`：

```python
def _trigger_pending_skill_optimizations(self) -> None:
    """扫描所有 skill，对 alert_triggered=true 的在后台触发优化。"""
    import asyncio
    from ..skills.perf_tracker import get_skills_with_pending_alerts

    skills_dir = Path.home() / ".auton" / "skill"
    if not skills_dir.exists():
        return

    pending_trackers = get_skills_with_pending_alerts(skills_dir)
    for tracker in pending_trackers:
        asyncio.create_task(
            self._optimize_skill_async(tracker),
            name=f"skill-optimize-{tracker.skill.name}",
        )
        self._logger.info("queued skill optimization: {n}", n=tracker.skill.name)

async def _optimize_skill_async(self, tracker: "SkillPerfTracker") -> None:
    """后台执行单个 skill 的优化。"""
    from ..skills.optimizer import SkillOptimizer

    try:
        optimizer = SkillOptimizer(tracker, self.llm)
        result = await optimizer.optimize()
        self._logger.info(
            "skill {n} optimized: updated={u} error={e}",
            n=tracker.skill.name,
            u=result.skill_md_updated,
            e=result.error,
        )
    except Exception:
        self._logger.exception("skill optimization failed: {n}", n=tracker.skill.name)
```

### Step 3: `auton/skills/perf_tracker.py` — 优化完成后清除 alert 标志

在 `SkillOptimizer.optimize()` 成功后，清除 `alert_triggered`：

修改 `SkillOptimizer._apply_to_skill_md()` 或在 `optimize()` 成功后调用 `tracker._clear_alert()`（新增）：

```python
def _clear_alert(self) -> None:
    """清除 alert_triggered 标志，优化完成后调用。"""
    data = self._read_perf()
    data["window_7d"]["alert_triggered"] = False
    data["alert"]["alert_count"] = 0  # 可选：重置计数
    data["updated_at"] = _now_iso()
    self._write_perf(data)
```

在 `SkillOptimizer.optimize()` 成功后调用：

```python
# 4. 清除 alert 标志
try:
    self.tracker._clear_alert()
except Exception:
    self._logger.warning("failed to clear alert flag: {e}", e=exc)
```

### Step 4: `auton/skills/__init__.py` — 导出 `get_skills_with_pending_alerts`

---

## 关键文件

| 文件 | 修改 |
|------|------|
| `auton/skills/perf_tracker.py` | 新增 `get_skills_with_pending_alerts()` + `_clear_alert()` |
| `auton/agent/agent.py` | `_do_stop()` 中添加后台任务调度 |
| `auton/skills/__init__.py` | 导出新函数 |

---

## 验证方式

1. **单元测试**：mock `SKILL_PERF.json` 的 `alert_triggered=true`，验证 `get_skills_with_pending_alerts()` 返回正确列表
2. **手动测试**：
   - 使用一个 skill（如 `github`）触发多次失败调用，使 7 日成功率 < 70%
   - 触发 `alert_triggered=true`
   - 结束会话，观察日志是否出现 `queued skill optimization: github`
   - 验证 `SKILL.md` 是否被更新，`alert_triggered` 是否被清除
3. **/`skill perf <name>`**：查看 `alert_triggered` 状态
