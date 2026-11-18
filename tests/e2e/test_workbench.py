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
    page.goto(BASE)
    expect(page.get_by_role("textbox", name="任务输入")).to_be_enabled()
    yield page
    context.close()
    assert not errors, errors


def screenshot(page: Page, name: str) -> None:
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
    expect(page.get_by_role("heading", name="学习", exact=True)).to_be_visible()
    expect(page.get_by_text("M17 · 待开发")).to_be_visible()
    page.get_by_role("button", name="返回对话").click()
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
    page.get_by_role("button", name=re.compile("^任务")).click()
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
    page.get_by_label("任务验收类型").select_option("file")
    page.get_by_label("真实任务目标").fill("Create a precise UTF-8 text file.")
    page.get_by_label("任务期望内容").fill("hello\n")
    page.get_by_role("button", name="启动真实任务").click()
    expect(record.get_by_role("status")).to_contain_text("等待审批", timeout=15000)
    expect(record.locator(".tool-output").first).to_contain_text("+hello")
    screenshot(page, "M09-approval.png")
    record.get_by_role("button", name="批准本次任务操作").click()
    expect(record.get_by_role("status")).to_contain_text("验收通过", timeout=15000)
    expect(record).to_contain_text("file-sha256-v1")
    record.get_by_text(re.compile("file.write · succeeded")).click()
    with page.expect_download() as artifact:
        record.get_by_role("link", name="下载任务文件 notes.md").click()
    assert Path(artifact.value.path()).read_text() == "hello\n"
    record.get_by_role("heading", name="执行记录").scroll_into_view_if_needed()
    screenshot(page, "M09-file.png")
    page.reload()
    page.get_by_role("button", name=re.compile("^任务")).click()
    page.get_by_role("button", name=re.compile("^Create a precise")).click()
    expect(page.get_by_label("真实任务执行记录")).to_contain_text("file-sha256-v1")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.get_by_label("真实任务执行记录").get_by_role(
        "heading", name="执行记录"
    ).scroll_into_view_if_needed()
    screenshot(page, "M09-mobile.png")
