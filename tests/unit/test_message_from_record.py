from auton.agent.message import Message


def test_from_record_handles_user_event():
    record = {"type": "user-message", "content": "你好", "timestamp": 123.0}
    msg = Message.from_record(record)
    assert msg
    assert msg.role == "user"
    assert msg.get_text() == "你好"


def test_from_record_handles_assistant_parts():
    record = {
        "role": "assistant",
        "parts": [
            {"type": "text", "content": "Hello"},
            {"type": "tool", "tool_name": "read", "tool_input": {"path": "a"}, "status": "completed"},
        ],
    }
    msg = Message.from_record(record)
    assert msg
    assert msg.role == "assistant"
    assert msg.get_text() == "Hello"
