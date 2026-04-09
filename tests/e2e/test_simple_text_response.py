"""E2E Test 1: 纯文本回复流程

测试路径：用户输入 → Session → SessionProcessor.run_stream() → LLM流式响应 → 返回

目的：
  - 熟悉核心链路：Session.add_user_message → SessionProcessor.run_stream → yield TextDeltaEvent
  - 验证 Message / TextPart / LLMContext 构建链路
  - 可以在以下位置打断点：
      - auton/agent/session.py:57   (add_user_message)
      - auton/agent/agent.py:257   (_handle_llm_event)
      - auton/agent/agent.py:193   (run_stream)
      - auton/llm/base.py:98       (LLMProvider.stream)

运行方式：
  pytest tests/e2e/test_simple_text_response.py -v
  # 或直接 python 运行（方便打断点）
  python -m tests.e2e.test_simple_text_response
"""

import asyncio
import sys
from pathlib import Path
from typing import AsyncIterator

# 确保项目根在 import 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from auton.agent.session import Session
from auton.agent.session_store import SessionStore
from auton.agent.agent import SessionProcessor
from auton.agent.message import Message
from auton.agent.context import ContextBuilder
from auton.agent.types import LLMContext
from auton.llm.base import (
    LLMProvider,
    LLMStreamEvent,
    TextStartEvent,
    TextDeltaEvent,
    TextFinishEvent,
)
from auton.tools import get_default_tools


# ─── Mock LLM：只返回文本，不调用任何工具 ────────────────────────────────────

class MockTextOnlyProvider(LLMProvider):
    """模拟只返回文本的 LLM Provider"""

    def __init__(self, response_text: str = "你好！我是 Auton，一个 AI 助手。") -> None:
        super().__init__(model="mock-model")
        self.response_text = response_text

    async def stream(self, ctx: LLMContext) -> AsyncIterator[LLMStreamEvent]:
        """模拟流式输出：逐字 yield"""
        yield TextStartEvent()
        for ch in self.response_text:
            yield TextDeltaEvent(delta=ch)
        yield TextFinishEvent(full_text=self.response_text)


# ─── 测试 ────────────────────────────────────────────────────────────────────

async def test_simple_text_response():
    """端到端：用户输入 → 纯文本回复（无工具调用）"""

    # 1. 创建 Session 和 Store（使用临时目录）
    import tempfile
    storage_dir = Path(tempfile.mkdtemp(prefix="auton_test_"))

    session_store = SessionStore(storage_dir)
    session = Session.create()
    query = "你好，介绍一下你自己"

    # 2. 添加用户消息
    session.add_user_message(query)
    assert len(session.messages) == 1
    assert session.messages[0].role == "user"
    assert session.messages[0].get_text() == query

    # 3. 创建 Processor（使用 mock LLM）
    llm = MockTextOnlyProvider(response_text="我是 Auton，你的 AI 助手！")
    tools = get_default_tools()
    processor = SessionProcessor(
        session=session,
        llm=llm,
        tools=tools,
        session_store=session_store,
    )

    # 4. 收集流式事件
    events = []
    text_deltas: list[str] = []
    async for event in processor.run_stream():
        events.append(event)
        # ProcessResult 没有 type，跳过
        if not hasattr(event, "type"):
            continue
        if event.type == "text_delta":
            text_deltas.append(getattr(event, "delta", ""))

    # 5. 验证结果
    full_text = "".join(text_deltas)
    assert full_text == "我是 Auton，你的 AI 助手！", f"Expected text, got: {full_text}"

    # 验证 session 中有用户消息和助手消息
    assert len(session.messages) >= 2
    assert session.messages[0].role == "user"
    assert session.messages[-1].role == "assistant"

    # 验证 session_store 中有 user message
    stored = session_store.read_session(session.meta.session_id)
    assert len(stored) > 0
    assert any(e.get("type") == "user-message" for e in stored)

    print(f"\n[PASS] test_simple_text_response")
    print(f"  session_id : {session.meta.session_id}")
    print(f"  messages   : {len(session.messages)}")
    print(f"  full_text  : {full_text}")
    print(f"  stored     : {len(stored)} events")


if __name__ == "__main__":
    asyncio.run(test_simple_text_response())
