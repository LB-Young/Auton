"""Subagents — BaseSubagent: 抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from loguru import logger

from .types import SubagentConfig, SubagentPhase, SubagentResult

if TYPE_CHECKING:
    pass


class BaseSubagent(ABC):
    """所有 Subagent 的抽象基类。

    设计原则：
      - 每个 Subagent 是无状态的工具类，通过 run() 方法执行
      - 通过 config() 类方法返回 SubagentConfig
      - 通过 system_prompt() 类方法返回专用系统提示词
      - 子类实现 _execute() 核心逻辑
    """

    name: str = ""          # 唯一标识
    description: str = ""   # 何时使用

    @classmethod
    def config(cls) -> SubagentConfig:
        """返回 Subagent 配置（子类可覆盖）"""
        return SubagentConfig(
            name=cls.name,
            description=cls.description,
        )

    @classmethod
    @abstractmethod
    def system_prompt(cls) -> str:
        """返回此 Subagent 的专用系统提示词（子类必须实现）"""
        raise NotImplementedError

    async def run(
        self,
        context: dict[str, Any],
        **kwargs: Any,
    ) -> SubagentResult:
        """异步执行入口。"""
        from datetime import datetime
        logger.info("subagent {n} starting", n=self.name)
        result = SubagentResult(
            name=self.name,
            success=True,
            phase=SubagentPhase.PLANNING,
        )
        try:
            output, findings, recommendations = await self._execute(context, **kwargs)
            result.output = output
            result.findings = findings
            result.recommendations = recommendations
            result.phase = SubagentPhase.COMPLETED
        except Exception as exc:
            result.success = False
            result.errors.append(str(exc))
            result.phase = SubagentPhase.COMPLETED
            logger.exception("subagent {n} failed: {e}", n=self.name, e=exc)
        result.completed_at = datetime.now()
        return result

    @abstractmethod
    async def _execute(
        self,
        context: dict[str, Any],
    ) -> tuple[str, list[str], list[str]]:
        """核心执行逻辑（子类必须实现）。Returns: (output, findings, recommendations)"""
        raise NotImplementedError
