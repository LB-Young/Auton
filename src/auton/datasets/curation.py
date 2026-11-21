import hashlib
import json
from typing import Protocol

from pydantic import JsonValue, ValidationError

from auton.agent.contracts import AgentRun, checkpoint_event_id
from auton.assess.contracts import normalize_protected_input
from auton.constitution.config import Principal
from auton.datasets.contracts import DatasetBuild, SourceProof, TrainingExample
from auton.datasets.dependencies import DatasetDependencies
from auton.datasets.sources import SourceSubject
from auton.datasets.store import digest
from auton.kernel.ports import ApplicationError
from auton.model.contracts import ModelMessage, ModelRequest
from auton.tools.contracts import ToolReceipt


def validate_loss_mask(example: TrainingExample) -> None:
    if example.kind != "executor":
        if example.input_messages or example.target_message or example.loss_message_indices:
            raise ApplicationError(
                422,
                "dataset_wrong_supervision_kind",
                "Classification samples cannot masquerade as chat SFT",
            )
        return
    if (
        example.target_message is None
        or example.target_message.role != "assistant"
        or example.loss_message_indices != (len(example.input_messages),)
    ):
        raise ApplicationError(
            422,
            "dataset_wrong_loss_mask",
            "Only the selected verified assistant target may carry loss",
        )
    messages = (*example.input_messages, example.target_message, *example.following_tool_results)
    if any(m.role != "tool" for m in example.following_tool_results):
        raise ApplicationError(
            422,
            "dataset_future_supervision",
            "Following tool receipts are evidence, never assistant targets",
        )
    try:
        ModelRequest(
            request_id="validate-only",
            principal=Principal(owner="validation", role="training"),
            goal_id="validate-only",
            model_id="not-dispatched",
            messages=messages,
            tools=example.tools,
        )
    except ValidationError as error:
        raise ApplicationError(
            422,
            "dataset_truncated_tool_pair",
            "Keep complete tool call/result associations and original constraints",
        ) from error


class Curator(Protocol):
    async def curate(
        self, principal: Principal, command: DatasetBuild, sources: tuple[SourceSubject, ...]
    ) -> tuple[TrainingExample, ...]: ...


class ExecutorCurator:
    async def curate(
        self, principal: Principal, command: DatasetBuild, sources: tuple[SourceSubject, ...]
    ) -> tuple[TrainingExample, ...]:
        examples = []
        for source in sources:
            run = source.run
            if run.command.acceptance.kind != "file" or set(run.command.allowed_tools) != {
                "file.write"
            }:
                raise ApplicationError(
                    422,
                    "dataset_semantic_sft_not_calibrated",
                    "Initial SFT scope is independently verified file actions",
                )
            for frame in source.frames:
                if len(frame.result.tool_calls) != 1:
                    continue
                call = frame.result.tool_calls[0]
                body = call.arguments.get("content")
                if (
                    call.name != "file_write"
                    or not isinstance(body, str)
                    or call.arguments.get("path") != run.command.acceptance.path
                    or hashlib.sha256(body.encode()).hexdigest() != run.command.acceptance.sha256
                ):
                    continue
                replies = tuple(
                    m for m in run.history if m.role == "tool" and m.tool_call_id == call.id
                )
                if len(replies) != 1 or replies[0].content is None:
                    continue
                try:
                    receipt = ToolReceipt.model_validate_json(replies[0].content)
                except ValidationError:
                    continue
                if (
                    receipt not in run.receipts
                    or receipt.outcome != "succeeded"
                    or not receipt.artifact
                    or receipt.artifact.sha256 != run.command.acceptance.sha256
                ):
                    continue
                # Project only the proven action; prose claims are not promoted to gold.
                target = ModelMessage(role="assistant", content=None, tool_calls=(call,))
                example = TrainingExample(
                    id=digest(
                        {
                            "kind": "executor",
                            "input": frame.request.digest,
                            "target": target.model_dump(mode="json"),
                        }
                    ),
                    kind="executor",
                    family=source.ref.family,
                    origin_group=source.ref.origin_group,
                    split=source.ref.split,
                    normalized_input=normalize_protected_input(run.command.goal),
                    normalized_target=normalize_protected_input(body),
                    input_messages=frame.request.messages,
                    target_message=target,
                    following_tool_results=replies,
                    tools=frame.request.tools,
                    loss_message_indices=(len(frame.request.messages),),
                    proofs=(source.proof,),
                    input_fingerprints=source.fingerprints,
                    lineage_tokens=source.group_tokens,
                    engineering_only=source.proof.source == "test",
                )
                validate_loss_mask(example)
                examples.append(example)
        return tuple(examples)


class DecisionCurator:
    def __init__(self, deps: DatasetDependencies) -> None:
        self.deps = deps

    async def curate(
        self, principal: Principal, command: DatasetBuild, sources: tuple[SourceSubject, ...]
    ) -> tuple[TrainingExample, ...]:
        eligible = {
            r.id: r for r in await self.deps.reviews.eligible(principal, command.project_id)
        }
        output = []
        for source in sources:
            reviewed = eligible.get(source.ref.review_id or "")
            if reviewed is None:
                raise ApplicationError(
                    409,
                    "dataset_decision_not_keep",
                    "Only current independently calibrated adopted beneficial KEEP is admitted",
                )
            record = await self.deps.reviews.get(principal, reviewed.id)
            teacher = record.subject.decision.source
            if not any(
                use.model_id == teacher.repository
                and use.declared_revision == teacher.revision
                and use.training_use_confirmed_by_user
                for use in source.grant.command.teacher_uses
            ):
                raise ApplicationError(
                    403,
                    "dataset_decision_teacher_terms_unknown",
                    "Decision-teacher permissions are distinct from actor permissions",
                )
            if (
                record.command.run_id != source.run.id
                or record.command.expected_run_version != source.run.version
            ):
                raise ApplicationError(
                    409, "dataset_decision_scope", "KEEP belongs to a different source checkpoint"
                )
            target = {
                k: v
                for k, v in reviewed.target.items()
                if k in {"question_id", "type", "selected_id"}
            }
            if not target.get("selected_id"):
                raise ApplicationError(
                    422,
                    "dataset_decision_target_missing",
                    "A missing or abstained answer is not a positive target",
                )
            proof = SourceProof.model_validate(
                {
                    **source.proof.model_dump(),
                    "review_id": reviewed.id,
                    "review_version": reviewed.version,
                }
            )
            example = TrainingExample(
                id=digest({"kind": "decision", "source": reviewed.source_digest, "target": target}),
                kind="decision",
                family=source.ref.family,
                origin_group=source.ref.origin_group,
                split=source.ref.split,
                normalized_input=normalize_protected_input(source.run.command.goal),
                normalized_target=digest(target),
                structured_input=reviewed.input,
                structured_target=target,
                proofs=(proof,),
                input_fingerprints=source.fingerprints,
                lineage_tokens=source.group_tokens,
                engineering_only=source.proof.source == "test",
            )
            validate_loss_mask(example)
            output.append(example)
        return tuple(output)


class RouterCurator:
    def __init__(self, deps: DatasetDependencies) -> None:
        self.deps = deps

    async def curate(
        self, principal: Principal, command: DatasetBuild, sources: tuple[SourceSubject, ...]
    ) -> tuple[TrainingExample, ...]:
        mapping = {s.run.id: s for s in sources}
        output = []
        for pair in command.router_pairs:
            if (
                pair.left_run_id not in mapping
                or pair.right_run_id not in mapping
                or pair.left_run_id == pair.right_run_id
            ):
                raise ApplicationError(
                    422,
                    "dataset_router_pair_scope",
                    "Compare two actually observed frozen source runs",
                )
            left, right = mapping[pair.left_run_id], mapping[pair.right_run_id]
            a, b = left.run, right.run
            for source in (left, right):
                run = source.run
                if (
                    run.decision_catalog_cutoff is None
                    or run.decision_catalog_goal_revision != run.goal_revision
                ):
                    raise ApplicationError(
                        409,
                        "dataset_router_catalog_missing",
                        "Candidate declarations must predate this goal revision",
                    )
                witness = await self.deps.events.lookup(
                    checkpoint_event_id(principal.owner, run.id, run.decision_catalog_cutoff)
                )
                first = (
                    await self.deps.events.lookup(source.frames[0].request_event)
                    if source.frames
                    else None
                )
                if witness is None or first is None or witness.cursor >= first.cursor:
                    raise ApplicationError(
                        409,
                        "dataset_router_catalog_witness_missing",
                        "The frozen catalog needs an original before-action checkpoint",
                    )
                historical = AgentRun.model_validate(witness.event.payload["run"])
                if (
                    historical.decision_candidate_catalog != run.decision_candidate_catalog
                    or historical.goal_revision != run.goal_revision
                ):
                    raise ApplicationError(
                        409,
                        "dataset_router_catalog_changed",
                        "Original candidate declaration differs",
                    )
                if (run.resolved_model_id or run.command.model_id) not in {
                    str(m.get("id")) for m in run.decision_candidate_catalog
                }:
                    raise ApplicationError(
                        409,
                        "dataset_router_candidate_unknown",
                        "Observed model was not in the original candidate declaration",
                    )
            if (
                not left.frames
                or not right.frames
                or left.frames[0].request.messages != right.frames[0].request.messages
                or left.frames[0].request.tools != right.frames[0].request.tools
                or left.frames[0].request.max_output_tokens
                != right.frames[0].request.max_output_tokens
            ):
                raise ApplicationError(
                    409,
                    "dataset_router_input_mismatch",
                    "Compare actual identical initial model inputs and tool protocols",
                )

            def condition(s: SourceSubject) -> str:
                r = s.run
                return digest(
                    {
                        "goal": r.command.goal,
                        "boundaries": r.command.boundaries,
                        "domain": r.command.data_domain,
                        "tools": r.command.allowed_tools,
                        "acceptance": r.command.acceptance.model_dump(mode="json"),
                        "budget": r.budget_limits,
                        "assets": s.assets.id,
                        "candidates": r.decision_candidate_catalog,
                    }
                )

            if (
                not a.decision_candidate_catalog
                or a.decision_catalog_cutoff is None
                or not b.decision_candidate_catalog
                or b.decision_catalog_cutoff is None
            ):
                raise ApplicationError(
                    409,
                    "dataset_router_catalog_missing",
                    "Do not reconstruct past candidate availability from a later registry",
                )
            if (
                condition(left) != condition(right)
                or (a.resolved_model_id or a.command.model_id)
                == (b.resolved_model_id or b.command.model_id)
                or left.ref.split != right.ref.split
            ):
                raise ApplicationError(
                    409,
                    "dataset_router_uncontrolled_pair",
                    "Goals, budgets, inputs and candidate declarations must match",
                )
            if a.command.acceptance.kind != "file" or set(a.command.allowed_tools) != {
                "file.write"
            }:
                raise ApplicationError(
                    422,
                    "dataset_router_initial_scope",
                    "Initial comparisons only cover isolated new-file tasks",
                )
            for s in (left, right):
                if len(s.run.receipts) != 1 or s.run.receipts[0].outcome != "succeeded":
                    raise ApplicationError(
                        409,
                        "dataset_router_effects_uncertain",
                        "Both compared file deliveries need known independent receipts",
                    )
                calls = [c for f in s.frames for c in f.result.tool_calls]
                if (
                    len(calls) != 1
                    or calls[0].name != "file_write"
                    or calls[0].arguments.get("expected_sha256") is not None
                ):
                    raise ApplicationError(
                        409,
                        "dataset_router_initial_state_unknown",
                        "Comparisons require one write into an absent file, "
                        "not unknown earlier state",
                    )
            # Both sources passed independent acceptance. More expensive is not
            # automatically more capable; label only observed within-domain cost.
            if (a.cost_microusd, a.tokens_used) == (b.cost_microusd, b.tokens_used):
                raise ApplicationError(
                    409,
                    "dataset_router_no_observed_preference",
                    "A tie is not evidence for an arbitrary preferred model",
                )
            winner = min((a, b), key=lambda r: (r.cost_microusd, r.tokens_used))
            target: dict[str, JsonValue] = {
                "model_id": winner.resolved_model_id or winner.command.model_id,
                "basis": "observed_file_success_then_actual_cost",
            }
            inputs: dict[str, JsonValue] = {
                "state": a.command.goal,
                "boundaries": list(a.command.boundaries),
                "candidate_catalog": list(a.decision_candidate_catalog),
                "limits": {k: v for k, v in a.budget_limits.items()},
                "tools": list(a.command.allowed_tools),
            }
            example = TrainingExample(
                id=digest(
                    {
                        "kind": "router",
                        "left": left.proof.source_digest,
                        "right": right.proof.source_digest,
                    }
                ),
                kind="router",
                family=left.ref.family,
                origin_group=left.ref.origin_group,
                split=left.ref.split,
                normalized_input=normalize_protected_input(a.command.goal),
                normalized_target=json.dumps(target, sort_keys=True),
                structured_input=inputs,
                structured_target=target,
                proofs=(left.proof, right.proof),
                input_fingerprints=tuple(dict.fromkeys((*left.fingerprints, *right.fingerprints))),
                lineage_tokens=tuple(dict.fromkeys((*left.group_tokens, *right.group_tokens))),
                engineering_only=left.proof.source == "test" or right.proof.source == "test",
            )
            validate_loss_mask(example)
            output.append(example)
        return tuple(output)


class DatasetCuratorFactory:
    def create(self, kind: str, deps: DatasetDependencies) -> Curator:
        if kind == "executor":
            return ExecutorCurator()
        if kind == "decision":
            return DecisionCurator(deps)
        if kind == "router":
            return RouterCurator(deps)
        raise ValueError("Unsupported dataset kind")
