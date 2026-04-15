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
    - CLI      : auton/adapters/cli/main.py
    - Web      : auton/adapters/web/app.py
    - Slack    : auton/adapters/slack/adapter.py
    - Discord  : auton/adapters/discord/adapter.py
    - WhatsApp : auton/adapters/whatsapp/adapter.py
    - Feishu   : auton/adapters/feishu/adapter.py
"""

from .session_factory import SessionFactory
from .types import SessionContext

__all__ = [
    "SessionFactory",
    "SessionContext",
]
