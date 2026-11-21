"""Release control tests use explicit synthetic receipts, never real quality evidence."""

import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_genome import EVOLUTION, USER, asset, publish
from test_genome import genome as genome

from auton.constitution.config import Principal
from auton.genome.contracts import AssetReleaseCommand
from auton.genome.service import GenomeService
from auton.kernel.config import KernelConfig
from auton.kernel.documents import VersionedDocumentStore, digest, key
from auton.kernel.events import Event, EventScope
from auton.kernel.factory import EventLogFactory
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.model.config import ModelSpec
from auton.model.contracts import ModelMessage, ModelRequest, ToolSpec
from auton.model.local_provider import LocalRuntimeProvider
from auton.model.publication_contracts import ModelActivation
from auton.model.publications import ModelPublications
from auton.model.runtime_worker import parse_output, verified_files
from auton.release.contracts import (
    ReleaseApproval,
    ReleaseConfig,
    ReleaseControl,
    ReleaseEvidence,
    ReleasePlanCommand,
    ReleaseScope,
)
from auton.release.service import Releases
from auton.release.sources import ReleaseSource


def local_spec() -> ModelSpec:
    return ModelSpec(
        id="local-candidate",
        provider="local",
        location="local",
        declared_revision="a" * 64,
        adapter_revision="b" * 64,
        base_revision="c" * 40,
        base_manifest_digest="d" * 64,
        template_revision="e" * 64,
        runtime_revision="auton-hf-json-v1",
        quantization="none",
        revision_is_pinned=True,
        endpoint="http://127.0.0.1:8091",
        local_secret_reference="AUTON_LOCAL_MODEL_TEST",
        expected_fingerprint="f" * 64,
    )


async def receipt(events: Any, deps: RuntimeDependencies, command: ModelActivation) -> None:
    await events.append(
        [
            Event(
                event_id=command.approval_event_id,
                kind="release.validation_authorized"
                if command.status == "evaluation"
                else "release.approved",
                source="test",
                timestamp=deps.now(),
                scope=EventScope(project_id=command.project_id),
                payload={
                    "owner_key": key(USER.owner, "release-owner"),
                    "release_id": command.release_id,
                    "target_digest": digest(command.target.model_dump(mode="json")),
                    "percentage": command.percentage,
                    "baseline_model_id": command.baseline_model_id,
                    "languages": list(command.languages),
                    "data_domains": list(command.data_domains),
                },
            )
        ]
    )


async def test_model_runtime_sticky_restart_scope_pause_revoke_and_independent_grants(
    tmp_path: Path,
    deps: RuntimeDependencies,
) -> None:
    events = EventLogFactory().create(KernelConfig(backend="memory"))
    await events.start()
    pub = ModelPublications(tmp_path / "pub", events, deps, test_source=True)
    await pub.start()
    spec = local_spec()
    activation = ModelActivation(
        release_id="release",
        project_id="project",
        target=spec,
        baseline_model_id="deepseek-v4-pro",
        percentage=5,
        approval_event_id="approval",
        languages=("en",),
        data_domains=("public",),
    )
    with pytest.raises(ApplicationError, match="approval"):
        await pub.activate(USER, activation, None)
    await receipt(events, deps, activation)
    with pytest.raises(ApplicationError):
        await pub.activate(USER, activation.model_copy(update={"percentage": 100}), None)
    profile = await pub.activate(USER, activation, None)
    assert (await pub.activate(USER, activation, None)) == profile  # lost acknowledgement
    selected = []
    for i in range(100):
        chosen = await pub.resolve(
            USER, "project", f"goal-{i}", "project_default", str(i), "Hello", "public"
        )
        if chosen == spec.id:
            selected.append(i)
    assert 0 < len(selected) < 20
    i = selected[0]
    pub.authorize(USER, spec.id, f"goal-{i}", spec, "Hello", "public")
    with pytest.raises(ApplicationError):
        pub.authorize(Principal(owner="other", role="runtime"), spec.id, f"goal-{i}")
    assert (
        await pub.resolve(USER, "project", "private", "project_default", "x", "Hello", "local-only")
        == "deepseek-v4-pro"
    )
    paused = await pub.control(USER, "project", "release", "pause", profile.version)
    assert (
        await pub.resolve(USER, "project", "new", "project_default", "new", "Hello", "public")
        == "deepseek-v4-pro"
    )
    assert (
        await pub.resolve(
            USER, "project", f"goal-{i}", "project_default", str(i), "Hello", "public"
        )
        == spec.id
    )
    await pub.close()
    pub = ModelPublications(tmp_path / "pub", events, deps, test_source=True)
    await pub.start()
    pub.authorize(USER, spec.id, f"goal-{i}", spec)
    await pub.control(USER, "project", "release", "rollback", paused.version)
    with pytest.raises(ApplicationError, match="Pinned"):
        pub.authorize(USER, spec.id, f"goal-{i}")
    await pub.close()
    await events.close()


async def test_evaluation_never_switches_default_and_exact_goal_grant_required(
    tmp_path: Path,
    deps: RuntimeDependencies,
) -> None:
    events = EventLogFactory().create(KernelConfig(backend="memory"))
    await events.start()
    pub = ModelPublications(tmp_path / "pub", events, deps, test_source=True)
    await pub.start()
    spec = local_spec()
    activation = ModelActivation(
        release_id="eval",
        project_id="project",
        target=spec,
        baseline_model_id="deepseek-v4-pro",
        percentage=100,
        status="evaluation",
        approval_event_id="eval-receipt",
    )
    await receipt(events, deps, activation)
    profile = await pub.activate(USER, activation, None)
    assert profile.current is None
    with pytest.raises(ApplicationError):
        await pub.resolve(USER, "project", "ordinary", "project_default", "x", "Hi", "public")
    with pytest.raises(ApplicationError):
        pub.authorize(USER, spec.id, "ordinary")
    await pub.grant_evaluation(USER, "project", "eval-goal", spec.id, "original")
    assert await pub.resolve(USER, "project", "eval-goal", spec.id, "original") == spec.id
    with pytest.raises(ApplicationError):
        await pub.resolve(USER, "project", "eval-goal", spec.id, "changed")
    with pytest.raises(ApplicationError):
        await pub.validate(USER, spec.id, "eval-goal", spec)
    calls = []

    async def guard(principal: Principal, identity: str) -> None:
        calls.append(identity)
        raise ApplicationError(409, "source_withdrawn", "Source withdrawn")

    pub.bind_guard(guard)
    with pytest.raises(ApplicationError, match="withdrawn"):
        await pub.validate(USER, spec.id, "eval-goal", spec)
    assert calls == ["eval"]
    await pub.close()
    await events.close()


@pytest.mark.parametrize("percentage,lost_ack", [(5, False), (100, False), (100, True)])
async def test_real_asset_rollout_overlay_scope_stickiness_pause_and_rollback(
    genome: GenomeService,
    percentage: int,
    lost_ack: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def synthetic_guard(principal: Principal, identity: str) -> None:
        assert identity == "test-release"

    genome.bind_release_guard(synthetic_guard)
    revision = await publish(genome, asset())
    # A baseline goal created before deployment stays on baseline even at 100%.
    baseline = await genome.resolve_for_goal(USER, "project", "before", "Hello", "public")
    candidate = asset(
        "candidate", "replacement", origin="inferred", source="evolution-proposal:test"
    )
    state = await genome.propose(
        EVOLUTION, "project", candidate, (await genome.view(USER, "project")).candidates_revision
    )
    command = AssetReleaseCommand(
        release_id="test-release",
        project_id="project",
        asset_id="notes",
        candidate_id=candidate.id,
        candidates_revision=state.candidates_revision or "",
        expected_revision=revision,
        content_sha256=hashlib.sha256(candidate.content.encode()).hexdigest(),
        percentage=percentage,
        approval_event_id="asset-approval",
        languages=("en",),
        data_domains=("public",),
    )
    with pytest.raises(ApplicationError):
        await genome.release_asset(USER, command)
    await genome.deps.events.append(
        [
            Event(
                event_id="asset-approval",
                kind="release.approved",
                source="runtime",
                timestamp=genome.deps.runtime.now(),
                scope=EventScope(project_id="project"),
                payload={
                    "owner_key": key(USER.owner, "release-owner"),
                    "release_id": command.release_id,
                    "candidate_sha256": command.content_sha256,
                    "target_digest": digest(
                        {"candidate_sha256": command.content_sha256, "asset_id": command.asset_id}
                    ),
                    "percentage": percentage,
                    "languages": ["en"],
                    "data_domains": ["public"],
                },
            )
        ]
    )
    if lost_ack:
        original_put = genome.resolver.profiles.put

        async def fail_once(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("synthetic lost acknowledgement after Git write")

        monkeypatch.setattr(genome.resolver.profiles, "put", fail_once)
        with pytest.raises(RuntimeError, match="lost acknowledgement"):
            await genome.release_asset(USER, command)
        monkeypatch.setattr(genome.resolver.profiles, "put", original_put)
    released = await genome.release_asset(USER, command)
    assert await genome.release_asset(USER, command) == released
    assert (await genome.resolve_for_goal(USER, "project", "before", "Hello", "public")).assets[
        0
    ].content == baseline.assets[0].content
    assert (
        await genome.resolve_for_goal(USER, "project", "private", "Hello", "local-only")
    ).assets[0].content == "first"
    chosen = []
    for i in range(100):
        snapshot = await genome.resolve_for_goal(USER, "project", f"g-{i}", "Hello", "public")
        if snapshot.release_ids:
            chosen.append(snapshot)
    assert chosen and (len(chosen) == 100 if percentage == 100 else len(chosen) < 20)
    paused = await genome.control_release_asset(USER, "project", released.id, "pause", 0)
    assert (
        await genome.resolve_for_goal(USER, "project", "after-pause", "Hello", "public")
    ).assets[0].content == "first"
    # Paused goals keep pinned candidate until explicit rollback.
    assert (await genome.snapshot(USER, "project", chosen[0].id)).assets[0].content == "replacement"
    if lost_ack:
        await publish(genome, asset(content="subsequent human edit"))
        with pytest.raises(ApplicationError, match="subsequent human"):
            await genome.control_release_asset(
                USER, "project", released.id, "rollback", paused.version
            )
        assert (await genome.resolve(USER, "project")).assets[0].content == "subsequent human edit"
        return
    revoked = await genome.control_release_asset(
        USER, "project", released.id, "rollback", paused.version
    )
    assert (
        await genome.control_release_asset(USER, "project", released.id, "rollback", paused.version)
        == revoked
    )
    with pytest.raises(ApplicationError, match="Pinned"):
        await genome.snapshot(USER, "project", chosen[0].id)
    assert (await genome.resolve(USER, "project")).assets[0].content == "first"


async def test_local_protocol_auth_exact_tokens_and_changed_fingerprint() -> None:
    class Secrets:
        def get(self, name: str) -> SecretStr:
            assert name == "AUTON_LOCAL_MODEL_TEST"
            return SecretStr("dedicated-local-token")

    provider = LocalRuntimeProvider(SimpleNamespace(), Secrets())
    spec = local_spec()
    request = ModelRequest(
        model_id=spec.id,
        request_id="request",
        principal=USER,
        goal_id="goal",
        messages=(ModelMessage(role="user", content="Hello"),),
    )

    def handler(r: httpx.Request) -> httpx.Response:
        assert r.headers["authorization"] == "Bearer dedicated-local-token"
        return httpx.Response(
            200,
            json={
                "tokens": 7,
                "request_digest": request.digest,
                "fingerprint": spec.expected_fingerprint,
            },
        )

    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert (await provider.count(request, spec))[0] == 7
    await provider.client.aclose()
    provider.client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"fingerprint": "changed"})
        )
    )
    with pytest.raises(ApplicationError, match="fingerprint"):
        await provider.count(request, spec)
    await provider.client.aclose()


def test_deployment_parser_and_file_manifest_fail_closed(tmp_path: Path) -> None:
    request = ModelRequest(
        model_id="local",
        request_id="r",
        principal=USER,
        goal_id="g",
        messages=(ModelMessage(role="user", content="Hello"),),
        tools=(ToolSpec(name="file_read", parameters={"type": "object"}),),
    )
    output = parse_output('<tool_call>{"name":"file_read","arguments":{}}</tool_call>', request)
    assert output["tool_calls"][0]["name"] == "file_read"
    with pytest.raises(ValueError):
        parse_output('<tool_call>{"name":"process_run","arguments":{}}</tool_call>', request)
    with pytest.raises(ValueError):
        parse_output("<tool_call>{", request)
    with pytest.raises(ValueError):
        parse_output(
            '<tool_call>{"name":"file_read","arguments":{}}</tool_call><tool_call>{', request
        )
    (tmp_path / "file").write_text("base")
    verified_files(tmp_path, {"file": hashlib.sha256(b"base").hexdigest()})
    (tmp_path / "file").write_text("replaced")
    with pytest.raises(ValueError, match="digest"):
        verified_files(tmp_path, {"file": hashlib.sha256(b"base").hexdigest()})


async def test_independent_approval_current_report_and_no_auto_publish(
    tmp_path: Path, deps: RuntimeDependencies
) -> None:
    events = EventLogFactory().create(KernelConfig(backend="memory"))
    await events.start()
    config = ReleaseConfig(directory=tmp_path / "release")
    source = ReleaseSource("a" * 64, "b" * 64, (), artifact_identity="artifact")

    class Sources:
        async def read(self, *args: Any) -> ReleaseSource:
            return source

    class Policy:
        async def evaluate(self, *args: Any) -> ReleaseEvidence:
            return ReleaseEvidence(
                source_digest=source.digest,
                target_digest=source.target_digest,
                evidence_digest=source.digest,
                eligible=True,
                blockers=(),
            )

    class Backend:
        calls = 0

        async def activate(self, *args: Any) -> int:
            self.calls += 1
            return 0

    backend = Backend()
    service = Releases(
        config,
        cast(Any, SimpleNamespace(events=events, runtime=deps, test_source=True)),
        VersionedDocumentStore(config, events, deps, True, "release"),
        cast(Any, Sources()),
        cast(Any, Policy()),
        cast(Any, backend),
        cast(Any, backend),
    )
    await service.start()
    command = ReleasePlanCommand(
        request_id="plan",
        project_id="project",
        kind="genome",
        source_id="c" * 64,
        mode="active",
        percentage=100,
    )
    record = await service.plan(USER, command)
    assert backend.calls == 0 and record.status == "ready"
    approval = ReleaseApproval(
        request_id="approve",
        expected_version=0,
        expected_evidence_digest=record.report.evidence_digest,
    )
    with pytest.raises(ApplicationError):
        await service.approve(USER, record.id, approval)
    approved = await service.approve(
        USER, record.id, approval.model_copy(update={"risks_reviewed": True})
    )
    assert backend.calls == 0
    source = replace(source, digest="d" * 64)
    with pytest.raises(ApplicationError):
        await service.control(
            USER,
            record.id,
            ReleaseControl(
                request_id="activate", expected_version=approved.version, action="activate"
            ),
        )
    assert backend.calls == 0
    await service.close()
    await events.close()


def test_api_missing_artifact_never_activates_and_owner_scope(client: TestClient) -> None:
    assert client.get("/api/v1/releases/status").json()["auto_approval"] is False
    result = client.post(
        "/api/v1/releases",
        json={
            "request_id": "missing",
            "project_id": "missing",
            "kind": "executor_model",
            "source_id": "a" * 64,
        },
    )
    assert result.status_code in {403, 404, 409}
    assert (
        client.post(
            "/api/v1/releases/" + "a" * 64 + "/commands",
            json={"request_id": "activate", "expected_version": 0, "action": "activate"},
        ).status_code
        == 404
    )


async def test_rollout_policy_counts_connected_origins_and_requires_exact_deployment() -> None:
    from auton.release.policy import RolloutPolicy

    spec = local_spec()
    reports: dict[str, Any] = {}
    runs: dict[str, Any] = {}
    cases = [
        SimpleNamespace(id=f"case-{i}", family=f"family-{i}", origin_group="shared", split="test")
        for i in range(40)
    ]
    windows = []
    candidate_ids: list[str] = []
    baseline_ids: list[str] = []
    for i, case in enumerate(cases):
        for prefix in ("candidate", "baseline"):
            identity = hashlib.sha256(f"{prefix}-{i}".encode()).hexdigest()
            (candidate_ids if prefix == "candidate" else baseline_ids).append(identity)
            report = SimpleNamespace(
                id=identity,
                project_id="project",
                split="test",
                source="runtime",
                current_evidence_valid=True,
                quality_release_eligible=True,
                outcome="pass",
                signals=(),
                metrics=SimpleNamespace(
                    usage_complete=True, model_latency_ms=10 if prefix == "candidate" else 20
                ),
                run_id=identity,
                candidate_revision=prefix,
                bank_revision="bank",
                case_id=case.id,
                family=case.family,
                groups=("domain:general",),
                environment_verified=True,
                model_dump=lambda **kwargs: {"synthetic_fixture": True},
            )
            reports[identity] = report
            runs[identity] = SimpleNamespace(
                executor_spec={
                    **spec.model_dump(),
                    "id": spec.id if prefix == "candidate" else "deepseek-v4-pro",
                },
                model_results=(SimpleNamespace(system_fingerprint=spec.expected_fingerprint),),
                command=SimpleNamespace(
                    goal="Hello",
                    data_domain="public",
                    allowed_tools=(),
                    acceptance="same",
                    boundaries=(),
                ),
                input_asset_snapshot_id="same",
                budget_limits={},
                receipts=(),
            )
            windows.append(
                SimpleNamespace(
                    window=SimpleNamespace(
                        id=identity, purpose="release", candidate_revision=prefix
                    ),
                    current=True,
                    used=1,
                )
            )

    class Assess:
        async def windows(self, *args: Any) -> Any:
            return windows

        async def bank(self, *args: Any) -> Any:
            return SimpleNamespace(revision="bank", cases=cases)

        async def report(self, principal: Any, identity: str) -> Any:
            return reports[identity]

        async def job(self, principal: Any, identity: str) -> Any:
            return SimpleNamespace(command=SimpleNamespace(window_id=identity))

    class Agent:
        async def get(self, principal: Any, identity: str) -> Any:
            return runs[identity]

    policy = RolloutPolicy(
        ReleaseConfig(), cast(Any, SimpleNamespace(assess=Assess(), agent=Agent()))
    )
    command = ReleasePlanCommand(
        request_id="quality",
        project_id="project",
        kind="executor_model",
        source_id=spec.declared_revision,
        target_model_id=spec.id,
        mode="canary",
        percentage=5,
        report_ids=tuple(candidate_ids),
        baseline_report_ids=tuple(baseline_ids),
        scope=ReleaseScope(domains=("general",), languages=("en",), data_domains=("public",)),
    )
    source = ReleaseSource("a" * 64, "b" * 64, (), model=spec)
    first = await policy.evaluate(USER, command, source)
    assert first.independent_families == 1 and not first.eligible
    for i, case in enumerate(cases):
        case.origin_group = f"origin-{i}"
    independent = await policy.evaluate(USER, command, source)
    assert independent.independent_families == 40 and independent.eligible, independent.blockers
    runs[candidate_ids[0]].model_results = (SimpleNamespace(system_fingerprint="changed"),)
    rejected = await policy.evaluate(USER, command, source)
    assert "evaluated_deployment_does_not_match_bundle" in rejected.blockers


async def test_runtime_warmup_failure_never_touches_pointer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from auton.release.adapters import ModelReleaseBackend

    class Secrets:
        def get(self, name: str) -> SecretStr:
            assert name == "AUTON_LOCAL_MODEL_TEST"
            return SecretStr("local-only-test-credential")

    original = httpx.AsyncClient
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        assert request.headers["authorization"] == "Bearer local-only-test-credential"
        return httpx.Response(200, json={"ready": False})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    backend = ModelReleaseBackend(cast(Any, SimpleNamespace(local_runtime_secrets=Secrets())))
    with pytest.raises(ApplicationError, match="Loaded runtime"):
        await backend.warm(ReleaseSource("a" * 64, "b" * 64, (), model=local_spec()))
    assert requests == ["/auton/manifest"]
