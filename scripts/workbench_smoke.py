"""Opt-in native browser acceptance: public fixture, Laya, DeepSeek, service restart."""

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from dev import api_command, free_port, servers, stop
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main(reuse_completed: bool = False, assess: bool = False) -> None:
    root = ROOT / ".auton_local/workbench-smoke"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    api_port, web_port = free_port(), free_port()
    while api_port == web_port:
        web_port = free_port()
    base = f"http://127.0.0.1:{web_port}"
    text = (
        'profile = "dev"\nimplementation = "disabled"\n'
        f"allowed_origins = [{json.dumps(base)}]\n"
        '[constitution]\nremote_providers = ["deepseek"]\n'
    )
    for section, folder in [
        ("kernel", "events"),
        ("server", "server"),
        ("tools", "tools"),
        ("genome", "assets"),
        ("agent", "agent"),
        ("experience", "experience"),
        ("assess", "assess"),
        ("delegation", "delegation"),
    ]:
        field = "data_directory" if section == "kernel" else "directory"
        text += f"[{section}]\n{field} = {json.dumps(str(root / folder))}\n"
    config = root / "config.toml"
    config.write_text(text)
    config.chmod(0o600)
    env = {**os.environ, "AUTON_CONFIG": str(config)}
    with servers(api_port, web_port, env) as processes, sync_playwright() as driver:
        browser = driver.chromium.launch(channel=os.environ.get("AUTON_BROWSER_CHANNEL", "chrome"))
        try:
            state = root / "browser-state.json"
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                storage_state=str(state) if reuse_completed else None,
            )
            page = context.new_page()
            page.goto(base)
            expect(page.get_by_role("heading", name="开始一件值得完成的事")).to_be_visible()
            context.storage_state(path=str(state))
            state.chmod(0o600)
            record = page.get_by_label("真实任务执行记录")
            if reuse_completed:
                history = page.request.get(
                    base + "/api/v1/agent/history?project_id=browser-smoke&limit=20"
                ).json()
                completed = [run for run in history["items"] if run["status"] == "succeeded"]
                assert completed, "No completed native browser fixture is available"
                page.goto(base + "?view=agent&project=browser-smoke&run=" + completed[-1]["id"])
            else:
                headers = {"X-Auton-Client": "web", "Origin": base}
                assert page.request.post(
                    base + "/api/v1/projects",
                    headers=headers,
                    data={"id": "browser-smoke", "title": "Public native browser smoke"},
                ).ok
                assert page.request.post(
                    base + "/api/v1/tools/workspaces",
                    headers=headers,
                    data={
                        "id": "browser-smoke",
                        "title": "Public native browser smoke",
                        "read_only": False,
                    },
                ).ok
                page.reload()
                page.get_by_label("任务验收类型").select_option("file")
                page.get_by_label("真实任务目标").fill(
                    "Write the public fixture exactly, then report the tool outcome."
                )
                page.get_by_label("任务期望内容").fill("hello\n")
                page.get_by_label("确认任务、项目资料及工作区内容均可发送给所选远程模型").check()
                page.get_by_role("button", name="启动真实任务").click()
                print("Native browser task accepted; waiting for Laya/DeepSeek.", flush=True)
                record = page.get_by_label("真实任务执行记录")
                expect(record.get_by_role("status")).to_contain_text("等待审批", timeout=180000)
                record.get_by_role("button", name="批准本次任务操作").click()
                expect(record.get_by_role("status")).to_contain_text("验收通过", timeout=120000)
                assert "测试替身" not in record.get_by_role("status").inner_text()
            expect(record.get_by_role("status")).to_contain_text("验收通过", timeout=15000)
            run_id = page.evaluate('new URL(location.href).searchParams.get("run")')
            snapshot = page.request.get(base + f"/api/v1/agent/runs/{run_id}/snapshot").json()
            run = snapshot["run"]
            assert run["source"] == "runtime" and run["model_results"] and run["judgments"]
            assert all(result["source"] == "remote" for result in run["model_results"])
            assert all(not item["adopted"] for item in run["judgments"])
            receipt = next(item for item in run["receipts"] if item["artifact"])
            artifact = page.request.get(
                base + f"/api/v1/tools/operations/{receipt['operation_id']}/artifact"
            )
            assert artifact.ok and artifact.body() == b"hello\n"
            record.get_by_text("file.write · succeeded", exact=False).click()
            record.get_by_role("button", name="预览任务文件 notes.md").click()
            expect(page.get_by_label("真实产物预览")).to_contain_text("hello")
            output = ROOT / "test-results"
            output.mkdir(exist_ok=True)
            page.screenshot(path=str(output / "M12-native-preview.png"), full_page=True)
            page.keyboard.press("Escape")
            assessment_reports = []
            if assess:
                for semantic in (False, True):
                    response = page.request.post(
                        base + "/api/v1/assessment/jobs",
                        headers={"X-Auton-Client": "web", "Origin": base},
                        data={
                            "request_id": "native-assess-" + str(semantic) + "-" + run_id[:48],
                            "project_id": "browser-smoke",
                            "run_id": run_id,
                            "expected_version": run["version"],
                            "semantic": semantic,
                            "repeats": 2 if semantic else 1,
                        },
                        timeout=150000,
                    )
                    assert response.ok, response.text()
                    report = response.json()["report"]
                    assert report and report["source"] == "runtime"
                    assert not report["quality_release_eligible"]
                    if not semantic:
                        assert report["outcome"] == "pass"
                        if not reuse_completed:
                            assert report["environment_verified"]
                    else:
                        assert report["outcome"] == "unknown"
                        assert len(report["judges"]) == 2
                        assert all(j["source"] == "remote" for j in report["judges"])
                    assessment_reports.append(report)
                page.goto(base + "?view=assess")
                page.get_by_label("评测项目", exact=True).select_option("browser-smoke")
                expect(page.get_by_label("评测统计")).to_contain_text("真实运行：1")
                page.screenshot(path=str(output / "M13-native-assessment.png"), full_page=True)
                page.goto(base + "?view=agent&project=browser-smoke&run=" + run_id)
            saved_url = page.url
            before = page.request.get(base + "/api/v1/bootstrap").json()["identity"]["identity_id"]
            print("Native task passed; restarting only the isolated backend.", flush=True)
            stop(processes[0])
            processes.append(
                subprocess.Popen(api_command(api_port), cwd=ROOT, env=env, start_new_session=True)
            )
            deadline = time.monotonic() + 30
            while True:
                try:
                    with urlopen(
                        f"http://127.0.0.1:{api_port}/api/v1/health", timeout=1
                    ) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError):
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError("Isolated backend did not restart")
                time.sleep(0.2)
            page.goto(saved_url)
            expect(record.get_by_role("status")).to_contain_text("验收通过", timeout=15000)
            after = page.request.get(base + "/api/v1/bootstrap").json()["identity"]["identity_id"]
            assert before == after
            restored = page.request.get(base + f"/api/v1/agent/runs/{run_id}").json()
            assert restored["model_results"] == run["model_results"]
            assert restored["steps"] == run["steps"] and len(restored["receipts"]) == len(
                run["receipts"]
            )
            summary = {
                "run_id": run_id,
                "source": run["source"],
                "status": restored["status"],
                "steps": run["steps"],
                "tokens": run["tokens_used"],
                "cost_microusd": run["cost_microusd"],
                "models": [r["reported_model"] for r in run["model_results"]],
                "fingerprints": [r["system_fingerprint"] for r in run["model_results"]],
                "artifact_sha256": hashlib.sha256(artifact.body()).hexdigest(),
                "identity_preserved": before == after,
                "restart_reissued_model_calls": 0,
                "assessment_reports": assessment_reports,
            }
            (output / "workbench-native.json").write_text(json.dumps(summary, indent=2) + "\n")
            print(json.dumps(summary), flush=True)
        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reuse-completed",
        action="store_true",
        help="Inspect a completed fixture using private browser state; no new model calls",
    )
    parser.add_argument(
        "--assess",
        action="store_true",
        help="Also run independent checks and two real private-journal judge calls (API cost)",
    )
    args = parser.parse_args()
    main(args.reuse_completed, args.assess)
