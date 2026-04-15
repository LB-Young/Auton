"""compress/sanitizer.py — Tool pair 清理（Post-pass）

压缩后可能出现孤立的 tool_call 或 tool_result，需要修复以避免 API 报错。
"""

from __future__ import annotations


def sanitize_tool_pairs(messages: list[dict]) -> list[dict]:
    """修复压缩后的 orphaned tool_call / tool_result 对。

    两种失败模式：
      1. tool_result 引用了被压缩的 tool_call → 删除 orphaned result
      2. assistant message 有 tool_calls 但结果被压缩 → 插入 stub result

    Args:
        messages: 压缩后的消息列表（dict 格式）

    Returns:
        清理后的消息列表
    """
    # 收集所有存活的 tool_call id
    surviving_call_ids: set[str] = set()
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                cid = _get_tool_call_id(tc)
                if cid:
                    surviving_call_ids.add(cid)

    # 收集所有 tool_result 的 id
    result_call_ids: set[str] = set()
    for msg in messages:
        if msg.get("role") == "tool":
            cid = msg.get("tool_call_id", "")
            if cid:
                result_call_ids.add(cid)

    # 删除 orphaned tool_result（引用了被压缩掉的 tool_call）
    orphaned_results = result_call_ids - surviving_call_ids
    if orphaned_results:
        messages = [
            m for m in messages
            if not (m.get("role") == "tool" and m.get("tool_call_id") in orphaned_results)
        ]

    # 插入 stub tool_result（tool_call 存在但结果被压缩）
    missing_results = surviving_call_ids - result_call_ids
    if missing_results:
        patched: list[dict] = []
        for msg in messages:
            patched.append(msg)
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls") or []:
                    cid = _get_tool_call_id(tc)
                    if cid in missing_results:
                        patched.append({
                            "role": "tool",
                            "content": "[结果已压缩，详见上文摘要]",
                            "tool_call_id": cid,
                        })
        messages = patched

    return messages


def _get_tool_call_id(tc: object) -> str:
    """从 tool_call 中提取 id（支持 dict 和对象两种格式）"""
    if isinstance(tc, dict):
        return tc.get("id", "")
    return getattr(tc, "id", "") or ""
