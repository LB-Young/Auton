"""Agent Policies — 决策策略"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from loguru import logger

from .types import ProcessResult


@dataclass
class PolicyInput:
    """策略输入：供决策使用的信息"""
    message_count: int
    token_count: int
    last_user_message: str
    step_count: int
    user_ask_mode: Literal["auto", "ask", "stop"] = "auto"
    explicit_stop: bool = False


class DecisionPolicy:
    """决定每轮执行后的行为：continue / compact / stop"""

    def __init__(
        self,
        compact_threshold: int = 180_000,
        max_turns: int = 500,
        recent_protect_turns: int = 2,
        recent_token_budget: int = 40_000,
    ) -> None:
        self.compact_threshold = compact_threshold
        self.max_turns = max_turns
        self.recent_protect_turns = recent_protect_turns
        self.recent_token_budget = recent_token_budget
        self._logger = logger.bind(name="DecisionPolicy")

    def decide(self, inp: PolicyInput) -> ProcessResult:
        """根据输入决定 ProcessResult"""
        # 1. 用户显式要求停止
        if inp.explicit_stop:
            return ProcessResult(status="stop", reason="user requested stop")

        # 2. token 接近上限 → compact
        if inp.token_count >= self.compact_threshold:
            self._logger.info(
                "policy=compact token_count={n} threshold={t}",
                n=inp.token_count, t=self.compact_threshold,
            )
            return ProcessResult(status="compact", reason=f"token count {inp.token_count} exceeds threshold")

        # 3. 达到最大轮数
        if inp.step_count >= self.max_turns:
            return ProcessResult(status="stop", reason="max turns reached")

        # 4. 用户要求确认
        if inp.user_ask_mode == "ask":
            return ProcessResult(status="stop", reason="awaiting user confirmation")

        # 5. 检测 stop 关键词
        lower = inp.last_user_message.lower().strip()
        stop_triggers = {"再见", "bye", "exit", "quit", "停止", "结束", "完成"}
        if lower in stop_triggers:
            return ProcessResult(status="stop", reason=f"user message triggers stop: {inp.last_user_message!r}")

        # 6. 默认继续
        return ProcessResult(status="continue", reason="")

    # ─── Compact 策略 ────────────────────────────────────────────────────

    def should_compact_now(self, token_count: int) -> bool:
        """判断当前是否需要 compact"""
        return token_count >= self.compact_threshold

    def compact_target_tokens(self) -> int:
        """compact 后希望达到的 token 数（约 50%）"""
        return int(self.compact_threshold * 0.5)
