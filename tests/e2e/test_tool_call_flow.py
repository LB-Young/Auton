"""E2E Test 2: 工具调用完整流程

测试路径：
  用户输入 → LLM决定调用工具 → SessionProcessor._execute_tools() → Tool.execute()
  → 工具结果写入 session messages → 下一轮 LLM 基于结果继续

目的：
  - 理解工具调用状态机：pending → running → completed/error
  - 理解 SessionProcessor._execute_tools() 如何驱动工具执行
  - 理解工具结果如何注入 session.messages 续上下文
  - 可以在以下位置打断点：
      - auton/agent/agent.py:296  (tool_use 事件处理)
      - auton/agent/agent.py:314  (_execute_tools)
      - auton/agent/agent.py:337  (tool.execute())
      - auton/agent/message.py:136 (add_tool)
      - auton/agent/message.py:348 (result 注入 session)

运行方式：
  pytest tests/e2e/test_tool_call_flow.py -v
  python -m tests.e2e.test_tool_call_flow
"""

import asyncio
import sys
from pathlib import Path
from typing import AsyncIterator

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from auton.agent.session import Session
from auton.agent.session_store import SessionStore
from auton.agent.agent import SessionProcessor
from auton.agent.policies import DecisionPolicy, PolicyInput
from auton.agent.types import LLMContext, ProcessResult  # noqa: F401
from auton.llm.base import (
    LLMProvider,
    LLMStreamEvent,
    TextStartEvent,
    TextDeltaEvent,
    TextFinishEvent,
    ToolUseEvent,
    ContentBlockStopEvent,
)
from auton.tools.base import Tool, ToolResult


# ─── Mock 工具：EchoTool（返回输入的翻转字符串）───────────────────────────────

class EchoTool(Tool):
    """测试用工具：将输入的 text 字段内容翻转返回"""

    name = "echo"
    description = "Echoes the input text, reversed. Input: {text: str}"

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to echo back"},
                },
                "required": ["text"],
            },
        }

    async def execute(self, text: str = "") -> ToolResult:
        reversed_text = text[::-1]
        return ToolResult(content=f"Reversed: {reversed_text}")


# ─── Mock LLM：第一次返回工具调用，第二次返回文本 ────────────────────────────

class MockToolCallProvider(LLMProvider):
    """模拟先调用工具、再返回文本的 LLM

    第1次 llm.stream() → tool_use 事件
    第2次 llm.stream() → 文本回复（接收到工具结果后）
    """

    def __init__(self, tool_name: str = "echo", tool_input: dict | None = None) -> None:
        super().__init__(model="mock-model")
        self.tool_name = tool_name
        self.tool_input = tool_input or {"text": "hello"}
        self._stream_call_count = 0

    async def stream(self, ctx: LLMContext) -> AsyncIterator[LLMStreamEvent]:
        self._stream_call_count += 1
        if self._stream_call_count == 1:
            # 第一次调用：触发工具
            yield ToolUseEvent(
                id="call_1",
                name=self.tool_name,
                input=self.tool_input,
            )
            yield ContentBlockStopEvent()
        else:
            # 第二次调用：返回文本（基于工具结果）
            text = f"工具已执行，输入翻转后: {self.tool_input['text'][::-1]}"
            yield TextStartEvent()
            for ch in text:
                yield TextDeltaEvent(delta=ch)
            yield TextFinishEvent(full_text=text)


# ─── 两轮决策策略：第一轮 continue（允许工具执行），第二轮 stop ──────────────

class TwoRoundPolicy(DecisionPolicy):
    """两轮策略：第1轮返回 continue 让工具执行，第2轮返回 stop 结束会话"""

    def __init__(self) -> None:
        super().__init__()
        self._decide_count = 0

    def decide(self, inp: PolicyInput) -> ProcessResult:
        self._decide_count += 1
        if self._decide_count == 1:
            return ProcessResult(status="continue", reason="first round: execute tool")
        else:
            return ProcessResult(status="stop", reason="second round: done")


# ─── 测试 ────────────────────────────────────────────────────────────────────

async def test_tool_call_flow():
    """端到端：用户输入 → LLM工具调用 → 工具执行 → LLM基于结果继续"""

    import tempfile

    storage_dir = Path(tempfile.mkdtemp(prefix="auton_test_tool_"))
    session_store = SessionStore(storage_dir)
    session = Session.create()
    query = "请用 echo 工具处理 hello"

    session.add_user_message(query)

    # 使用自定义 Mock 工具集（只有 EchoTool）
    tools = [EchoTool()]
    llm = MockToolCallProvider(tool_name="echo", tool_input={"text": "hello"})

    processor = SessionProcessor(
        session=session,
        llm=llm,
        tools=tools,
        session_store=session_store,
        policy=TwoRoundPolicy(),
    )

    # 收集完整事件流
    all_events: list[LLMStreamEvent] = []
    tool_calls: list[ToolUseEvent] = []
    text_deltas: list[str] = []

    async for event in processor.run_stream():
        all_events.append(event)
        # ProcessResult (decision) 没有 type，跳过
        if not hasattr(event, "type"):
            continue
        if event.type == "tool_use":
            tool_calls.append(event)
        elif event.type == "text_delta":
            text_deltas.append(getattr(event, "delta", ""))

    # 验证：LLM 发起了工具调用
    assert len(tool_calls) >= 1, f"Expected at least 1 tool call, got {len(tool_calls)}"
    assert tool_calls[0].name == "echo", f"Expected 'echo', got '{tool_calls[0].name}'"
    assert tool_calls[0].input == {"text": "hello"}

    # 验证：session 中有工具结果消息
    tool_result_msgs = [
        m for m in session.messages
        if m.role == "user" and "[tool:" in m.get_text()
    ]
    assert len(tool_result_msgs) >= 1, "Expected at least one tool result in session.messages"

    first_result = tool_result_msgs[0].get_text()
    assert "Reversed: olleh" in first_result, f"Unexpected tool result: {first_result}"

    # 验证：最终 LLM 给出了文本回复
    full_text = "".join(text_deltas)
    assert "olleh" in full_text, f"Expected 'olleh' in response, got: {full_text}"

    # 验证：session 消息数量合理（user + assistant + tool_result + final assistant）
    assert len(session.messages) >= 4, (
        f"Expected >= 4 messages (user, assistant+tool, user+tool_result, assistant), "
        f"got {len(session.messages)}"
    )

    print(f"\n[PASS] test_tool_call_flow")
    print(f"  session_id  : {session.meta.session_id}")
    print(f"  messages    : {len(session.messages)}")
    print(f"  tool_calls  : {[e.name for e in tool_calls]}")
    print(f"  tool_result : {first_result[:80]}")
    print(f"  final_text  : {full_text[:80]}")


if __name__ == "__main__":
    asyncio.run(test_tool_call_flow())
