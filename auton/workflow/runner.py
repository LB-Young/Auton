"""Workflow — 工作流执行引擎

执行工作流步骤，处理条件分支，断点续执。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from loguru import logger

from .dsl import TemplateRenderer
from .store import WorkflowStore, RunStore
from .types import (
    RunStatus,
    StepStatus,
    WorkflowCondition,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStep,
)


class WorkflowRunner:
    """工作流执行引擎

    用法：
        runner = WorkflowRunner()
        run = runner.create_run("wf_deploy", params={"env": "prod"})
        await runner.run(run.id)          # 同步执行
        runner.pause(run.id)             # 暂停（断点）
        runner.resume(run.id)            # 恢复
    """

    def __init__(
        self,
        wf_store: WorkflowStore | None = None,
        run_store: RunStore | None = None,
    ) -> None:
        self.wf_store = wf_store or WorkflowStore()
        self.run_store = run_store or RunStore()
        self._logger = logger.bind(name="WorkflowRunner")

    # ─── 创建执行实例 ─────────────────────────────────────────────────────

    def create_run(
        self,
        workflow_id: str,
        params: dict | None = None,
    ) -> WorkflowRun | None:
        """创建工作流执行实例"""
        wf = self.wf_store.load(workflow_id)
        if wf is None:
            self._logger.warning("workflow not found: {id}", id=workflow_id)
            return None

        run = WorkflowRun(
            workflow_id=wf.id,
            workflow_name=wf.name,
            status="idle",
            params=params or {},
            step_states={s.id: "pending" for s in wf.steps},
        )
        run.add_log("run_created", detail=f"workflow={wf.id}")
        self.run_store.save(run)
        self._logger.info("created run {id} for workflow {wf}", id=run.id, wf=workflow_id)
        return run

    # ─── 同步执行（全部完成）────────────────────────────────────────────

    async def run(self, run_id: str) -> WorkflowRun | None:
        """执行工作流（异步完整执行）"""
        run = self.run_store.load(run_id)
        if run is None:
            return None

        wf = self.wf_store.load(run.workflow_id)
        if wf is None:
            run.status = "failed"
            run.error = f"工作流定义不存在: {run.workflow_id}"
            self.run_store.save(run)
            return run

        run.status = "running"
        run.started_at = datetime.now()
        run.add_log("run_started")
        self.run_store.save(run)

        try:
            await self._execute_steps(wf, run)
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
            run.add_log("run_failed", detail=str(exc))
            self.run_store.save(run)
            self._logger.error("run {id} failed: {e}", id=run_id, e=exc)

        return run

    async def _execute_steps(self, wf: WorkflowDefinition, run: WorkflowRun) -> None:
        """按拓扑顺序执行所有步骤"""
        sorted_steps = wf.topological_order()
        renderer = TemplateRenderer(run.params)

        for step in sorted_steps:
            run.current_step = step.id
            run.step_states[step.id] = "running"
            run.add_log("step_start", step_id=step.id)
            self.run_store.save(run)

            try:
                result = await self._execute_step(step, wf, run, renderer)
                if result.status == "breakpoint":
                    run.status = "breakpoint"
                    run.breakpoint_step = step.id
                    run.breakpoint_reason = result.output or "断点触发"
                    run.add_log("breakpoint", step_id=step.id, detail=result.output)
                    self.run_store.save(run)
                    return  # 暂停执行
            except Exception as exc:
                await self._handle_step_failure(step, wf, run, exc)
                if wf.on_failure == "stop":
                    run.status = "failed"
                    run.error = str(exc)
                    run.add_log("run_failed", step_id=step.id, detail=str(exc))
                    self.run_store.save(run)
                    return
                # skip 或 retry 由 _handle_step_failure 处理

        # 所有步骤完成
        run.status = "completed"
        run.completed_at = datetime.now()
        run.add_log("run_completed")
        self.run_store.save(run)

    async def _execute_step(
        self,
        step: WorkflowStep,
        wf: WorkflowDefinition,
        run: WorkflowRun,
        renderer: TemplateRenderer,
    ) -> StepResult:
        """执行单个步骤"""
        from datetime import datetime

        step.started_at = datetime.now()

        # 检查是否应跳过
        if step.skip:
            run.step_states[step.id] = "skipped"
            self.run_store.save(run)
            return StepResult(step_id=step.id, status="skipped")

        # 根据类型执行
        if step.type == "task":
            result = await self._execute_task_step(step, wf, run, renderer)
        elif step.type == "condition":
            result = await self._execute_condition_step(step, wf, run, renderer)
        elif step.type == "checkpoint":
            result = self._execute_checkpoint_step(step, run)
        elif step.type == "input":
            result = self._execute_input_step(step, run, renderer)
        elif step.type == "output":
            result = self._execute_output_step(step, run, renderer)
        else:
            result = StepResult(step_id=step.id, status="completed", output=f"unknown type: {step.type}")

        step.completed_at = datetime.now()

        if result.status == "breakpoint":
            run.step_states[step.id] = "breakpoint"
            run.finished_step_id = step.id
        elif result.status == "failed":
            run.step_states[step.id] = "failed"
            run.finished_step_id = step.id
        else:
            run.step_states[step.id] = "completed"
            run.finished_step_id = step.id

        step.output = result.output
        step.error = result.error
        step.task_id = result.task_id
        run.output += f"\n[{step.id}] {result.output}"
        run.add_log("step_done", step_id=step.id, detail=result.status)

        self.run_store.save(run)
        return result

    async def _execute_task_step(
        self,
        step: WorkflowStep,
        wf: WorkflowDefinition,
        run: WorkflowRun,
        renderer: TemplateRenderer,
    ) -> StepResult:
        """执行任务步骤（关联 M9 Task）"""
        from auton.task import TaskManager

        tm = TaskManager()
        task_ref = step.task
        if task_ref is None:
            return StepResult(step_id=step.id, status="completed", output="(no task)")

        # 渲染任务描述
        title = renderer.render(task_ref.title)
        desc = renderer.render(task_ref.description)

        # 创建 M9 Task
        task = tm.create(
            title=title,
            description=desc,
            tags=["workflow", wf.id],
            created_by="workflow",
        )
        step.task_id = task.id
        run.add_log("task_created", step_id=step.id, detail=f"task_id={task.id}")

        # 轮询任务状态
        max_wait = 300  # 最多等 300 秒
        waited = 0
        while waited < max_wait:
            await asyncio.sleep(1)
            waited += 1

            t = tm.get(task.id)
            if t is None:
                return StepResult(step_id=step.id, status="failed", error="task not found")

            if t.status == "completed":
                return StepResult(
                    step_id=step.id,
                    status="completed",
                    output=t.output or "任务完成",
                    task_id=task.id,
                )
            if t.status == "failed":
                return StepResult(
                    step_id=step.id,
                    status="failed",
                    error=t.error or "任务失败",
                    task_id=task.id,
                )
            if t.status == "killed":
                return StepResult(
                    step_id=step.id,
                    status="failed",
                    error="任务被终止",
                    task_id=task.id,
                )

        # 超时
        tm.stop(task.id)
        return StepResult(step_id=step.id, status="failed", error="任务执行超时（300s）")

    async def _execute_condition_step(
        self,
        step: WorkflowStep,
        wf: WorkflowDefinition,
        run: WorkflowRun,
        renderer: TemplateRenderer,
    ) -> StepResult:
        """执行条件分支"""
        cond = step.condition
        if cond is None:
            return StepResult(step_id=step.id, status="completed", output="无条件")

        # 计算条件
        expr = renderer.render(cond.expression)
        result = renderer.evaluate_condition(expr)
        cond.result = result

        if result:
            output = f"条件满足 ({{{{ expr }}}}): 执行 {cond.then}"
            # 标记 else 分支为 skipped
            for else_step_id in cond.else_:
                if else_step_id in run.step_states:
                    run.step_states[else_step_id] = "skipped"
        else:
            output = f"条件不满足: 执行 {cond.else_}"
            for then_step_id in cond.then:
                if then_step_id in run.step_states:
                    run.step_states[then_step_id] = "skipped"

        return StepResult(step_id=step.id, status="completed", output=output)

    def _execute_checkpoint_step(
        self,
        step: WorkflowStep,
        run: WorkflowRun,
        renderer: TemplateRenderer,
    ) -> StepResult:
        """执行断点步骤（无条件触发断点）"""
        if step.breakpoints:
            return StepResult(
                step_id=step.id,
                status="breakpoint",
                output=f"断点: {step.description}",
            )
        return StepResult(step_id=step.id, status="completed", output="checkpoint")

    def _execute_input_step(
        self,
        step: WorkflowStep,
        run: WorkflowRun,
        renderer: TemplateRenderer,
    ) -> StepResult:
        """执行输入步骤（永远断点，等待用户）"""
        return StepResult(
            step_id=step.id,
            status="breakpoint",
            output=f"等待输入: {step.description}",
        )

    def _execute_output_step(
        self,
        step: WorkflowStep,
        run: WorkflowRun,
        renderer: TemplateRenderer,
    ) -> StepResult:
        """执行输出步骤"""
        output = renderer.render(step.description)
        return StepResult(step_id=step.id, status="completed", output=output)

    async def _handle_step_failure(
        self,
        step: WorkflowStep,
        wf: WorkflowDefinition,
        run: WorkflowRun,
        exc: Exception,
    ) -> None:
        """处理步骤失败"""
        run.step_states[step.id] = "failed"
        run.finished_step_id = step.id
        step.error = str(exc)
        run.add_log("step_failed", step_id=step.id, detail=str(exc))
        self.run_store.save(run)

        if step.on_failure == "retry" and step.max_retries > 0:
            # 重试逻辑（简化版：直接重试一次）
            for i in range(step.max_retries):
                run.add_log("step_retry", step_id=step.id, detail=f"retry {i+1}")
                self.run_store.save(run)
                step.status = "running"
                return  # 实际重试由调用方处理
        elif step.on_failure == "skip":
            run.step_states[step.id] = "skipped"
            run.add_log("step_skipped", step_id=step.id)

    # ─── 断点续执 ────────────────────────────────────────────────────────

    async def resume(self, run_id: str) -> WorkflowRun | None:
        """从断点恢复执行"""
        run = self.run_store.load(run_id)
        if run is None:
            return None
        if run.status != "breakpoint":
            self._logger.warning("run {id} is not at breakpoint (status={s})", id=run_id, s=run.status)
            return run

        wf = self.wf_store.load(run.workflow_id)
        if wf is None:
            run.status = "failed"
            run.error = "工作流定义不存在"
            self.run_store.save(run)
            return run

        run.status = "running"
        run.breakpoint_step = None
        run.breakpoint_reason = ""
        run.add_log("run_resumed", detail=f"resuming from step {run.finished_step_id}")
        self.run_store.save(run)

        try:
            await self._execute_steps(wf, run)
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
            run.add_log("run_failed", detail=str(exc))
            self.run_store.save(run)

        return run

    def pause(self, run_id: str) -> WorkflowRun | None:
        """手动暂停（在当前步骤断点）"""
        run = self.run_store.load(run_id)
        if run is None:
            return None
        if run.status not in {"running", "idle"}:
            return run

        run.status = "breakpoint"
        run.breakpoint_step = run.current_step
        run.breakpoint_reason = "用户手动暂停"
        run.add_log("run_paused", step_id=run.current_step, detail="manual pause")
        self.run_store.save(run)
        return run

    def stop(self, run_id: str) -> WorkflowRun | None:
        """取消执行"""
        run = self.run_store.load(run_id)
        if run is None:
            return None
        run.status = "cancelled"
        run.add_log("run_cancelled")
        self.run_store.save(run)
        return run

    # ─── 查询 ────────────────────────────────────────────────────────────

    def get_run(self, run_id: str) -> WorkflowRun | None:
        return self.run_store.load(run_id)

    def list_runs(self, workflow_id: str | None = None, status: str | None = None) -> list[WorkflowRun]:
        return self.run_store.list(workflow_id=workflow_id, status=status)
