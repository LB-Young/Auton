from auton.tools.adapters import FileAdapter, McpAdapter, ProcessAdapter
from auton.tools.config import ToolConfig
from auton.tools.ledger import OperationLedgerFactory
from auton.tools.ports import ToolAdapterPort, ToolHostPort
from auton.tools.sandbox import FileSandbox, SandboxFactory
from auton.tools.service import ToolDependencies, ToolHost


class ToolAdapterFactory:
    def create(self, config: ToolConfig, sandbox: FileSandbox) -> dict[str, ToolAdapterPort]:
        files = FileAdapter(sandbox)
        adapters: dict[str, ToolAdapterPort] = {
            "file.read": files,
            "file.list": files,
            "file.write": files,
            "process.run": ProcessAdapter(config),
        }
        if config.mcp_enabled:
            adapters["mcp.sha256"] = McpAdapter(config)
        return adapters


class ToolHostFactory:
    def create(self, config: ToolConfig, deps: ToolDependencies) -> ToolHostPort:
        sandbox = SandboxFactory().create(config)
        return ToolHost(
            config,
            deps,
            sandbox,
            OperationLedgerFactory().create(deps.events, deps.runtime),
            ToolAdapterFactory().create(config, sandbox),
        )
