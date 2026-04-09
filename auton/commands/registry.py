"""Commands Registry — 命令注册表

加载所有内置命令，提供全局单例访问。
"""

from __future__ import annotations

from loguru import logger

from .base import Command, CommandRegistry as BaseRegistry

__all__ = ["get_command_registry", "CommandRegistry"]

_registry: BaseRegistry | None = None


def get_command_registry() -> BaseRegistry:
    """获取全局命令注册表（懒加载单例）"""
    global _registry
    if _registry is None:
        _registry = _load_builtin_commands()
    return _registry


def _load_builtin_commands() -> BaseRegistry:
    """加载所有内置命令"""
    registry = BaseRegistry()

    # 注册内置命令
    # 注意：这些命令的实现需要 Memory/Skills/Cron 子系统支撑
    # 完整实现在各自里程碑中（M4/M6/M8）

    # ✅ M3 核心命令（已完整实现）
    from .help import HelpCommand
    from .model import ModelCommand
    from .compact import CompactCommand
    from .plan import PlanCommand
    from .config_cmd import ConfigCommand
    from .session_cmd import SessionCommand

    # Help 需要 registry 引用（循环引用，所以这里传入）
    registry.register(HelpCommand(registry))
    registry.register(ModelCommand())
    registry.register(CompactCommand())
    registry.register(PlanCommand())
    registry.register(ConfigCommand())
    registry.register(SessionCommand())

    # 🟡 M4 Memory 命令（stub，memory 子系统未就绪）
    from . import memory_cmd
    registry.register(memory_cmd.MemoryCommand())

    # 🟡 M6 Skills 命令（stub，skills 子系统未就绪）
    from . import skill_cmd
    registry.register(skill_cmd.SkillCommand())

    # ✅ M5 Security 命令
    from . import security_cmd
    registry.register(security_cmd.SecurityCommand())

    # 🟡 M8 Cron 命令（stub，cron 子系统未就绪）
    from . import cron_cmd
    registry.register(cron_cmd.CronCommand())

    # ✅ M9 Tasks 命令
    from . import tasks_cmd
    registry.register(tasks_cmd.TasksCommand())

    # ✅ M10 Workflow 命令
    from . import workflow_cmd
    registry.register(workflow_cmd.WorkflowCommand())

    # ✅ M11 MCP 命令
    from . import mcp_cmd
    registry.register(mcp_cmd.MCPCommand())

    # ✅ M12 Multi-Agent 命令
    from . import agents_cmd
    registry.register(agents_cmd.AgentsCommand())

    logger.info("loaded {n} commands", n=len(registry))
    return registry
