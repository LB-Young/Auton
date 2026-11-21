import httpx

from auton.constitution.config import Principal
from auton.genome.contracts import AssetReleaseState
from auton.kernel.ports import ApplicationError
from auton.model.publication_contracts import ModelActivation, ModelProfile
from auton.release.contracts import ReleaseRecord
from auton.release.dependencies import ReleaseDependencies
from auton.release.sources import ReleaseSource


class GenomeReleaseBackend:
    def __init__(self, deps: ReleaseDependencies) -> None:
        self.deps = deps

    async def activate(
        self, principal: Principal, record: ReleaseRecord, source: ReleaseSource
    ) -> int:
        if source.asset_command is None or not record.approval_event_id:
            raise ApplicationError(
                409, "release_asset_manifest_missing", "Frozen asset approval required"
            )
        command = source.asset_command.model_copy(
            update={"release_id": record.id, "approval_event_id": record.approval_event_id}
        )
        result = await self.deps.genome_writer.release_asset(principal, command)
        return result.version

    async def control(
        self, principal: Principal, record: ReleaseRecord, action: str
    ) -> AssetReleaseState:
        return await self.deps.genome_writer.control_release_asset(
            principal, record.command.project_id, record.id, action, record.effect_version or 0
        )


class ModelReleaseBackend:
    def __init__(self, deps: ReleaseDependencies) -> None:
        self.deps = deps

    async def warm(self, source: ReleaseSource) -> None:
        spec = source.model
        if spec is None or not spec.endpoint:
            raise ApplicationError(
                409, "release_runtime_missing", "Configure an immutable local deployment"
            )
        if spec.local_secret_reference is None:
            raise ApplicationError(
                503,
                "release_runtime_credential_missing",
                "Dedicated local runtime credential required",
            )
        token = self.deps.local_runtime_secrets.get(spec.local_secret_reference)
        try:
            async with httpx.AsyncClient(
                timeout=10, follow_redirects=False, trust_env=False
            ) as client:
                response = await client.get(
                    spec.endpoint + "/auton/manifest",
                    headers={"Authorization": "Bearer " + token.get_secret_value()},
                )
        except httpx.HTTPError as error:
            raise ApplicationError(
                503, "release_warmup_failed", "Local runtime warmup failed"
            ) from error
        if response.status_code != 200 or len(response.content) > 20000:
            raise ApplicationError(
                503, "release_warmup_failed", "Local deployment is not prewarmed"
            )
        try:
            observed = response.json()
            if not isinstance(observed, dict):
                raise ValueError()
        except ValueError as error:
            raise ApplicationError(
                503, "release_warmup_failed", "Runtime manifest is invalid"
            ) from error
        expected = {
            "model_id": spec.id,
            "bundle_id": spec.declared_revision,
            "adapter_sha256": spec.adapter_revision,
            "base_revision": spec.base_revision,
            "base_manifest_digest": spec.base_manifest_digest,
            "template_revision": spec.template_revision,
            "runtime_revision": spec.runtime_revision,
            "quantization": spec.quantization,
            "fingerprint": spec.expected_fingerprint,
        }
        if (
            any(observed.get(k) != v for k, v in expected.items())
            or observed.get("ready") is not True
        ):
            raise ApplicationError(
                409,
                "release_runtime_manifest_mismatch",
                "Loaded runtime does not match the approved artifact",
            )

    async def activate(
        self,
        principal: Principal,
        record: ReleaseRecord,
        source: ReleaseSource,
        validation: bool = False,
    ) -> int:
        if source.model is None:
            raise ApplicationError(409, "release_runtime_missing", "No local model target")
        await self.warm(source)
        old = await self.deps.models_writer.profile(principal, record.command.project_id)
        command = ModelActivation(
            release_id=record.id,
            project_id=record.command.project_id,
            target=source.model,
            baseline_model_id=record.command.baseline_model_id,
            percentage=100 if validation else record.command.percentage,
            status="evaluation" if validation else "active",
            approval_event_id=(
                record.validation_event_id if validation else record.approval_event_id
            )
            or "missing",
            languages=("zh", "en", "mixed", "other")
            if validation
            else record.command.scope.languages,
            data_domains=("public", "local-only")
            if validation
            else record.command.scope.data_domains,
        )
        result = await self.deps.models_writer.activate(
            principal, command, old.version if old else None
        )
        return result.version

    async def control(
        self, principal: Principal, record: ReleaseRecord, action: str
    ) -> ModelProfile:
        return await self.deps.models_writer.control(
            principal, record.command.project_id, record.id, action, record.effect_version or 0
        )


class GenomeReleaseFactory:
    def create(self, deps: ReleaseDependencies) -> GenomeReleaseBackend:
        return GenomeReleaseBackend(deps)


class ModelReleaseFactory:
    def create(self, deps: ReleaseDependencies) -> ModelReleaseBackend:
        return ModelReleaseBackend(deps)
