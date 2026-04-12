"""项目模式确认意图解析。"""

from __future__ import annotations


def parse_project_mode_reply(text: str) -> bool | None:
    """解析用户是否确认按项目模式开启。

    Returns:
        True: 明确同意项目模式
        False: 明确拒绝项目模式
        None: 无法判断
    """
    normalized = (text or "").strip().lower()
    if not normalized:
        return None

    explicit_negative_patterns = [
        "不是项目模式",
        "不可以项目模式",
        "不要项目模式",
        "别用项目模式",
        "先不项目模式",
        "暂不项目模式",
        "不按项目模式",
        "不用项目模式",
        "先不要项目模式",
        "暂时不要项目模式",
    ]
    for pattern in explicit_negative_patterns:
        if pattern in normalized:
            return False

    negative_keywords = [
        "否",
        "不用",
        "不需要",
        "普通模式",
        "闲聊模式",
        "date模式",
        "日期模式",
    ]
    for kw in negative_keywords:
        if kw in normalized:
            return False

    positive_phrases = [
        "按项目模式",
        "切到项目模式",
        "开启项目模式",
        "进入项目模式",
        "用项目模式",
    ]
    for phrase in positive_phrases:
        if phrase in normalized:
            return True

    if normalized in {"是", "是的", "好的", "可以", "行", "好"}:
        return True
    return None

