"""Unit tests for browser tool helper logic."""

from __future__ import annotations

from auton.tools.browser import _looks_like_html_dump


def test_html_dump_detection_flags_common_patterns():
    assert _looks_like_html_dump("return document.documentElement.outerHTML;")
    assert _looks_like_html_dump("document.body.innerHTML")


def test_html_dump_detection_allows_other_scripts():
    assert not _looks_like_html_dump("return document.title;")
    assert not _looks_like_html_dump("() => window.location.href")
