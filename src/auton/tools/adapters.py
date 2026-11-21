import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

import anyio
from pydantic import ValidationError

from auton.tools.config import ToolConfig
from auton.tools.contracts import (
    AdapterResult,
    FileList,
    FileRead,
    FileWrite,
    HashText,
    ProcessRun,
    ToolRequest,
    ToolWorkspace,
)
from auton.tools.ports import ToolError
from auton.tools.sandbox import FileSandbox


def child_environment() -> dict[str, str]:
    return {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TMPDIR") if key in os.environ}


async def stop(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    await process.wait()


class FileAdapter:
    def __init__(self, sandbox: FileSandbox) -> None:
        self.sandbox = sandbox

    async def invoke(self, request: ToolRequest, workspace: ToolWorkspace) -> AdapterResult:
        if request.tool == "file.list":
            args_list = FileList.model_validate(request.arguments)
            text = await anyio.to_thread.run_sync(
                lambda: self.sandbox.list_files(workspace, args_list.path)
            )
            return AdapterResult(output=text)
        if request.tool == "file.read":
            args = FileRead.model_validate(request.arguments)
            data = await anyio.to_thread.run_sync(lambda: self.sandbox.read(workspace, args.path))
            assert data is not None
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ToolError(
                    "binary_file_unsupported", "Only UTF-8 text files are supported"
                ) from error
            sha = hashlib.sha256(data).hexdigest()
            if args.start_line != 1 or args.max_lines is not None:
                lines = text.splitlines(keepends=True)
                stop = args.start_line - 1 + (args.max_lines or 200)
                chunk = lines[args.start_line - 1 : stop]
                text = json.dumps(
                    {
                        "path": args.path,
                        "sha256": sha,
                        "start_line": args.start_line,
                        "end_line": args.start_line - 1 + len(chunk),
                        "total_lines": len(lines),
                        "content": "".join(chunk),
                    },
                    ensure_ascii=False,
                )
            return AdapterResult(output=text, sha256=sha, size_bytes=len(data))
        args_write = FileWrite.model_validate(request.arguments)
        sha, size = await anyio.to_thread.run_sync(
            lambda: self.sandbox.write(
                workspace,
                args_write.path,
                args_write.content.encode(),
                args_write.expected_sha256,
                hashlib.sha256((workspace.owner + request.operation_id).encode()).hexdigest(),
            )
        )
        return AdapterResult(output="File written", sha256=sha, size_bytes=size)


class ProcessAdapter:
    def __init__(self, config: ToolConfig) -> None:
        self.config = config

    async def invoke(self, request: ToolRequest, workspace: ToolWorkspace) -> AdapterResult:
        args = ProcessRun.model_validate(request.arguments)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-S",
            str(Path(__file__).with_name("process_worker.py")),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=child_environment(),
            limit=self.config.max_output_bytes,
        )
        try:
            async with asyncio.timeout(self.config.process_timeout_seconds):
                stdout, _ = await process.communicate(args.model_dump_json().encode())
            if len(stdout) > self.config.max_output_bytes:
                raise ToolError("output_limit", "Process output exceeds the limit")
            if process.returncode not in {0, 1}:
                return AdapterResult(
                    output="Process exited without a valid result",
                    code="process_exit",
                    exit_code=process.returncode,
                )
            result = json.loads(stdout)
            return AdapterResult(
                output=result["output"], code=result["code"], exit_code=process.returncode
            )
        except TimeoutError as error:
            raise ToolError("process_timeout", "Owned process exceeded its deadline") from error
        except (ValueError, KeyError, ValidationError) as error:
            raise ToolError(
                "process_protocol_error", "Process output is not a valid result"
            ) from error
        finally:
            await stop(process)


class McpAdapter:
    def __init__(self, config: ToolConfig) -> None:
        self.config = config

    async def invoke(self, request: ToolRequest, workspace: ToolWorkspace) -> AdapterResult:
        from auton.tools.mcp_server import INPUT_SCHEMA, PROTOCOL

        args = HashText.model_validate(request.arguments)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-S",
            str(Path(__file__).with_name("mcp_server.py")),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=child_environment(),
            limit=65536,
        )

        async def rpc(
            method: str, params: dict[str, object], identity: int | None
        ) -> dict[str, object]:
            assert process.stdin and process.stdout
            message: dict[str, object] = {"jsonrpc": "2.0", "method": method, "params": params}
            if identity is not None:
                message["id"] = identity
            process.stdin.write((json.dumps(message) + "\n").encode())
            await process.stdin.drain()
            if identity is None:
                return {}
            for _ in range(8):
                raw = await process.stdout.readline()
                if len(raw) > 65536 or not raw:
                    raise ValueError("Invalid MCP frame")
                reply = json.loads(raw)
                if reply.get("jsonrpc") != "2.0" or "method" in reply:
                    raise ValueError("Unrequested MCP message")
                if (
                    reply.get("id") != identity
                    or "error" in reply
                    or not isinstance(reply.get("result"), dict)
                ):
                    raise ValueError("Invalid MCP response")
                return dict(reply["result"])
            raise ValueError("Too many MCP messages")

        try:
            async with asyncio.timeout(self.config.process_timeout_seconds):
                initialized = await rpc(
                    "initialize",
                    {
                        "protocolVersion": PROTOCOL,
                        "capabilities": {},
                        "clientInfo": {"name": "auton", "version": "0.1"},
                    },
                    1,
                )
                if initialized.get("protocolVersion") != PROTOCOL:
                    raise ValueError("MCP version mismatch")
                await rpc("notifications/initialized", {}, None)
                discovered = await rpc("tools/list", {}, 2)
                tools = discovered.get("tools")
                if (
                    not isinstance(tools, list)
                    or len(tools) != 1
                    or tools[0].get("name") != "sha256"
                    or tools[0].get("inputSchema") != INPUT_SCHEMA
                ):
                    raise ValueError("Tool schema changed")
                reply = await rpc(
                    "tools/call", {"name": "sha256", "arguments": args.model_dump()}, 3
                )
                structured = reply.get("structuredContent")
                expected = hashlib.sha256(args.text.encode()).hexdigest()
                if (
                    reply.get("isError") is not False
                    or not isinstance(structured, dict)
                    or structured.get("sha256") != expected
                ):
                    raise ValueError("MCP tool failed or returned invalid output")
                return AdapterResult(output=expected)
        except TimeoutError as error:
            raise ToolError("mcp_timeout", "MCP server exceeded its deadline") from error
        except (ValueError, TypeError, AttributeError) as error:
            raise ToolError(
                "mcp_protocol_error", "MCP result failed the pinned local contract"
            ) from error
        finally:
            await stop(process)
