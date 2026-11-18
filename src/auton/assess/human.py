"""Human preference provenance is retained without converting preference into gold."""

import hashlib

from auton.agent.contracts import AgentRun
from auton.assess.contracts import Signal
from auton.constitution.config import Principal
from auton.kernel.events import EventScope, StoredEvent
from auton.kernel.storage import EventLogPort


async def human_signals(
    principal: Principal, run: AgentRun, source: StoredEvent, events: EventLogPort
) -> tuple[Signal, ...]:
    signals: list[Signal] = []
    cursor = 0
    for _ in range(50):
        rows = await events.read(
            after=cursor,
            limit=200,
            scope=EventScope.model_validate(
                {"project_id": run.command.project_id, "run_id": run.id}
            ),
        )
        for row in rows:
            cursor = row.cursor
            payload = row.event.payload
            command = payload.get("command")
            if row.event.kind != "agent.user_feedback" or not isinstance(command, dict):
                continue
            request_id = command.get("request_id")
            if not isinstance(request_id, str):
                continue
            expected_id = (
                "user-feedback:"
                + hashlib.sha256((principal.owner + "\0" + request_id).encode()).hexdigest()
            )
            if (
                row.event.event_id != expected_id
                or payload.get("checkpoint_event_id") != source.event.event_id
                or payload.get("run_id") != run.id
                or payload.get("label_source") != "human-feedback"
                or payload.get("verified_quality") is not False
                or command.get("expected_goal_revision") != run.goal_revision
                or command.get("checkpoint_version") != run.version
                or command.get("category") not in {"delivery", "approval"}
                or command.get("rating") not in {"helpful", "unhelpful"}
            ):
                continue
            signals.append(
                Signal(
                    name="user_preference",
                    source="human",
                    verdict="unknown",
                    evidence=(row.event.event_id,),
                    reason=(
                        f"{command['category']}:{command['rating']}; preference_is_not_quality_gold"
                    ),
                )
            )
        if len(rows) < 200:
            return tuple(signals)
    signals.append(
        Signal(
            name="human_history",
            source="human",
            verdict="unknown",
            reason="feedback_history_scan_limit",
        )
    )
    return tuple(signals)
