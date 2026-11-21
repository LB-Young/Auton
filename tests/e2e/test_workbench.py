"""Real HTTP/WebSocket browser acceptance, orchestrated by Python."""

import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

pytestmark = pytest.mark.browser
BASE = os.environ.get("AUTON_BASE_URL", "http://127.0.0.1:5173")
EVIDENCE = Path(os.environ.get("AUTON_EVIDENCE_DIR", "test-results"))


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as driver:
        channel = os.environ.get("AUTON_BROWSER_CHANNEL")
        browser = driver.chromium.launch(channel=channel)
        yield browser
        browser.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(BASE + "?view=chat")
    expect(page.get_by_role("textbox", name="任务输入")).to_be_enabled()
    yield page
    context.close()
    assert not errors, errors


def screenshot(page: Page, name: str) -> None:
    # Commit responsive layout/compositor frames before capturing resized views.
    page.evaluate(
        "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(EVIDENCE / name), full_page=True, animations="disabled")


def test_desktop_stream_stop_artifact_reload_and_theme(page: Page) -> None:
    expect(page.get_by_role("heading", name="今天，想一起完成什么？")).to_be_visible()
    screenshot(page, "desktop-home.png")
    page.get_by_role("button", name=re.compile("^新对话")).click()
    text = page.get_by_role("textbox", name="任务输入")
    text.fill("先验证停止生成")
    page.get_by_role("button", name="发送消息").click()
    expect(page.get_by_role("button", name="停止生成", exact=True)).to_be_visible()
    expect(page.locator(".message.assistant")).to_contain_text("这是一次框架演示")
    page.get_by_role("button", name="停止生成", exact=True).click()
    expect(page.locator(".message-footnote")).to_contain_text("已停止")
    expect(page.get_by_role("button", name="发送消息")).to_be_visible()
    text.fill("帮我梳理一个模块化项目的开发顺序")
    text.press("Enter")
    panel = page.get_by_role("complementary", name="产物面板")
    expect(panel.get_by_role("heading", name="项目起步笔记", exact=True, level=2)).to_be_visible(
        timeout=15000
    )
    expect(panel).to_contain_text("没有写入工作目录或发布")
    screenshot(page, "desktop-conversation.png")
    page.reload()
    expect(page.locator(".message.user")).to_have_count(2)
    expect(page.locator(".message.assistant")).to_have_count(2)
    expect(panel).to_be_visible()
    page.get_by_role("button", name="切换深色主题").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    screenshot(page, "desktop-dark.png")
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")


def test_narrow_screen_navigation_and_artifact(page: Page) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.reload()
    expect(page.get_by_role("textbox", name="任务输入")).to_be_enabled()
    expect(page.get_by_role("button", name="展开导航")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    screenshot(page, "mobile-home.png")
    page.get_by_role("button", name="展开导航").click()
    page.get_by_role("button", name=re.compile("^学习")).click()
    expect(page.get_by_role("heading", name="数据集与谱系", exact=True)).to_be_visible()
    expect(page.get_by_text("暂无数据快照。", exact=True)).to_be_visible()
    page.get_by_role("button", name="展开导航").click()
    page.get_by_role("button", name="演示对话 · Demo", exact=True).click()
    text = page.get_by_role("textbox", name="任务输入")
    text.fill("移动端演示")
    page.get_by_role("button", name="发送消息").click()
    panel = page.get_by_role("complementary", name="产物面板")
    expect(panel).to_contain_text("项目起步笔记", timeout=15000)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    screenshot(page, "mobile-artifact.png")
    page.get_by_role("button", name="关闭产物面板").click()
    expect(text).to_be_visible()


def test_ime_and_send_error_preserve_draft(page: Page) -> None:
    text = page.get_by_role("textbox", name="任务输入")
    text.fill("中文输入法候选确认")
    text.dispatch_event("keydown", {"key": "Enter", "code": "Enter", "isComposing": True})
    expect(page.locator(".message.user")).to_have_count(0)
    page.route("**/api/v1/sessions/*/messages", lambda route: route.abort())
    page.get_by_role("button", name="发送消息").click()
    expect(page.get_by_role("alert")).to_be_visible()
    expect(text).to_have_value("中文输入法候选确认")
    page.unroute("**/api/v1/sessions/*/messages")
    page.get_by_role("button", name="发送消息").click()
    expect(page.locator(".message.user")).to_have_count(1)
    expect(page.get_by_role("button", name="停止生成", exact=True)).to_be_visible()
    page.reload()
    expect(page.locator(".message.user")).to_have_count(1)
    expect(page.get_by_role("complementary", name="产物面板")).to_contain_text(
        "项目起步笔记", timeout=15000
    )


def test_persistent_kernel_is_distinct_from_demo_chat_storage(page: Page) -> None:
    page.get_by_role("button", name="设置与连接").click()
    expect(page.get_by_role("heading", name="设置与连接")).to_be_visible()
    expect(
        page.locator(".settings-card")
        .filter(has=page.get_by_role("heading", name="连接状态"))
        .locator("dl")
    ).to_contain_text("SQLite · WAL/FULL")
    expect(
        page.locator(".settings-card")
        .filter(has=page.get_by_role("heading", name="连接状态"))
        .locator("dl")
    ).to_contain_text("仅内存 · 重启服务后清空")
    screenshot(page, "M02-storage-settings.png")


def test_policy_settings_do_not_expose_credentials(page: Page) -> None:
    page.get_by_role("button", name="设置与连接").click()
    expect(page.get_by_role("heading", name="权限与预算")).to_be_visible()
    expect(
        page.locator(".settings-card").filter(has=page.get_by_role("heading", name="权限与预算"))
    ).to_contain_text("未授权外发")
    expect(
        page.locator(".settings-card").filter(has=page.get_by_role("heading", name="权限与预算"))
    ).to_contain_text("100,000")
    expect(
        page.locator(".settings-card").filter(has=page.get_by_role("heading", name="权限与预算"))
    ).to_contain_text("$5.00")
    page.get_by_role("button", name="检查私密数据外发").click()
    expect(page.get_by_role("status")).to_contain_text("禁止执行")
    page.get_by_role("button", name="检查工具写入").click()
    expect(page.get_by_role("status")).to_contain_text("需要批准")
    screenshot(page, "M03-policy-settings.png")


def test_model_catalog_probe_and_mobile_layout(page: Page) -> None:
    page.get_by_role("button", name=re.compile("^模型")).click()
    expect(page.get_by_role("heading", name="模型", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="fixture-model")).to_be_visible()
    expect(page.get_by_text("测试替身 · 无真实推理", exact=True)).to_be_visible()
    page.get_by_role("button", name="检测 fixture-model").click()
    expect(page.get_by_role("status")).to_contain_text("测试响应")
    expect(page.get_by_role("status")).to_contain_text("输入 10 / 输出 5")
    screenshot(page, "M04-models.png")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    screenshot(page, "M04-models-mobile.png")


def test_local_judgment_preview_records_source_without_adopting(page: Page) -> None:
    page.get_by_role("button", name=re.compile("^模型")).click()
    expect(page.get_by_role("heading", name="本地判断 · Laya")).to_be_visible()
    page.get_by_label("待判断任务").fill("把一份软件需求拆成开发步骤")
    page.get_by_role("button", name="预览本地判断").click()
    result = page.locator(".judgment-result")
    expect(result).to_contain_text("测试判断")
    expect(result).to_contain_text("未采用")
    expect(result).to_contain_text("输入截止点 0 · 目标修订 1")
    expect(result).to_contain_text("信息充分性")
    page.get_by_role("heading", name="本地判断 · Laya").scroll_into_view_if_needed()
    screenshot(page, "M05-judgment.png")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    screenshot(page, "M05-judgment-mobile.png")


def test_real_tools_review_approval_write_read_download_and_mcp(page: Page) -> None:
    page.get_by_role("button", name=re.compile("^工具")).click()
    expect(page.get_by_role("heading", name="工具", exact=True)).to_be_visible()
    page.get_by_label("允许新工作区申请写入与固定进程操作").check()
    page.get_by_role("button", name="创建工具工作区").click()
    expect(page.get_by_label("工具工作区")).not_to_have_value("")
    page.get_by_label("工具输入内容").fill("# browser artifact\n")
    page.get_by_role("button", name="准备并预览").click()
    expect(page.get_by_role("heading", name="操作预览")).to_be_visible()
    expect(page.locator(".tool-output")).to_contain_text("+# browser artifact")
    expect(page.get_by_role("button", name="执行已批准操作")).to_be_disabled()
    screenshot(page, "M06-approval.png")
    page.get_by_role("button", name="批准本次操作").click()
    page.get_by_role("button", name="执行已批准操作").click()
    result = page.get_by_role("status")
    expect(result).to_contain_text("操作成功")
    expect(result).to_contain_text("notes.md")
    with page.expect_download() as download:
        page.get_by_role("link", name="下载已验证文件").click()
    assert Path(download.value.path()).read_text() == "# browser artifact\n"
    screenshot(page, "M06-receipt.png")
    page.get_by_label("选择工具").select_option("file.read")
    page.get_by_role("button", name="准备并预览").click()
    page.get_by_role("button", name="执行只读操作").click()
    expect(page.get_by_role("status")).to_contain_text("# browser artifact")
    page.get_by_label("选择工具").select_option("mcp.sha256")
    page.get_by_label("工具输入内容").fill("hello")
    page.get_by_role("button", name="准备并预览").click()
    page.get_by_role("button", name="执行只读操作").click()
    expect(page.get_by_role("status")).to_contain_text("2cf24dba5fb0a30e")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    screenshot(page, "M06-mobile.png")


def test_git_assets_candidates_snapshot_history_and_revocation(page: Page) -> None:
    page.get_by_role("button", name=re.compile("^资产")).click()
    expect(page.get_by_role("heading", name="资产", exact=True)).to_be_visible()
    page.get_by_label("资产项目 ID", exact=True).fill("browser-project")
    page.get_by_label("资产项目名称").fill("浏览器资产项目")
    page.get_by_label("资产项目说明").fill("仅使用本项目资料")
    page.get_by_role("button", name="创建资产项目").click()
    expect(page.get_by_role("heading", name="学习候选")).to_be_visible()
    page.get_by_label("资产候选内容").fill("用户明确要求所有报告用中文。")
    page.get_by_role("button", name="保存到学习候选").click()
    expect(page.get_by_role("button", name="晋升 项目笔记")).to_be_visible()
    screenshot(page, "M07-candidate.png")
    page.get_by_role("button", name="晋升 项目笔记").click()
    expect(page.get_by_role("button", name="历史 项目笔记")).to_be_visible()
    page.get_by_role("button", name="生成使用快照").click()
    expect(page.get_by_role("status")).to_contain_text("1 个项目资产")
    page.get_by_role("button", name="历史 项目笔记").click()
    expect(page.get_by_role("heading", name="资产历史")).to_be_visible()
    page.get_by_role("heading", name="资产历史").scroll_into_view_if_needed()
    screenshot(page, "M07-history.png")
    page.get_by_role("button", name="撤回 项目笔记 及派生引用").click()
    expect(page.get_by_text("当前没有可用的正式资产")).to_be_visible()
    page.get_by_role("button", name="生成使用快照").click()
    expect(page.get_by_role("status")).to_contain_text("0 个项目资产")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    screenshot(page, "M07-mobile.png")


def test_context_budget_sources_compression_and_mobile(page: Page) -> None:
    page.get_by_role("button", name=re.compile("^资产")).click()
    page.get_by_label("资产项目 ID", exact=True).fill("context-browser")
    page.get_by_label("资产项目名称").fill("上下文验证项目")
    page.get_by_label("资产项目说明").fill("保持项目边界")
    page.get_by_role("button", name="创建资产项目").click()
    page.get_by_label("资产候选内容").fill("上下文预算应保留用户最新目标，资料不能授予管理员权限。")
    page.get_by_role("button", name="保存到学习候选").click()
    page.get_by_role("button", name="晋升 项目笔记").click()
    expect(page.get_by_role("button", name="历史 项目笔记")).to_be_visible()
    page.get_by_role("button", name=re.compile("^上下文")).click()
    page.get_by_label("上下文目标").fill("检查上下文预算")
    page.get_by_label("上下文边界").fill("不得删除文件")
    page.get_by_role("button", name="装配上下文", exact=True).click()
    result = page.locator(".context-result")
    expect(result).to_contain_text("上下文已就绪")
    expect(result).to_contain_text("测试计数 · 非真实 tokenizer")
    expect(result).to_contain_text("未修改 checkpoint")
    expect(result).to_contain_text("不可信证据")
    page.get_by_role("heading", name="上下文已就绪").scroll_into_view_if_needed()
    screenshot(page, "M08-sources.png")
    page.get_by_label("上下文历史").fill(
        "\n".join("旧轮次" + str(i) + " x" * 250 for i in range(25))
    )
    page.get_by_role("button", name="装配上下文", exact=True).click()
    expect(result).to_contain_text("上下文已就绪")
    expect(result).not_to_contain_text("移除 0 个完整旧轮次")
    expect(result).to_contain_text("排除 1 个证据块")
    page.get_by_text("高级视图：完整输入与版本", exact=True).click()
    expect(result).to_contain_text("不得删除文件")
    page.get_by_role("button", name="重新校验快照").click()
    expect(result).to_contain_text("上下文已就绪")
    page.get_by_text("高级视图：完整输入与版本", exact=True).click()
    page.get_by_role("heading", name="上下文已就绪").scroll_into_view_if_needed()
    screenshot(page, "M08-context.png")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    screenshot(page, "M08-context-mobile.png")
    page.get_by_label("上下文目标").fill("新修订")
    expect(page.locator(".context-result")).to_have_count(0)


def test_agent_research_and_approved_file_delivery(page: Page) -> None:
    page.get_by_role("button", name=re.compile("^资产")).click()
    page.get_by_label("资产项目 ID", exact=True).fill("agent-browser")
    page.get_by_label("资产项目名称").fill("Agent 验收项目")
    page.get_by_role("button", name="创建资产项目").click()
    page.get_by_label("资产候选内容").fill(
        "Context retrieval preserves provenance and project boundaries."
    )
    page.get_by_role("button", name="保存到学习候选").click()
    page.get_by_role("button", name="晋升 项目笔记").click()
    expect(page.get_by_role("button", name="历史 项目笔记")).to_be_visible()
    page.get_by_role("button", name=re.compile("^工具")).click()
    page.get_by_label("允许新工作区申请写入与固定进程操作").check()
    page.get_by_role("button", name="创建工具工作区").click()
    expect(page.get_by_label("工具工作区")).not_to_have_value("")
    page.locator(".workspace-nav").get_by_role("button", name=re.compile("^任务")).click()
    page.get_by_label("真实任务目标").fill("Research context retrieval and provenance.")
    page.get_by_role("button", name="启动真实任务").click()
    record = page.get_by_label("真实任务执行记录")
    expect(record.get_by_role("status")).to_contain_text("验收通过", timeout=15000)
    expect(record.get_by_role("status")).to_contain_text("测试替身")
    expect(record).to_contain_text("retrieval-citations-v1")
    with page.expect_download() as report:
        record.get_by_role("link", name="下载任务报告").click()
    assert "[asset:notes]" in Path(report.value.path()).read_text()
    record.get_by_role("heading", name="执行记录").scroll_into_view_if_needed()
    screenshot(page, "M09-research.png")
    open_task_settings(page)
    page.get_by_label("任务验收类型").select_option("file")
    page.get_by_label("真实任务目标").fill("Create a precise UTF-8 text file.")
    page.get_by_label("任务期望内容").fill("hello\n")
    page.get_by_role("button", name="启动真实任务").click()
    expect(record.get_by_role("status")).to_contain_text("等待审批", timeout=15000)
    expect(record.locator(".tool-output").first).to_contain_text("+hello")
    screenshot(page, "M09-approval.png")
    record.get_by_role("button", name="暂停任务").click()
    expect(record.get_by_role("status")).to_contain_text("已暂停", timeout=15000)
    trace = record.get_by_label("任务轨迹与恢复")
    expect(trace.get_by_role("button", name="从已核对检查点恢复")).to_be_enabled(timeout=15000)
    trace.evaluate("el => el.scrollIntoView({block: 'start'})")
    screenshot(page, "M10-recovery.png")
    trace.get_by_role("button", name="从已核对检查点恢复").click()
    expect(record.get_by_role("status")).to_contain_text("等待审批", timeout=15000)
    expect(record.get_by_role("link", name="下载任务文件 notes.md")).to_have_count(0)
    page.reload()
    page.locator(".workspace-nav").get_by_role("button", name=re.compile("^任务")).click()
    page.get_by_role("button", name=re.compile("^打开任务 Create a precise")).click()
    expect(record.get_by_role("status")).to_contain_text("等待审批", timeout=15000)
    screenshot(page, "M11-reconnected-approval.png")
    record.get_by_role("button", name="批准本次任务操作").click()
    expect(record.get_by_role("status")).to_contain_text("验收通过", timeout=15000)
    expect(record).to_contain_text("file-sha256-v1")
    record.get_by_text(re.compile("file.write · succeeded")).click()
    with page.expect_download() as artifact:
        record.get_by_role("link", name="下载任务文件 notes.md").click()
    assert Path(artifact.value.path()).read_text() == "hello\n"
    record.get_by_role("heading", name="执行记录").scroll_into_view_if_needed()
    screenshot(page, "M09-file.png")
    expect(trace).to_contain_text("投影已追平", timeout=15000)
    expect(trace.get_by_role("button", name="从已核对检查点恢复")).to_be_disabled()
    trace.get_by_text("展开事件时间线", exact=True).click()
    expect(trace).to_contain_text("model.completed")
    trace.evaluate("el => el.scrollIntoView({block: 'start'})")
    screenshot(page, "M10-timeline.png")
    page.reload()
    page.locator(".workspace-nav").get_by_role("button", name=re.compile("^任务")).click()
    page.get_by_role("button", name=re.compile("^打开任务 Create a precise")).click()
    expect(page.get_by_label("真实任务执行记录")).to_contain_text("file-sha256-v1")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.get_by_label("真实任务执行记录").get_by_role(
        "heading", name="执行记录"
    ).scroll_into_view_if_needed()
    screenshot(page, "M09-mobile.png")
    mobile_trace = page.get_by_label("任务轨迹与恢复")
    expect(mobile_trace).to_contain_text("投影已追平", timeout=15000)
    mobile_trace.evaluate("el => el.scrollIntoView({block: 'start'})")
    screenshot(page, "M10-mobile.png")


def test_server_upload_candidate_and_identity(page: Page) -> None:
    page.get_by_role("button", name=re.compile("^资产")).click()
    page.get_by_label("资产项目 ID").fill("server-upload")
    page.get_by_role("button", name="创建资产项目").click()
    page.get_by_label("上传项目文本").set_input_files(
        {
            "name": "upload.md",
            "mimeType": "text/markdown",
            "buffer": b"# Imported notes\nRead before promotion.\n",
        }
    )
    expect(page.get_by_role("button", name="晋升 upload.md")).to_be_visible(timeout=15000)
    expect(page.get_by_role("button", name="历史 upload.md")).to_have_count(0)
    page.get_by_role("button", name="晋升 upload.md").scroll_into_view_if_needed()
    screenshot(page, "M11-upload-candidate.png")
    page.reload()
    page.get_by_role("button", name=re.compile("^资产")).click()
    page.get_by_label("选择资产项目").select_option("server-upload")
    expect(page.get_by_role("button", name="晋升 upload.md")).to_be_visible()
    # UI does not promote uploaded material implicitly, even after reloading.
    page.get_by_role("button", name="晋升 upload.md").click()
    expect(page.get_by_role("button", name="历史 upload.md")).to_be_visible()
    page.get_by_role("button", name=re.compile("^设置")).click()
    expect(page.get_by_text("本机身份：", exact=False)).to_be_visible()
    screenshot(page, "M11-identity.png")


def seed_workbench(page: Page, identity: str) -> None:
    headers = {"X-Auton-Client": "web", "Origin": BASE}
    project = page.request.post(
        BASE + "/api/v1/projects", headers=headers, data={"id": identity, "title": identity}
    )
    assert project.ok
    assert page.request.post(
        BASE + "/api/v1/tools/workspaces",
        headers=headers,
        data={"id": identity, "title": identity, "read_only": False},
    ).ok
    candidate = page.request.post(
        BASE + f"/api/v1/projects/{identity}/candidates",
        headers=headers,
        data={
            "expected": None,
            "asset": {
                "id": "notes",
                "name": "Notes",
                "kind": "document",
                "origin": "user_explicit",
                "source": "browser fixture",
                "content": "Context retrieval preserves provenance and project boundaries.",
            },
        },
    ).json()
    assert page.request.post(
        BASE + f"/api/v1/projects/{identity}/assets/notes/promote",
        headers=headers,
        data={
            "expected": candidate["revision"],
            "candidates_revision": candidate["candidates_revision"],
        },
    ).ok


def create_workbench_run(page: Page, project: str, goal: str, request: str) -> dict[str, object]:
    response = page.request.post(
        BASE + "/api/v1/agent/runs",
        headers={"X-Auton-Client": "web", "Origin": BASE},
        data={
            "request_id": request,
            "project_id": project,
            "workspace_id": project,
            "model_id": "fixture-model",
            "goal": goal,
            "allowed_tools": ["file.read"],
            "acceptance": {"kind": "research"},
        },
    )
    assert response.ok
    return response.json()  # type: ignore[no-any-return]


def open_task_settings(page: Page) -> None:
    toggle = page.locator(".task-settings-toggle")
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()
    expect(page.get_by_label("任务项目")).to_be_visible()


def test_new_task_composer_without_setup_and_draft_navigation(page: Page) -> None:
    page.goto(BASE)
    goal = page.get_by_label("真实任务目标")
    expect(goal).to_be_focused()
    expect(goal).to_be_in_viewport()
    expect(goal).to_be_enabled()
    goal.fill("先写任务目标，再配置项目和工作区。")
    expect(page.get_by_role("button", name="启动真实任务")).to_be_enabled()
    expect(page.get_by_label("任务项目")).not_to_be_visible()
    expect(page.get_by_label("任务工作区")).not_to_be_visible()
    expect(page.get_by_label("任务模型")).not_to_be_visible()
    screenshot(page, "new-task-chat-desktop.png")
    goal.press("Enter")
    expect(page.get_by_role("alert")).to_contain_text("尚未发送：请先在任务设置中配置项目、工作区")
    expect(page.get_by_label("任务项目")).to_be_visible()
    expect(goal).to_have_value("先写任务目标，再配置项目和工作区。")
    page.locator(".task-settings-toggle").click()
    page.get_by_role("button", name="启动真实任务").click()
    expect(page.get_by_label("任务工作区")).to_be_visible()
    expect(page.get_by_label("真实任务执行记录")).to_have_count(0)
    open_task_settings(page)
    page.get_by_role("button", name="创建项目与添加资料", exact=True).click()
    expect(page).to_have_url(re.compile(r"view=genome"))
    page.get_by_role("button", name=re.compile("^任务 已接入")).click()
    expect(goal).to_have_value("先写任务目标，再配置项目和工作区。")
    open_task_settings(page)
    page.get_by_role("button", name="创建工作区", exact=True).click()
    expect(page).to_have_url(re.compile(r"view=tools"))
    page.get_by_role("button", name="新任务", exact=False).click()
    expect(goal).to_be_focused()
    expect(goal).to_have_value("")
    expect(page.get_by_role("alert")).to_have_count(0)
    goal.fill("新的目标可以直接输入")
    page.set_viewport_size({"width": 390, "height": 844})
    goal.focus()
    expect(goal).to_be_in_viewport()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    screenshot(page, "new-task-composer-mobile.png")


def test_new_task_resets_content_boundaries_and_public_consent(page: Page) -> None:
    seed_workbench(page, "composer-reset")
    page.goto(BASE)
    goal = page.get_by_label("真实任务目标")
    expect(page.get_by_label("任务项目")).to_have_value("composer-reset")
    expect(page.get_by_label("任务工作区")).to_have_value("composer-reset")
    goal.fill("上一条任务")
    open_task_settings(page)
    page.get_by_text("任务边界（可选）", exact=True).click()
    page.get_by_label("真实任务边界").fill("上一条边界")
    open_task_settings(page)
    page.get_by_label("任务验收类型").select_option("file")
    page.get_by_label("任务目标路径").fill("old.txt")
    page.get_by_label("任务期望内容").fill("old content")
    consent = page.get_by_role(
        "checkbox", name="确认任务、项目资料及工作区内容均可发送给所选远程模型"
    )
    consent.check()
    selected_model = page.get_by_label("任务模型").input_value()
    page.get_by_role("button", name="新任务", exact=False).click()
    expect(goal).to_be_focused()
    expect(goal).to_have_value("")
    expect(page.get_by_label("任务项目")).not_to_be_visible()
    # Consent remains present in the hidden configuration, and is reset.
    assert not page.locator('.task-settings input[type="checkbox"]').is_checked()
    open_task_settings(page)
    expect(consent).not_to_be_checked()
    expect(page.get_by_label("真实任务边界")).to_have_value("")
    expect(page.get_by_label("任务验收类型")).to_have_value("research")
    expect(page.get_by_label("任务项目")).to_have_value("composer-reset")
    expect(page.get_by_label("任务工作区")).to_have_value("composer-reset")
    expect(page.get_by_label("任务模型")).to_have_value(selected_model)
    open_task_settings(page)
    page.get_by_label("任务验收类型").select_option("file")
    expect(page.get_by_label("任务目标路径")).to_have_value("notes.md")
    expect(page.get_by_label("任务期望内容")).to_have_value("")
    screenshot(page, "new-task-composer-desktop.png")


def test_workbench_default_ime_retry_artifact_feedback_and_url(page: Page) -> None:
    seed_workbench(page, "main-workbench")
    page.goto(BASE)
    expect(page.get_by_role("heading", name="开始一件值得完成的事")).to_be_visible()
    expect(page.get_by_label("任务项目")).to_have_value("main-workbench")
    expect(page.get_by_text("正在加载任务连接…", exact=True)).to_have_count(0)
    screenshot(page, "M12-home.png")
    text = page.get_by_label("真实任务目标")
    text.fill("Research provenance for this project.")
    text.dispatch_event(
        "keydown", {"key": "Enter", "code": "Enter", "isComposing": True, "keyCode": 229}
    )
    expect(page.get_by_label("真实任务执行记录")).to_have_count(0)
    calls: list[str] = []

    def once(route: object) -> None:
        from playwright.sync_api import Route

        assert isinstance(route, Route)
        body = route.request.post_data_json
        assert isinstance(body, dict)
        calls.append(str(body["request_id"]))
        if len(calls) == 1:
            route.abort()
        else:
            route.continue_()

    page.route("**/api/v1/agent/runs", once)
    page.get_by_role("button", name="启动真实任务").click()
    expect(page.get_by_role("alert")).to_contain_text("连接中断")
    expect(text).to_have_value("Research provenance for this project.")
    page.get_by_role("button", name="启动真实任务").click()
    record = page.get_by_label("真实任务执行记录")
    expect(record.get_by_role("status")).to_contain_text("验收通过", timeout=15000)
    assert len(calls) == 2 and calls[0] == calls[1]
    page.unroute("**/api/v1/agent/runs", once)
    url = page.url
    assert "run=" in url and "project=main-workbench" in url
    record.get_by_label("任务反馈说明").fill("Useful structure; verify claims independently.")
    record.get_by_role("button", name="有帮助", exact=True).click()
    expect(record).to_contain_text("反馈已保存 · 用户标签")
    record.get_by_role("button", name="预览任务报告").click()
    expect(page.get_by_label("真实产物预览")).to_contain_text("[asset:notes]")
    panel = page.get_by_label("真实产物预览")
    before = panel.bounding_box()
    assert before is not None
    page.get_by_label("产物面板宽度").focus()
    page.keyboard.press("ArrowRight")
    after = panel.bounding_box()
    assert after is not None and after["width"] > before["width"]
    screenshot(page, "M12-workbench-report.png")
    page.keyboard.press("Escape")
    expect(page.get_by_label("真实产物预览")).to_have_count(0)
    page.reload()
    expect(record.get_by_role("status")).to_contain_text("验收通过", timeout=15000)
    assert page.url == url
    # A hostile response is still rendered as text/Markdown, never executable HTML.
    page.route(
        "**/api/v1/agent/runs/*/report",
        lambda route: route.fulfill(
            status=200,
            body=(
                "<script>window.autonInjected=true</script>\n"
                '<img src=x onerror="window.autonInjected=true">\n\n'
                '[unsafe](javascript:alert(1))\n\n```python\nprint("safe")\n```'
            ),
        ),
    )
    record.get_by_role("button", name="预览任务报告").click()
    preview = page.get_by_label("真实产物预览")
    expect(preview.get_by_role("button", name="复制代码")).to_be_visible()
    assert not page.evaluate("Boolean(window.autonInjected)")
    assert preview.locator('script,img,a[href^="javascript:"]').count() == 0
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    preview.get_by_role("button", name="复制代码").click()
    expect(preview.get_by_role("button", name="已复制")).to_be_visible()
    page.keyboard.press("Escape")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    record.get_by_role("heading", name="执行记录").scroll_into_view_if_needed()
    screenshot(page, "M12-workbench-mobile.png")
    page.set_viewport_size({"width": 1440, "height": 900})
    page.unroute("**/api/v1/agent/runs/*/report")
    open_task_settings(page)
    page.get_by_label("任务验收类型").select_option("file")
    page.get_by_label("真实任务目标").fill("Write an exact fixture file.")
    page.get_by_label("任务期望内容").fill("hello\n")
    page.get_by_role("button", name="启动真实任务").click()
    expect(record.get_by_role("status")).to_contain_text("等待审批", timeout=15000)
    run_id = page.evaluate('new URL(location.href).searchParams.get("run")')
    old = page.request.get(BASE + f"/api/v1/agent/runs/{run_id}").json()
    record.get_by_label("修订真实任务目标").fill(
        "Write the exact same approved fixture only after review."
    )
    record.get_by_role("button", name="修订并安全暂停").click()
    expect(record.get_by_role("status")).to_contain_text("已暂停", timeout=15000)
    late = page.request.post(
        BASE + f"/api/v1/agent/runs/{run_id}/commands",
        headers={"X-Auton-Client": "web", "Origin": BASE},
        data={
            "request_id": "late-approval",
            "expected_goal_revision": old["goal_revision"],
            "expected_version": old["version"],
            "action": "approve",
        },
    )
    assert late.status == 409
    record.get_by_role("button", name="恢复任务", exact=True).click()
    expect(record.get_by_role("status")).to_contain_text("等待审批", timeout=15000)
    record.get_by_label("审批拒绝原因").fill("Do not write this fixture.")
    record.get_by_role("button", name="拒绝并停止任务").click()
    expect(record.get_by_role("status")).to_contain_text("已停止", timeout=15000)
    expect(record.get_by_role("link", name="下载任务文件 notes.md")).to_have_count(0)


def test_workbench_history_pagination_search_and_late_snapshot(page: Page) -> None:
    from playwright.sync_api import Route

    seed_workbench(page, "history-workbench")
    runs = [
        create_workbench_run(
            page, "history-workbench", f"History task {index:02} provenance", f"page-{index}"
        )
        for index in range(23)
    ]
    page.goto(BASE + "?view=agent&project=history-workbench")
    page.locator(".task-history > summary").click()
    history = page.get_by_role("article").filter(
        has=page.get_by_role("heading", name="项目会话与任务")
    )
    expect(history.get_by_role("button", name=re.compile("^History task"))).to_have_count(10)
    history.get_by_role("button", name="加载更多任务").click()
    expect(history.get_by_role("button", name=re.compile("^History task"))).to_have_count(20)
    history.get_by_role("button", name="加载更多任务").click()
    expect(history.get_by_role("button", name=re.compile("^History task"))).to_have_count(23)
    expect(history.get_by_role("button", name="加载更多任务")).to_have_count(0)
    page.get_by_label("搜索项目任务", exact=True).fill("History task 22")
    expect(history.get_by_role("button", name=re.compile("^History task"))).to_have_count(1)
    page.get_by_label("搜索项目任务", exact=True).fill("History task 0")
    expect(history.get_by_role("button", name=re.compile("^History task"))).to_have_count(10)
    held: list[Route] = []
    first_id = str(runs[0]["id"])
    page.route(f"**/api/v1/agent/runs/{first_id}/snapshot", lambda route: held.append(route))
    history.get_by_role("button", name=re.compile("^History task 00")).click()
    page.wait_for_function('new URL(location.href).searchParams.has("run")')
    page.wait_for_timeout(150)
    assert held
    history.get_by_role("button", name=re.compile("^History task 01")).click()
    expect(page.get_by_label("真实任务执行记录")).to_contain_text("History task 01")
    old = page.request.get(BASE + f"/api/v1/agent/runs/{first_id}/snapshot").text()
    for route in held:
        route.fulfill(status=200, content_type="application/json", body=old)
    expect(page.get_by_label("真实任务执行记录")).to_contain_text("History task 01")
    assert str(runs[1]["id"]) in page.url
    screenshot(page, "M12-history.png")
    # Cross-project or unavailable deep links do not silently show a different run.
    page.goto(BASE + "?view=agent&project=not-owned&run=" + first_id)
    expect(page.get_by_role("alert")).to_contain_text("项目不可访问")
    expect(page.get_by_label("真实任务执行记录")).to_have_count(0)


def test_assessment_checkpoint_evidence_unknown_gate_comparison_and_mobile(page: Page) -> None:
    import hashlib
    import time

    identity = "assessment-browser"
    seed_workbench(page, identity)
    headers = {"X-Auton-Client": "web", "Origin": BASE}
    created = page.request.post(
        BASE + "/api/v1/agent/runs",
        headers=headers,
        data={
            "request_id": "assessment-browser-file",
            "project_id": identity,
            "workspace_id": identity,
            "model_id": "fixture-model",
            "goal": "Create a precise UTF-8 text file.",
            "allowed_tools": ["file.write"],
            "acceptance": {
                "kind": "file",
                "path": "notes.md",
                "sha256": hashlib.sha256(b"hello\n").hexdigest(),
            },
        },
    )
    assert created.ok
    run_id = created.json()["id"]

    def await_run(status: str) -> dict[str, object]:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            value = page.request.get(BASE + f"/api/v1/agent/runs/{run_id}").json()
            if value["status"] == status:
                return value  # type: ignore[no-any-return]
            time.sleep(0.03)
        raise AssertionError(f"Run did not reach {status}: {value['status']}")

    paused = await_run("waiting_approval")
    assert page.request.post(
        BASE + f"/api/v1/agent/runs/{run_id}/commands",
        headers=headers,
        data={
            "request_id": "assessment-browser-approve",
            "expected_goal_revision": paused["goal_revision"],
            "action": "approve",
        },
    ).ok
    await_run("succeeded")
    page.goto(BASE + "?view=assess")
    expect(page.get_by_role("heading", name="评测", exact=True)).to_be_visible()
    expect(page.get_by_text("尚无人工元评测校准，语义可信门禁关闭。", exact=True)).to_be_visible()
    page.get_by_label("评测项目", exact=True).select_option(identity)
    expect(page.get_by_label("评测运行", exact=True)).to_be_enabled()
    page.get_by_label("评测运行", exact=True).select_option(run_id)
    expect(page.get_by_role("button", name="评测当前检查点")).to_be_enabled()
    page.get_by_role("button", name="评测当前检查点").click()
    evidence = page.get_by_label("评测证据", exact=True)
    expect(evidence.get_by_role("heading", name="通过 · operational")).to_be_visible()
    expect(evidence).to_contain_text("独立检查")
    expect(evidence).to_contain_text("发布候选行：不符合")
    expect(page.get_by_label("评测统计")).to_contain_text("已知分母 1")
    page.get_by_role("checkbox", name=re.compile("调用语义裁判")).check()
    page.get_by_role("button", name="评测当前检查点").click()
    expect(evidence.get_by_role("heading", name="未知 · operational")).to_be_visible()
    expect(page.get_by_label("评测统计")).to_contain_text("未知 1")
    reports = page.request.get(BASE + f"/api/v1/assessment/reports?project_id={identity}").json()
    assert len(reports) == 2 and all(not r["quality_release_eligible"] for r in reports)
    page.get_by_label("基线报告", exact=True).select_option(reports[0]["id"])
    page.get_by_label("候选报告", exact=True).select_option(reports[1]["id"])
    page.get_by_role("button", name="比较候选", exact=True).click()
    expect(page.get_by_text("不可作为改进证据", exact=True)).to_be_visible()
    page.get_by_role("button", name="添加训练种子").click()
    expect(
        page.get_by_text("train 2 · development 0 · test 0 · meta 0", exact=True)
    ).to_be_visible()
    page.get_by_role("heading", name="评测", exact=True).scroll_into_view_if_needed()
    screenshot(page, "M13-assessment-desktop.png")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("heading", name="评测", exact=True).scroll_into_view_if_needed()
    screenshot(page, "M13-assessment-mobile.png")
    page.reload()
    expect(page.get_by_role("heading", name="评测", exact=True)).to_be_visible()
    expect(page.get_by_text("尚无人工元评测校准，语义可信门禁关闭。", exact=True)).to_be_visible()


def test_assessment_unavailable_error_is_explicit(page: Page) -> None:
    page.route(
        "**/api/v1/assessment/status",
        lambda route: route.fulfill(
            status=403,
            content_type="application/json",
            body='{"code":"assessment_forbidden","message":"当前身份不能读取评测"}',
        ),
    )
    page.goto(BASE + "?view=assess")
    expect(page.get_by_role("alert")).to_have_text("当前身份不能读取评测")
    expect(page.get_by_role("button", name="评测当前检查点")).to_be_disabled()


def test_delegation_private_dag_approvals_conflict_and_mobile(page: Page) -> None:
    import json

    identity = "delegation-browser"
    seed_workbench(page, identity)
    page.goto(BASE + "?view=delegation")
    expect(page.get_by_role("heading", name="多 Agent", exact=True)).to_be_visible()
    page.get_by_label("委派项目", exact=True).select_option(identity)
    page.get_by_text("新建任务契约", exact=True).click()
    page.get_by_role("button", name="填入公开合成示例（不自动运行）", exact=True).click()
    command = json.loads(page.get_by_label("委派契约 JSON", exact=True).input_value())
    assert command["public"] is False and command["children"][0]["limits"]["max_tokens"] == 8000
    page.get_by_role("button", name="创建父任务", exact=True).click()
    state = page.get_by_label("父任务状态", exact=True)
    expect(state.get_by_role("heading", name="待启动", exact=True)).to_be_visible()
    headers = {"X-Auton-Client": "web", "Origin": BASE}
    conflicting = page.request.post(
        BASE + "/api/v1/delegation",
        headers=headers,
        data={**command, "request_id": "same-output-conflict"},
    )
    assert conflicting.status == 409 and conflicting.json()["code"] == "delegation_write_conflict"
    forged = page.request.post(
        BASE + "/api/v1/delegation", headers=headers, data={**command, "role": "runtime"}
    )
    assert forged.status == 422
    page.get_by_role("button", name="启动委派", exact=True).click()
    expect(page.get_by_label("alpha 待审批差异", exact=True)).to_contain_text(
        "+hello", timeout=20000
    )
    expect(page.get_by_label("beta 待审批差异", exact=True)).to_contain_text(
        "+hello", timeout=20000
    )
    screenshot(page, "M14-worker-approvals.png")
    page.get_by_role("button", name="批准子任务 alpha 本次操作", exact=True).click()
    expect(page.get_by_role("heading", name="alpha · 独立验收通过", exact=True)).to_be_visible(
        timeout=20000
    )
    page.get_by_role("button", name="批准子任务 beta 本次操作", exact=True).click()
    expect(state.get_by_role("heading", name="等待审批", exact=True)).to_be_visible(timeout=20000)
    merge = page.get_by_label("集成差异", exact=True)
    expect(merge).to_contain_text("+hello")
    expect(state).to_contain_text("工具调用 2 / 8")
    screenshot(page, "M14-integration-approval.png")
    page.get_by_role("button", name="批准最终合并", exact=True).click()
    expect(state.get_by_role("heading", name="父目标验收通过", exact=True)).to_be_visible(
        timeout=20000
    )
    expect(state).to_contain_text("工具调用 3 / 8")
    link = page.get_by_role("link", name="下载父任务交付", exact=True)
    artifact_url = link.get_attribute("href")
    assert artifact_url
    artifact = page.request.get(BASE + artifact_url)
    assert artifact.ok and artifact.body() == b"hello\nhello\n"
    page.reload()
    expect(state.get_by_role("heading", name="父目标验收通过", exact=True)).to_be_visible()
    page.get_by_role("heading", name="多 Agent", exact=True).scroll_into_view_if_needed()
    screenshot(page, "M14-delegation-desktop.png")
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("heading", name="多 Agent", exact=True).scroll_into_view_if_needed()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    screenshot(page, "M14-delegation-mobile.png")
    parent_id = page.request.get(BASE + f"/api/v1/delegation?project_id={identity}").json()[0]["id"]
    page.context.clear_cookies()
    page.request.get(BASE + "/api/v1/bootstrap")
    assert page.request.get(BASE + f"/api/v1/delegation/{parent_id}").status == 404


def test_evolution_local_patch_arena_gate_failure_restart_and_mobile(page: Page) -> None:
    import hashlib
    import json
    import time
    from typing import Any, cast
    from uuid import uuid4

    identity = "evolution-" + uuid4().hex[:12]
    seed_workbench(page, identity)
    headers = {"X-Auton-Client": "web", "Origin": BASE}

    def post(path: str, body: object) -> dict[str, Any]:
        response = page.request.post(BASE + "/api/v1" + path, headers=headers, data=body)
        assert response.ok, response.text()
        return cast(dict[str, Any], response.json())

    content = (
        "# Skill\nPreserve project and user boundaries.\n\n"
        "## Execution\nRead the goal.\nWrite once.\nReport the receipt.\n\n"
        "## Safety\nNever expand granted permissions or invent evidence.\n"
    )
    assets = page.request.get(BASE + f"/api/v1/projects/{identity}/assets").json()
    pending = post(
        f"/projects/{identity}/candidates",
        {
            "asset": {
                "id": "skill",
                "name": "Skill",
                "kind": "skill",
                "content": content,
                "origin": "user_explicit",
                "source": "public browser synthetic test",
            },
            "expected": assets["candidates_revision"],
        },
    )
    post(
        f"/projects/{identity}/assets/skill/promote",
        {"expected": pending["revision"], "candidates_revision": pending["candidates_revision"]},
    )
    snapshot = post(f"/projects/{identity}/snapshots", {})
    workspace = "evo-source-" + uuid4().hex[:8]
    post("/tools/workspaces", {"id": workspace, "title": "Synthetic source", "read_only": False})
    goal = "Write hello followed by a newline to notes.md. Report only the observed tool receipt."
    sha = hashlib.sha256(b"hello\n").hexdigest()
    run = post(
        "/agent/runs",
        {
            "request_id": uuid4().hex,
            "project_id": identity,
            "workspace_id": workspace,
            "model_id": "fixture-model",
            "goal": goal,
            "allowed_tools": ["file.write"],
            "acceptance": {"kind": "file", "path": "notes.md", "sha256": sha},
        },
    )
    deadline = time.monotonic() + 30
    while run["status"] != "succeeded":
        if run["status"] == "waiting_approval":
            post(
                "/agent/runs/" + run["id"] + "/commands",
                {
                    "request_id": uuid4().hex,
                    "expected_goal_revision": 1,
                    "expected_version": run["version"],
                    "action": "approve",
                },
            )
        assert run["status"] not in {"failed", "blocked", "cancelled"}, run["reason"]
        assert time.monotonic() < deadline
        page.wait_for_timeout(100)
        run = page.request.get(BASE + "/api/v1/agent/runs/" + run["id"]).json()
    report = post(
        "/assessment/jobs",
        {
            "request_id": uuid4().hex,
            "project_id": identity,
            "run_id": run["id"],
            "expected_version": run["version"],
        },
    )["report"]
    page.goto(BASE + "?view=evolve")
    expect(page.get_by_role("heading", name="资产进化", exact=True)).to_be_visible()
    page.get_by_label("进化项目", exact=True).select_option(identity)
    page.get_by_label("进化命令 JSON", exact=True).fill(
        json.dumps(
            {
                "request_id": uuid4().hex,
                "project_id": identity,
                "asset_id": "skill",
                "report_ids": [report["id"]],
            }
        )
    )
    page.get_by_role("button", name="诊断证据", exact=True).click()
    expect(page.get_by_text("最近操作结果", exact=True)).to_be_visible()
    diagnosis = json.loads(
        page.locator("details")
        .filter(has=page.locator("summary", has_text="最近操作结果"))
        .locator("pre")
        .inner_text()
    )
    body = "Read the goal.\nWrite once.\nReport the receipt.\n\n"
    page.get_by_label("进化操作", exact=True).select_option("propose")
    page.get_by_label("进化命令 JSON", exact=True).fill(
        json.dumps(
            {
                "request_id": uuid4().hex,
                "project_id": identity,
                "diagnosis_id": diagnosis["id"],
                "base_snapshot_id": snapshot["id"],
                "asset_id": "skill",
                "expected_content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                "direction": "Improve receipt verification within existing permissions.",
                "rationale": "A bounded engineering hypothesis.",
                "patch": {
                    "heading": "## Execution",
                    "before": body,
                    "after": body.replace("Write once.", "Write once and verify the receipt."),
                },
            }
        )
    )
    page.get_by_role("button", name="提出局部补丁", exact=True).click()
    expect(page.get_by_label("候选差异", exact=True)).to_contain_text("+Write once and verify")
    screenshot(page, "M15-evolution-diff-desktop.png")
    proposal = page.request.get(BASE + f"/api/v1/evolution/proposals?project_id={identity}").json()[
        0
    ]
    bank = page.request.get(BASE + "/api/v1/assessment/bank").json()
    core = "core-" + uuid4().hex[:8]
    dev = "dev-" + uuid4().hex[:8]
    bank = post(
        "/assessment/bank",
        {
            "request_id": uuid4().hex,
            "expected_revision": bank["revision"],
            "cases": [
                {
                    "id": i,
                    "family": i,
                    "origin_group": i,
                    "split": split,
                    "prompt": prompt,
                    "kind": "file",
                    "target_path": "notes.md",
                    "expected_sha256": sha,
                    "source": "test_fixture",
                }
                for i, split, prompt in (
                    (core, "train", goal),
                    (
                        dev,
                        "development",
                        "Deliver hello and a final newline inside notes.md, "
                        "then report the tool outcome.",
                    ),
                )
            ],
        },
    )
    arena = post(
        "/evolution/arenas",
        {
            "request_id": uuid4().hex,
            "proposal_id": proposal["id"],
            "expected_proposal_version": proposal["version"],
            "bank_revision": bank["revision"],
            "train_cases": [core],
            "development_cases": [dev],
            "repeats": 1,
            "model_id": "fixture-model",
            "limits": {
                "max_steps": 3,
                "max_tokens": 8000,
                "max_cost_microusd": 4000,
                "max_tool_calls": 1,
            },
            "checkpoints": [{"name": "old-digest"}],
        },
    )
    page.get_by_role("button", name="刷新进化记录", exact=True).click()
    expect(page.get_by_role("button", name="开始隔离评测", exact=True)).to_be_enabled()
    page.get_by_role("button", name="开始隔离评测", exact=True).click()
    for _ in range(6):
        approval = page.get_by_role("button", name="批准当前文件改动", exact=True)
        expect(approval).to_be_enabled(timeout=30000)
        approval.click()
        # Wait for this exact approval to settle before selecting a later checkpoint.
        expect(approval).to_be_disabled(timeout=10000)
    deadline = time.monotonic() + 30
    while True:
        value = page.request.get(BASE + "/api/v1/evolution/arenas/" + arena["id"]).json()
        if value["status"] == "complete":
            break
        assert value["status"] not in {"blocked", "cancelled"}, value["reason"]
        assert time.monotonic() < deadline
        page.wait_for_timeout(100)
    page.get_by_role("button", name="刷新进化记录", exact=True).click()
    expect(page.get_by_text("G3_repeated_validation：hold", exact=False).first).to_be_visible()
    page.get_by_role("checkbox").check()
    page.get_by_role("button", name="提交学习候选", exact=True).click()
    # Mock executors have no independently observed provider fingerprint.
    # All file checks passing must not bypass the frozen executor identity gate.
    expect(page.get_by_role("alert")).to_contain_text(
        "Failed structural, protocol or regression gates"
    )
    assert (
        page.request.get(BASE + f"/api/v1/projects/{identity}/assets").json()["revision"]
        == snapshot["revision"]
    )
    page.reload()
    page.get_by_label("进化项目", exact=True).select_option(identity)
    expect(page.get_by_label("候选差异", exact=True)).to_contain_text("+Write once and verify")
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("heading", name="资产进化", exact=True).scroll_into_view_if_needed()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    screenshot(page, "M15-evolution-mobile.png")


def test_decision_review_shadow_exclusion_manual_revision_reload_and_mobile(page: Page) -> None:
    import json
    import time
    from uuid import uuid4

    project = "review-" + uuid4().hex[:10]
    seed_workbench(page, project)
    created = create_workbench_run(
        page, project, "Research context retrieval and cite [asset:notes].", "source-review"
    )
    deadline = time.monotonic() + 20
    while True:
        run = page.request.get(BASE + "/api/v1/agent/runs/" + str(created["id"])).json()
        if run["status"] in {"succeeded", "failed", "blocked"}:
            break
        assert time.monotonic() < deadline
        page.wait_for_timeout(100)
    assert run["judgments"] and not run["judgments"][0]["adopted"]
    page.goto(BASE + "?view=decision_review")
    expect(page.get_by_role("heading", name="决策轨迹复核", exact=True)).to_be_visible()
    page.get_by_label("复核项目", exact=True).select_option(project)
    page.get_by_role("button", name="填写复核命令", exact=True).click()
    editor = page.get_by_label("复核命令 JSON", exact=True)
    expect(editor).not_to_have_value("")
    command = json.loads(editor.input_value())
    assert command["run_id"] == run["id"] and command["public"] is False
    page.get_by_role("button", name="执行两阶段复核", exact=True).click()
    state = page.get_by_label("决策样本状态", exact=True)
    expect(state).to_contain_text("HOLD", timeout=15000)
    expect(state).to_contain_text("不进入正向训练")
    expect(page.get_by_text("阶段 A：仅看决策前状态", exact=True)).to_be_visible()
    expect(page.get_by_text("阶段 B：后续实际贡献", exact=True)).to_be_visible()
    expect(page.get_by_text("自动准入：关闭", exact=False).first).to_be_visible()
    screenshot(page, "M16-decision-review-desktop.png")
    page.get_by_label("复核操作", exact=True).select_option("revise")
    page.get_by_role("button", name="填写复核命令", exact=True).click()
    expect(editor).to_have_value(re.compile("proposed_verdict", re.S))
    correction = json.loads(editor.input_value())
    correction["proposed_verdict"] = "DROP"
    correction["reason"] = (
        "This manual exclusion must not give an unused judgment credit for actor success."
    )
    editor.fill(json.dumps(correction))
    page.get_by_role("button", name="保存人工修订", exact=True).click()
    expect(page.get_by_text("人工修订历史", exact=True)).to_be_visible()
    expect(state).to_contain_text("DROP")
    page.reload()
    page.get_by_label("复核项目", exact=True).select_option(project)
    expect(page.get_by_text("人工修订历史", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("heading", name="决策轨迹复核", exact=True).scroll_into_view_if_needed()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    screenshot(page, "M16-decision-review-mobile.png")


def test_datasets_scoped_grant_defaults_withdraw_reload_and_mobile(page: Page) -> None:
    import json
    from uuid import uuid4

    project = "dataset-" + uuid4().hex[:10]
    seed_workbench(page, project)
    page.goto(BASE + "?view=datasets")
    expect(page.get_by_role("heading", name="数据集与谱系", exact=True)).to_be_visible()
    page.get_by_label("数据项目", exact=True).select_option(project)
    expect(page.get_by_text("暂无数据快照。", exact=True)).to_be_visible()
    page.get_by_role("button", name="准备数据命令", exact=True).click()
    editor = page.get_by_label("数据命令", exact=True)
    expect(editor).not_to_have_value("")
    command = json.loads(editor.input_value())
    assert command["local_training_authorized"] is False
    assert command["allow_local_only_data"] is False
    screenshot(page, "M17-datasets-desktop.png")
    page.get_by_label("数据操作", exact=True).select_option("withdraw")
    page.get_by_role("button", name="准备数据命令", exact=True).click()
    expect(editor).to_have_value(re.compile('"reason"', re.S))
    command = json.loads(editor.input_value())
    command["project_id"] = "another-project"
    editor.fill(json.dumps(command))
    page.get_by_role("button", name="提交数据操作", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("命令项目必须与当前项目一致")
    page.reload()
    expect(page.get_by_role("heading", name="数据集与谱系", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    screenshot(page, "M17-datasets-mobile.png")


def test_portable_training_disabled_defaults_plan_and_mobile(page: Page) -> None:
    import json
    from uuid import uuid4

    project = "training-" + uuid4().hex[:10]
    seed_workbench(page, project)
    page.goto(BASE + "?view=training")
    expect(page.get_by_role("heading", name="执行模型训练", exact=True)).to_be_visible()
    expect(page.get_by_text("训练后端未配置。", exact=False)).to_be_visible()
    page.get_by_label("训练项目", exact=True).select_option(project)
    page.get_by_role("button", name="准备训练计划", exact=True).click()
    editor = page.get_by_label("训练计划命令", exact=True)
    command = json.loads(editor.input_value())
    assert command["engineering_probe"] is False and command["project_id"] == project
    command["train_artifact_id"] = "0" * 64
    editor.fill(json.dumps(command))
    page.get_by_role("button", name="检查并保存计划", exact=True).click()
    expect(page.get_by_text("training_backend_disabled", exact=False).first).to_be_visible()
    expect(page.get_by_role("button", name="启动训练作业", exact=True)).to_be_disabled()
    screenshot(page, "M18-training-desktop.png")
    page.reload()
    page.get_by_label("训练项目", exact=True).select_option(project)
    expect(page.get_by_role("button", name="启动训练作业", exact=True)).to_be_disabled()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    screenshot(page, "M18-training-mobile.png")


def test_decision_training_is_separate_and_preserves_teacher_only(page: Page) -> None:
    import json
    from uuid import uuid4

    project = "student-" + uuid4().hex[:10]
    seed_workbench(page, project)
    page.goto(BASE + "?view=decision_training")
    expect(page.get_by_role("heading", name="决策模型训练与评估", exact=True)).to_be_visible()
    page.get_by_label("训练项目", exact=True).select_option(project)
    expect(page.get_by_text("线上不引入 student 路由。", exact=False)).to_be_visible()
    page.get_by_role("button", name="准备训练计划", exact=True).click()
    editor = page.get_by_label("训练计划命令", exact=True)
    command = json.loads(editor.input_value())
    command["train_artifact_id"] = "0" * 64
    editor.fill(json.dumps(command))
    page.get_by_role("button", name="检查并保存计划", exact=True).click()
    expect(page.get_by_role("button", name="启动训练作业", exact=True)).to_be_disabled()
    expect(page.get_by_role("heading", name="四层评估与离线预测", exact=True)).to_be_visible()
    screenshot(page, "M19-decision-training-desktop.png")
    page.reload()
    page.get_by_label("训练项目", exact=True).select_option(project)
    expect(page.get_by_role("button", name="启动训练作业", exact=True)).to_be_disabled()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    screenshot(page, "M19-decision-training-mobile.png")


def test_release_control_empty_errors_reload_and_mobile(page: Page) -> None:
    import json
    from uuid import uuid4

    project = "release-" + uuid4().hex[:10]
    seed_workbench(page, project)
    page.goto(BASE + "?view=release")
    expect(page.get_by_role("heading", name="发布与回滚", exact=True)).to_be_visible()
    page.get_by_label("发布项目", exact=True).select_option(project)
    expect(page.get_by_text("当前项目还没有发布报告。", exact=True)).to_be_visible()
    expect(page.get_by_text("自动批准：关闭", exact=False)).to_be_visible()
    editor = page.get_by_label("发布计划 JSON", exact=True)
    expect(editor).not_to_have_value("")
    command = json.loads(editor.input_value())
    assert command["mode"] == "canary" and command["percentage"] == 5
    command["kind"] = "executor_model"
    command["source_id"] = "0" * 64
    editor.fill(json.dumps(command))
    page.get_by_role("button", name="检查发布证据", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("No owned immutable training candidate")
    screenshot(page, "M20-release-desktop.png")
    page.reload()
    expect(page.get_by_role("heading", name="发布与回滚", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    screenshot(page, "M20-release-mobile.png")


def test_background_operations_disabled_plan_pause_backup_and_mobile(page: Page) -> None:
    import json
    from uuid import uuid4

    project = "operations-" + uuid4().hex[:10]
    seed_workbench(page, project)
    page.goto(BASE + "?view=operations")
    expect(page.get_by_role("heading", name="后台运行与监控", exact=True)).to_be_visible()
    page.get_by_label("后台项目", exact=True).select_option(project)
    expect(page.get_by_text("宿主调度未启用。", exact=False)).to_be_visible()
    editor = page.get_by_label("后台计划 JSON", exact=True)
    expect(editor).not_to_have_value("")
    command = json.loads(editor.input_value())
    assert command["enabled"] is False and command["confirm_background_actions"] is False
    page.get_by_role("button", name="保存后台计划", exact=True).click()
    expect(page.get_by_role("heading", name="telemetry · 暂停", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="恢复计划", exact=True)).to_be_disabled()
    page.get_by_role("button", name="暂停当前身份调度", exact=True).click()
    expect(page.get_by_role("button", name="恢复当前身份调度", exact=True)).to_be_visible()
    page.get_by_role("button", name="创建调度备份", exact=True).click()
    expect(page.get_by_text('"scope": "owned_operations_state_only"', exact=False)).to_be_visible()
    screenshot(page, "M21-operations-desktop.png")
    page.reload()
    expect(page.get_by_role("button", name="恢复当前身份调度", exact=True)).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    screenshot(page, "M21-operations-mobile.png")
