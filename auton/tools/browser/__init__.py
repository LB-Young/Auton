"""Browser Tool — Playwright-based browser automation

Single BrowserTool with action dispatch to sub-methods.
Browser lifecycle: module-level lazy singleton (_browser, _page, _context).
"""

from __future__ import annotations

import base64
import json
import random
import time
from typing import TYPE_CHECKING, Any

from ..base import Tool, ToolResult

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, ConsoleMessage


# ─── Module-level lazy singleton state ───────────────────────────────────────

_browser: Browser | None = None
_context: BrowserContext | None = None
_page: Page | None = None
_initialized: bool = False
_console_logs: dict[int, list[dict[str, Any]]] = {}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
MAX_CONSOLE_ENTRIES = 200
DEFAULT_CONSOLE_LIMIT = 50
_HTML_DUMP_KEYWORDS = (
    "outerhtml",
    "innerhtml",
)


def _looks_like_html_dump(script: str) -> bool:
    """Best-effort detection of scripts that try to dump raw HTML."""
    normalized = script.lower()
    return any(keyword in normalized for keyword in _HTML_DUMP_KEYWORDS)


def _get_cdp_port() -> int:
    """Generate a random CDP port in range 9222-9299."""
    return random.randint(9222, 9299)


async def _ensure_browser(
    headless: bool = True,
    user_agent: str | None = None,
    viewport: dict[str, int] | None = None,
) -> None:
    """Lazily start the browser and create a default context/page."""
    global _browser, _context, _page, _initialized

    if _initialized:
        return

    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    cdp_port = _get_cdp_port()

    # Launch Chromium with CDP debugging enabled
    _browser = await playwright.chromium.launch(
        headless=headless,
        args=[
            f"--remote-debugging-port={cdp_port}",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )
    viewport_config = (viewport or DEFAULT_VIEWPORT).copy()
    _context = await _browser.new_context(
        viewport=viewport_config,
        user_agent=user_agent or DEFAULT_USER_AGENT,
    )

    def _on_new_page(page: Page) -> None:
        _register_page(page)

    _context.on("page", _on_new_page)
    _page = await _context.new_page()
    _register_page(_page)
    _initialized = True


def _register_page(page: Page) -> None:
    """Attach console + lifecycle listeners to a page."""
    pid = id(page)
    if pid in _console_logs:
        return
    _console_logs[pid] = []

    def _on_console(message: "ConsoleMessage") -> None:
        entry = {
            "type": message.type,
            "text": message.text,
            "timestamp": time.time(),
            "location": message.location,
        }
        logs = _console_logs.setdefault(pid, [])
        logs.append(entry)
        if len(logs) > MAX_CONSOLE_ENTRIES:
            del logs[: len(logs) - MAX_CONSOLE_ENTRIES]

    def _on_close(_: Any) -> None:
        _console_logs.pop(pid, None)
        global _page
        if _page is page:
            _page = None

    page.on("console", _on_console)
    page.on("close", _on_close)


def _list_pages() -> list[Page]:
    """Return currently open pages (tabs)."""
    if _context is None:
        return []
    return [p for p in _context.pages if not p.is_closed()]


def _active_tab_index() -> int | None:
    pages = _list_pages()
    for idx, candidate in enumerate(pages):
        if candidate is _page:
            return idx
    return 0 if pages else None


def _normalize_tab_index(value: Any) -> int | None:
    """Convert user-provided tab argument to an index or None."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("tab must be a non-negative integer index")
    if isinstance(value, int):
        if value < 0:
            raise ValueError("tab must be a non-negative integer index")
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError("tab must be a non-negative integer index")
        return _normalize_tab_index(int(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if not stripped.isdigit():
            raise ValueError("tab must be a non-negative integer index")
        return int(stripped)
    raise ValueError("tab must be a non-negative integer index")


def _coerce_positive_int(value: Any, label: str) -> int:
    """Ensure numeric input is a positive integer."""
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:  # noqa: PERF203 - clarity
        raise ValueError(f"{label} must be a positive integer") from exc
    if number <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return number


def _page_index(page: Page) -> int | None:
    """Return the index for a given page."""
    pages = _list_pages()
    for idx, candidate in enumerate(pages):
        if candidate is page:
            return idx
    return None


def _require_page(tab: Any = None) -> Page:
    """Resolve a page by tab index (default: active tab)."""
    if not _initialized or _context is None:
        raise RuntimeError("Browser not started. Call start action first.")
    pages = _list_pages()
    if not pages:
        raise RuntimeError("No tabs open. Use navigate or open action first.")
    tab_index = _normalize_tab_index(tab)
    global _page
    if tab_index is not None:
        if tab_index >= len(pages):
            raise ValueError(
                f"Tab index {tab_index} out of range (0-{len(pages) - 1}).",
            )
        _page = pages[tab_index]
        return _page
    if _page and not _page.is_closed():
        return _page
    _page = pages[0]
    return _page


# ─── BrowserTool ─────────────────────────────────────────────────────────────


class BrowserTool(Tool):
    """Browser automation tool powered by Playwright.

    All actions accept an ``action`` parameter dispatching to the appropriate
    sub-method.  The browser is a lazy singleton — it is started on the first
    action that requires it.
    """

    name = "browser"
    description = (
        "Automate a Chromium browser: navigate, snapshot, screenshot, "
        "click, type, press, hover, scroll, tabs, evaluate, start, stop, etc."
    )

    # ── schema ───────────────────────────────────────────────────────────────

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "start", "stop", "status", "navigate", "open", "focus",
                        "close", "tabs", "snapshot", "screenshot", "console",
                        "click", "type", "press", "hover", "scroll",
                        "evaluate", "back", "forward", "reload",
                    ],
                    "description": (
                        "The browser action to perform. "
                        "start/stop control lifecycle; "
                        "navigate/open/focus/close/tabs/status manage tabs; "
                        "snapshot/screenshot/console/evaluate inspect pages; "
                        "click/type/press/hover/scroll/back/forward/reload interact with "
                        "the current page."
                    ),
                },
                # Page-level / lifecycle
                "headless": {
                    "type": "boolean",
                    "description": "Start browser in headless mode (default: true).",
                },
                "user_agent": {
                    "type": "string",
                    "description": "Custom user agent when starting the browser.",
                },
                "viewport_width": {
                    "type": "integer",
                    "description": "Viewport width in pixels (start action only).",
                },
                "viewport_height": {
                    "type": "integer",
                    "description": "Viewport height in pixels (start action only).",
                },
                "url": {
                    "type": "string",
                    "description": "URL for navigate/open actions.",
                },
                "full": {
                    "type": "boolean",
                    "description": (
                        "Return the full accessibility tree including all descendants "
                        "(for snapshot action)."
                    ),
                },
                "filename": {
                    "type": "string",
                    "description": (
                        "Save screenshot to this file path instead of returning base64. "
                        "(for screenshot action)."
                    ),
                },
                # Interaction
                "selector": {
                    "type": "string",
                    "description": (
                        "CSS selector for element-targeted actions "
                        "(click / type / press / hover / scroll)."
                    ),
                },
                "text": {
                    "type": "string",
                    "description": "Text to type (for type action).",
                },
                "submit": {
                    "type": "boolean",
                    "description": (
                        "Whether to submit the form after typing (for type action)."
                    ),
                },
                "key": {
                    "type": "string",
                    "description": (
                        "Key to press, e.g. 'Enter', 'Escape', 'ArrowDown' "
                        "(for press action)."
                    ),
                },
                "script": {
                    "type": "string",
                    "description": (
                        "JavaScript expression to evaluate in the page context "
                        "(for evaluate action). The expression's return value is returned."
                    ),
                },
                "tab": {
                    "type": "integer",
                    "description": (
                        "Optional tab index (0-based). Defaults to the active tab."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of console entries to return (for console action)."
                    ),
                },
                "level": {
                    "type": "string",
                    "description": (
                        "Console level filter such as 'log', 'error', 'warning'."
                    ),
                },
            },
            "required": ["action"],
        }

    # ── execute ─────────────────────────────────────────────────────────────

    async def execute(self, action: str, **kwargs: Any) -> ToolResult:
        """Dispatch ``action`` to the appropriate sub-method."""
        method_name = f"_{action}"
        method = getattr(self, method_name, None)
        if method is None:
            return ToolResult(
                content=f"Unknown action: {action}",
                success=False,
                error=f"browser.{action} is not implemented",
            )
        try:
            return await method(**kwargs)
        except Exception as exc:  # noqa: BLE-001
            return ToolResult(
                content=f"Browser error during {action}: {exc}",
                success=False,
                error=str(exc),
            )

    # ── lifecycle ───────────────────────────────────────────────────────────

    async def _start(
        self,
        headless: bool = True,
        user_agent: str | None = None,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
    ) -> ToolResult:
        """Start the Chromium browser."""
        global _browser, _context, _page, _initialized
        if _initialized:
            page_url = _page.url if _page else "(none)"
            return ToolResult(content=f"Browser already running. Current page: {page_url}")
        viewport = None
        if viewport_width is not None or viewport_height is not None:
            width = (
                _coerce_positive_int(viewport_width, "viewport_width")
                if viewport_width is not None
                else DEFAULT_VIEWPORT["width"]
            )
            height = (
                _coerce_positive_int(viewport_height, "viewport_height")
                if viewport_height is not None
                else DEFAULT_VIEWPORT["height"]
            )
            viewport = {"width": width, "height": height}
        await _ensure_browser(headless=headless, user_agent=user_agent, viewport=viewport)
        active = _active_tab_index()
        info = {
            "headless": headless,
            "viewport": viewport or DEFAULT_VIEWPORT,
            "active_tab": active,
        }
        return ToolResult(content=json.dumps(info, ensure_ascii=False))

    async def _stop(self) -> ToolResult:
        """Stop the Chromium browser and clean up resources."""
        global _browser, _context, _page, _initialized
        if not _initialized:
            return ToolResult(content="Browser is not running.")
        if _page:
            await _page.close()
        if _context:
            await _context.close()
        if _browser:
            await _browser.close()
        _page = None
        _context = None
        _browser = None
        _initialized = False
        _console_logs.clear()
        return ToolResult(content="Browser stopped.")

    async def _status(self) -> ToolResult:
        """Return current browser/page status."""
        if not _initialized:
            return ToolResult(content="Browser is not running.")
        page = _require_page()
        active = _active_tab_index()
        return ToolResult(content=json.dumps({
            "running": True,
            "url": page.url,
            "title": await page.title(),
            "active_tab": active,
            "tab_count": len(_list_pages()),
        }, ensure_ascii=False))

    async def _open(self, url: str | None = None) -> ToolResult:
        """Open a new tab, optionally navigating immediately."""
        await _ensure_browser()
        if _context is None:
            raise RuntimeError("Browser context is not available.")
        page = await _context.new_page()
        global _page
        _page = page
        if url:
            response = await page.goto(url, wait_until="domcontentloaded")
            title = await page.title()
            status = response.status if response else 0
            idx = _page_index(page)
            return ToolResult(content=f"Opened tab {idx}: [{status}] {title}\n{page.url}")
        idx = _page_index(page)
        return ToolResult(content=f"Opened tab {idx} (about:blank)")

    async def _focus(self, tab: int | None = None) -> ToolResult:
        """Switch the active tab."""
        if tab is None:
            raise ValueError("tab is required for focus action.")
        page = _require_page(tab)
        await page.bring_to_front()
        idx = _page_index(page)
        title = await page.title()
        return ToolResult(content=f"Focused tab {idx}: {title}\n{page.url}")

    async def _close(self, tab: int | None = None) -> ToolResult:
        """Close the specified tab (defaults to active)."""
        if not _initialized:
            return ToolResult(content="Browser is not running.")
        page = _require_page(tab)
        idx = _page_index(page)
        url = page.url
        await page.close()
        _console_logs.pop(id(page), None)
        remaining = _list_pages()
        global _page
        if _page is page:
            _page = remaining[0] if remaining else None
        return ToolResult(content=f"Closed tab {idx}: {url}")

    async def _console(
        self,
        tab: int | None = None,
        level: str | None = None,
        limit: int | None = None,
    ) -> ToolResult:
        """Return recent console messages from a tab."""
        page = _require_page(tab)
        idx = _page_index(page)
        entries = list(_console_logs.get(id(page), []))
        if level:
            level_lower = level.lower()
            entries = [
                entry for entry in entries
                if str(entry.get("type", "")).lower() == level_lower
            ]
        if limit is None:
            max_entries = DEFAULT_CONSOLE_LIMIT
        elif limit == 0:
            max_entries = None
        else:
            max_entries = _coerce_positive_int(limit, "limit")
        if max_entries:
            entries = entries[-max_entries:]
        payload = {"tab": idx, "entries": entries}
        return ToolResult(content=json.dumps(payload, indent=2, ensure_ascii=False))

    # ── navigation ──────────────────────────────────────────────────────────

    async def _navigate(self, url: str, tab: int | None = None) -> ToolResult:
        """Navigate to the given URL."""
        await _ensure_browser(headless=True)
        page = _require_page(tab)
        response = await page.goto(url, wait_until="domcontentloaded")
        title = await page.title()
        status = response.status if response else 0
        return ToolResult(content=f"[{status}] {title}\n{page.url}")

    async def _back(self, tab: int | None = None) -> ToolResult:
        """Go back in browser history."""
        page = _require_page(tab)
        await page.go_back(wait_until="domcontentloaded")
        return ToolResult(content=f"Back: {page.url}")

    async def _forward(self, tab: int | None = None) -> ToolResult:
        """Go forward in browser history."""
        page = _require_page(tab)
        await page.go_forward(wait_until="domcontentloaded")
        return ToolResult(content=f"Forward: {page.url}")

    async def _reload(self, tab: int | None = None) -> ToolResult:
        """Reload the current page."""
        page = _require_page(tab)
        await page.reload(wait_until="domcontentloaded")
        return ToolResult(content=f"Reloaded: {page.url}")

    # ── inspection ─────────────────────────────────────────────────────────

    async def _snapshot(self, full: bool = False, tab: int | None = None) -> ToolResult:
        """Return an ARIA accessibility snapshot of the current page."""
        page = _require_page(tab)
        snapshot = await page.accessibility.snapshot(full=full)
        if snapshot is None:
            return ToolResult(content="No accessibility tree (page may be loading).")
        return ToolResult(content=json.dumps(snapshot, indent=2, ensure_ascii=False))

    async def _screenshot(self, filename: str | None = None, tab: int | None = None) -> ToolResult:
        """Take a PNG screenshot of the current page."""
        page = _require_page(tab)
        if filename:
            await page.screenshot(path=filename, type="png")
            return ToolResult(content=f"Screenshot saved to {filename}")
        # Return base64-encoded PNG
        image_bytes = await page.screenshot(type="png")
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return ToolResult(content=f"data:image/png;base64,{b64}")

    async def _tabs(self) -> ToolResult:
        """List all open browser tabs (pages)."""
        if not _initialized:
            return ToolResult(content="Browser is not running.")
        pages = _list_pages()
        rows = []
        for i, p in enumerate(pages):
            try:
                title = await p.title()
            except Exception:  # noqa: BLE001
                title = "(title unavailable)"
            rows.append({
                "index": i,
                "url": p.url,
                "title": title,
                "active": p is _page,
                "console_entries": len(_console_logs.get(id(p), [])),
            })
        return ToolResult(content=json.dumps({"tabs": rows}, indent=2, ensure_ascii=False))

    async def _evaluate(self, script: str, tab: int | None = None) -> ToolResult:
        """Execute a JavaScript expression in the page context."""
        if _looks_like_html_dump(script):
            return ToolResult(
                content=(
                    "Direct HTML/DOM dumps are disabled. "
                    "Use the snapshot action to inspect page structure."
                ),
                success=False,
                error="html_dump_blocked",
            )
        page = _require_page(tab)
        try:
            result = await page.evaluate(script)
            return ToolResult(content=json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as exc:
            return ToolResult(content=f"Script error: {exc}", success=False, error=str(exc))

    # ── interaction ─────────────────────────────────────────────────────────

    async def _click(self, selector: str, tab: int | None = None) -> ToolResult:
        """Click an element identified by a CSS selector."""
        page = _require_page(tab)
        await page.click(selector, timeout=10000)
        return ToolResult(content=f"Clicked: {selector}")

    async def _type(
        self,
        selector: str,
        text: str,
        submit: bool = False,
        tab: int | None = None,
    ) -> ToolResult:
        """Type text into an input field; optionally submit the form."""
        page = _require_page(tab)
        await page.fill(selector, text)
        if submit:
            await page.press(selector, "Enter")
            return ToolResult(content=f"Typed into {selector} and submitted")
        return ToolResult(content=f"Typed into: {selector}")

    async def _press(
        self,
        selector: str | None = None,
        key: str = "",
        tab: int | None = None,
    ) -> ToolResult:
        """Press a keyboard key. If selector is provided, focuses element first."""
        page = _require_page(tab)
        if selector:
            await page.press(selector, key)
        else:
            await page.keyboard.press(key)
        return ToolResult(content=f"Pressed: {key}" + (f" on {selector}" if selector else ""))

    async def _hover(self, selector: str, tab: int | None = None) -> ToolResult:
        """Hover over an element."""
        page = _require_page(tab)
        await page.hover(selector)
        return ToolResult(content=f"Hovered: {selector}")

    async def _scroll(self, selector: str, tab: int | None = None) -> ToolResult:
        """Scroll the element into view."""
        page = _require_page(tab)
        await page.locator(selector).scroll_into_view_if_needed()
        return ToolResult(content=f"Scrolled to: {selector}")
