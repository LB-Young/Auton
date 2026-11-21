"""Verify multi-turn inputs against owned immutable predecessor checkpoints."""

from auton.agent.contracts import AgentRun
from auton.agent.ports import AgentRuntimePort
from auton.constitution.config import Principal
from auton.kernel.ports import ApplicationError
from auton.model.contracts import ModelMessage


async def conversation_ancestors(
    principal: Principal, run: AgentRun, agent: AgentRuntimePort
) -> tuple[AgentRun, ...]:
    refs = run.command.prior_runs
    if not refs and not run.command.prior_messages:
        return ()
    ancestors = []
    messages = []
    for index, ref in enumerate(refs):
        prior = await agent.get(principal, ref.id)
        if (
            prior.id == run.id
            or prior.version != ref.version
            or prior.status not in {"succeeded", "failed", "cancelled"}
            or prior.command.project_id != run.command.project_id
            or prior.command.workspace_id != run.command.workspace_id
            or prior.command.prior_runs != refs[:index]
        ):
            raise ApplicationError(
                409, "conversation_lineage_changed", "Predecessor checkpoint lineage changed"
            )
        ancestors.append(prior)
        messages.append(ModelMessage(role="user", content=prior.command.goal))
        if prior.final_text:
            messages.append(ModelMessage(role="assistant", content=prior.final_text))
    if tuple(messages) != run.command.prior_messages:
        raise ApplicationError(
            409,
            "conversation_history_unproven",
            "Historical messages need original run checkpoints",
        )
    return tuple(ancestors)
