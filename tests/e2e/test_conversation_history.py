import json
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from test_workbench import BASE, screenshot
from test_workbench import browser as browser
from test_workbench import page as page

pytestmark = pytest.mark.browser


def test_copy_session_history_path_exports_latest_record(page: Page) -> None:
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.goto(BASE)
    copy = page.get_by_role("button", name="复制会话记录路径", exact=True)
    expect(copy).to_be_disabled()
    text = page.get_by_role("textbox", name="对话输入", exact=True)
    expect(text).to_be_enabled()
    text.fill("记录这次讨论用于分析")
    page.get_by_role("button", name="发送消息", exact=True).click()
    expect(page.get_by_label("助手消息", exact=True)).to_contain_text("已回复", timeout=15000)
    copy.click()
    expect(page.locator(".cw-history-toast").get_by_role("status")).to_contain_text(
        "已复制会话记录路径"
    )
    location = page.get_by_role("textbox", name="会话记录路径", exact=True)
    path = Path(location.input_value())
    assert path.is_absolute() and path.is_file()
    assert page.evaluate("navigator.clipboard.readText()") == str(path)
    body = json.loads(path.read_text())
    identity = page.evaluate('new URL(location.href).searchParams.get("conversation")')
    assert body["conversation"]["id"] == identity
    assert body["messages"][0]["content"] == "记录这次讨论用于分析"
    assert body["turns"][0]["status"] == "succeeded"
    screenshot(page, "conversation-copy-history-path.png")
    text.fill("继续记录第二轮")
    page.get_by_role("button", name="发送消息", exact=True).click()
    expect(page.get_by_label("助手消息", exact=True)).to_have_count(2)
    expect(page.get_by_label("助手消息", exact=True).last).to_contain_text("已回复", timeout=15000)
    copy.click()
    expect(location).to_have_value(str(path))
    expect(page.locator(".cw-history-toast").get_by_role("status")).to_contain_text(
        "已复制会话记录路径"
    )
    assert len(json.loads(path.read_text())["turns"]) == 2
    page.get_by_role("button", name="新对话", exact=False).click()
    expect(copy).to_be_disabled()
    expect(location).to_have_count(0)


def test_denied_clipboard_keeps_an_exported_path_for_manual_copy(page: Page) -> None:
    page.add_init_script(
        "Object.defineProperty(navigator, 'clipboard', { value: { "
        "write: () => Promise.reject(new Error('denied')), "
        "writeText: () => Promise.reject(new Error('denied')) } });"
    )
    page.goto(BASE)
    text = page.get_by_role("textbox", name="对话输入", exact=True)
    expect(text).to_be_enabled()
    text.fill("剪贴板权限失败也保留路径")
    page.get_by_role("button", name="发送消息", exact=True).click()
    expect(page.get_by_label("助手消息", exact=True)).to_contain_text("已回复", timeout=15000)
    page.get_by_role("button", name="复制会话记录路径", exact=True).click()
    expect(page.locator(".cw-history-toast").get_by_role("status")).to_contain_text(
        "浏览器未允许自动复制"
    )
    location = page.get_by_role("textbox", name="会话记录路径", exact=True)
    assert Path(location.input_value()).is_file()
    location.focus()
    assert location.evaluate(
        "node => node.selectionStart === 0 && node.selectionEnd === node.value.length"
    )
