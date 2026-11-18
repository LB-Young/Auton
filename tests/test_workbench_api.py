import pytest
from fastapi.testclient import TestClient
from test_agent import agent as agent
from test_agent import create
from test_context import USER
from test_context import context as context

from auton.agent.service import AgentRuntime
from auton.constitution.config import Principal
from auton.kernel.ports import ApplicationError
from auton.server.feedback import FeedbackCommand, FeedbackFactory


async def test_history_pages_search_and_more_than_100_runs(agent: AgentRuntime) -> None:
    expected = []
    for index in range(103):
        run = agent.runs.create(
            USER.owner,
            create(
                request_id=f"history-{index}",
                goal=f"Case {index:03} keyword" if index % 2 else f"Case {index:03} plain",
            ),
            "test",
        )
        run = run.model_copy(update={"session_id": agent.sessions.create(USER.owner, "project")})
        await agent.repo.save(USER.owner, run)
        expected.append(run.id)
    cursor = 0
    actual: list[str] = []
    while True:
        page = await agent.page(USER, "project", cursor, 13, "")
        actual.extend(item.id for item in page.items)
        if page.next_cursor is None:
            break
        assert page.next_cursor > cursor
        cursor = page.next_cursor
    assert actual == expected and len(set(actual)) == 103
    matches = await agent.page(USER, "project", 0, 20, "KEYWORD")
    assert len(matches.items) == 20 and all(
        "keyword" in item.command.goal for item in matches.items
    )
    assert not (await agent.page(USER, "project", 0, 20, "no matching task")).items
    with pytest.raises(ApplicationError):
        await agent.page(Principal(owner="other", role="user"), "project", 0, 10, "")
    with pytest.raises(ApplicationError):
        await agent.page(USER, "project", -1, 10, "")


async def test_feedback_is_checkpoint_bound_human_label_and_idempotent(agent: AgentRuntime) -> None:
    run = agent.runs.create(USER.owner, create(), "test").model_copy(
        update={"session_id": agent.sessions.create(USER.owner, "project")}
    )
    await agent.repo.save(USER.owner, run)
    feedback = FeedbackFactory().create(agent, agent.deps.events, agent.deps.runtime)
    command = FeedbackCommand(
        request_id="feedback-1",
        expected_goal_revision=1,
        checkpoint_version=0,
        rating="helpful",
        note="Useful structure, facts still need independent checking.",
    )
    first = await feedback.submit(USER, run.id, command)
    assert await feedback.submit(USER, run.id, command) == first
    assert not first.verified_quality and first.label_source == "human-feedback"
    stored = await agent.deps.events.lookup(first.event_id)
    assert stored and stored.event.payload["verified_quality"] is False
    assert stored.event.payload["checkpoint_event_id"] == first.checkpoint_event_id
    with pytest.raises(ApplicationError):
        await feedback.submit(USER, run.id, command.model_copy(update={"rating": "unhelpful"}))
    with pytest.raises(ApplicationError):
        await feedback.submit(
            USER,
            run.id,
            command.model_copy(
                update={"request_id": "wrong-revision", "expected_goal_revision": 2}
            ),
        )
    with pytest.raises(ApplicationError):
        await feedback.submit(USER.model_copy(update={"role": "runtime"}), run.id, command)
    with pytest.raises(ApplicationError):
        await feedback.submit(USER.model_copy(update={"owner": "other"}), run.id, command)


def test_history_and_feedback_http_validation(client: TestClient) -> None:
    client.post("/api/v1/projects", json={"id": "web", "title": "Web"})
    client.post("/api/v1/tools/workspaces", json={"id": "web", "title": "Web"})
    run = client.post(
        "/api/v1/agent/runs",
        json=create(project_id="web", workspace_id="web").model_dump(mode="json"),
    ).json()
    response = client.get("/api/v1/agent/history?project_id=web&limit=1")
    assert response.status_code == 200 and response.json()["items"][0]["id"] == run["id"]
    assert client.get("/api/v1/agent/history?project_id=web&after=-1").status_code == 422
    assert client.get("/api/v1/agent/history?project_id=web&limit=100").status_code == 422
    path = "/api/v1/agent/runs/" + run["id"] + "/feedback"
    body = dict(
        request_id="web-label", expected_goal_revision=1, checkpoint_version=0, rating="helpful"
    )
    receipt = client.post(path, json=body)
    assert receipt.status_code == 200 and receipt.json()["verified_quality"] is False
    assert client.post(path, json=body).json() == receipt.json()
    assert client.post(path, json={**body, "verified_quality": True}).status_code == 422
    client.cookies.clear()
    client.get("/api/v1/bootstrap")
    assert client.post(path, json=body).status_code == 404
    assert client.get("/api/v1/agent/history?project_id=web").status_code == 409


async def test_revised_goal_resumes_with_policy_alignment_and_rejects_old_approval(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_agent import command, generate, result, wait

    from auton.agent.contracts import RunCommand
    from auton.model.contracts import ModelRequest, ModelResult, ToolCall

    async def model(request: ModelRequest) -> ModelResult:
        return result(
            request,
            calls=(
                ToolCall(
                    id="write",
                    name="file_write",
                    arguments={"path": "notes.md", "content": "hello\n"},
                ),
            ),
        )

    generate(agent, monkeypatch, model)
    run = await agent.create(
        USER,
        create(
            acceptance={"kind": "file", "path": "notes.md", "sha256": "0" * 64},
            allowed_tools=["file.write"],
        ),
    )
    old = await wait(agent, run.id)
    assert old.status == "waiting_approval"
    revised = await command(
        agent, old, "revise", goal="First revision; do not use the old approval."
    )
    revised = await command(agent, revised, "revise", goal="Second revision while still paused.")
    assert revised.goal_revision == 3
    await command(agent, revised, "resume")
    current = await wait(agent, run.id)
    assert current.status == "waiting_approval" and current.goal_revision == 3
    with pytest.raises(ApplicationError):
        await agent.command(
            USER,
            run.id,
            RunCommand(
                request_id="late-old-approval",
                expected_goal_revision=1,
                expected_version=old.version,
                action="approve",
            ),
        )
    with pytest.raises(ApplicationError):
        await agent.deps.goals.synchronize_goal(
            USER.model_copy(update={"role": "runtime"}), "agent-goal-" + run.id, 4
        )
    with pytest.raises(ApplicationError):
        await agent.deps.goals.synchronize_goal(USER, "agent-goal-" + run.id, 1)
    await command(agent, current, "cancel")
    assert not (await agent.get(USER, run.id)).receipts
