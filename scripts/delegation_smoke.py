"""Opt-in real Laya/DeepSeek supervisor-worker and paired single-agent acceptance."""

import argparse
import hashlib
import json
import os
import time
from typing import Any

from dev import ROOT, free_port, servers
from playwright.sync_api import APIRequestContext, expect, sync_playwright


def main(reuse: bool) -> None:
    root = ROOT / ".auton_local/delegation-smoke"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    api_port, web_port = free_port(), free_port()
    while web_port == api_port:
        web_port = free_port()
    base = f"http://127.0.0.1:{web_port}"
    config = root / "config.toml"
    text = (
        'profile = "dev"\nimplementation = "disabled"\n'
        + f"allowed_origins = [{json.dumps(base)}]\n"
        + '[constitution]\nremote_providers = ["deepseek"]\n'
    )
    for section in (
        "server",
        "tools",
        "genome",
        "agent",
        "experience",
        "assess",
        "delegation",
        "kernel",
    ):
        field = "data_directory" if section == "kernel" else "directory"
        text += f"[{section}]\n{field} = {json.dumps(str(root / section))}\n"
    config.write_text(text)
    config.chmod(0o600)
    env = {**os.environ, "AUTON_CONFIG": str(config)}
    with servers(api_port, web_port, env), sync_playwright() as driver:
        browser = driver.chromium.launch(channel=os.environ.get("AUTON_BROWSER_CHANNEL", "chrome"))
        try:
            state = root / "browser-state.json"
            context = browser.new_context(
                storage_state=str(state) if reuse else None,
                viewport={"width": 1440, "height": 1000},
            )
            page = context.new_page()
            request: APIRequestContext = context.request
            request.get(base + "/api/v1/bootstrap")
            context.storage_state(path=str(state))
            state.chmod(0o600)
            headers = {"X-Auton-Client": "web", "Origin": base}
            catalog = request.get(base + "/api/v1/models").json()
            model_id = next(
                m["id"] for m in catalog if m["provider"] == "deepseek" and "flash" in m["id"]
            )

            def post(path: str, body: object) -> dict[str, Any]:
                response = request.post(
                    base + "/api/v1" + path, headers=headers, data=body, timeout=150000
                )
                assert response.ok, f"{path}: {response.status} {response.text()}"
                return response.json()  # type: ignore[no-any-return]

            pointer = root / "progress.json"
            if reuse:
                progress = json.loads(pointer.read_text())
                parent_id = progress["parent_id"]
            else:
                post(
                    "/projects", {"id": "delegation-smoke", "title": "Public delegation acceptance"}
                )
                post(
                    "/tools/workspaces",
                    {"id": "parent-output", "title": "Supervisor output", "read_only": False},
                )
                limits = request.get(base + "/api/v1/delegation/status").json()["host_limits"]
                goal = (
                    "Write exactly two hello lines with a final newline (hello\\nhello\\n) "
                    "to delivery.md. Report the tool outcome."
                )
                child_limits = {
                    **limits,
                    "max_steps": 3,
                    "max_tokens": 8000,
                    "max_tool_calls": 1,
                    "max_cost_microusd": 4000,
                }
                command = {
                    "request_id": "native-supervisor",
                    "project_id": "delegation-smoke",
                    "workspace_id": "parent-output",
                    "goal": goal,
                    "public": True,
                    "limits": limits,
                    "children": [
                        {
                            "id": key,
                            "role": "worker",
                            "goal": (
                                "Write exactly hello followed by one newline to notes.md, "
                                "then report the tool outcome."
                            ),
                            "model_id": model_id,
                            "limits": child_limits,
                            "allowed_tools": ["file.write"],
                            "acceptance": {
                                "kind": "file",
                                "path": "notes.md",
                                "sha256": hashlib.sha256(b"hello\n").hexdigest(),
                            },
                        }
                        for key in ("alpha", "beta")
                    ],
                    "merge_order": ["alpha", "beta"],
                    "separator": "",
                    "acceptance": {
                        "kind": "file",
                        "path": "delivery.md",
                        "sha256": hashlib.sha256(b"hello\nhello\n").hexdigest(),
                    },
                }
                parent = post("/delegation", command)
                parent_id = parent["id"]
                progress = {"parent_id": parent_id, "baseline_id": None}
                pointer.write_text(json.dumps(progress))
                pointer.chmod(0o600)
            deadline = time.monotonic() + 300
            while True:
                parent = request.get(base + f"/api/v1/delegation/{parent_id}").json()
                status = parent["status"]
                if status == "integrated":
                    break
                assert status not in {"blocked", "cancelled"}, parent["reason"]
                if status == "draft":
                    action = {"action": "start"}
                elif status == "waiting_approval":
                    assert "+hello" in parent["integration"]["preview"]
                    action = {"action": "approve_integration"}
                else:
                    child = next(
                        (c for c in parent["children"] if c["status"] == "waiting_approval"), None
                    )
                    if child:
                        assert "+hello" in child["pending_preview"]
                        action = {"action": "approve_child", "child_id": child["id"]}
                    else:
                        action = None
                if action:
                    body = {
                        "request_id": "native-" + str(parent["version"]),
                        "expected_version": parent["version"],
                        **action,
                    }
                    response = request.post(
                        base + f"/api/v1/delegation/{parent_id}/commands",
                        headers=headers,
                        data=body,
                    )
                    assert response.ok or (
                        response.status == 409
                        and response.json()["code"] == "delegation_version_changed"
                    ), response.text()
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "Native supervisor did not complete in bounded acceptance window"
                    )
                time.sleep(0.2)
            assert (
                parent["source"] == "runtime"
                and not parent["unknown_calls"]
                and not parent["unknown_tools"]
            )
            if not progress["baseline_id"]:
                post(
                    "/tools/workspaces",
                    {"id": "single-output", "title": "Single baseline", "read_only": False},
                )
                baseline = post(
                    "/agent/runs",
                    {
                        "request_id": "native-single-baseline",
                        "project_id": "delegation-smoke",
                        "workspace_id": "single-output",
                        "model_id": model_id,
                        "goal": parent["command"]["goal"],
                        "allowed_tools": ["file.write"],
                        "data_domain": "public",
                        "acceptance": parent["command"]["acceptance"],
                        "limits": parent["command"]["limits"],
                        "asset_snapshot_id": parent["input_snapshot_id"],
                    },
                )
                progress["baseline_id"] = baseline["id"]
                pointer.write_text(json.dumps(progress))
            baseline_id = progress["baseline_id"]
            deadline = time.monotonic() + 180
            while True:
                baseline = request.get(base + f"/api/v1/agent/runs/{baseline_id}").json()
                if baseline["status"] == "succeeded":
                    break
                assert baseline["status"] not in {"blocked", "failed", "cancelled"}, baseline[
                    "reason"
                ]
                if baseline["status"] == "waiting_approval":
                    post(
                        f"/agent/runs/{baseline_id}/commands",
                        {
                            "request_id": "native-baseline-approve",
                            "expected_goal_revision": baseline["goal_revision"],
                            "expected_version": baseline["version"],
                            "action": "approve",
                        },
                    )
                if time.monotonic() >= deadline:
                    raise RuntimeError("Native single baseline did not finish")
                time.sleep(0.2)
            contrast = post(
                f"/delegation/{parent_id}/contrast",
                {
                    "request_id": "native-paired-contrast",
                    "baseline_run_id": baseline_id,
                    "expected_version": baseline["version"],
                },
            )
            assert contrast["comparable"] and not contrast["improvement_established"], contrast
            for run_id in [baseline_id, *[c["run_id"] for c in parent["children"]]]:
                run = request.get(base + f"/api/v1/agent/runs/{run_id}").json()
                assert all(r["source"] == "remote" for r in run["model_results"])
                assert run["judgments"] and all(not j["adopted"] for j in run["judgments"])
            artifact = request.get(
                base
                + "/api/v1/tools/operations/"
                + parent["integration_receipt"]["operation_id"]
                + "/artifact"
            )
            assert artifact.body() == b"hello\nhello\n"
            page.goto(base + "?view=delegation")
            expect(
                page.get_by_label("父任务状态").get_by_role("heading", name="父目标验收通过")
            ).to_be_visible()
            page.get_by_label("单 Agent 基线运行 ID", exact=True).fill(baseline_id)
            page.get_by_role("button", name="比较单多 Agent", exact=True).click()
            expect(page.get_by_text("同条件单次对照 · 真实运行", exact=True)).to_be_visible()
            output = ROOT / "test-results"
            output.mkdir(exist_ok=True)
            page.get_by_role("heading", name="多 Agent", exact=True).scroll_into_view_if_needed()
            page.screenshot(path=str(output / "M14-native.png"), full_page=True)
            summary = {
                "comparison": contrast,
                "parent_tool_calls": parent["total_tool_calls"],
                "artifact_sha256": hashlib.sha256(artifact.body()).hexdigest(),
            }
            (output / "delegation-native.json").write_text(json.dumps(summary, indent=2) + "\n")
            print(json.dumps(summary), flush=True)
        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reuse-completed",
        action="store_true",
        help="Reuse owned tasks/results; no repeated model calls",
    )
    main(parser.parse_args().reuse_completed)
