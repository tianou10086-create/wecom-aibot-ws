"""Minimal 10-line interactive WeCom AI Bot example."""

import os
from wecom_aibot_ws import BotMessage, WeComAIBotClient

bot = WeComAIBotClient(
    bot_id=os.environ["WECOM_BOT_ID"],
    secret=os.environ["WECOM_BOT_SECRET"],
)


@bot.on_message
def handle_reply(msg: BotMessage) -> str:
    print(f"[{msg.chattype}] chatid={msg.chatid} user={msg.userid}: {msg.text}")
    return f"收到消息：`{msg.text}`\n当前会话 ID (`chatid`)：`{msg.chatid}`"


if __name__ == "__main__":
    print("WeCom AI Bot listening via wss://openws.work.weixin.qq.com ...")
    bot.run_forever()
