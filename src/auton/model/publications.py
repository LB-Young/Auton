"""Owner-scoped, goal-sticky runtime pointers and separate offline evaluation grants."""

import hashlib
from collections.abc import Awaitable, Callable
from pathlib import Path

from auton.constitution.config import Principal
from auton.kernel.documents import VersionedDocumentStore, digest, key
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.kernel.storage import EventLogPort
from auton.model.config import ModelSpec
from auton.model.contracts import Contract
from auton.model.publication_contracts import (
    ModelActivation,
    ModelAssignment,
    ModelProfile,
    input_language,
)


class PublicationStoreConfig(Contract):
    directory: Path
    max_documents: int = 10000

    @property
    def digest(self) -> str:
        return digest({"schema": "model-publications-v1"})


class ModelPublications:
    def __init__(
        self,
        directory: Path,
        events: EventLogPort,
        runtime: RuntimeDependencies,
        enabled: bool = True,
        test_source: bool = False,
    ) -> None:
        self.events, self.enabled, self.test_source = events, enabled, test_source
        self.store = VersionedDocumentStore(
            PublicationStoreConfig(directory=directory),
            events,
            runtime,
            test_source,
            "model_publications",
        )
        self.profiles: dict[tuple[str, str], ModelProfile] = {}
        self.assignments: dict[tuple[str, str], ModelAssignment] = {}
        self.guard: Callable[[Principal, str], Awaitable[None]] | None = None

    def bind_guard(self, guard: Callable[[Principal, str], Awaitable[None]]) -> None:
        self.guard = guard

    async def start(self) -> None:
        if not self.enabled:
            return
        await self.store.start()
        owners = [
            str(r[0]) for r in self.store.database().execute("SELECT DISTINCT owner FROM heads")
        ]
        for owner in owners:
            for value in await self.store.list("profile", owner):
                profile = ModelProfile.model_validate(value)
                self.profiles[(owner, profile.project_id)] = profile
            for value in await self.store.list("assignment", owner):
                assignment = ModelAssignment.model_validate(value)
                self.assignments[(owner, assignment.goal_id)] = assignment

    async def close(self) -> None:
        self.profiles.clear()
        self.assignments.clear()
        await self.store.close()

    def visible(self, owner: str, model_id: str) -> bool:
        return any(
            o == owner
            and any(
                r.target.id == model_id and r.status in {"active", "paused", "evaluation"}
                for r in p.releases.values()
            )
            for (o, _), p in self.profiles.items()
        )

    def activation(self, principal: Principal, assignment: ModelAssignment) -> ModelActivation:
        profile = self.profiles.get((principal.owner, assignment.project_id))
        record = profile.releases.get(assignment.release_id or "") if profile else None
        if record is None or record.status == "revoked" or record.target.id != assignment.model_id:
            raise ApplicationError(
                409, "model_release_revoked", "Pinned model release is no longer usable"
            )
        if record.status == "evaluation" and assignment.purpose != "evaluation":
            raise ApplicationError(
                409, "model_evaluation_only", "Unapproved models have no production assignment"
            )
        return record

    def authorize(
        self,
        principal: Principal,
        model_id: str,
        goal: str,
        spec: ModelSpec | None = None,
        goal_text: str | None = None,
        data_domain: str | None = None,
    ) -> None:
        assigned = self.assignments.get((principal.owner, goal))
        if assigned is None or assigned.model_id != model_id:
            raise ApplicationError(409, "model_release_scope", "No exact owned goal assignment")
        record = self.activation(principal, assigned)
        if spec is not None and spec != record.target:
            raise ApplicationError(
                409,
                "model_deployment_changed",
                "Configured deployment differs from approved bundle",
            )
        if goal_text is not None and input_language(goal_text) not in record.languages:
            raise ApplicationError(
                409,
                "model_language_outside_scope",
                "Current goal language is outside approved scope",
            )
        if data_domain is not None and data_domain not in record.data_domains:
            raise ApplicationError(
                403, "model_data_outside_scope", "Current data domain is outside approved scope"
            )

    async def validate(
        self,
        principal: Principal,
        model_id: str,
        goal: str,
        spec: ModelSpec,
        goal_text: str | None = None,
        data_domain: str | None = None,
    ) -> None:
        self.authorize(principal, model_id, goal, spec, goal_text, data_domain)
        if self.guard is None:
            raise ApplicationError(
                503,
                "model_source_guard_unavailable",
                "Independent release source guard is required",
            )
        await self.guard(principal, self.assignments[(principal.owner, goal)].release_id or "")

    async def resolve(
        self,
        principal: Principal,
        project: str,
        goal: str,
        requested: str,
        creation_digest: str = "",
        goal_text: str = "",
        data_domain: str = "local-only",
    ) -> str:
        if not self.enabled:
            if requested == "project_default":
                raise ApplicationError(
                    409, "model_profile_missing", "No approved project executor profile"
                )
            return requested
        assignment_id = key(principal.owner, "assignment:" + goal)
        saved = await self.store.get("assignment", principal.owner, assignment_id)
        if saved:
            existing = ModelAssignment.model_validate(saved)
            if existing.project_id != project or existing.creation_digest != creation_digest:
                raise ApplicationError(
                    409, "model_goal_assignment_conflict", "Goal creation input is immutable"
                )
            self.assignments[(principal.owner, goal)] = existing
            return existing.model_id
        profile = self.profiles.get((principal.owner, project))
        current = profile.releases.get(profile.current or "") if profile else None
        if requested != "project_default" and (current is None or current.target.id != requested):
            return requested
        if current is None:
            raise ApplicationError(
                409, "model_profile_missing", "No approved project executor profile"
            )
        fraction = (
            int(
                hashlib.sha256(
                    (principal.owner + "\0" + project + "\0" + goal).encode()
                ).hexdigest()[:8],
                16,
            )
            % 100
        )
        in_scope = (
            input_language(goal_text) in current.languages and data_domain in current.data_domains
        )
        chosen = (
            current.target.id
            if current.status == "active" and in_scope and fraction < current.percentage
            else current.baseline_model_id
        )
        if requested != "project_default" and chosen != requested:
            raise ApplicationError(
                409, "model_outside_canary", "Goal is outside the active approved cohort"
            )
        assert profile is not None
        bound = next(
            (
                r
                for r in reversed(tuple(profile.releases.values()))
                if r.target.id == chosen and r.status in {"active", "paused"}
            ),
            None,
        )
        assignment = ModelAssignment(
            id=assignment_id,
            project_id=project,
            goal_id=goal,
            model_id=chosen,
            release_id=bound.release_id if bound else None,
            creation_digest=creation_digest,
        )
        await self.store.put(
            "assignment", principal.owner, assignment_id, assignment.model_dump(mode="json"), None
        )
        self.assignments[(principal.owner, goal)] = assignment
        return chosen

    async def grant_evaluation(
        self, principal: Principal, project: str, goal: str, model_id: str, creation_digest: str
    ) -> None:
        if principal.role != "user":
            raise ApplicationError(
                403, "release_user_required", "Only users authorize isolated evaluation"
            )
        profile = self.profiles.get((principal.owner, project))
        record = (
            next(
                (
                    r
                    for r in reversed(tuple(profile.releases.values()))
                    if r.target.id == model_id and r.status == "evaluation"
                ),
                None,
            )
            if profile
            else None
        )
        if record is None:
            return
        approval = await self.events.lookup(record.approval_event_id)
        if approval is None or approval.event.kind != "release.validation_authorized":
            raise ApplicationError(
                409, "model_validation_grant_missing", "Frozen offline validation grant required"
            )
        identity = key(principal.owner, "assignment:" + goal)
        assignment = ModelAssignment(
            id=identity,
            project_id=project,
            goal_id=goal,
            model_id=model_id,
            release_id=record.release_id,
            creation_digest=creation_digest,
            purpose="evaluation",
        )
        old = await self.store.get("assignment", principal.owner, identity)
        if old and ModelAssignment.model_validate(old) != assignment:
            raise ApplicationError(
                409, "model_goal_assignment_conflict", "Evaluation goal scope changed"
            )
        if old is None:
            await self.store.put(
                "assignment", principal.owner, identity, assignment.model_dump(mode="json"), None
            )
        self.assignments[(principal.owner, goal)] = assignment

    async def profile(self, principal: Principal, project: str) -> ModelProfile | None:
        if not self.enabled:
            return None
        value = await self.store.get(
            "profile", principal.owner, key(principal.owner, "profile:" + project)
        )
        if value is None:
            return None
        record = ModelProfile.model_validate(value)
        self.profiles[(principal.owner, project)] = record
        return record

    async def activate(
        self, principal: Principal, command: ModelActivation, expected: int | None
    ) -> ModelProfile:
        if principal.role != "user" or not self.enabled:
            raise ApplicationError(
                403, "release_writer_required", "Configured approved release writer required"
            )
        approval = await self.events.lookup(command.approval_event_id)
        kind = (
            "release.validation_authorized"
            if command.status == "evaluation"
            else "release.approved"
        )
        if (
            approval is None
            or approval.event.kind != kind
            or approval.event.source != ("test" if self.test_source else "runtime")
            or approval.event.scope.project_id != command.project_id
            or approval.event.payload.get("release_id") != command.release_id
            or approval.event.payload.get("owner_key") != key(principal.owner, "release-owner")
            or approval.event.payload.get("target_digest")
            != digest(command.target.model_dump(mode="json"))
            or approval.event.payload.get("percentage") != command.percentage
            or approval.event.payload.get("baseline_model_id") != command.baseline_model_id
            or approval.event.payload.get("languages") != list(command.languages)
            or approval.event.payload.get("data_domains") != list(command.data_domains)
        ):
            raise ApplicationError(
                409, "release_approval_missing", "Exact owned model approval receipt required"
            )
        identity = key(principal.owner, "profile:" + command.project_id)
        value = await self.store.get("profile", principal.owner, identity)
        old = ModelProfile.model_validate(value) if value else None
        if old:
            self.profiles[(principal.owner, command.project_id)] = old
            if old.releases.get(command.release_id) == command:
                return old
        if (old.version if old else None) != expected:
            raise ApplicationError(
                409, "model_profile_changed", "Refresh project pointer before activation"
            )
        result = ModelProfile(
            id=identity,
            version=old.version + 1 if old else 0,
            project_id=command.project_id,
            current=old.current
            if command.status == "evaluation" and old
            else None
            if command.status == "evaluation"
            else command.release_id,
            releases={**(old.releases if old else {}), command.release_id: command},
        )
        await self.store.put(
            "profile", principal.owner, identity, result.model_dump(mode="json"), expected
        )
        self.profiles[(principal.owner, command.project_id)] = result
        return result

    async def control(
        self, principal: Principal, project: str, release: str, action: str, expected: int
    ) -> ModelProfile:
        if principal.role != "user":
            raise ApplicationError(
                403, "release_user_required", "Only user release control may change deployment"
            )
        identity = key(principal.owner, "profile:" + project)
        value = await self.store.get("profile", principal.owner, identity)
        old = ModelProfile.model_validate(value) if value else None
        status = "paused" if action == "pause" else "revoked"
        if (
            old
            and release in old.releases
            and old.releases[release].status == status
            and old.version in {expected, expected + 1}
        ):
            self.profiles[(principal.owner, project)] = old
            return old
        if old is None or old.version != expected or release not in old.releases:
            raise ApplicationError(409, "model_profile_changed", "Project model pointer changed")
        current = old.releases[release]
        result = old.model_copy(
            update={
                "version": old.version + 1,
                "releases": {
                    **old.releases,
                    release: current.model_copy(update={"status": status}),
                },
            }
        )
        await self.store.put(
            "profile", principal.owner, identity, result.model_dump(mode="json"), old.version
        )
        self.profiles[(principal.owner, project)] = result
        return result
