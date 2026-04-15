"""Model Command — /model"""

from __future__ import annotations

from typing import Any

from .base import Command, CommandResult


class ModelCommand(Command):
    name = "model"
    description = "切换 LLM Provider 或查看当前模型"
    patterns = [
        ("/model",),
        ("/model", "<model_name>"),
    ]

    SUPPORTED_PROVIDERS = {
        "anthropic": ["claude-sonnet-4-20250514", "claude-opus-4-20250514"],
        "minimax": ["MiniMax-M2.7", "MiniMax-M2.1-32K"],
        "openai": ["gpt-4o", "gpt-4-turbo"],
        "ollama": ["llama3", "codellama"],
    }

    async def handle(self, args: dict[str, Any]) -> CommandResult:
        if not args:
            # /model — 显示当前模型
            from ..llm import AnthropicProvider, MiniMaxProvider

            lines = [
                "# Available Models",
                "",
            ]
            for provider, models in self.SUPPORTED_PROVIDERS.items():
                lines.append(f"## {provider}")
                for model in models:
                    lines.append(f"- `{model}`")
                lines.append("")

            return CommandResult(content="\n".join(lines))

        model_name = args.get("<model_name>") or args.get("_subcommand", "")
        if model_name.startswith("MiniMax") or model_name.startswith("claude"):
            # 判断 provider
            if model_name.startswith("MiniMax"):
                return CommandResult(
                    content=f"[stub] Switch to minimax provider with model `{model_name}`. "
                    "Provider switching requires CLI restart or session reload.",
                )
            else:
                return CommandResult(
                    content=f"[stub] Switch to anthropic provider with model `{model_name}`. "
                    "Provider switching requires CLI restart or session reload.",
                )

        return CommandResult(
            content=f"Unknown model: `{model_name}`. Use `/model` to see available models.",
            success=False,
        )
