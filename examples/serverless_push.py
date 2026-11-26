"""One-shot serverless push example (for GitHub Actions / Cron / AWS Lambda)."""

import os
from wecom_aibot_ws import send_oneshot_markdown

ack = send_oneshot_markdown(
    bot_id=os.environ["WECOM_BOT_ID"],
    secret=os.environ["WECOM_BOT_SECRET"],
    chatid=os.environ["WECOM_CHATID"],
    content="**🚀 云端构建完成**\n- 状态：`Success`\n- 环境：`GitHub Actions (Zero Dependencies)`",
)
print("Delivered:", ack)
