import hashlib
import json

from auton.agent.contracts import AgentRun, checkpoint_event_id
from auton.constitution.config import Principal
from auton.decision_review.contracts import EvidenceFact, ReviewCommand, ReviewSubject
from auton.decision_review.dependencies import ReviewDependencies
from auton.decision_review.store import digest
from auton.judgment.contracts import JudgmentRequest, JudgmentResult
from auton.kernel.ports import ApplicationError


class DecisionSourceReader:
    def __init__(self, deps: ReviewDependencies) -> None:
        self.deps = deps

    async def read(self, principal: Principal, command: ReviewCommand) -> ReviewSubject:
        run = await self.deps.agent.get(principal, command.run_id)
        if run.command.project_id != command.project_id:
            raise ApplicationError(404, "decision_review_scope", "No owned project decision")
        if run.version != command.expected_run_version:
            raise ApplicationError(
                409, "decision_review_run_changed", "Freeze the exact actor checkpoint"
            )
        decision = next((j for j in run.judgments if j.request_id == command.judgment_id), None)
        if decision is None or command.judgment_id not in run.judgment_ids:
            raise ApplicationError(
                404, "decision_review_missing", "No recorded decision in this actor"
            )
        answer = next((a for a in decision.answers if a.question_id == command.question_id), None)
        if answer is None:
            raise ApplicationError(404, "decision_review_answer_missing", "No recorded answer")
        identity = hashlib.sha256(
            (principal.owner + "\0" + command.judgment_id).encode()
        ).hexdigest()
        started = await self.deps.events.lookup("judgment:" + identity + ":started")
        completed = await self.deps.events.lookup("judgment:" + identity + ":completed")
        if (
            started is None
            or completed is None
            or not isinstance(started.event.payload.get("request"), dict)
        ):
            raise ApplicationError(
                409, "decision_review_input_missing", "Original judgment input is unavailable"
            )
        request = JudgmentRequest.model_validate(started.event.payload["request"])
        recorded = JudgmentResult.model_validate(completed.event.payload["result"])
        if (
            request.principal.owner != principal.owner
            or request.request_id != command.judgment_id
            or request.digest != decision.request_digest
            or recorded.request_digest != request.digest
            or recorded.answers != decision.answers
            or recorded.source != decision.source
            or request.goal_id != "agent-goal-" + run.id
            or recorded.goal_revision != request.goal_revision
            or request.state_cutoff != decision.state_cutoff
            or completed.cursor <= started.cursor
        ):
            raise ApplicationError(
                409,
                "decision_review_source_mismatch",
                "Decision provenance does not match the actor",
            )
        before = await self.deps.events.lookup(
            checkpoint_event_id(principal.owner, run.id, request.state_cutoff)
        )
        terminal = await self.deps.events.lookup(
            checkpoint_event_id(principal.owner, run.id, run.version)
        )
        if before is None or terminal is None or before.cursor >= started.cursor:
            raise ApplicationError(
                409, "decision_review_cutoff_missing", "Original actor cutoff cannot be proven"
            )
        original = AgentRun.model_validate(before.event.payload["run"])
        if (
            original.goal_revision != request.goal_revision
            or original.command.goal != request.state
        ):
            raise ApplicationError(
                409, "decision_review_cutoff_mismatch", "Original state and goal revision differ"
            )
        # A stage sees only original request/answer + these before-cutoff facts, never
        # the terminal run, trajectory, acceptance result, future costs or human feedback.
        before_facts = (
            EvidenceFact(
                id=before.event.event_id,
                digest=before.event.digest(),
                kind="actor_cutoff",
                cursor=before.cursor,
                text="Original goal revision " + str(request.goal_revision),
            ),
            EvidenceFact(
                id=started.event.event_id,
                digest=started.event.digest(),
                kind="judgment_input",
                cursor=started.cursor,
                text="Frozen original question/state/options",
            ),
        )
        trajectory = await self.deps.experience.trajectory(principal, command.project_id, run.id)
        blockers = []
        if not trajectory.caught_up or trajectory.missing_references:
            blockers.append("trajectory_incomplete")
        if run.status not in {"succeeded", "failed", "cancelled"}:
            blockers.append("task_not_terminal")
        if not decision.adopted:
            blockers.append("answer_not_adopted_no_actor_success_credit")
        else:
            adoption = await self.deps.events.lookup("judgment:" + identity + ":adopted")
            if (
                adoption is None
                or adoption.event.payload.get("request_digest") != request.digest
                or adoption.event.payload.get("policy_action") != "select_executor"
                or adoption.event.payload.get("model_id") != run.command.model_id
            ):
                blockers.append("actual_adoption_receipt_missing_or_executor_mismatch")
            question = next(q for q in request.questions if q.id == command.question_id)
            if question.point != "executor_tier":
                blockers.append("fanout_answer_not_the_adopted_action")
        if answer.status != "answered":
            blockers.append("answer_not_valid")
        if run.goal_revision != request.goal_revision:
            blockers.append("goal_changed_after_decision")
        if request.data_domain == "secret":
            blockers.append("secret_input_not_reviewable")
        snapshot_id = run.input_asset_snapshot_id or run.command.asset_snapshot_id
        if snapshot_id is None:
            blockers.append("original_input_configuration_missing")
        else:
            snapshot = await self.deps.assets.snapshot(principal, command.project_id, snapshot_id)
            if snapshot.purpose == "optimization_arena":
                blockers.append("optimization_arena_not_training_evidence")
        after = [
            EvidenceFact(
                id=terminal.event.event_id,
                digest=terminal.event.digest(),
                kind="actor_checkpoint",
                cursor=terminal.cursor,
                text=(
                    f"Observed status={run.status}; reason={run.reason}; "
                    f"tokens={run.tokens_used}; cost_microusd={run.cost_microusd}"
                ),
            )
        ]
        # Bounded facts are explicit summaries of real, hash-bound events. Omitting
        # an oversized/missing chain lowers attribution; it never invents a replay.
        manifest = [(n.id, n.cursor, n.kind, n.goal_revision, n.details) for n in trajectory.nodes]
        relevant = [
            n
            for n in trajectory.nodes
            if n.kind
            in {
                "model.completed",
                "model.failed",
                "tool.completed",
                "tool.unknown",
                "agent.user_feedback",
                "agent.command",
                "judgment.adopted",
            }
        ]
        if len(relevant) > 30:
            blockers.append("trajectory_exceeds_review_window")
        for node in relevant[:30]:
            if node.cursor <= completed.cursor or node.goal_revision != request.goal_revision:
                continue
            raw = await self.deps.events.lookup(node.id)
            if raw is None:
                blockers.append("trajectory_event_missing")
                continue
            details = raw.event.payload if node.kind == "agent.user_feedback" else node.details
            text = json.dumps(details, ensure_ascii=False, sort_keys=True)
            if len(text) > 1000:
                blockers.append("trajectory_fact_truncated")
                text = text[:1000]
            after.append(
                EvidenceFact(
                    id=node.id,
                    digest=raw.event.digest(),
                    kind=node.kind,
                    cursor=node.cursor,
                    text=text,
                )
            )
        interaction_group = None
        if self.deps.delegation is not None:
            parents = await self.deps.delegation.list(principal, command.project_id)
            for parent in parents:
                if any(child.run_id == run.id for child in parent.children):
                    interaction_group = parent.id
                    blockers.append("multi_agent_interaction_requires_separate_attribution")
                    after.append(
                        EvidenceFact(
                            id="delegation:" + parent.id + ":" + str(parent.version),
                            digest=digest(parent.model_dump(mode="json")),
                            kind="delegation_dag",
                            cursor=terminal.cursor,
                            text=json.dumps(
                                {
                                    "parent": parent.id,
                                    "version": parent.version,
                                    "links": [
                                        (
                                            c.id,
                                            c.depends_on,
                                            next(
                                                (
                                                    state.run_id
                                                    for state in parent.children
                                                    if state.id == c.id
                                                ),
                                                None,
                                            ),
                                        )
                                        for c in parent.command.children
                                    ],
                                },
                                ensure_ascii=False,
                            )[:1000],
                        )
                    )
        passed, current = False, False
        if command.assessment_report_id:
            report = await self.deps.assess.report(principal, command.assessment_report_id)
            if (
                report.run_id != run.id
                or report.project_id != command.project_id
                or report.checkpoint_version != run.version
            ):
                raise ApplicationError(
                    409,
                    "decision_review_assessment_scope",
                    "Acceptance belongs to a different actor checkpoint",
                )
            current = report.current_evidence_valid
            passed = current and report.outcome == "pass" and report.environment_verified
            if report.split in {"test", "meta"}:
                blockers.append("protected_assessment_not_training_evidence")
            if not current:
                blockers.append("assessment_evidence_stale")
            after.append(
                EvidenceFact(
                    id="assessment:" + report.id,
                    digest=digest(report.model_dump(mode="json")),
                    kind="independent_assessment",
                    cursor=terminal.cursor,
                    text=(
                        f"Independent outcome={report.outcome}; current={current}; "
                        f"semantic={report.semantic_verdict}"
                    ),
                )
            )
        else:
            blockers.append("independent_assessment_missing")
        if (
            any(r.outcome == "unknown" for r in run.receipts)
            or (run.steps - len(run.model_results) - len(run.undispatched_model_request_ids)) > 0
        ):
            blockers.append("unknown_model_or_tool_effect")
        # No current actor emits a verified decision-to-action causal edge. This
        # capability must be backed by actual registered receipts before admitting KEEP.
        blockers.append("decision_effect_or_comparative_evidence_missing")
        environment_failure = any(
            r.code in {"service_unavailable", "process_timeout", "workspace_unavailable"}
            for r in run.receipts
        )
        return ReviewSubject(
            request=request,
            decision=decision,
            answer=answer,
            checkpoint_id=terminal.event.event_id,
            checkpoint_digest=terminal.event.digest(),
            run_version=run.version,
            goal_revision=run.goal_revision,
            source="test" if self.deps.test_source or run.source == "test" else "runtime",
            before_evidence=before_facts,
            after_evidence=tuple(after),
            source_digest=digest(
                {
                    "before": [f.model_dump(mode="json") for f in before_facts],
                    "after": [f.model_dump(mode="json") for f in after],
                    "request": request.digest,
                    "decision": decision.model_dump(mode="json"),
                    "full_trajectory_manifest": manifest,
                }
            ),
            blockers=tuple(dict.fromkeys(blockers)),
            assessment_report_id=command.assessment_report_id,
            assessment_passed=passed,
            assessment_current=current,
            goal_changed=run.goal_revision != request.goal_revision,
            environment_failure=environment_failure,
            interaction_group=interaction_group,
            actual_model_ids=tuple(sorted({r.reported_model for r in run.model_results})),
            actual_fingerprints=tuple(
                sorted({r.system_fingerprint for r in run.model_results if r.system_fingerprint})
            ),
        )


class DecisionSourceFactory:
    def create(self, deps: ReviewDependencies) -> DecisionSourceReader:
        return DecisionSourceReader(deps)
