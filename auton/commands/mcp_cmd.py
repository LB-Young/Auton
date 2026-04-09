"""MCP Command — /mcp（MCP Server 管理）"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..core.config import get_config
from ..tools.mcp import MCPClient, MCPClientConfig, load_mcp_servers, stop_mcp_servers
from .base import Command, CommandResult


class MCPCommand(Command):
    """MCP Server 管理命令"""

    name = "mcp"
    description = "管理 MCP Server（list/status/start/stop/add/remove）"
    patterns = [
        ("/mcp",),
        ("/mcp", "list"),
        ("/mcp", "status"),
        ("/mcp", "start"),
        ("/mcp", "stop"),
        ("/mcp", "add"),
        ("/mcp", "remove"),
        ("/mcp", "start", "<name>"),
        ("/mcp", "stop", "<name>"),
        ("/mcp", "remove", "<name>"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._logger = logger.bind(name="MCPCommand")

    async def handle(self, args: dict[str, Any]) -> CommandResult:
        sub = args.get("_subcommand") or "list"

        handler = {
            "list": self._list,
            "status": self._status,
            "start": self._start,
            "stop": self._stop,
            "add": self._add,
            "remove": self._remove,
        }.get(sub)

        if handler:
            return await handler(args)
        return CommandResult(content=self._usage(), success=False)

    # ─── /mcp list ─────────────────────────────────────────────────────────

    async def _list(self, _args: dict) -> CommandResult:
        from ..tools.mcp import _mcp_clients

        config = get_config()
        servers = config.mcp.servers
        active = set(_mcp_clients.keys())

        if not servers:
            return CommandResult(content=self._empty_state())

        lines = ["## MCP Servers\n"]
        for s in servers:
            status_icon = "✅ running" if s.name in active else "⚠️  stopped"
            cmd_str = " ".join(s.command)
            lines.append(f"- **{s.name}** — {status_icon}")
            lines.append(f"  命令: `{cmd_str}`")
            if s.args:
                lines.append(f"  参数: `{' '.join(s.args)}`")

        return CommandResult(content="\n".join(lines))

    def _empty_state(self) -> str:
        return (
            "**当前没有配置 MCP Server。**\n\n"
            "在 `~/.auton/config.yaml` 中添加配置：\n"
            "```yaml\n"
            "mcp:\n"
            "  servers:\n"
            "    - name: github\n"
            "      command: [npx, -y, @modelcontextprotocol/server-github]\n"
            "      env:\n"
            "        GITHUB_TOKEN: ${GITHUB_TOKEN}\n"
            "```\n\n"
            "或使用 `/mcp add` 引导添加。"
        )

    # ─── /mcp status ───────────────────────────────────────────────────────

    async def _status(self, _args: dict) -> CommandResult:
        from ..tools.mcp import _mcp_clients

        config = get_config()
        servers = config.mcp.servers
        active = set(_mcp_clients.keys())

        if not servers:
            return CommandResult(content="未配置任何 MCP Server。")

        lines = ["## MCP Status\n"]
        for s in servers:
            if s.name in active:
                client = _mcp_clients[s.name]
                tool_count = len(client.tools)
                status_icon = "✅"
                status_text = f"running — {tool_count} 工具"
            else:
                status_icon = "⚠️ "
                status_text = "stopped"
            lines.append(f"{status_icon} **{s.name}**: {status_text}")

        return CommandResult(content="\n".join(lines))

    # ─── /mcp start <name> ────────────────────────────────────────────────

    async def _start(self, args: dict) -> CommandResult:
        from ..tools.mcp import _mcp_clients
        from ..tools import get_registry

        name = args.get("<name>", "").strip()
        if not name:
            return CommandResult(content="用法：`/mcp start <name>`", success=False)

        config = get_config()
        server_cfg = next((s for s in config.mcp.servers if s.name == name), None)
        if server_cfg is None:
            return CommandResult(content=f"未找到 MCP Server：`{name}`", success=False)

        if name in _mcp_clients:
            return CommandResult(content=f"✅ MCP Server `{name}` 已在运行。")

        mcp_cfg = server_cfg.model_dump()
        client = MCPClient(MCPClientConfig(**mcp_cfg))
        try:
            await client.start()
            _mcp_clients[name] = client
            registry = get_registry()
            registry.set_mcp_client(name, client)
            tool_count = len(client.tools)
            return CommandResult(
                content=f"✅ MCP Server `{name}` 已启动（{tool_count} 个工具）"
            )
        except Exception as exc:
            self._logger.error("failed to start MCP server {name}: {exc}", name=name, exc=exc)
            return CommandResult(
                content=f"❌ 启动 MCP Server `{name}` 失败：{exc}",
                success=False,
            )

    # ─── /mcp stop <name> ────────────────────────────────────────────────

    async def _stop(self, args: dict) -> CommandResult:
        from ..tools.mcp import _mcp_clients

        name = args.get("<name>", "").strip()
        if not name:
            return CommandResult(content="用法：`/mcp stop <name>`", success=False)

        if name not in _mcp_clients:
            return CommandResult(content=f"MCP Server `{name}` 未运行。")

        try:
            await _mcp_clients[name].stop()
            del _mcp_clients[name]
            return CommandResult(content=f"🛑 MCP Server `{name}` 已停止。")
        except Exception as exc:
            self._logger.error("failed to stop MCP server {name}: {exc}", name=name, exc=exc)
            return CommandResult(content=f"❌ 停止 MCP Server `{name}` 失败：{exc}", success=False)

    # ─── /mcp add ─────────────────────────────────────────────────────────

    async def _add(self, _args: dict) -> CommandResult:
        return CommandResult(
            content=(
                "**添加 MCP Server**\n\n"
                "请提供以下信息，我来帮你写入配置：\n\n"
                "1. **Server 名称**（如 `github`、`filesystem`）\n"
                "2. **启动命令**（如 `npx -y @modelcontextprotocol/server-github`）\n"
                "3. **环境变量**（如有，如 `GITHUB_TOKEN`）\n"
                "4. **参数**（如有，如允许的路径列表）\n\n"
                "示例配置格式：\n"
                "```yaml\n"
                "mcp:\n"
                "  servers:\n"
                "    - name: github\n"
                "      command: [npx, -y, @modelcontextprotocol/server-github]\n"
                "      env:\n"
                "        GITHUB_TOKEN: ${GITHUB_TOKEN}\n"
                "```"
            )
        )

    # ─── /mcp remove ───────────────────────────────────────────────────────

    async def _remove(self, args: dict) -> CommandResult:
        name = args.get("<name>", "").strip()
        if not name:
            return CommandResult(content="用法：`/mcp remove <name>`", success=False)

        import yaml
        from pathlib import Path

        config_path = Path("~/.auton/config.yaml").expanduser()
        if not config_path.exists():
            return CommandResult(content=f"配置文件不存在：`{config_path}`", success=False)

        try:
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            servers = data.get("mcp", {}).get("servers", [])
            before = len(servers)
            servers = [s for s in servers if s.get("name") != name]

            if len(servers) == before:
                return CommandResult(content=f"未找到 MCP Server：`{name}`", success=False)

            if "mcp" not in data:
                data["mcp"] = {}
            data["mcp"]["servers"] = servers

            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

            return CommandResult(content=f"✅ 已从配置中移除 `{name}`（重启生效）。")
        except Exception as exc:
            self._logger.error("failed to remove MCP server: {exc}", exc=exc)
            return CommandResult(content=f"❌ 移除失败：{exc}", success=False)

    # ─── 帮助 ─────────────────────────────────────────────────────────────

    def _usage(self) -> str:
        return """**/mcp** — MCP Server 管理命令

## 用法
```
/mcp list            — 列出所有配置的 MCP Server
/mcp status          — 显示每个 server 的运行状态
/mcp start <name>    — 启动指定 server
/mcp stop <name>     — 停止指定 server
/mcp add             — 引导添加新 server
/mcp remove <name>   — 从配置中移除 server
```

## 示例
```
/mcp list
/mcp status
/mcp start github
/mcp stop filesystem
```

## 配置格式（~/.auton/config.yaml）
```yaml
mcp:
  servers:
    - name: github
      command: [npx, -y, @modelcontextprotocol/server-github]
      env:
        GITHUB_TOKEN: ${GITHUB_TOKEN}
    - name: filesystem
      command: [npx, -y, @modelcontextprotocol/server-filesystem]
      args: [/Users/liubaoyang/allowed]
```
"""
