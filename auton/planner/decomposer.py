"""Planner — 任务分解器

将复杂任务递归分解为可执行的原子步骤。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from .types import PlanStep, Risk, RiskLevel

if TYPE_CHECKING:
    from ..llm.base import LLMProvider


@dataclass
class DecompositionResult:
    steps: list[dict]
    subtask_boundaries: list[int]  # 子任务分界线（步骤 index）
    confidence: float


class TaskDecomposer:
    """任务分解器

    支持两种模式：
    1. LLM 模式（依赖 LLM）：更智能的分解，能理解语义
    2. 启发式模式（无 LLM）：基于规则的结构化分解
    """

    def __init__(self, llm: "LLMProvider | None" = None) -> None:
        self.llm = llm
        self._logger = logger.bind(name="TaskDecomposer")

    def decompose(
        self,
        task: str,
        context: str = "",
        max_depth: int = 2,
    ) -> DecompositionResult:
        """分解任务为步骤

        Args:
            task: 原始任务描述
            context: 额外上下文（项目信息、技术栈等）
            max_depth: 最大递归深度
        """
        if self.llm is not None:
            return self._decompose_llm(task, context, max_depth)
        else:
            return self._decompose_heuristic(task, context)

    def _decompose_llm(
        self,
        task: str,
        context: str,
        max_depth: int,
    ) -> DecompositionResult:
        """基于 LLM 的智能分解"""
        prompt = self._build_decompose_prompt(task, context, max_depth)

        try:
            response = self.llm.complete(prompt)
            return self._parse_llm_response(response, task)
        except Exception as exc:
            self._logger.warning("LLM decompose failed: {e}, falling back to heuristic", e=exc)
            return self._decompose_heuristic(task, context)

    def _build_decompose_prompt(
        self,
        task: str,
        context: str,
        max_depth: int,
    ) -> str:
        context_part = f"\n\n## 项目上下文\n{context}" if context else ""
        return f"""将以下任务分解为 3-7 个可执行的原子步骤。

## 任务
{task}
{context_part}

## 要求
1. 每个步骤必须是一个原子操作（一个工具调用或一段文字描述）
2. 步骤之间标注依赖关系（用 "依赖: step_N" 表示）
3. 每个步骤标注：
   - description: 简短描述
   - tool: 建议使用的工具（read/edit/write/bash/grep/glob/web_search 等，null 表示无需工具）
   - params: 工具参数（如果 tool 非 null）
   - confidence: 完成把握（0.0-1.0）

## 输出格式（JSON array）
[
  {{
    "index": 1,
    "description": "分析现有 auth 模块结构",
    "tool": "grep",
    "params": {{"pattern": "def .*auth", "path": "src/auth"}},
    "confidence": 0.9,
    "depends_on": []
  }},
  ...
]

## 开始分解
"""

    def _parse_llm_response(self, response: str, task: str) -> DecompositionResult:
        """解析 LLM 返回的分解结果"""
        import json

        # 提取 JSON 部分
        json_match = re.search(r"\[[\s\S]*\]", response)
        if not json_match:
            # fallback
            return self._decompose_heuristic(task, "")

        try:
            data = json.loads(json_match.group())
            steps = []
            for item in data:
                step = {
                    "description": item.get("description", ""),
                    "tool": item.get("tool"),
                    "params": item.get("params", {}),
                    "confidence": item.get("confidence", 0.8),
                    "depends_on": item.get("depends_on", []),
                }
                steps.append(step)

            confidence = sum(s["confidence"] for s in steps) / len(steps) if steps else 0.5
            return DecompositionResult(
                steps=steps,
                subtask_boundaries=[],
                confidence=confidence,
            )
        except json.JSONDecodeError:
            return self._decompose_heuristic(task, "")

    def _decompose_heuristic(self, task: str, context: str) -> DecompositionResult:
        """基于规则的启发式分解

        适用于没有 LLM 或 LLM 不可用时的降级方案。
        """
        task_lower = task.lower()
        steps: list[dict] = []
        idx = 1

        # 通用分析步骤
        needs_analysis = any(k in task_lower for k in ["重构", "重构", "修改", "改进", "优化", "设计", "重构", "写", "开发", "实现", "build", "refactor", "implement", "write", "create"])
        needs_test = any(k in task_lower for k in ["测试", "测试", "test", "单元测试"])
        needs_review = any(k in task_lower for k in ["review", "review", "审查"])

        # 1. 分析步骤
        if needs_analysis:
            steps.append({
                "index": idx,
                "description": f"分析任务范围和现有代码结构: {task[:50]}",
                "tool": "glob",
                "params": {"pattern": "**/*.py"},
                "confidence": 0.9,
                "depends_on": [],
            })
            idx += 1

            steps.append({
                "index": idx,
                "description": "理解现有代码依赖关系和接口",
                "tool": "grep",
                "params": {"pattern": "^class |^def ", "path": "."},
                "confidence": 0.85,
                "depends_on": [idx - 1],
            })
            idx += 1

        # 2. 核心实现步骤
        steps.append({
            "index": idx,
            "description": f"执行核心实现: {task[:50]}",
            "tool": None,
            "params": {},
            "confidence": 0.7,
            "depends_on": [idx - 1] if idx > 1 else [],
        })
        idx += 1

        # 3. 测试步骤
        if needs_test:
            steps.append({
                "index": idx,
                "description": "编写并运行测试验证实现",
                "tool": "bash",
                "params": {"command": "python -m pytest tests/ -v"},
                "confidence": 0.8,
                "depends_on": [idx - 1],
            })
            idx += 1

        # 4. 审查步骤
        if needs_review:
            steps.append({
                "index": idx,
                "description": "代码审查并检查潜在问题",
                "tool": None,
                "params": {},
                "confidence": 0.75,
                "depends_on": [idx - 1],
            })

        # 确保至少有 3 步
        if len(steps) < 3:
            steps.append({
                "index": idx,
                "description": "验证最终结果",
                "tool": None,
                "params": {},
                "confidence": 0.8,
                "depends_on": [idx - 1] if idx > 1 else [],
            })

        return DecompositionResult(
            steps=steps,
            subtask_boundaries=[],
            confidence=sum(s["confidence"] for s in steps) / len(steps),
        )

    @staticmethod
    def suggest_tool_for_step(description: str) -> tuple[str | None, dict]:
        """根据步骤描述建议工具

        Returns:
            (tool_name, suggested_params)
        """
        desc_lower = description.lower()

        # 文件读取类
        if any(k in desc_lower for k in ["分析", "查看", "理解", "检查", "analyze", "view", "check"]):
            if any(k in desc_lower for k in ["结构", "目录", "文件列表", "structure"]):
                return "glob", {}
            return "grep", {"pattern": "^def |^class "}

        # 代码修改类
        if any(k in desc_lower for k in ["修改", "改动", "编辑", "edit", "modify", "change"]):
            return "edit", {}

        # 新建文件类
        if any(k in desc_lower for k in ["新建", "创建", "write", "create", "add"]):
            return "write", {}

        # 执行命令类
        if any(k in desc_lower for k in ["运行", "执行", "test", "run", "install"]):
            if "test" in desc_lower:
                return "bash", {"command": "python -m pytest -v"}
            return "bash", {}

        # 搜索类
        if any(k in desc_lower for k in ["搜索", "查找", "search", "find"]):
            return "grep", {}

        return None, {}

    @staticmethod
    def estimate_confidence(description: str, tool: str | None) -> float:
        """估计步骤完成把握"""
        base = 0.8

        if tool is None:
            # 需要推理的步骤，降低把握
            return base - 0.1

        # 已知安全的工具
        safe_tools = {"glob", "grep", "read"}
        if tool in safe_tools:
            return base + 0.1

        # 有风险的命令
        risky_patterns = ["rm", "delete", "drop", "shutdown", "kill"]
        if tool == "bash":
            for pattern in risky_patterns:
                if pattern in description.lower():
                    return base - 0.2

        return base
