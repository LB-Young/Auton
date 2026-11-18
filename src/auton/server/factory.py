import asyncio
import hashlib
import re
from typing import Literal
from urllib.parse import quote

from anyio import CancelScope
from fastapi import FastAPI, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from auton.agent.contracts import AgentRun, CreateRun, RunCommand, RunPage
from auton.constitution.config import (
    ActionRequest,
    ConstitutionConfig,
    PolicyDecision,
    Principal,
    PublicPolicy,
)
from auton.context.contracts import ContextRequest, ContextSnapshot, TaskState
from auton.demo.ports import (
    ConversationPort,
    CreateSession,
    ErrorBody,
    SendMessage,
    Session,
    SessionEvent,
    StopRun,
)
from auton.experience.contracts import RecoveryCommand, Trajectory
from auton.genome.contracts import Asset, Project, Revision, Snapshot, VersionInfo
from auton.judgment.contracts import JudgmentInfo, JudgmentRequest, JudgmentResult
from auton.judgment.questions import JudgmentQuestionsFactory
from auton.kernel.ports import ApplicationError
from auton.model.contracts import ModelInfo, ModelMessage, ModelRequest, ModelResult
from auton.server.config import ServerConfig
from auton.server.feedback import FeedbackCommand, FeedbackReceipt
from auton.server.identity import IdentityInfo
from auton.server.limits import RequestLimits
from auton.server.ports import BootstrapResponse, HealthResponse, ServerDependencies
from auton.server.run_events import EventStreamFactory, RunSnapshot
from auton.server.uploads import UploadCommand, UploadIntent, UploadReceipt
from auton.tools.contracts import (
    ToolApproval,
    ToolDescriptor,
    ToolName,
    ToolPlan,
    ToolReceipt,
    ToolRequest,
)


class LegacyIdentityCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")


class ContextPreviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    request_id: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=100)
    state: TaskState
    history: tuple[ModelMessage, ...] = Field(default=(), max_length=300)
    public: bool = False

    @model_validator(mode="after")
    def bounded_history(self) -> "ContextPreviewCommand":
        if any(m.role == "system" for m in self.history):
            raise ValueError("System messages are host-only")
        if len(self.model_dump_json().encode()) > 1000000:
            raise ValueError("Preview input too large")
        return self


class PolicyRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: str
    config: ConstitutionConfig


class ModelProbe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class JudgmentPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    state: str = Field(min_length=1, max_length=12000)
    public: bool = False


class ToolWorkspaceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    title: str = Field(min_length=1, max_length=100)
    read_only: bool = True


class WorkspaceView(BaseModel):
    id: str
    title: str
    read_only: bool
    revision: int


class ToolPrepareCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    workspace_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    tool: ToolName
    arguments: dict[str, JsonValue]


class ToolExecuteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_id: str | None = Field(default=None, max_length=200)


class AssetProposalCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset: Asset
    expected: str | None = None


class AssetPublishCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected: str = Field(pattern=r"^[a-f0-9]{40}$")
    candidates_revision: str = Field(pattern=r"^[a-f0-9]{40}$")


class AssetRevisionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected: str = Field(pattern=r"^[a-f0-9]{40}$")
    revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{40}$")


class ServerFactory:
    def create(self, config: ServerConfig, deps: ServerDependencies) -> FastAPI:
        stream = EventStreamFactory().create(
            config.settings, deps.agent, deps.events, deps.identity
        )
        app = FastAPI(
            title="Auton",
            version="0.1.0",
            lifespan=deps.lifespan,
            responses={
                status: {"model": ErrorBody}
                for status in (401, 403, 404, 409, 410, 413, 422, 429, 501, 503)
            },
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(config.allowed_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Auton-Client"],
        )
        app.add_middleware(
            TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
        )

        app.add_middleware(RequestLimits)

        @app.exception_handler(RequestValidationError)
        async def invalid_request(
            _request: Request, _error: RequestValidationError
        ) -> JSONResponse:
            return JSONResponse(
                status_code=422,
                content={
                    "code": "invalid_request",
                    "message": "请求或配置字段不合法；输入内容不会回显",
                },
            )

        @app.exception_handler(ApplicationError)
        async def application_error(_request: Request, error: ApplicationError) -> JSONResponse:
            deps.logger.info("request_rejected code=%s", deps.redact(error.code))
            return JSONResponse(
                status_code=error.status,
                content=ErrorBody(
                    code=deps.redact(error.code), message=deps.redact(str(error))
                ).model_dump(),
            )

        def service() -> ConversationPort:
            if deps.conversation is None:
                raise ApplicationError(
                    501, "not_implemented", "主对话 Demo 未启用，请使用真实任务接口"
                )
            return deps.conversation

        def owner(request: Request) -> str:
            value = deps.identity.owner(request.cookies.get("auton_owner", ""))
            if request.method != "GET":
                origin = request.headers.get("origin")
                if origin is not None and origin not in config.allowed_origins:
                    raise ApplicationError(403, "origin_denied", "请求来源不允许")
                if request.headers.get("x-auton-client") != "web":
                    raise ApplicationError(403, "client_required", "缺少工作台命令标识")
            return value

        @app.get("/api/v1/health")
        async def health(response: Response) -> HealthResponse:
            ready = deps.is_ready()
            response.status_code = 200 if ready else 503
            return HealthResponse(status="ready" if ready else "starting", profile=config.profile)

        @app.get("/api/v1/bootstrap")
        async def bootstrap(request: Request, response: Response) -> BootstrapResponse:
            if request.headers.get("sec-fetch-site") == "cross-site" or (
                request.headers.get("origin") is not None
                and request.headers["origin"] not in config.allowed_origins
            ):
                raise ApplicationError(403, "origin_denied", "Bootstrap source is not allowed")
            value, identity = await deps.identity.session(request.cookies.get("auton_owner", ""))
            response.set_cookie(
                "auton_owner",
                value,
                httponly=True,
                samesite="strict",
                max_age=identity.remaining_seconds,
            )
            response.headers["Cache-Control"] = "no-store"
            return BootstrapResponse(
                identity=identity,
                profile=config.profile,
                demo=deps.conversation is not None,
                implementation=deps.implementation,
                modules=deps.modules,
                event_storage=deps.storage(),
                policy=deps.control.public(),
            )

        @app.post("/api/v1/identity/adopt-legacy")
        async def adopt_legacy_identity(
            request: Request, response: Response, command: LegacyIdentityCommand
        ) -> IdentityInfo:
            if (
                request.headers.get("origin") not in config.allowed_origins
                or request.headers.get("x-auton-client") != "web"
            ):
                raise ApplicationError(
                    403, "origin_denied", "Explicit local client action required"
                )
            legacy = request.cookies.get("auton_owner", "")
            if not re.fullmatch(r"[a-zA-Z0-9_-]{43}", legacy):
                raise ApplicationError(401, "legacy_identity_invalid", "No legacy local cookie")
            await deps.genome.view(Principal(owner=legacy, role="user"), command.project_id)
            token, identity = await deps.identity.adopt_legacy(legacy)
            response.set_cookie(
                "auton_owner",
                token,
                httponly=True,
                samesite="strict",
                max_age=identity.remaining_seconds,
            )
            return identity

        @app.post("/api/v1/identity/reset")
        async def reset_identity(
            request: Request, response: Response, command: ModelProbe
        ) -> IdentityInfo:
            if (
                request.headers.get("origin") not in config.allowed_origins
                or request.headers.get("x-auton-client") != "web"
            ):
                raise ApplicationError(
                    403, "origin_denied", "Identity reset requires an explicit local client action"
                )
            token, identity = await deps.identity.session("")
            response.set_cookie(
                "auton_owner",
                token,
                httponly=True,
                samesite="strict",
                max_age=identity.remaining_seconds,
            )
            return identity

        @app.post("/api/v1/uploads")
        async def prepare_upload(request: Request, command: UploadCommand) -> UploadIntent:
            return await deps.uploads.prepare(Principal(owner=owner(request), role="user"), command)

        @app.post(
            "/api/v1/uploads/{upload_id}/content",
            openapi_extra={
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/octet-stream": {
                            "schema": {"type": "string", "format": "binary"}
                        }
                    },
                }
            },
        )
        async def complete_upload(request: Request, upload_id: str) -> UploadReceipt:
            principal = Principal(owner=owner(request), role="user")
            chunks: list[bytes] = []
            total = 0
            async for chunk in request.stream():
                total += len(chunk)
                if total > config.settings.max_upload_bytes:
                    raise ApplicationError(
                        413, "upload_too_large", "Upload exceeds the configured byte limit"
                    )
                chunks.append(chunk)
            return await deps.uploads.complete(principal, upload_id, b"".join(chunks))

        @app.get("/api/v1/projects")
        async def projects(request: Request) -> list[Project]:
            return await deps.genome.projects(Principal(owner=owner(request)))

        @app.post("/api/v1/projects", status_code=201)
        async def create_project(request: Request, project: Project) -> Revision:
            return await deps.genome.create_project(
                Principal(owner=owner(request), role="user"), project
            )

        @app.get("/api/v1/projects/{project_id}/assets")
        async def asset_catalog(request: Request, project_id: str) -> Revision:
            return await deps.genome.view(Principal(owner=owner(request)), project_id)

        @app.post("/api/v1/projects/{project_id}/candidates")
        async def propose_asset(
            request: Request, project_id: str, command: AssetProposalCommand
        ) -> Revision:
            return await deps.genome.propose(
                Principal(owner=owner(request), role="user"),
                project_id,
                command.asset,
                command.expected,
            )

        @app.post("/api/v1/projects/{project_id}/assets/{asset_id}/promote")
        async def promote_asset(
            request: Request, project_id: str, asset_id: str, command: AssetPublishCommand
        ) -> Revision:
            return await deps.genome.promote(
                Principal(owner=owner(request), role="user"),
                project_id,
                asset_id,
                command.expected,
                command.candidates_revision,
            )

        @app.post("/api/v1/projects/{project_id}/assets/{asset_id}/revoke")
        async def revoke_asset(
            request: Request, project_id: str, asset_id: str, command: AssetRevisionCommand
        ) -> Revision:
            return await deps.genome.revoke(
                Principal(owner=owner(request), role="user"), project_id, asset_id, command.expected
            )

        @app.post("/api/v1/projects/{project_id}/assets/{asset_id}/rollback")
        async def rollback_asset(
            request: Request, project_id: str, asset_id: str, command: AssetRevisionCommand
        ) -> Revision:
            if not command.revision:
                raise ApplicationError(422, "revision_required", "Select a historical version")
            return await deps.genome.rollback(
                Principal(owner=owner(request), role="user"),
                project_id,
                asset_id,
                command.revision,
                command.expected,
            )

        @app.get("/api/v1/projects/{project_id}/assets/{asset_id}/history")
        async def asset_history(
            request: Request, project_id: str, asset_id: str
        ) -> list[VersionInfo]:
            return await deps.genome.history(Principal(owner=owner(request)), project_id, asset_id)

        @app.get("/api/v1/projects/{project_id}/assets/{asset_id}/diff")
        async def asset_diff(
            request: Request, project_id: str, asset_id: str, revision: str
        ) -> str:
            return await deps.genome.diff(
                Principal(owner=owner(request)), project_id, asset_id, revision
            )

        @app.get("/api/v1/projects/{project_id}/runs/{run_id}/trajectory")
        async def trajectory(
            request: Request,
            project_id: str,
            run_id: str,
            purpose: Literal["inspect", "recovery"] = "inspect",
        ) -> Trajectory:
            return await deps.experience.trajectory(
                Principal(owner=owner(request), role="user"), project_id, run_id, purpose
            )

        @app.post("/api/v1/projects/{project_id}/runs/{run_id}/recover")
        async def recover(
            request: Request, project_id: str, run_id: str, command: RecoveryCommand
        ) -> AgentRun:
            return await deps.commands.recover(
                Principal(owner=owner(request), role="user"), project_id, run_id, command
            )

        @app.get("/api/v1/agent/history")
        async def run_history(
            request: Request,
            project_id: str,
            after: int = Query(default=0, ge=0, lt=2**63),
            limit: int = Query(default=10, ge=1, le=20),
            search: str = Query(default="", max_length=100),
        ) -> RunPage:
            return await deps.agent.page(
                Principal(owner=owner(request), role="user"), project_id, after, limit, search
            )

        @app.post("/api/v1/agent/runs/{run_id}/feedback")
        async def run_feedback(
            request: Request, run_id: str, command: FeedbackCommand
        ) -> FeedbackReceipt:
            return await deps.feedback.submit(
                Principal(owner=owner(request), role="user"), run_id, command
            )

        @app.get("/api/v1/agent/runs/{run_id}/snapshot")
        async def run_snapshot(request: Request, run_id: str) -> RunSnapshot:
            return await stream.snapshot(Principal(owner=owner(request), role="user"), run_id)

        @app.websocket("/api/v1/agent/runs/{run_id}/events")
        async def run_events(websocket: WebSocket, run_id: str, after: int = 0) -> None:
            try:
                if websocket.headers.get("origin") not in config.allowed_origins:
                    raise ApplicationError(403, "origin_denied", "Socket origin is not allowed")
                token = websocket.cookies.get("auton_owner", "")
                principal = Principal(owner=deps.identity.owner(token), role="user")
                await stream.connect(websocket, principal, token, run_id, after)
            except ApplicationError:
                await websocket.close(code=1008)

        @app.post("/api/v1/agent/runs")
        async def create_agent_run(request: Request, command: CreateRun) -> AgentRun:
            return await deps.commands.create(Principal(owner=owner(request), role="user"), command)

        @app.get("/api/v1/agent/runs")
        async def agent_runs(request: Request, project_id: str) -> list[AgentRun]:
            return await deps.agent.list(Principal(owner=owner(request), role="user"), project_id)

        @app.get("/api/v1/agent/runs/{run_id}")
        async def agent_run(request: Request, run_id: str) -> AgentRun:
            return await deps.agent.get(Principal(owner=owner(request), role="user"), run_id)

        @app.post("/api/v1/agent/runs/{run_id}/commands")
        async def agent_command(request: Request, run_id: str, command: RunCommand) -> AgentRun:
            return await deps.commands.apply(
                Principal(owner=owner(request), role="user"), run_id, command
            )

        @app.get("/api/v1/agent/runs/{run_id}/report")
        async def agent_report(request: Request, run_id: str) -> Response:
            name, data = await deps.agent.report(
                Principal(owner=owner(request), role="user"), run_id
            )
            return Response(
                data,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name),
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        @app.post("/api/v1/projects/{project_id}/context")
        async def prepare_context(
            request: Request, project_id: str, command: ContextPreviewCommand
        ) -> ContextSnapshot:
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", project_id):
                raise ApplicationError(422, "invalid_project", "Invalid project identifier")
            principal = Principal(owner=owner(request), role="runtime")
            return await deps.context.prepare(
                ContextRequest(
                    request_id=command.request_id,
                    principal=principal,
                    project_id=project_id,
                    goal_id=hashlib.sha256(
                        (principal.owner + "context-preview" + project_id).encode()
                    ).hexdigest(),
                    model_id=command.model_id,
                    state=command.state,
                    history=command.history,
                    data_domain="public" if command.public else "local-only",
                )
            )

        @app.get("/api/v1/projects/{project_id}/context/{snapshot_id}")
        async def get_context(
            request: Request, project_id: str, snapshot_id: str
        ) -> ContextSnapshot:
            return await deps.context.snapshot(
                Principal(owner=owner(request), role="runtime"), project_id, snapshot_id
            )

        @app.post("/api/v1/projects/{project_id}/snapshots")
        async def resolve_assets(request: Request, project_id: str) -> Snapshot:
            return await deps.genome.resolve(Principal(owner=owner(request)), project_id)

        @app.get("/api/v1/projects/{project_id}/snapshots/{snapshot_id}")
        async def get_asset_snapshot(
            request: Request, project_id: str, snapshot_id: str
        ) -> Snapshot:
            return await deps.genome.snapshot(
                Principal(owner=owner(request)), project_id, snapshot_id
            )

        @app.get("/api/v1/tools")
        async def tools_catalog(request: Request) -> list[ToolDescriptor]:
            owner(request)
            return deps.tools.catalog()

        @app.get("/api/v1/tools/workspaces")
        async def tool_workspaces(request: Request) -> list[WorkspaceView]:
            values = await deps.tools.workspaces(Principal(owner=owner(request)))
            return [WorkspaceView.model_validate(item.model_dump()) for item in values]

        @app.post("/api/v1/tools/workspaces", status_code=201)
        async def create_tool_workspace(
            request: Request, command: ToolWorkspaceCommand
        ) -> WorkspaceView:
            value = await deps.tools.create_workspace(
                Principal(owner=owner(request), role="user"),
                command.id,
                command.title,
                command.read_only,
            )
            return WorkspaceView.model_validate(value.model_dump())

        @app.post("/api/v1/tools/operations")
        async def prepare_tool(request: Request, command: ToolPrepareCommand) -> ToolPlan:
            principal = Principal(owner=owner(request), role="runtime")
            workspace = await deps.tools.workspace(principal, command.workspace_id)
            return await deps.tools.prepare(
                ToolRequest(
                    **command.model_dump(),
                    principal=principal,
                    goal_id=workspace.goal_id,
                    goal_revision=workspace.revision,
                )
            )

        @app.post("/api/v1/tools/operations/{operation_id}/approve")
        async def approve_tool(request: Request, operation_id: str) -> ToolApproval:
            return await deps.tools.approve(
                Principal(owner=owner(request), role="user"), operation_id
            )

        @app.post("/api/v1/tools/operations/{operation_id}/execute")
        async def execute_tool(
            request: Request, operation_id: str, command: ToolExecuteCommand
        ) -> ToolReceipt:
            return await deps.tools.execute(
                Principal(owner=owner(request)), operation_id, command.approval_id
            )

        @app.post("/api/v1/tools/operations/{operation_id}/reconcile")
        async def reconcile_tool(request: Request, operation_id: str) -> ToolReceipt:
            return await deps.tools.reconcile(Principal(owner=owner(request)), operation_id)

        @app.get("/api/v1/tools/operations/{operation_id}")
        async def tool_receipt(request: Request, operation_id: str) -> ToolReceipt:
            return await deps.tools.receipt(Principal(owner=owner(request)), operation_id)

        @app.get("/api/v1/tools/operations/{operation_id}/artifact")
        async def tool_artifact(request: Request, operation_id: str) -> Response:
            name, data = await deps.tools.artifact(Principal(owner=owner(request)), operation_id)
            return Response(
                data,
                media_type="text/plain",
                headers={
                    "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name, safe=""),
                    "X-Content-Type-Options": "nosniff",
                    "Cache-Control": "no-store",
                },
            )

        @app.get("/api/v1/judgment")
        async def judgment_info(request: Request) -> JudgmentInfo:
            owner(request)
            return deps.judgment.info()

        @app.post("/api/v1/judgment/preview")
        async def judgment_preview(request: Request, command: JudgmentPreview) -> JudgmentResult:
            value = owner(request)
            return await deps.judgment.decide(
                JudgmentRequest(
                    request_id=command.request_id,
                    principal=Principal(owner=value, role="runtime"),
                    goal_id="judgment-preview-" + hashlib.sha256(value.encode()).hexdigest(),
                    state=command.state,
                    questions=JudgmentQuestionsFactory().create(),
                    data_domain="public" if command.public else "local-only",
                )
            )

        @app.get("/api/v1/models")
        async def models(request: Request) -> list[ModelInfo]:
            owner(request)
            return deps.models.catalog()

        @app.post("/api/v1/models/{model_id}/probe")
        async def probe_model(request: Request, model_id: str, command: ModelProbe) -> ModelResult:
            value = owner(request)
            return await deps.models.generate(
                ModelRequest(
                    model_id=model_id,
                    request_id="probe-" + command.request_id,
                    principal=Principal(owner=value, role="runtime"),
                    goal_id="model-probe-" + hashlib.sha256(value.encode()).hexdigest(),
                    messages=(ModelMessage(role="user", content="Reply with only the word OK."),),
                    max_output_tokens=16,
                    data_domain="public",
                )
            )

        @app.get("/api/v1/policy")
        async def public_policy(request: Request) -> PublicPolicy:
            owner(request)
            return deps.control.public()

        @app.post("/api/v1/policy/preview")
        async def preview_policy(request: Request, action: ActionRequest) -> PolicyDecision:
            value = owner(request)
            # HTTP callers cannot impersonate a human role via a preview body.
            action = action.model_copy(update={"principal": Principal(owner=value, role="runtime")})
            return deps.control.preview(action)

        @app.post("/api/v1/policy/revisions")
        async def revise_policy(request: Request, revision: PolicyRevision) -> PublicPolicy:
            principal = Principal(owner=owner(request), role="user")
            await deps.control.reconfigure(principal, revision.config, revision.expected_version)
            return deps.control.public()

        @app.get("/api/v1/capabilities")
        async def capabilities() -> list[dict[str, object]]:
            return [module.model_dump(mode="json") for module in deps.modules]

        @app.get("/api/v1/sessions")
        async def sessions(request: Request) -> list[Session]:
            return service().list_sessions(owner(request))

        @app.post("/api/v1/sessions", status_code=201)
        async def create_session(request: Request, command: CreateSession) -> Session:
            return service().create_session(owner(request), command)

        @app.get("/api/v1/sessions/{session_id}")
        async def get_session(request: Request, session_id: str) -> Session:
            return service().get_session(owner(request), session_id)

        @app.post("/api/v1/sessions/{session_id}/messages", status_code=202)
        async def send(request: Request, session_id: str, command: SendMessage) -> Session:
            value = owner(request)
            decision = deps.control.preview(
                ActionRequest(
                    principal=Principal(owner=value),
                    goal_id=session_id,
                    goal_revision=1,
                    operation_id=command.request_id,
                    action="demo.start",
                )
            )
            if decision.outcome != "allow":
                raise ApplicationError(403, decision.reason_codes[0], "当前策略不允许启动此演示")
            return await service().send(value, session_id, command)

        @app.post("/api/v1/sessions/{session_id}/stop")
        async def stop(request: Request, session_id: str, command: StopRun) -> Session:
            return await service().stop(owner(request), session_id, command)

        # Declare the WebSocket schema alongside the HTTP OpenAPI components.
        # /contracts is a schema, not a pretend event endpoint.
        @app.get("/api/v1/contracts/session-event")
        async def event_contract() -> dict[str, object]:
            return SessionEvent.model_json_schema()

        @app.websocket("/api/v1/sessions/{session_id}/events")
        async def events(websocket: WebSocket, session_id: str) -> None:
            try:
                value = deps.identity.owner(websocket.cookies.get("auton_owner", ""))
                if websocket.headers.get("origin") not in config.allowed_origins:
                    raise ApplicationError(403, "origin_denied", "Socket origin is not allowed")
            except ApplicationError:
                await websocket.close(code=1008)
                return
            queue: asyncio.Queue[SessionEvent] | None = None
            conversation = deps.conversation
            if conversation is None:
                await websocket.close(code=1013)
                return
            try:
                queue = conversation.subscribe(value, session_id)
            except ApplicationError:
                await websocket.close(code=1008)
                return
            await websocket.accept()

            async def receive_until_disconnect() -> None:
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        return

            receiver = asyncio.create_task(receive_until_disconnect())
            pending_event: asyncio.Task[SessionEvent] | None = None
            try:
                while not receiver.done():
                    pending_event = asyncio.create_task(queue.get())
                    done, _ = await asyncio.wait(
                        [receiver, pending_event], return_when=asyncio.FIRST_COMPLETED
                    )
                    if receiver in done:
                        break
                    await websocket.send_json(pending_event.result().model_dump(mode="json"))
            except (asyncio.CancelledError, WebSocketDisconnect, OSError, RuntimeError):
                pass
            finally:
                receiver.cancel()
                # Gather independently: Task is invariant, with distinct result types.
                with CancelScope(shield=True):
                    await asyncio.gather(receiver, return_exceptions=True)
                    if pending_event is not None:
                        pending_event.cancel()
                        await asyncio.gather(pending_event, return_exceptions=True)
                    conversation.unsubscribe(session_id, queue)

        return app
