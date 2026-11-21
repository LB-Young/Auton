from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from test_workbench import BASE, screenshot
from test_workbench import browser as browser
from test_workbench import page as page

pytestmark = pytest.mark.browser


def test_choose_local_project_and_approved_write_changes_original_directory(
    page: Page, tmp_path: Path
) -> None:
    project = tmp_path / "fixture-project"
    project.mkdir()
    (project / "README.md").write_text("Selected project fixture")
    page.goto(BASE)
    text = page.get_by_role("textbox", name="对话输入", exact=True)
    expect(text).to_be_enabled()
    text.fill("[TEST FIXTURE] Create hello.txt")
    page.get_by_role("button", name="选择项目目录", exact=True).click()
    picker = page.get_by_role("dialog", name="选择本地项目目录")
    expect(picker).to_be_visible()
    picker.get_by_label("项目目录路径").fill(str(project))
    picker.get_by_role("button", name="打开路径", exact=True).click()
    expect(picker.get_by_label("项目目录路径")).to_have_value(str(project.resolve()))
    expect(picker.get_by_role("button", name="使用此目录")).to_be_enabled()
    screenshot(page, "local-project-picker.png")
    picker.get_by_role("button", name="使用此目录").click()
    expect(picker).to_have_count(0)
    expect(text).to_have_value("[TEST FIXTURE] Create hello.txt")
    expect(page.locator(".cw-project-chip")).to_contain_text("fixture-project")
    page.get_by_role("button", name="发送消息", exact=True).click()
    panel = page.get_by_label("工作面板", exact=True)
    expect(panel.get_by_role("button", name="批准本次操作")).to_be_visible(timeout=15000)
    assert not (project / "hello.txt").exists()
    expect(panel.locator(".cw-project-location")).to_contain_text(str(project.resolve()))
    screenshot(page, "local-project-approval.png")
    panel.get_by_role("button", name="批准本次操作").click()
    expect(page.get_by_label("助手消息", exact=True)).to_contain_text("已回复", timeout=15000)
    assert (project / "hello.txt").read_text() == "hello\n"
    assert not (project / ".auton-lock").exists()
    identity = page.evaluate('new URL(location.href).searchParams.get("conversation")')
    conversation = page.request.get(BASE + f"/api/v1/conversations/{identity}").json()
    assert conversation["conversation"]["project_path"] == str(project.resolve())
    page.reload()
    expect(page.locator(".cw-project-chip")).to_contain_text("fixture-project")
    page.get_by_role("button", name="选择项目目录", exact=True).click()
    expect(picker).to_contain_text("开启一个新对话")
    picker.get_by_role("button", name="取消", exact=True).click()
    expect(page.get_by_label("用户消息", exact=True)).to_have_count(1)
    page.get_by_role("button", name="切回普通对话", exact=True).click()
    expect(page.locator(".cw-project-chip")).to_have_count(0)
    expect(page.get_by_label("用户消息", exact=True)).to_have_count(0)
    assert "conversation=" not in page.url
    history = page.get_by_label("历史对话", exact=True)
    history.get_by_role("button", name="[TEST FIXTURE] Create hello.txt", exact=True).click()
    expect(page.locator(".cw-project-chip")).to_contain_text("fixture-project")
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name="选择项目目录", exact=True).click()
    expect(picker).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    screenshot(page, "local-project-picker-mobile.png")
    page.keyboard.press("Escape")
    expect(picker).to_have_count(0)


def test_invalid_directory_does_not_bind_or_clear_draft(page: Page, tmp_path: Path) -> None:
    page.goto(BASE)
    text = page.get_by_role("textbox", name="对话输入", exact=True)
    expect(text).to_be_enabled()
    text.fill("保留这个草稿")
    page.get_by_role("button", name="选择项目目录", exact=True).click()
    picker = page.get_by_role("dialog", name="选择本地项目目录")
    picker.get_by_label("项目目录路径").fill(str(tmp_path / "not-found"))
    picker.get_by_role("button", name="打开路径", exact=True).click()
    expect(picker.get_by_role("alert")).to_contain_text("无法浏览")
    expect(picker.get_by_role("button", name="使用此目录")).to_be_disabled()
    picker.get_by_role("button", name="取消", exact=True).click()
    expect(text).to_have_value("保留这个草稿")
    expect(page.locator(".cw-project-chip")).to_have_count(0)


def test_context_limit_explains_why_project_processing_stopped(page: Page) -> None:
    from playwright.sync_api import Route

    def blocked_snapshot(route: Route) -> None:
        response = route.fetch()
        body = response.json()
        body["run"]["status"] = "blocked"
        body["run"]["reason"] = "context:critical_context_limit"
        body["run"]["final_text"] = ""
        body["transient"] = None
        route.fulfill(response=response, json=body)

    page.route("**/api/v1/agent/runs/*/snapshot", blocked_snapshot)
    page.goto(BASE)
    text = page.get_by_role("textbox", name="对话输入", exact=True)
    expect(text).to_be_enabled()
    text.fill("Context explanation fixture")
    page.get_by_role("button", name="发送消息", exact=True).click()
    expect(page.get_by_label("助手消息", exact=True)).to_contain_text(
        "超过上下文上限", timeout=15000
    )
    expect(page.get_by_label("工作面板", exact=True)).to_contain_text("旧任务的预算不会自动改变")
