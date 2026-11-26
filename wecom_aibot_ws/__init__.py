"""Zero-dependency Python SDK for WeCom (Enterprise WeChat) AI Bot WebSocket API."""

from .client import (
    WECOM_WS_HOST,
    WECOM_WS_PORT,
    BotMessage,
    MinimalWebSocketClient,
    WeComAIBotClient,
    WeComBotError,
    send_oneshot_markdown,
)

__version__ = "0.1.0"
__all__ = [
    "WECOM_WS_HOST",
    "WECOM_WS_PORT",
    "BotMessage",
    "MinimalWebSocketClient",
    "WeComAIBotClient",
    "WeComBotError",
    "send_oneshot_markdown",
    "__version__",
]
