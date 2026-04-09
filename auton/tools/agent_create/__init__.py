"""agent_create Tool — 创建并运行子 Agent（M12 Multi-Agent）"""

from __future__ import annotations

from ..base import Tool, ToolResult


class AgentCreateTool(Tool):
    """agent_create 工具

    主 Agent 通过此工具调用子 agent。
    支持等待完成（wait=true）或立即返回 run_id（wait=false）。
    """
    name = "agent_create"
    description = "Create and run a sub-agent to complete a specific task"

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "Agent name (builtin or user-defined)",
                },
                "prompt": {
                    "type": "string",
                    "description": "Task description for the sub-agent",
                },
                "wait": {
                    "type": "boolean",
                    "description": "Whether to wait for completion (default: true)",
                    "default": True,
                },
            },
            "required": ["agent", "prompt"],
        }

    async def execute(
        self,
        agent: str,
        prompt: str,
        wait: bool = True,
    ) -> ToolResult:
        from auton.agent import AgentManager
        from auton.agent.session import Session

        # 获取父会话 ID（从当前 session 注入）
        parent_session_id = getattr(Session, "_current_session_id", "main") if hasattr(Session, "_current_session_id") else "main"

        manager = AgentManager()
        run = manager.create_run(agent, prompt, parent_session_id)
        if not run:
            return ToolResult(
                content=f"Agent not found: {agent}",
                success=False,
                error=f"No agent named '{agent}'",
            )

        if not wait:
            # 后台运行，立即返回 run_id
            return ToolResult(
                content=f"Agent '{agent}' started in background. run_id: `{run.run_id}`\n"
                f"Use `/agents get {run.run_id}` to check status.",
            )

        # 等待完成
        result = await manager.start_run(run.run_id)
        run = manager.get_run(run.run_id)
        status_emoji = {
            "completed": "✅",
            "failed": "❌",
            "aborted": "🛑",
        }
        icon = status_emoji.get(run.status, "?") if run else "?"
        lines = [
            f"{icon} Agent `{agent}` finished (run_id: `{run.run_id}`)",
            "",
            "## Result",
            result,
        ]
        if run and run.error:
            lines.append("")
            lines.append(f"**Error**: {run.error}")

        return ToolResult(content="\n".join(lines))
