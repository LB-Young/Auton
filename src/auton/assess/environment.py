from auton.agent.contracts import AgentRun, checkpoint_event_id
from auton.assess.store import digest
from auton.constitution.config import Principal
from auton.context.ports import ContextEnginePort
from auton.kernel.events import EventScope, StoredEvent
from auton.kernel.ports import ApplicationError
from auton.kernel.storage import EventLogPort
from auton.tools.contracts import ToolWorkspace, operation_event_id, workspace_event_id


async def conditions(
    principal: Principal,
    run: AgentRun,
    source: StoredEvent,
    events: EventLogPort,
    context: ContextEnginePort,
) -> tuple[str, bool, tuple[str, ...], dict[str, str]]:
    reasons: list[str] = []
    evidence_text: dict[str, str] = {}
    asset_snapshots: set[str] = set()
    context_versions: set[str] = set()
    initial_messages_digest: str | None = None
    for identity in run.context_ids:
        snapshot = await context.snapshot(
            principal.model_copy(update={"role": "runtime"}), run.command.project_id, identity
        )
        if initial_messages_digest is None:
            initial_messages_digest = digest(
                {
                    "messages": [m.model_dump(mode="json") for m in snapshot.messages],
                    "tools": [t.model_dump(mode="json") for t in snapshot.tools],
                }
            )
        asset_snapshots.add(snapshot.asset_snapshot_id)
        context_versions.add(
            snapshot.instructions_revision
            + ":"
            + snapshot.retrieval_revision
            + ":"
            + snapshot.compression_revision
        )
        for evidence in snapshot.evidence:
            for asset_id in evidence.asset_ids:
                evidence_text["asset:" + asset_id] = evidence.text
    if len(asset_snapshots) > 1:
        reasons.append("input_assets_changed_during_run")
    seed = await events.lookup(checkpoint_event_id(principal.owner, run.id, 0))
    workspace_source = await events.lookup(
        workspace_event_id(principal.owner, run.command.workspace_id)
    )
    if seed is None or workspace_source is None or workspace_source.cursor >= seed.cursor:
        reasons.append("initial_workspace_provenance_missing")
    else:
        workspace = ToolWorkspace.model_validate(workspace_source.event.payload["workspace"])
        if workspace.owner != principal.owner:
            raise ApplicationError(
                403,
                "assessment_workspace_scope",
                "Workspace provenance belongs to a different actor",
            )
        operations = {plan.operation_id for plan in run.plans} | {
            r.operation_id for r in run.receipts
        }
        cursor, scanned = 0, 0
        while scanned < 10000:
            batch = await events.read(
                after=cursor,
                limit=200,
                scope=EventScope.model_validate({"goal_id": workspace.goal_id}),
            )
            if not batch:
                break
            for row in batch:
                if row.cursor > source.cursor:
                    break
                cursor = row.cursor
                scanned += 1
                operation = row.event.scope.operation_id
                if row.event.kind not in {"tool.prepared", "tool.started"} or not operation:
                    continue
                stage = row.event.kind.split(".")[1]
                if row.event.event_id != operation_event_id(principal.owner, str(operation), stage):
                    raise ApplicationError(
                        403, "assessment_tool_scope", "Unexpected operation ownership"
                    )
                if row.cursor < seed.cursor:
                    reasons.append("workspace_was_previously_used")
                elif str(operation) not in operations:
                    reasons.append("concurrent_or_external_workspace_operation")
            if len(batch) < 200 or batch[-1].cursor > source.cursor:
                break
        if scanned >= 10000:
            reasons.append("workspace_history_scan_limit")
    required = {
        "max_steps",
        "max_tokens",
        "max_cost_microusd",
        "max_tool_calls",
        "max_output_tokens",
    }
    if set(run.budget_limits) != required or any(v <= 0 for v in run.budget_limits.values()):
        reasons.append("original_run_budget_missing")
    if not run.executor_spec:
        reasons.append("original_executor_spec_missing")
    if run.goal_revision != 1:
        reasons.append("user_revisions_change_the_experiment")
    signature = {
        "goal": run.command.goal,
        "initial_messages_digest": initial_messages_digest,
        "pricing_revision": run.executor_spec.get("price_revision"),
        "boundaries": run.command.boundaries,
        "allowed_tools": run.command.allowed_tools,
        "acceptance": run.command.acceptance.model_dump(mode="json"),
        "data_domain": run.command.data_domain,
        "budget": run.budget_limits,
        "assets": sorted(asset_snapshots),
        "context_versions": sorted(context_versions),
        "initial_workspace": "host-ledger-empty" if not reasons else "unverified",
    }
    return digest(signature), not reasons, tuple(dict.fromkeys(reasons)), evidence_text
