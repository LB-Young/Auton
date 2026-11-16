"""Real HTTP/WebSocket browser acceptance, orchestrated by Python."""

import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

pytestmark = pytest.mark.browser
BASE = "http://127.0.0.1:5173"
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
