"""Workflow — DSL 解析器

将 YAML 格式工作流定义解析为 WorkflowDefinition 对象。
"""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from .types import (
    TaskRef,
    WorkflowCondition,
    WorkflowDefinition,
    WorkflowStep,
)


class DSLParseError(Exception):
    """DSL 解析错误"""


class DSLParser:
    """工作流 DSL 解析器

    支持格式：YAML（.autowf / .yaml）

    用法：
        parser = DSLParser()
        wf = parser.parse(yaml_text)
        wf = parser.parse_file(Path("~/.auton/workflows/my_flow.autowf"))
    """

    def __init__(self) -> None:
        self._logger = logger.bind(name="DSLParser")

    def parse(self, text: str) -> WorkflowDefinition:
        """解析 YAML/文本为 WorkflowDefinition"""
        import yaml

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise DSLParseError(f"YAML 解析失败: {exc}")

        if not isinstance(data, dict):
            raise DSLParseError("工作流定义必须是顶层字典")

        self._validate_required(data)

        steps = []
        for i, step_data in enumerate(data.get("steps", [])):
            try:
                step = self._parse_step(step_data)
                steps.append(step)
            except Exception as exc:
                raise DSLParseError(f"步骤 {i} 解析失败: {exc}")

        wf = WorkflowDefinition(
            id=data["id"],
            name=data.get("name", data["id"]),
            version=str(data.get("version", "1.0")),
            description=data.get("description", ""),
            steps=steps,
            breakpoints=self._list(data.get("breakpoints", [])),
            on_failure=data.get("on_failure", "stop"),
            tags=self._list(data.get("tags", [])),
        )
        self._logger.debug("parsed workflow {id} with {n} steps", id=wf.id, n=len(steps))
        return wf

    def parse_file(self, path: Path) -> WorkflowDefinition:
        """从文件加载并解析"""
        text = path.read_text(encoding="utf-8")
        return self.parse(text)

    def _validate_required(self, data: dict) -> None:
        """验证必需字段"""
        if "id" not in data:
            raise DSLParseError("缺少必需字段: id")
        if "steps" not in data:
            raise DSLParseError("缺少必需字段: steps")
        if not isinstance(data["steps"], list):
            raise DSLParseError("steps 必须是列表")

    def _parse_step(self, data: dict) -> WorkflowStep:
        """解析单个步骤"""
        step_id = data.get("id")
        if not step_id:
            raise DSLParseError("步骤缺少 id 字段")

        step_type = data.get("type", "task")
        self._validate_step_type(step_type, data)

        task = None
        condition = None
        description = data.get("description", "")
        if step_type == "task":
            task_data = data.get("task", {})
            if not task_data:
                raise DSLParseError(f"步骤 {step_id} 是 task 类型，但缺少 task 字段")
            task = TaskRef(
                title=task_data.get("title", step_id),
                description=task_data.get("description", ""),
                params=task_data.get("params", {}),
            )
            if not description:
                description = task.title

        elif step_type == "condition":
            cond_data = data.get("condition", {})
            condition = WorkflowCondition(
                expression=cond_data.get("expression", ""),
                then=self._list(cond_data.get("then", [])),
                else_=self._list(cond_data.get("else", [])),
            )

        return WorkflowStep(
            id=step_id,
            type=step_type,
            description=description,
            task=task,
            condition=condition,
            depends_on=self._list(data.get("depends_on", [])),
            breakpoints=bool(data.get("breakpoints", False)),
            skip=bool(data.get("skip", False)),
            max_retries=int(data.get("max_retries", 0)),
            on_failure=data.get("on_failure", "stop"),
        )

    def _validate_step_type(self, step_type: str, data: dict) -> None:
        """验证步骤类型合法性"""
        valid_types = {"task", "condition", "input", "output", "checkpoint"}
        if step_type not in valid_types:
            raise DSLParseError(
                f"未知的步骤类型: {step_type}，可选: {', '.join(valid_types)}"
            )

    def _list(self, val) -> list:
        if val is None:
            return []
        if isinstance(val, list):
            return val
        return [val]


class TemplateRenderer:
    """Jinja2 风格的变量替换渲染器

    支持: {{ variable }} 替换
    """

    def __init__(self, params: dict) -> None:
        self.params = params

    def render(self, text: str) -> str:
        """替换 {{ variable }} 为实际值"""
        def replacer(m: re.Match) -> str:
            key = m.group(1).strip()
            # 支持点号访问: {{ env.name }}
            keys = key.split(".")
            val = self.params
            for k in keys:
                if isinstance(val, dict):
                    val = val.get(k)
                else:
                    return m.group(0)
            if val is None:
                return m.group(0)  # 保持原样
            return str(val)

        return re.sub(r"\{\{\s*(.*?)\s*\}\}", replacer, text)

    def evaluate_condition(self, expression: str) -> bool:
        """计算简单条件表达式"""
        expression = self.render(expression.strip())
        return self._eval_simple(expression)

    def _eval_simple(self, expr: str) -> bool:
        """计算简单布尔表达式"""
        # 去除引号
        expr = expr.strip()

        # 处理 == / !=
        for op in ["==", "!=", ">=", "<=", ">", "<"]:
            if op in expr:
                parts = expr.split(op)
                if len(parts) == 2:
                    left, right = parts[0].strip(), parts[1].strip()
                    left = left.strip("'\"")
                    right = right.strip("'\"")
                    try:
                        left_n = float(left)
                        right_n = float(right)
                        left, right = left_n, right_n
                    except ValueError:
                        pass
                    if op == "==":
                        return left == right
                    if op == "!=":
                        return left != right
                    if op == ">=":
                        return left >= right
                    if op == "<=":
                        return left <= right
                    if op == ">":
                        return left > right
                    if op == "<":
                        return left < right

        # 纯字符串真值
        if expr.lower() in ("true", "yes", "1"):
            return True
        if expr.lower() in ("false", "no", "0", "null", "none"):
            return False
        return bool(expr)
