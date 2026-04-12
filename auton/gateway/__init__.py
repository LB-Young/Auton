"""Gateway — 统一接入层

提供各平台接入 Auton 的统一入口。

快速上手：

    from auton.gateway import SessionFactory

    async def main():
        ctx = await SessionFactory().build(session_mode="project")
        ctx.session.add_user_message("帮我读一下 README")
        async for event in ctx.processor.run_stream():
            if hasattr(event, "type") and event.type == "text_delta":
                print(event.delta, end="", flush=True)

支持的接入方式：
    - CLI      : auton/cli/main.py
    - Web      : auton/web/app.py
    - Slack    : auton/gateway/adapters/slack.py  （待实现）
    - 飞书      : auton/gateway/adapters/feishu.py （待实现）
"""

from .session_factory import SessionFactory
from .types import SessionContext

__all__ = [
    "SessionFactory",
    "SessionContext",
]
