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
from auton.assess.contracts import (
    Aggregate,
    AssessmentStatus,
    BatchEvaluation,
    BatchResult,
    BlindWindow,
    BlindWindowCommand,
    CalibrationCommand,
    CalibrationReport,
    CaseBank,
    CompareCommand,
    Comparison,
    EvalCase,
    EvalJob,
    EvalReport,
    EvaluateCommand,
    ImportCases,
    SeedCommand,
    WindowView,
)
from auton.constitution.config import (
    ActionRequest,
    ConstitutionConfig,
    PolicyDecision,
    Principal,
    PublicPolicy,
)
from auton.context.contracts import ContextRequest, ContextSnapshot, TaskState
from auton.datasets.contracts import (
    DataGrant,
    DataGrantCommand,
    DatasetArtifact,
    DatasetBuild,
    DatasetSnapshot,
    DatasetStatus,
    DatasetWithdrawal,
    ExportCommand,
)
from auton.decision_review.contracts import (
    CalibrationView,
    HumanRevision,
    MetaCaseCommand,
    ReviewCommand,
    ReviewExport,
    ReviewRecord,
    ReviewStatus,
)
from auton.delegation.contracts import (
    ContrastCommand,
    DelegationCommand,
    DelegationCreate,
    DelegationStatus,
    DelegationView,
    SingleMultiContrast,
)
from auton.demo.ports import (
    ConversationPort,
    CreateSession,
    ErrorBody,
    SendMessage,
    Session,
    SessionEvent,
    StopRun,
)
from auton.evolve.contracts import (
    ArenaCommand,
    ArenaControl,
    ArenaView,
    DiagnoseCommand,
    Diagnosis,
    EvolutionStatus,
    GenerationRecord,
    PlaybookEntry,
    Proposal,
    ProposalCommand,
    ReflectCommand,
    SubmitProposal,
)
from auton.experience.contracts import RecoveryCommand, Trajectory
from auton.genome.contracts import Asset, Project, Revision, Snapshot, VersionInfo
from auton.judgment.contracts import JudgmentInfo, JudgmentRequest, JudgmentResult
from auton.judgment.questions import JudgmentQuestionsFactory
from auton.kernel.ports import ApplicationError
from auton.model.contracts import ModelInfo, ModelMessage, ModelRequest, ModelResult
from auton.release.contracts import (
    ReleaseApproval,
    ReleaseControl,
    ReleaseObservation,
    ReleasePlanCommand,
    ReleaseRecord,
    ReleaseStatus,
    ReleaseValidationRun,
)
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
from auton.training.contracts import (
    TrainingBundle,
    TrainingControl,
    TrainingJob,
    TrainingJobCommand,
    TrainingPlan,
    TrainingPlanCommand,
    TrainingStatus,
)
from auton.training.decision_contracts import (
    DecisionEvaluation,
    DecisionEvaluationCommand,
    ShadowEvaluation,
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

        @app.get("/api/v1/releases/status")
        async def release_status(request: Request) -> ReleaseStatus:
            owner(request)
            return deps.release.status()

        @app.get("/api/v1/releases")
        async def releases(request: Request, project_id: str) -> tuple[ReleaseRecord, ...]:
            return await deps.release.list(Principal(owner=owner(request), role="user"), project_id)

        @app.post("/api/v1/releases", status_code=201)
        async def release_plan(request: Request, command: ReleasePlanCommand) -> ReleaseRecord:
            return await deps.release.plan(Principal(owner=owner(request), role="user"), command)

        @app.get("/api/v1/releases/{release_id}")
        async def release_get(request: Request, release_id: str) -> ReleaseRecord:
            return await deps.release.get(Principal(owner=owner(request), role="user"), release_id)

        @app.post("/api/v1/releases/{release_id}/approvals")
        async def release_approve(
            request: Request, release_id: str, command: ReleaseApproval
        ) -> ReleaseRecord:
            return await deps.release.approve(
                Principal(owner=owner(request), role="user"), release_id, command
            )

        @app.post("/api/v1/releases/{release_id}/commands")
        async def release_control(
            request: Request, release_id: str, command: ReleaseControl
        ) -> ReleaseRecord:
            return await deps.release.control(
                Principal(owner=owner(request), role="user"), release_id, command
            )

        @app.post("/api/v1/releases/{release_id}/observations")
        async def release_observe(
            request: Request, release_id: str, command: ReleaseObservation
        ) -> ReleaseRecord:
            return await deps.release.observe(
                Principal(owner=owner(request), role="user"), release_id, command
            )

        @app.post("/api/v1/releases/{release_id}/validation")
        async def release_validate(request: Request, release_id: str) -> ReleaseRecord:
            return await deps.release.prepare_validation(
                Principal(owner=owner(request), role="user"), release_id
            )

        @app.post("/api/v1/releases/{release_id}/validation/runs", status_code=201)
        async def release_validation_run(
            request: Request, release_id: str, command: ReleaseValidationRun
        ) -> AgentRun:
            return await deps.release.validation_run(
                Principal(owner=owner(request), role="user"), release_id, command
            )

        @app.get("/api/v1/training/status")
        async def training_status(request: Request) -> TrainingStatus:
            owner(request)
            return deps.training.status()

        @app.get("/api/v1/training/plans")
        async def training_plans(request: Request, project_id: str) -> tuple[TrainingPlan, ...]:
            return await deps.training.plans(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.post("/api/v1/training/plans", status_code=201)
        async def training_plan(request: Request, command: TrainingPlanCommand) -> TrainingPlan:
            return await deps.training.plan(Principal(owner=owner(request), role="user"), command)

        @app.post("/api/v1/training/jobs", status_code=201)
        async def training_create(request: Request, command: TrainingJobCommand) -> TrainingJob:
            return await deps.training.create(Principal(owner=owner(request), role="user"), command)

        @app.get("/api/v1/training/jobs")
        async def training_jobs(request: Request, project_id: str) -> tuple[TrainingJob, ...]:
            return await deps.training.jobs(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.get("/api/v1/training/jobs/{job_id}")
        async def training_job(request: Request, job_id: str) -> TrainingJob:
            return await deps.training.get(Principal(owner=owner(request), role="user"), job_id)

        @app.post("/api/v1/training/jobs/{job_id}/commands")
        async def training_control(
            request: Request, job_id: str, command: TrainingControl
        ) -> TrainingJob:
            return await deps.training.control(
                Principal(owner=owner(request), role="user"), job_id, command
            )

        @app.get("/api/v1/training/bundles")
        async def training_bundles(request: Request, project_id: str) -> tuple[TrainingBundle, ...]:
            return await deps.training.bundles(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.get("/api/v1/decision-training/status")
        async def decision_training_status(request: Request) -> TrainingStatus:
            owner(request)
            return deps.decision_training.status()

        @app.get("/api/v1/decision-training/plans")
        async def decision_training_plans(
            request: Request, project_id: str
        ) -> tuple[TrainingPlan, ...]:
            return await deps.decision_training.plans(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.post("/api/v1/decision-training/plans", status_code=201)
        async def decision_training_plan(
            request: Request, command: TrainingPlanCommand
        ) -> TrainingPlan:
            return await deps.decision_training.plan(
                Principal(owner=owner(request), role="user"), command
            )

        @app.post("/api/v1/decision-training/jobs", status_code=201)
        async def decision_training_create(
            request: Request, command: TrainingJobCommand
        ) -> TrainingJob:
            return await deps.decision_training.create(
                Principal(owner=owner(request), role="user"), command
            )

        @app.get("/api/v1/decision-training/jobs")
        async def decision_training_jobs(
            request: Request, project_id: str
        ) -> tuple[TrainingJob, ...]:
            return await deps.decision_training.jobs(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.get("/api/v1/decision-training/jobs/{job_id}")
        async def decision_training_job(request: Request, job_id: str) -> TrainingJob:
            return await deps.decision_training.get(
                Principal(owner=owner(request), role="user"), job_id
            )

        @app.post("/api/v1/decision-training/jobs/{job_id}/commands")
        async def decision_training_control(
            request: Request, job_id: str, command: TrainingControl
        ) -> TrainingJob:
            return await deps.decision_training.control(
                Principal(owner=owner(request), role="user"), job_id, command
            )

        @app.get("/api/v1/decision-training/bundles")
        async def decision_training_bundles(
            request: Request, project_id: str
        ) -> tuple[TrainingBundle, ...]:
            return await deps.decision_training.bundles(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.post("/api/v1/decision-training/evaluations", status_code=201)
        async def decision_training_evaluate(
            request: Request, command: DecisionEvaluationCommand
        ) -> DecisionEvaluation:
            return await deps.decision_training.evaluate(
                Principal(owner=owner(request), role="user"), command
            )

        @app.get("/api/v1/decision-training/evaluations")
        async def decision_training_evaluations(
            request: Request, project_id: str
        ) -> tuple[DecisionEvaluation, ...]:
            return await deps.decision_training.evaluations(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.get("/api/v1/decision-training/bundles/{bundle_id}/shadow-replay")
        async def decision_training_shadow(
            request: Request, project_id: str, bundle_id: str
        ) -> ShadowEvaluation:
            return await deps.decision_training.shadow_replay(
                Principal(owner=owner(request), role="user"), project_id, bundle_id
            )

        @app.get("/api/v1/datasets/status")
        async def dataset_status(request: Request) -> DatasetStatus:
            owner(request)
            return deps.datasets.status()

        @app.get("/api/v1/datasets/grants")
        async def dataset_grants(request: Request, project_id: str) -> tuple[DataGrant, ...]:
            return await deps.datasets.grants(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.post("/api/v1/datasets/grants", status_code=201)
        async def dataset_grant(request: Request, command: DataGrantCommand) -> DataGrant:
            return await deps.datasets.grant(Principal(owner=owner(request), role="user"), command)

        @app.post("/api/v1/datasets/snapshots", status_code=201)
        async def build_dataset(request: Request, command: DatasetBuild) -> DatasetSnapshot:
            return await deps.datasets.build(Principal(owner=owner(request), role="user"), command)

        @app.get("/api/v1/datasets/snapshots")
        async def dataset_snapshots(
            request: Request, project_id: str
        ) -> tuple[DatasetSnapshot, ...]:
            return await deps.datasets.list(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.get("/api/v1/datasets/snapshots/{snapshot_id}")
        async def dataset_snapshot(request: Request, snapshot_id: str) -> DatasetSnapshot:
            return await deps.datasets.get(
                Principal(owner=owner(request), role="user"), snapshot_id
            )

        @app.post("/api/v1/datasets/withdrawals")
        async def withdraw_dataset_source(
            request: Request, command: DatasetWithdrawal
        ) -> tuple[str, ...]:
            return await deps.datasets.withdraw(
                Principal(owner=owner(request), role="user"), command
            )

        @app.post("/api/v1/datasets/snapshots/{snapshot_id}/exports", status_code=201)
        async def export_dataset(
            request: Request, snapshot_id: str, command: ExportCommand
        ) -> DatasetArtifact:
            return await deps.datasets.export(
                Principal(owner=owner(request), role="user"), snapshot_id, command
            )

        @app.get("/api/v1/datasets/artifacts/{artifact_id}")
        async def read_dataset_artifact(request: Request, artifact_id: str) -> Response:
            artifact, content = await deps.datasets.read_artifact(
                Principal(owner=owner(request), role="user"), artifact_id
            )
            return Response(
                content=content,
                media_type="application/x-ndjson",
                headers={
                    "Content-Disposition": f'attachment; filename="dataset-{artifact.id}.jsonl"',
                    "Cache-Control": "no-store",
                },
            )

        @app.get("/api/v1/decision-review/status")
        async def decision_review_status(request: Request) -> ReviewStatus:
            owner(request)
            return deps.decision_review.status()

        @app.post("/api/v1/decision-review/jobs", status_code=201)
        async def review_decision(request: Request, command: ReviewCommand) -> ReviewRecord:
            return await deps.decision_review.review(
                Principal(owner=owner(request), role="user"), command
            )

        @app.get("/api/v1/decision-review/reviews")
        async def decision_reviews(request: Request, project_id: str) -> tuple[ReviewRecord, ...]:
            return await deps.decision_review.list(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.get("/api/v1/decision-review/reviews/{review_id}")
        async def decision_review(request: Request, review_id: str) -> ReviewRecord:
            return await deps.decision_review.get(
                Principal(owner=owner(request), role="user"), review_id
            )

        @app.post("/api/v1/decision-review/reviews/{review_id}/revisions")
        async def revise_decision_review(
            request: Request, review_id: str, command: HumanRevision
        ) -> ReviewRecord:
            return await deps.decision_review.revise(
                Principal(owner=owner(request), role="user"), review_id, command
            )

        @app.post("/api/v1/decision-review/meta")
        async def decision_review_meta(
            request: Request, command: MetaCaseCommand
        ) -> CalibrationView:
            return await deps.decision_review.annotate_meta(
                Principal(owner=owner(request), role="user"), command
            )

        @app.get("/api/v1/decision-review/calibrations")
        async def decision_review_calibrations(request: Request) -> tuple[CalibrationView, ...]:
            return await deps.decision_review.calibrations(
                Principal(owner=owner(request), role="user")
            )

        @app.get("/api/v1/decision-review/eligible")
        async def decision_review_eligible(
            request: Request, project_id: str
        ) -> tuple[ReviewExport, ...]:
            return await deps.decision_review.eligible(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.get("/api/v1/evolution/status")
        async def evolution_status(request: Request) -> EvolutionStatus:
            owner(request)
            return deps.evolve.status()

        @app.post("/api/v1/evolution/diagnoses")
        async def evolution_diagnose(request: Request, command: DiagnoseCommand) -> Diagnosis:
            return await deps.evolve.diagnose(Principal(owner=owner(request), role="user"), command)

        @app.post("/api/v1/evolution/proposals", status_code=201)
        async def evolution_propose(request: Request, command: ProposalCommand) -> Proposal:
            return await deps.evolve.propose(Principal(owner=owner(request), role="user"), command)

        @app.post("/api/v1/evolution/reflections", status_code=201)
        async def evolution_reflect(request: Request, command: ReflectCommand) -> Proposal:
            return await deps.evolve.reflect(Principal(owner=owner(request), role="user"), command)

        @app.get("/api/v1/evolution/proposals")
        async def evolution_proposals(request: Request, project_id: str) -> tuple[Proposal, ...]:
            return await deps.evolve.proposals(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.get("/api/v1/evolution/proposals/{proposal_id}")
        async def evolution_proposal(request: Request, proposal_id: str) -> Proposal:
            return await deps.evolve.proposal(
                Principal(owner=owner(request), role="user"), proposal_id
            )

        @app.get("/api/v1/evolution/generations")
        async def evolution_generations(
            request: Request, project_id: str
        ) -> tuple[GenerationRecord, ...]:
            return await deps.evolve.generations(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.get("/api/v1/evolution/playbook")
        async def evolution_playbook(
            request: Request, project_id: str
        ) -> tuple[PlaybookEntry, ...]:
            return await deps.evolve.playbook(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.post("/api/v1/evolution/arenas", status_code=201)
        async def evolution_create_arena(request: Request, command: ArenaCommand) -> ArenaView:
            return await deps.evolve.create_arena(
                Principal(owner=owner(request), role="user"), command
            )

        @app.get("/api/v1/evolution/arenas")
        async def evolution_arenas(request: Request, project_id: str) -> tuple[ArenaView, ...]:
            return await deps.evolve.arenas(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.get("/api/v1/evolution/arenas/{arena_id}")
        async def evolution_arena(request: Request, arena_id: str) -> ArenaView:
            return await deps.evolve.arena(Principal(owner=owner(request), role="user"), arena_id)

        @app.post("/api/v1/evolution/arenas/{arena_id}/commands")
        async def evolution_control(
            request: Request, arena_id: str, command: ArenaControl
        ) -> ArenaView:
            return await deps.evolve.control_arena(
                Principal(owner=owner(request), role="user"), arena_id, command
            )

        @app.post("/api/v1/evolution/proposals/{proposal_id}/submit")
        async def evolution_submit(
            request: Request, proposal_id: str, command: SubmitProposal
        ) -> Proposal:
            return await deps.evolve.submit(
                Principal(owner=owner(request), role="user"), proposal_id, command
            )

        @app.get("/api/v1/delegation/status")
        async def supervisor_status(request: Request) -> DelegationStatus:
            owner(request)
            return deps.delegation.status()

        @app.post("/api/v1/delegation/{parent_id}/contrast")
        async def contrast_supervisor(
            request: Request, parent_id: str, command: ContrastCommand
        ) -> SingleMultiContrast:
            return await deps.delegation.contrast(
                Principal(owner=owner(request), role="user"), parent_id, command
            )

        @app.post("/api/v1/delegation", status_code=201)
        async def create_supervisor(request: Request, command: DelegationCreate) -> DelegationView:
            return await deps.delegation.create(
                Principal(owner=owner(request), role="user"), command
            )

        @app.get("/api/v1/delegation")
        async def list_supervisors(request: Request, project_id: str) -> tuple[DelegationView, ...]:
            return await deps.delegation.list(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.get("/api/v1/delegation/{parent_id}")
        async def get_supervisor(request: Request, parent_id: str) -> DelegationView:
            return await deps.delegation.get(
                Principal(owner=owner(request), role="user"), parent_id
            )

        @app.post("/api/v1/delegation/{parent_id}/commands")
        async def control_supervisor(
            request: Request, parent_id: str, command: DelegationCommand
        ) -> DelegationView:
            return await deps.delegation.command(
                Principal(owner=owner(request), role="user"), parent_id, command
            )

        @app.get("/api/v1/assessment/status")
        async def assessment_status(request: Request) -> AssessmentStatus:
            owner(request)
            return deps.assess.status()

        @app.get("/api/v1/assessment/bank")
        async def assessment_bank(request: Request) -> CaseBank:
            return await deps.assess.bank(Principal(owner=owner(request), role="user"))

        @app.post("/api/v1/assessment/bank")
        async def import_assessment_cases(request: Request, command: ImportCases) -> CaseBank:
            return await deps.assess.import_cases(
                Principal(owner=owner(request), role="user"), command
            )

        @app.post("/api/v1/assessment/seed")
        async def seed_assessment_cases(request: Request, command: SeedCommand) -> CaseBank:
            return await deps.assess.seed(Principal(owner=owner(request), role="user"), command)

        @app.get("/api/v1/assessment/train-cases")
        async def assessment_training_cases(request: Request) -> tuple[EvalCase, ...]:
            return await deps.assess.train_cases(Principal(owner=owner(request), role="user"))

        @app.get("/api/v1/assessment/windows")
        async def assessment_windows(request: Request) -> tuple[WindowView, ...]:
            return await deps.assess.windows(Principal(owner=owner(request), role="user"))

        @app.post("/api/v1/assessment/windows")
        async def assessment_window(request: Request, command: BlindWindowCommand) -> BlindWindow:
            return await deps.assess.open_window(
                Principal(owner=owner(request), role="user"), command
            )

        @app.post("/api/v1/assessment/jobs")
        async def evaluate_run(request: Request, command: EvaluateCommand) -> EvalJob:
            return await deps.assess.evaluate(Principal(owner=owner(request), role="user"), command)

        @app.get("/api/v1/assessment/jobs/{job_id}")
        async def assessment_job(request: Request, job_id: str) -> EvalJob:
            return await deps.assess.job(Principal(owner=owner(request), role="user"), job_id)

        @app.get("/api/v1/assessment/reports")
        async def assessment_reports(request: Request, project_id: str) -> tuple[EvalReport, ...]:
            return await deps.assess.reports(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.get("/api/v1/assessment/reports/{report_id}")
        async def assessment_report(request: Request, report_id: str) -> EvalReport:
            return await deps.assess.report(Principal(owner=owner(request), role="user"), report_id)

        @app.get("/api/v1/assessment/aggregate")
        async def assessment_aggregate(request: Request, project_id: str) -> Aggregate:
            return await deps.assess.aggregate(
                Principal(owner=owner(request), role="user"), project_id
            )

        @app.post("/api/v1/assessment/compare")
        async def compare_assessment(request: Request, command: CompareCommand) -> Comparison:
            return await deps.assess.compare(
                Principal(owner=owner(request), role="user"), command.baseline, command.candidate
            )

        @app.post("/api/v1/assessment/batches")
        async def assessment_batch(request: Request, command: BatchEvaluation) -> BatchResult:
            return await deps.assess.batch(Principal(owner=owner(request), role="user"), command)

        @app.post("/api/v1/assessment/calibrations")
        async def calibrate_judge(
            request: Request, command: CalibrationCommand
        ) -> CalibrationReport:
            return await deps.assess.calibrate(
                Principal(owner=owner(request), role="user"), command
            )

        @app.get("/api/v1/assessment/calibrations")
        async def assessment_calibrations(request: Request) -> tuple[CalibrationReport, ...]:
            return await deps.assess.calibrations(Principal(owner=owner(request), role="user"))

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
            return deps.models.catalog(Principal(owner=owner(request), role="user"))

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
