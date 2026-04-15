"""Workflow — 工作流持久化存储

工作流定义存储在 ~/.auton/workflows/
工作流执行记录存储在 ~/.auton/workflow_runs/
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from ..core.paths import resolve_userspace_path

from .dsl import DSLParser, DSLParseError
from .types import WorkflowDefinition, WorkflowRun


class WorkflowStore:
    """工作流定义存储"""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = storage_dir or resolve_userspace_path("workflows")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.parser = DSLParser()
        self._logger = logger.bind(name="WorkflowStore")

    # ─── 工作流定义 CRUD ─────────────────────────────────────────────────

    def save(self, wf: WorkflowDefinition) -> None:
        """保存工作流定义（YAML 文件）"""
        import yaml
        from datetime import datetime

        wf.updated_at = datetime.now()
        path = self._workflow_path(wf.id)
        # 保留原始 YAML 格式
        data = {
            "id": wf.id,
            "name": wf.name,
            "version": wf.version,
            "description": wf.description,
            "breakpoints": wf.breakpoints,
            "on_failure": wf.on_failure,
            "tags": wf.tags,
            "steps": [],
        }
        for step in wf.steps:
            s = {
                "id": step.id,
                "type": step.type,
                "description": step.description,
                "depends_on": step.depends_on,
                "breakpoints": step.breakpoints,
                "skip": step.skip,
                "max_retries": step.max_retries,
                "on_failure": step.on_failure,
            }
            if step.task:
                s["task"] = {
                    "title": step.task.title,
                    "description": step.task.description,
                    "params": step.task.params,
                }
            if step.condition:
                s["condition"] = {
                    "expression": step.condition.expression,
                    "then": step.condition.then,
                    "else": step.condition.else_,
                }
            data["steps"].append(s)

        path.write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False), encoding="utf-8")
        self._logger.debug("saved workflow {id}", id=wf.id)

    def load(self, workflow_id: str) -> WorkflowDefinition | None:
        """加载工作流定义"""
        path = self._workflow_path(workflow_id)
        if not path.exists():
            return None
        try:
            return self.parser.parse_file(path)
        except DSLParseError as exc:
            self._logger.warning("failed to load workflow {id}: {e}", id=workflow_id, e=exc)
            return None

    def load_text(self, workflow_id: str) -> str:
        """加载工作流原始 YAML 文本"""
        path = self._workflow_path(workflow_id)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def delete(self, workflow_id: str) -> bool:
        """删除工作流定义"""
        path = self._workflow_path(workflow_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list(self) -> list[WorkflowDefinition]:
        """列出所有工作流定义"""
        workflows: list[WorkflowDefinition] = []
        for path in self.storage_dir.glob("*.autowf"):
            try:
                wf = self.parser.parse_file(path)
                workflows.append(wf)
            except DSLParseError:
                continue
        for path in self.storage_dir.glob("*.yaml"):
            if path.name == "index.yaml":
                continue
            try:
                wf = self.parser.parse_file(path)
                workflows.append(wf)
            except DSLParseError:
                continue
        workflows.sort(key=lambda w: w.updated_at, reverse=True)
        return workflows

    def parse_text(self, text: str) -> WorkflowDefinition:
        """解析 YAML 文本并保存"""
        wf = self.parser.parse(text)
        self.save(wf)
        return wf

    def _workflow_path(self, workflow_id: str) -> Path:
        # 支持 .autowf 和 .yaml 后缀
        p = self.storage_dir / f"{workflow_id}.autowf"
        if p.exists():
            return p
        return self.storage_dir / f"{workflow_id}.yaml"


# ─── 执行记录存储 ──────────────────────────────────────────────────────────────

class RunStore:
    """工作流执行记录存储"""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = storage_dir or resolve_userspace_path("workflow_runs")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logger.bind(name="RunStore")

    def save(self, run: WorkflowRun) -> None:
        """保存执行记录"""
        path = self._run_path(run.id)
        path.write_text(
            json.dumps(run.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._logger.debug("saved run {id} status={status}", id=run.id, status=run.status)

    def load(self, run_id: str) -> WorkflowRun | None:
        """加载执行记录"""
        path = self._run_path(run_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return WorkflowRun.from_dict(data)
        except (json.JSONDecodeError, KeyError) as exc:
            self._logger.warning("failed to load run {id}: {e}", id=run_id, e=exc)
            return None

    def delete(self, run_id: str) -> bool:
        """删除执行记录"""
        path = self._run_path(run_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list(self, workflow_id: str | None = None, status: str | None = None) -> list[WorkflowRun]:
        """列出执行记录"""
        runs: list[WorkflowRun] = []
        for path in self.storage_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                run = WorkflowRun.from_dict(data)
                if workflow_id and run.workflow_id != workflow_id:
                    continue
                if status and run.status != status:
                    continue
                runs.append(run)
            except (json.JSONDecodeError, KeyError):
                continue
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return runs

    def list_active(self) -> list[WorkflowRun]:
        """列出活跃执行（running / breakpoint / idle）"""
        active_statuses = {"running", "breakpoint", "idle"}
        return [r for r in self.list() if r.status in active_statuses]

    def _run_path(self, run_id: str) -> Path:
        return self.storage_dir / f"{run_id}.json"
