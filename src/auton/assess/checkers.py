import hashlib
import re

from auton.agent.contracts import AgentRun
from auton.assess.contracts import EvalCase, Signal, Verdict
from auton.assess.ports import CheckerPort
from auton.constitution.config import Principal
from auton.context.ports import ContextEnginePort
from auton.kernel.events import StoredEvent
from auton.kernel.ports import ApplicationError
from auton.tools.ports import ToolHostPort


class DeterministicChecker:
    def __init__(self, tools: ToolHostPort, context: ContextEnginePort) -> None:
        self.tools, self.context = tools, context

    async def check(
        self, principal: Principal, run: AgentRun, source: StoredEvent, case: EvalCase | None
    ) -> tuple[Signal, ...]:
        signals: list[Signal] = []
        if run.reason in {
            "invalid_model_output",
            "unregistered_or_disallowed_tool",
            "sensitive_model_tool_output",
            "duplicate_tool_call_ids",
            "repeated_tool_loop",
        }:
            signals.append(
                Signal(
                    name="model_protocol",
                    source="deterministic",
                    verdict="fail",
                    evidence=(source.event.event_id,),
                    reason=run.reason,
                    critical=True,
                )
            )
        if run.reason in {"run_step_or_tool_limit", "run_budget_limit", "run_tool_limit"}:
            signals.append(
                Signal(
                    name="budget_completion",
                    source="deterministic",
                    verdict="fail",
                    evidence=(source.event.event_id,),
                    reason="task_not_completed_within_fixed_budget",
                )
            )
        evidence: tuple[str, ...] = (source.event.event_id,)
        verdict: Verdict
        protocol: Verdict
        pending: set[str] = set()
        seen: set[str] = set()
        valid = True
        for message in run.history:
            if message.role == "assistant":
                if pending:
                    valid = False
                for call in message.tool_calls:
                    if call.id in seen:
                        valid = False
                    seen.add(call.id)
                    pending.add(call.id)
            elif message.role == "tool":
                if message.tool_call_id not in pending:
                    valid = False
                pending.discard(message.tool_call_id or "")
        protocol = "fail" if not valid else "unknown" if pending else "pass"
        signals.append(
            Signal(
                name="tool_protocol",
                source="deterministic",
                verdict=protocol,
                evidence=evidence,
                reason="orphan_or_repeated_tool_pair"
                if not valid
                else "pending_tool_results"
                if pending
                else "paired_tool_messages",
                critical=True,
            )
        )
        if case and (case.prompt != run.command.goal or case.kind != run.command.acceptance.kind):
            signals.append(
                Signal(
                    name="business",
                    source="deterministic",
                    verdict="unknown",
                    evidence=evidence,
                    reason="case_input_mismatch",
                    critical=case.critical,
                )
            )
            return tuple(signals)
        if run.command.acceptance.kind == "file":
            target = case.target_path if case else run.command.acceptance.path
            expected = case.expected_sha256 if case else run.command.acceptance.sha256
            writes = [
                r
                for r in run.receipts
                if r.artifact and r.tool == "file.write" and r.outcome == "succeeded"
            ]
            unexpected = [
                r.operation_id for r in writes if r.artifact and r.artifact.path != target
            ]
            if unexpected:
                signals.append(
                    Signal(
                        name="write_scope",
                        source="deterministic",
                        verdict="fail",
                        evidence=tuple(unexpected),
                        reason="unexpected_output_path",
                        critical=True,
                    )
                )
            receipt = next(
                (r for r in reversed(writes) if r.artifact and r.artifact.path == target), None
            )
            if receipt is None:
                verdict, reason = "unknown", "no_independently_readable_file_receipt"
            else:
                try:
                    _, data = await self.tools.artifact(
                        principal.model_copy(update={"role": "runtime"}), receipt.operation_id
                    )
                    verdict = "pass" if hashlib.sha256(data).hexdigest() == expected else "fail"
                    reason = (
                        "independent_file_digest_matches"
                        if verdict == "pass"
                        else "independent_file_digest_mismatch"
                    )
                    evidence = (*evidence, receipt.operation_id, hashlib.sha256(data).hexdigest())
                except ApplicationError as error:
                    verdict, reason = "unknown", "artifact_unavailable:" + error.code
            signals.append(
                Signal(
                    name="business",
                    source="deterministic",
                    verdict=verdict,
                    evidence=evidence,
                    reason=reason,
                    critical=case.critical if case else False,
                )
            )
        else:
            allowed: set[str] = set()
            try:
                for identity in run.context_ids:
                    snapshot = await self.context.snapshot(
                        principal.model_copy(update={"role": "runtime"}),
                        run.command.project_id,
                        identity,
                    )
                    allowed.update(
                        asset_id for item in snapshot.evidence for asset_id in item.asset_ids
                    )
                cited = set(re.findall(r"\[asset:([a-zA-Z0-9_-]+)\]", run.final_text))
                verdict = (
                    "pass"
                    if len(cited) >= run.command.acceptance.min_sources and cited <= allowed
                    else "fail"
                    if run.final_text
                    else "unknown"
                )
                reason = (
                    "citation_structure_only"
                    if verdict == "pass"
                    else "missing_or_unsupported_citations"
                )
            except ApplicationError as error:
                verdict, reason = "unknown", "evidence_unavailable:" + error.code
            signals.append(
                Signal(
                    name="citation_structure",
                    source="deterministic",
                    verdict=verdict,
                    evidence=evidence,
                    reason=reason,
                )
            )
            signals.append(
                Signal(
                    name="business",
                    source="deterministic",
                    verdict="unknown",
                    evidence=evidence,
                    reason="semantic_truth_requires_calibrated_independent_judge",
                )
            )
        signals.append(
            Signal(
                name="actor_claim",
                source="unverified-self-report",
                verdict="unknown",
                evidence=evidence,
                reason="Actor claims and M09 checks do not establish independent semantic truth",
            )
        )
        return tuple(signals)


class CheckerFactory:
    def create(self, tools: ToolHostPort, context: ContextEnginePort) -> CheckerPort:
        return DeterministicChecker(tools, context)
