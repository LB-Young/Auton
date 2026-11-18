import hashlib

from auton.constitution.config import Principal
from auton.delegation.contracts import DelegationView
from auton.kernel.ports import ApplicationError
from auton.tools.contracts import ToolRequest
from auton.tools.ports import ToolHostPort


class ResultIntegrator:
    def __init__(self, tools: ToolHostPort) -> None:
        self.tools = tools

    async def content(
        self, principal: Principal, parent: DelegationView, receipts: dict[str, str]
    ) -> str:
        fragments: list[str] = []
        for child_id in parent.command.merge_order:
            spec = next(c for c in parent.command.children if c.id == child_id)
            operation = receipts.get(child_id)
            if operation is None:
                raise ApplicationError(
                    409, "integration_missing_fragment", "A verified fragment is missing"
                )
            _, data = await self.tools.artifact(principal, operation)
            if hashlib.sha256(data).hexdigest() != spec.acceptance.sha256:
                raise ApplicationError(
                    409,
                    "integration_fragment_changed",
                    "Child output no longer matches its contract",
                )
            fragments.append(data.decode("utf-8"))
        text = parent.command.separator.join(fragments)
        if len(text.encode()) > 131072:
            raise ApplicationError(
                413, "integration_size_limit", "Integration exceeds bounded UTF-8 artifact limit"
            )
        if hashlib.sha256(text.encode()).hexdigest() != parent.command.acceptance.sha256:
            raise ApplicationError(
                409,
                "integration_parent_acceptance_failed",
                "Children passed but assembled output fails parent acceptance",
            )
        return text

    async def request(
        self, principal: Principal, parent: DelegationView, receipts: dict[str, str]
    ) -> ToolRequest:
        text = await self.content(principal, parent, receipts)
        workspace = await self.tools.workspace(principal, parent.command.workspace_id)
        return ToolRequest(
            operation_id="merge-" + parent.id[:56],
            principal=principal.model_copy(update={"role": "runtime"}),
            workspace_id=workspace.id,
            goal_id=workspace.goal_id,
            goal_revision=workspace.revision,
            tool="file.write",
            arguments={
                "path": parent.command.acceptance.path,
                "content": text,
                "expected_sha256": parent.command.expected_previous_sha256,
            },
        )


class ResultIntegratorFactory:
    def create(self, tools: ToolHostPort) -> ResultIntegrator:
        return ResultIntegrator(tools)
