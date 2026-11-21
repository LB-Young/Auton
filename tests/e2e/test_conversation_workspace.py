"""Conversation-first UI over real HTTP/agent execution with test-only model providers."""

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from test_workbench import BASE, screenshot
from test_workbench import browser as browser
from test_workbench import page as page

pytestmark = pytest.mark.browser


def test_conversation_first_multiturn_reload_panels_and_approval(page: Page) -> None:
    page.goto(BASE + "?view=agent")
    expect(page.get_by_role("heading", name="今天，想一起完成什么？")).to_be_visible()
    text = page.get_by_role("textbox", name="对话输入", exact=True)
    expect(text).to_be_enabled()
    expect(page.get_by_label("选择模型")).to_have_value("fixture-model")
    expect(page.get_by_label("任务项目")).to_have_count(0)
    expect(page.get_by_label("工作面板", exact=True)).to_have_count(0)
    screenshot(page, "conversation-home-desktop.png")
    text.fill("我叫小李，请记住我的名字。")
    text.dispatch_event(
        "keydown", {"key": "Enter", "code": "Enter", "isComposing": True, "keyCode": 229}
    )
    expect(page.get_by_label("用户消息", exact=True)).to_have_count(0)
    page.get_by_role("button", name="发送消息", exact=True).click()
    expect(page.get_by_label("助手消息", exact=True)).to_contain_text("已回复", timeout=15000)
    first_url = page.url
    expect(page).to_have_url(re.compile("conversation="))
    text.fill("我刚才说我叫什么？")
    text.press("Enter")
    expect(page.get_by_label("用户消息", exact=True)).to_have_count(2)
    expect(page.get_by_label("助手消息", exact=True).last).to_contain_text("已回复", timeout=15000)
    identity = page.evaluate('new URL(location.href).searchParams.get("conversation")')
    response = page.request.get(BASE + f"/api/v1/conversations/{identity}").json()
    assert len(response["turns"]) == 2
    prior = response["turns"][1]["command"]["prior_messages"]
    assert any(m["role"] == "user" and m["content"] == "我叫小李，请记住我的名字。" for m in prior)
    assert any(m["role"] == "assistant" for m in prior)
    assert response["turns"][1]["judgment_ids"]
    page.get_by_role("button", name="展开工作面板").click()
    expect(page.get_by_label("工作面板", exact=True)).to_be_visible()
    screenshot(page, "conversation-panel-desktop.png")
    page.get_by_role("button", name="关闭工作面板").click()
    expect(page.get_by_label("工作面板", exact=True)).to_have_count(0)
    page.reload()
    expect(page.get_by_label("用户消息", exact=True)).to_have_count(2)
    text.fill("[TEST FIXTURE] Create hello.txt")
    page.get_by_role("button", name="发送消息", exact=True).click()
    panel = page.get_by_label("工作面板", exact=True)
    expect(panel).to_be_visible(timeout=15000)
    expect(panel.get_by_role("button", name="批准本次操作")).to_be_visible()
    expect(panel).to_contain_text("hello.txt")
    screenshot(page, "conversation-approval-desktop.png")
    panel.get_by_role("button", name="批准本次操作").click()
    expect(page.get_by_label("助手消息", exact=True).last).to_contain_text("已回复", timeout=15000)
    panel.get_by_role("button", name="hello.txt", exact=True).click()
    expect(panel).to_contain_text("hello")
    with page.expect_download() as artifact:
        panel.get_by_role("link", name="下载 hello.txt").click()
    assert Path(artifact.value.path()).read_text() == "hello\n"
    page.get_by_role("button", name="关闭工作面板").click()
    screenshot(page, "conversation-multiturn-desktop.png")
    page.get_by_role("button", name="新对话", exact=False).click()
    expect(page.get_by_label("用户消息", exact=True)).to_have_count(0)
    text.fill("新的草稿")
    history = page.get_by_label("历史对话", exact=True)
    history.get_by_role("button", name="我叫小李，请记住我的名字。", exact=True).click()
    expect(page.get_by_label("用户消息", exact=True)).to_have_count(3)
    assert first_url == page.url
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.get_by_role("button", name="展开工作面板").click()
    expect(panel).to_be_visible()
    page.keyboard.press("Escape")
    expect(panel).to_have_count(0)
    page.get_by_role("button", name="打开历史对话").click()
    expect(history).to_be_in_viewport()
    page.get_by_role("button", name="关闭历史对话", exact=True).click()
    text.fill("手机端可以继续输入")
    screenshot(page, "conversation-mobile.png")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("reload_after_failure", [False, True])
def test_conversation_send_retry_preserves_draft_and_does_not_duplicate(
    page: Page, reload_after_failure: bool
) -> None:
    from playwright.sync_api import Route

    page.goto(BASE)
    text = page.get_by_role("textbox", name="对话输入", exact=True)
    expect(text).to_be_enabled()
    text.fill("retry a real conversational turn")
    calls: list[str] = []

    def lose_response(route: Route) -> None:
        body = route.request.post_data_json
        assert isinstance(body, dict)
        calls.append(str(body["request_id"]))
        if len(calls) == 1:
            route.fetch()
            route.abort("failed")
        else:
            route.continue_()

    page.route("**/api/v1/conversations/*/turns", lose_response)
    page.get_by_role("button", name="发送消息", exact=True).click()
    expect(page.get_by_role("alert")).to_contain_text("连接中断")
    expect(text).to_have_value("retry a real conversational turn")
    if reload_after_failure:
        page.get_by_role("button", name="重新加载", exact=True).click()
        expect(text).to_have_value("")
    else:
        page.get_by_role("button", name="发送消息", exact=True).click()
    expect(page.get_by_label("用户消息", exact=True)).to_have_count(1)
    expect(page.get_by_label("助手消息", exact=True)).to_contain_text("已回复", timeout=15000)
    if reload_after_failure:
        assert len(calls) == 1
    else:
        assert len(calls) == 2 and calls[0] == calls[1]
    page.reload()
    expect(page.get_by_label("用户消息", exact=True)).to_have_count(1)


def test_model_dropdown_shows_remote_local_versions_and_recipient(page: Page) -> None:
    from playwright.sync_api import Route

    def catalog(route: Route) -> None:
        models = route.fetch().json()
        local = models[0]
        local["adapter_revision"] = "local-v7"
        remote = {
            **local,
            "id": "remote-preview",
            "provider": "deepseek",
            "location": "remote",
            "adapter_revision": None,
        }
        route.fulfill(json=[local, remote])

    page.route("**/api/v1/models", catalog)
    page.goto(BASE)
    models = page.get_by_label("选择模型")
    expect(models).to_have_value("fixture-model")
    expect(models.locator('option[value="fixture-model"]')).to_contain_text(
        "本地 · fixture-model · local-v7"
    )
    expect(models.locator('option[value="remote-preview"]')).to_contain_text("远程 API")
    models.select_option("remote-preview")
    expect(page.locator(".cw-caption")).to_contain_text(
        "对话历史及本会话读取的文件将发送给 deepseek"
    )
    models.select_option("fixture-model")
    expect(page.locator(".cw-caption")).to_contain_text("本地模型")
    expect(page.get_by_role("button", name="决策训练", exact=False)).to_have_count(0)
    expect(page.get_by_label("任务验收类型")).to_have_count(0)
