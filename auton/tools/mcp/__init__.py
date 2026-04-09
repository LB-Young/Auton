"""MCP Tool — Model Context Protocol 工具调用

通过 MCP (Model Context Protocol) 连接外部工具服务。
MCP server 提供的工具通过本模块透传给 Agent。

MCP 协议简介：
  - Agent 通过 stdio 或 HTTP/SSE 与 MCP server 通信
  - MCP server 注册一组工具（tools/list）
  - Agent 通过 tools/call 调用工具
  - 工具结果通过 JSON-RPC 返回

配置方式（config/default.yaml）：
  mcp:
    servers:
      - name: "github"
        command: ["npx", "-y", "@modelcontextprotocol/server-github"]
        env:
          GITHUB_TOKEN: "${GITHUB_TOKEN}"
      - name: "filesystem"
        command: ["npx", "-y", "@modelcontextprotocol/server-filesystem"]
        args: ["/allowed/path"]
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from ..base import Tool, ToolResult

if TYPE_CHECKING:
    pass


# ─── MCP 协议类型 ───────────────────────────────────────────────────────────

JSONRPC_REQUEST = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "",
    "params": {},
}

JSONRPC_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": None,
}

JSONRPC_ERROR = {
    "jsonrpc": "2.0",
    "id": 1,
    "error": {
        "code": -32600,
        "message": "",
    },
}


# ─── MCP Client ──────────────────────────────────────────────────────────────

@dataclass
class MCPToolDefinition:
    """MCP 服务器注册的单个工具定义"""
    name: str
    description: str
    input_schema: dict[str, Any]
    server: str  # 所属 MCP server 名称


@dataclass
class MCPClientConfig:
    """MCP Server 配置"""
    name: str
    command: list[str]  # e.g. ["npx", "-y", "@modelcontextprotocol/server-github"]
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)  # 环境变量


class MCPClient:
    """MCP 客户端 — 与 MCP server 进程通信（stdio 模式）"""

    def __init__(self, config: MCPClientConfig) -> None:
        self.config = config
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_id = 0
        self._logger = logger.bind(name=f"MCP:{config.name}")
        self._tools: list[MCPToolDefinition] = []
        self._initialized = False

    async def start(self) -> None:
        """启动 MCP server 进程并初始化"""
        if self._initialized:
            return

        cmd = self.config.command + self.config.args
        env = {**os.environ, **self.config.env}

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader = self._proc.stdout
        self._writer = asyncio.StreamWriter(
            self._proc.stdin,  # type: ignore
            None,
            self._proc,
        )

        # 发送 initialize 请求
        await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {}, "sampling": {}},
                "clientInfo": {
                    "name": "auton-agent",
                    "version": "0.1.0",
                },
            },
        )

        # 发送 initialized 通知
        await self._send_notification("initialized", {})

        self._initialized = True
        self._logger.info("MCP server {name} started", name=self.config.name)

        # 获取工具列表
        await self._load_tools()

    async def _load_tools(self) -> None:
        """获取 MCP server 注册的所有工具"""
        try:
            response = await self._send_request("tools/list", {})
            tools_result = response.get("tools", [])
            self._tools = [
                MCPToolDefinition(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                    server=self.config.name,
                )
                for t in tools_result
            ]
            self._logger.info(
                "loaded {n} tools from MCP server {server}",
                n=len(self._tools),
                server=self.config.name,
            )
        except Exception as exc:
            self._logger.error(
                "failed to load tools from {server}: {exc}",
                server=self.config.name,
                exc=exc,
            )

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """发送 JSON-RPC 请求并等待响应"""
        if not self._writer or not self._reader:
            raise RuntimeError("MCP client not started")

        self._request_id += 1
        req_id = self._request_id
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        request_str = json.dumps(request) + "\n"
        self._writer.write(request_str.encode("utf-8"))
        await self._writer.drain()

        # 读取响应
        response_line = await self._reader.readline()
        if not response_line:
            raise RuntimeError(f"MCP server {self.config.name} closed unexpectedly")

        response = json.loads(response_line.decode("utf-8"))

        if "error" in response:
            raise RuntimeError(
                f"MCP error: {response['error'].get('message', 'unknown')}"
            )

        return response.get("result", {})

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """发送 JSON-RPC 通知（无响应）"""
        if not self._writer:
            raise RuntimeError("MCP client not started")

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        notification_str = json.dumps(notification) + "\n"
        self._writer.write(notification_str.encode("utf-8"))
        await self._writer.drain()

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """调用 MCP 工具"""
        if not self._initialized:
            await self.start()

        try:
            result = await self._send_request(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": arguments,
                },
            )
            content = result.get("content", [])
            if isinstance(content, list):
                text = "\n".join(
                    c.get("text", "") for c in content if c.get("type") == "text"
                )
            else:
                text = str(content)
            return ToolResult(content=text)
        except Exception as exc:
            self._logger.error(
                "MCP tool call failed: {server}/{tool} -> {exc}",
                server=self.config.name,
                tool=tool_name,
                exc=exc,
            )
            return ToolResult(content=str(exc), success=False, error=str(exc))

    @property
    def tools(self) -> list[MCPToolDefinition]:
        """获取 MCP server 注册的工具列表"""
        return self._tools

    async def stop(self) -> None:
        """停止 MCP server 进程"""
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        self._initialized = False
        self._logger.info("MCP server {name} stopped", name=self.config.name)


# ─── MCP Tool ────────────────────────────────────────────────────────────────

class MCPTool(Tool):
    """MCP 工具代理 — 透传 MCP server 工具调用"""

    name = "mcp"
    description = "Call a tool from an MCP server"

    def __init__(self) -> None:
        self._logger = logger.bind(name="MCPTool")

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "server": {
                    "type": "string",
                    "description": "MCP server name (e.g. github, filesystem)",
                },
                "tool": {
                    "type": "string",
                    "description": "Tool name on the MCP server",
                },
                "arguments": {
                    "type": "object",
                    "description": "Tool arguments",
                },
            },
            "required": ["server", "tool"],
        }

    async def execute(
        self,
        server: str,
        tool: str,
        arguments: dict | None = None,
    ) -> ToolResult:
        from ..registry import get_registry

        registry = get_registry()
        mcp_client = registry.get_mcp_client(server)

        if mcp_client is None:
            self._logger.warning(
                "MCP server {server} not configured or not started",
                server=server,
            )
            return ToolResult(
                content=(
                    f"MCP server '{server}' is not configured or not started.\n"
                    "To enable MCP servers, add them to config/default.yaml:\n"
                    "  mcp:\n"
                    "    servers:\n"
                    f"      - name: {server!r}\n"
                    "        command: [...]\n"
                    f"Configure MCP servers in your ~/.auton/config.yaml"
                ),
                success=False,
                error=f"MCP server '{server}' not found",
            )

        arguments = arguments or {}
        return await mcp_client.call_tool(tool, arguments)


# ─── MCP 客户端管理器 ────────────────────────────────────────────────────────

_mcp_clients: dict[str, MCPClient] = {}


async def load_mcp_servers(config: dict[str, Any]) -> dict[str, MCPClient]:
    """从配置加载所有 MCP server

    支持两种格式：
      1. 新格式（推荐）：config["mcp"].servers 是 list[MCPServerConfig]
      2. 旧格式（兼容）：config["mcp"]["servers"] 是 list[dict]
    """
    global _mcp_clients

    mcp_config = config.get("mcp", {})
    auto_start = mcp_config.get("auto_start", True)
    if not auto_start:
        return _mcp_clients

    servers = mcp_config.get("servers", [])

    for server_cfg in servers:
        # 支持 dict（旧格式）或 pydantic 模型（新格式）
        cfg_dict = server_cfg.model_dump() if hasattr(server_cfg, "model_dump") else server_cfg

        name = cfg_dict.get("name")
        if not name:
            continue

        # 环境变量替换
        command = cfg_dict.get("command") or []
        args = cfg_dict.get("args") or []
        env = {k: _resolve_env_var(v) for k, v in (cfg_dict.get("env") or {}).items()}

        client_config = MCPClientConfig(name=name, command=command, args=args, env=env)
        client = MCPClient(client_config)

        try:
            await client.start()
            _mcp_clients[name] = client
        except Exception as exc:
            logger.error(
                "failed to start MCP server {name}: {exc}",
                name=name,
                exc=exc,
            )

    return _mcp_clients


async def stop_mcp_servers() -> None:
    """停止所有 MCP server"""
    for name, client in list(_mcp_clients.items()):
        await client.stop()
    _mcp_clients.clear()


def _resolve_env_var(value: str) -> str:
    """解析 ${VAR} 环境变量引用"""
    import re
    pattern = re.compile(r"\$\{([^}]+)\}")
    matches = pattern.findall(value)
    for var in matches:
        value = value.replace(f"${{{var}}}", os.environ.get(var, ""))
    return value
