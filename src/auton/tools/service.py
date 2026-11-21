import asyncio
import difflib
import hashlib
from dataclasses import dataclass

import anyio
from anyio import CancelScope
from pydantic import BaseModel, JsonValue, ValidationError

from auton.constitution.config import ActionRequest, Principal, Usage
from auton.constitution.ports import ApprovalControlPort, ExecutionControlPort, PolicyControlPort
from auton.constitution.secrets import Redactor
from auton.kernel.events import Event
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.kernel.storage import EventLogPort, StorageError
from auton.tools.config import ToolConfig
from auton.tools.contracts import (
    AdapterResult,
    FileList,
    FileRead,
    FileWrite,
    HashText,
    LocalDirectories,
    ProcessRun,
    ToolApproval,
    ToolArtifact,
    ToolDescriptor,
    ToolPlan,
    ToolReceipt,
    ToolRequest,
    ToolWorkspace,
    workspace_event_id,
)
from auton.tools.ledger import OperationLedger
from auton.tools.ports import ToolAdapterPort, ToolError
from auton.tools.sandbox import FileSandbox, components


@dataclass(frozen=True)
class ToolDependencies:
    control: ExecutionControlPort
    policy: PolicyControlPort
    approvals: ApprovalControlPort
    events: EventLogPort
    runtime: RuntimeDependencies


class ToolHost:
    def __init__(
        self,
        config: ToolConfig,
        deps: ToolDependencies,
        sandbox: FileSandbox,
        ledger: OperationLedger,
        adapters: dict[str, ToolAdapterPort],
    ) -> None:
        self.config, self.deps, self.sandbox, self.ledger, self.adapters = (
            config,
            deps,
            sandbox,
            ledger,
            adapters,
        )
        self._lock = asyncio.Lock()
        self.ready = False
        self.redactor = Redactor()

    async def start(self) -> None:
        self.ready = True

    async def close(self) -> None:
        self.ready = False

    def catalog(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                id=tool,
                title=title,
                effect=effect,
                approval_required=tool in {"file.write", "process.run"},
                input_schema=schema.model_json_schema(),
                isolation=isolation,
            )
            for tool, title, effect, schema, isolation in (
                ("file.read", "读取文本文件", "read", FileRead, "Descriptor-relative POSIX files"),
                (
                    "file.list",
                    "浏览项目目录（相对路径，空字符串表示根目录）",
                    "read",
                    FileList,
                    "Descriptor-relative POSIX directories",
                ),
                (
                    "file.write",
                    "原子写入文本文件",
                    "write",
                    FileWrite,
                    "Descriptor-relative POSIX files; cooperative writers",
                ),
                (
                    "process.run",
                    "运行固定 Python 检查",
                    "process",
                    ProcessRun,
                    "Fixed allowlist child, no arbitrary code/OS sandbox",
                ),
                *(
                    (
                        (
                            "mcp.sha256",
                            "MCP 文本 SHA256",
                            "read",
                            HashText,
                            "Pinned local stdio server",
                        ),
                    )
                    if self.config.mcp_enabled
                    else ()
                ),
            )
        ]

    @staticmethod
    def workspace_event(owner: str, workspace_id: str) -> str:
        return workspace_event_id(owner, workspace_id)

    async def workspace(self, principal: Principal, workspace_id: str) -> ToolWorkspace:
        stored = await self.deps.events.lookup(self.workspace_event(principal.owner, workspace_id))
        if stored is None:
            raise ToolError("workspace_not_found", "Workspace is not owned by this browser/task")
        return ToolWorkspace.model_validate(stored.event.payload["workspace"])

    async def create_workspace(
        self, principal: Principal, workspace_id: str, title: str, read_only: bool
    ) -> ToolWorkspace:
        if principal.role != "user":
            raise ToolError("human_required", "Only the human control plane can create tool scopes")
        workspace = ToolWorkspace(
            id=workspace_id,
            owner=principal.owner,
            title=title,
            goal_id="tool-goal-" + OperationLedger.key(principal.owner, workspace_id),
            read_only=read_only or self.config.read_only,
        )
        return await self._store_workspace(principal, workspace)

    async def browse_directories(self, principal: Principal, path: str | None) -> LocalDirectories:
        if principal.role != "user":
            raise ToolError("human_required", "只有用户可以浏览本机项目目录")
        return await anyio.to_thread.run_sync(lambda: self.sandbox.browse_directories(path))

    async def bind_project_workspace(
        self, principal: Principal, workspace_id: str, title: str, path: str, read_only: bool
    ) -> ToolWorkspace:
        if principal.role != "user":
            raise ToolError("human_required", "只有用户可以选择本机项目目录")
        root, device, inode = await anyio.to_thread.run_sync(
            lambda: self.sandbox.selected_directory(path)
        )
        workspace = ToolWorkspace(
            id=workspace_id,
            owner=principal.owner,
            title=title,
            goal_id="tool-goal-" + OperationLedger.key(principal.owner, workspace_id),
            read_only=read_only or self.config.read_only,
            root_path=root,
            root_device=device,
            root_inode=inode,
        )
        return await self._store_workspace(principal, workspace)

    async def _store_workspace(
        self, principal: Principal, workspace: ToolWorkspace
    ) -> ToolWorkspace:
        workspace_id = workspace.id
        existing = await self.deps.events.lookup(
            self.workspace_event(principal.owner, workspace_id)
        )
        if existing:
            previous = ToolWorkspace.model_validate(existing.event.payload["workspace"])
            if previous != workspace:
                raise ToolError("operation_conflict", "Workspace scope is immutable")
            return previous
        await anyio.to_thread.run_sync(self.sandbox.initialize, workspace)
        await self.deps.control.register_goal(principal, workspace.goal_id)
        event = Event(
            event_id=self.workspace_event(principal.owner, workspace_id),
            kind="tool.workspace",
            timestamp=self.deps.runtime.now(),
            source="runtime",
            payload={"workspace": workspace.model_dump(mode="json")},
        )
        try:
            await self.deps.events.append([event])
        except StorageError:
            existing = await self.deps.events.lookup(event.event_id)
            if existing is None or existing.event.payload != event.payload:
                raise
        return workspace

    async def workspaces(self, principal: Principal) -> list[ToolWorkspace]:
        items = []
        cursor = 0
        while batch := await self.deps.events.read(after=cursor, limit=1000):
            for stored in batch:
                if stored.event.kind == "tool.workspace":
                    item = ToolWorkspace.model_validate(stored.event.payload["workspace"])
                    if item.owner == principal.owner:
                        items.append(item)
            cursor = batch[-1].cursor
        return items

    async def _validate(self, request: ToolRequest) -> ToolWorkspace:
        if not self.ready:
            raise ToolError("tool_not_ready", "Tool host has not started")
        workspace = await self.workspace(request.principal, request.workspace_id)
        if request.goal_id != workspace.goal_id or request.goal_revision != workspace.revision:
            raise ToolError("scope_mismatch", "Tool invocation is outside the bound goal/workspace")
        if request.tool not in self.adapters:
            raise ToolError("tool_not_found", "Tool is not enabled")
        if (workspace.read_only or self.config.read_only) and request.tool in {
            "file.write",
            "process.run",
        }:
            raise ToolError("read_only", "This task cannot write files or start processes")
        schemas: dict[str, type[BaseModel]] = {
            "file.read": FileRead,
            "file.list": FileList,
            "file.write": FileWrite,
            "process.run": ProcessRun,
            "mcp.sha256": HashText,
        }
        try:
            args = schemas[request.tool].model_validate(request.arguments)
        except ValidationError as error:
            raise ToolError(
                "invalid_tool_input", "Tool arguments do not match its schema"
            ) from error
        if isinstance(args, (FileRead, FileWrite)):
            components(args.path)
        if isinstance(args, FileList) and args.path not in {"", "."}:
            components(args.path)
        if isinstance(args, FileWrite) and len(args.content.encode()) > self.config.max_file_bytes:
            raise ToolError("file_too_large", "Content exceeds the configured byte limit")
        if self.redactor.text(request.model_dump_json()) != request.model_dump_json():
            raise ToolError("credential_in_input", "Do not put credentials in tool arguments")
        return workspace

    @staticmethod
    def action(request: ToolRequest) -> ActionRequest:
        return ActionRequest(
            principal=request.principal,
            goal_id=request.goal_id,
            goal_revision=request.goal_revision,
            operation_id="tool-" + request.operation_id,
            action="tool.write" if request.tool in {"file.write", "process.run"} else "tool.read",
            input_digest=request.digest,
        )

    async def prepare(self, request: ToolRequest) -> ToolPlan:
        async with self._lock:
            workspace = await self._validate(request)
            existing = await self.ledger.get(
                request.principal.owner, request.operation_id, "prepared"
            )
            if existing:
                if existing["request_digest"] != request.digest:
                    raise ToolError("operation_conflict", "Operation id belongs to different input")
                return ToolPlan.model_validate(existing["plan"])
            decision = self.deps.policy.preview(self.action(request))
            if decision.outcome == "deny":
                raise ToolError(decision.reason_codes[0], "Policy rejects this operation")
            preview: str = request.tool
            if request.tool == "file.write":
                args = FileWrite.model_validate(request.arguments)
                before = await anyio.to_thread.run_sync(
                    lambda: self.sandbox.read(workspace, args.path, missing_ok=True)
                )
                checksum = hashlib.sha256(before).hexdigest() if before is not None else None
                if checksum != args.expected_sha256:
                    raise ToolError("file_changed", "Current content differs from expected digest")
                try:
                    old = before.decode("utf-8") if before else ""
                except UnicodeDecodeError as error:
                    raise ToolError(
                        "binary_file_unsupported", "Only UTF-8 text files are supported"
                    ) from error
                preview = "".join(
                    difflib.unified_diff(
                        old.splitlines(keepends=True),
                        args.content.splitlines(keepends=True),
                        fromfile="before/" + args.path,
                        tofile="after/" + args.path,
                    )
                )
                if len(preview.encode()) > self.config.max_file_bytes * 2 + 4096:
                    raise ToolError("preview_limit", "Diff exceeds review limit")
            elif request.tool == "process.run":
                args_process = ProcessRun.model_validate(request.arguments)
                preview = f"{args_process.program}\n" + args_process.source
            elif request.tool == "file.read":
                preview = FileRead.model_validate(request.arguments).path
            elif request.tool == "file.list":
                preview = "List directory: " + (
                    FileList.model_validate(request.arguments).path or "."
                )
            else:
                preview = HashText.model_validate(request.arguments).text
            plan = ToolPlan(
                operation_id=request.operation_id,
                request_digest=request.digest,
                workspace_id=workspace.id,
                tool=request.tool,
                title=next(t.title for t in self.catalog() if t.id == request.tool),
                preview=self.redactor.text(preview),
                requires_approval=decision.outcome == "approval_required",
                policy_version=decision.policy_version,
            )
            await self.ledger.put(
                request,
                "prepared",
                {"request": request.model_dump(mode="json"), "plan": plan.model_dump(mode="json")},
            )
            return plan

    async def _request(self, principal: Principal, operation_id: str) -> ToolRequest:
        value = await self.ledger.get(principal.owner, operation_id, "prepared")
        if value is None:
            raise ToolError("operation_not_found", "No owned prepared operation")
        return ToolRequest.model_validate(value["request"])

    async def approve(self, principal: Principal, operation_id: str) -> ToolApproval:
        async with self._lock:
            request = await self._request(principal, operation_id)
            await self._validate(request)
            approval = await self.deps.approvals.approve(principal, self.action(request))
            return ToolApproval(
                id=approval.id, operation_id=operation_id, expires_at=approval.expires_at
            )

    def _receipt(
        self,
        request: ToolRequest,
        result: AdapterResult | None = None,
        *,
        outcome: str = "unknown",
        code: str = "outcome_unknown",
        evidence: str = "No complete adapter acknowledgement",
        reconciled: bool = False,
    ) -> ToolReceipt:
        artifact = None
        if result and result.sha256 and request.tool in {"file.read", "file.write"}:
            artifact = ToolArtifact(
                id="artifact-" + self.ledger.key(request.principal.owner, request.operation_id),
                path=str(request.arguments["path"]),
                sha256=result.sha256,
                size_bytes=result.size_bytes,
            )
        return ToolReceipt.model_validate(
            {
                "operation_id": request.operation_id,
                "request_digest": request.digest,
                "tool": request.tool,
                "workspace_id": request.workspace_id,
                "outcome": outcome,
                "code": code,
                "output": self.redactor.text(result.output) if result else "",
                "evidence": evidence,
                "reconciled": reconciled,
                "exit_code": result.exit_code if result else None,
                "artifact": artifact,
            }
        )

    async def _settle(self, request: ToolRequest, reservation_id: str) -> None:
        await self.deps.control.settle(request.principal, reservation_id, Usage(tool_calls=1))

    async def execute(
        self, principal: Principal, operation_id: str, approval_id: str | None = None
    ) -> ToolReceipt:
        if self._lock.locked():
            raise ApplicationError(429, "tool_busy", "Tool host is processing another command")
        async with self._lock:
            request = await self._request(principal, operation_id)
            complete = await self.ledger.get(principal.owner, operation_id, "completed")
            if complete:
                return ToolReceipt.model_validate(complete["receipt"])
            received = await self.ledger.get(principal.owner, operation_id, "received")
            if received:
                await self._settle(request, str(received["reservation_id"]))
                await self.ledger.put(request, "completed", {"receipt": received["receipt"]})
                return ToolReceipt.model_validate(received["receipt"])
            started = await self.ledger.get(principal.owner, operation_id, "started")
            if started:
                return await self._reconcile(request, started)
            workspace = await self._validate(request)
            reservation = await self.deps.control.reserve(
                self.action(request),
                Usage(tool_calls=1),
                "tool-" + request.operation_id,
                approval_id,
            )
            if reservation.status != "reserved":
                return self._receipt(request)
            begun = False
            try:
                await self.deps.control.begin(request.principal, reservation.id)
                begun = True
                await self.ledger.put(
                    request, "started", {"reservation_id": reservation.id, "attempt": 1}
                )
                result = await self.adapters[request.tool].invoke(request, workspace)
                receipt = self._receipt(
                    request,
                    result,
                    outcome="succeeded" if result.code == "ok" else "failed",
                    code=result.code,
                    evidence="Adapter acknowledged the operation",
                )
                await self.ledger.put(
                    request,
                    "received",
                    {"receipt": receipt.model_dump(mode="json"), "reservation_id": reservation.id},
                )
                await self._settle(request, reservation.id)
                await self.ledger.put(
                    request, "completed", {"receipt": receipt.model_dump(mode="json")}
                )
                return receipt
            except BaseException as error:
                with CancelScope(shield=True):
                    if not begun:
                        await self.deps.control.release(request.principal, reservation.id)
                    elif isinstance(error, ToolError):
                        outcome = "unknown" if error.uncertain else "failed"
                        receipt = self._receipt(
                            request, outcome=outcome, code=error.code, evidence=str(error)
                        )
                        await self._settle(request, reservation.id)
                        stage = "unknown" if error.uncertain else "completed"
                        await self.ledger.put(
                            request, stage, {"receipt": receipt.model_dump(mode="json")}
                        )
                        return receipt
                    else:
                        # Storage failure/cancel may occur after a write. Preserve the started
                        # intent; only explicit state reconciliation may resolve it.
                        await self.ledger.put(
                            request, "interrupted", {"code": "result_unconfirmed"}
                        )
                raise

    async def _reconcile(self, request: ToolRequest, started: dict[str, JsonValue]) -> ToolReceipt:
        workspace = await self.workspace(request.principal, request.workspace_id)
        receipt = self._receipt(request)
        if request.tool == "file.write":
            args = FileWrite.model_validate(request.arguments)
            data = await anyio.to_thread.run_sync(
                lambda: self.sandbox.read(workspace, args.path, missing_ok=True)
            )
            if (
                data is not None
                and hashlib.sha256(data).hexdigest()
                == hashlib.sha256(args.content.encode()).hexdigest()
            ):
                result = AdapterResult(
                    output="Intended content is present; no write was repeated",
                    sha256=hashlib.sha256(data).hexdigest(),
                    size_bytes=len(data),
                )
                receipt = self._receipt(
                    request,
                    result,
                    outcome="succeeded",
                    code="intended_state_observed",
                    evidence=(
                        "Observed matching file digest; this is state reconciliation, "
                        "not a recovered execution acknowledgement"
                    ),
                    reconciled=True,
                )
                await self._settle(request, str(started["reservation_id"]))
                await self.ledger.put(
                    request, "completed", {"receipt": receipt.model_dump(mode="json")}
                )
                return receipt
        return receipt

    async def reconcile(self, principal: Principal, operation_id: str) -> ToolReceipt:
        async with self._lock:
            request = await self._request(principal, operation_id)
            completed = await self.ledger.get(principal.owner, operation_id, "completed")
            if completed:
                return ToolReceipt.model_validate(completed["receipt"])
            started = await self.ledger.get(principal.owner, operation_id, "started")
            if not started:
                raise ToolError("operation_not_started", "Operation has not dispatched")
            return await self._reconcile(request, started)

    async def receipt(self, principal: Principal, operation_id: str) -> ToolReceipt:
        request = await self._request(principal, operation_id)
        for stage in ("completed", "unknown"):
            value = await self.ledger.get(principal.owner, operation_id, stage)
            if value:
                return ToolReceipt.model_validate(value["receipt"])
        return self._receipt(request)

    async def artifact(self, principal: Principal, operation_id: str) -> tuple[str, bytes]:
        request = await self._request(principal, operation_id)
        receipt = await self.receipt(principal, operation_id)
        if receipt.outcome != "succeeded" or receipt.artifact is None:
            raise ToolError("artifact_not_found", "No successful artifact for this operation")
        workspace = await self.workspace(principal, request.workspace_id)
        artifact = receipt.artifact
        data = await anyio.to_thread.run_sync(lambda: self.sandbox.read(workspace, artifact.path))
        if data is None or hashlib.sha256(data).hexdigest() != receipt.artifact.sha256:
            raise ToolError("artifact_changed", "Artifact path has changed since the receipt")
        # Downloads are current verified local bytes; no HTML is rendered by the service.
        return receipt.artifact.path.split("/")[-1], data
