"""Auton 接入层 — 多平台适配器

支持的平台：
    - CLI      : auton/adapters/cli/main.py
    - Web      : auton/adapters/web/app.py
    - Slack    : auton/adapters/slack/adapter.py
    - Discord  : auton/adapters/discord/adapter.py
    - WhatsApp : auton/adapters/whatsapp/adapter.py
    - Feishu   : auton/adapters/feishu/adapter.py

快速启动示例：

    # Slack
    from auton.adapters.slack import run_slack_adapter
    run_slack_adapter(session_mode="chat")

    # Discord
    from auton.adapters.discord import run_discord_adapter
    run_discord_adapter(token="YOUR_TOKEN")

    # WhatsApp
    from auton.adapters.whatsapp import run_whatsapp_adapter
    run_whatsapp_adapter()

    # Feishu
    from auton.adapters.feishu import run_feishu_adapter
    run_feishu_adapter()
"""

from . import cli
from . import web

# 可选平台适配器：仅在依赖已安装时加载，缺失时静默跳过
def _try_import(name: str) -> None:
    try:
        import importlib
        importlib.import_module(f".{name}", package=__name__)
    except (ImportError, ModuleNotFoundError):
        pass

_try_import("slack")
_try_import("discord")
_try_import("feishu")
_try_import("whatsapp")

__all__ = [
    "cli",
    "web",
    "slack",
    "discord",
    "feishu",
    "whatsapp",
]
