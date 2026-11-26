<div align="center">

# ⚡ wecom-aibot-ws

**Zero-Dependency Python SDK for WeCom (Enterprise WeChat) AI Bot WebSocket API**  
**纯 Python 标准库、零第三方依赖的企业微信「智能机器人 API 长连接 & 云函数短连接」轻量 SDK**

[![CI](https://github.com/tianou10086-create/wecom-aibot-ws/actions/workflows/ci.yml/badge.svg)](https://github.com/tianou10086-create/wecom-aibot-ws/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Dependencies: 0](https://img.shields.io/badge/Dependencies-0%20(Pure%20Stdlib)-brightgreen)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 🎯 解决什么痛点？ (Why `wecom-aibot-ws`?)

企业微信（WeCom）推出了全新的**智能机器人 API 长连接模式**（`wss://openws.work.weixin.qq.com`）：**无需公网服务器、无需固定公网 IP、无需备案域名与回调加解密**，仅凭 `Bot ID` 和 `Secret` 即可收发群聊/单聊消息！

但官方目前仅提供了 Node.js SDK（`@wecom/aibot-node-sdk`）。在 Python 环境（尤其是 **GitHub Actions 定时任务、云函数 Serverless、Docker 精简镜像、内网受限机器**）中，安装复杂的异步第三方依赖往往很繁琐。

`wecom-aibot-ws` 用 **不到 350 行纯 Python 标准库代码** 完整实现了 RFC 6455 TLS WebSocket 与企微智能机器人协议：
- ✅ **零第三方依赖（`dependencies = []`）**：标准库 `ssl` + `socket` 直连，拷走单文件也能跑；
- ✅ **双模合一**：既支持 **7×24 常驻长连接双向对话**（内置 28s `ping` 保活 + 指数退避自动重连），又支持 **Serverless 一次性短连接主动推送**（专为 GitHub Actions / Crontab / AWS Lambda 设计，发完即关不挂起进程）；
- ✅ **自动区分群聊与私聊**：清晰解析 `BotMessage.is_group`、`chatid` 与 `userid`。

---

## 📦 安装 (Installation)

```bash
pip install git+https://github.com/tianou10086-create/wecom-aibot-ws.git
```

或者直接将 [`wecom_aibot_ws/client.py`](wecom_aibot_ws/client.py) 单文件复制到你的项目中即可使用！

---

## 🚀 5 行代码快速上手 (Quickstart)

### 场景 1：GitHub Actions / Crontab 无状态主动推送（One-Shot Push）

无需后台守护线程，一行调用完成 `TLS 握手 → aibot_subscribe 鉴权 → aibot_send_msg 推送 → 安全关闭连接`：

```python
from wecom_aibot_ws import send_oneshot_markdown

send_oneshot_markdown(
    bot_id="aib_your_bot_id",
    secret="your_bot_secret",
    chatid="wr_your_group_or_user_chatid",
    content="**🚀 监控提醒**\n- 服务状态：`正常`\n- 来自：`wecom-aibot-ws` 零依赖直推",
)
```

> 💡 **如何首次获取企微群的 `chatid`？**  
> 将智能机器人拉入企业微信群（后台需将机器人设为「多人可用」），在本地运行下方「场景 2」脚本并在群内 `@机器人` 说一句话，终端就会打印出该群的 `chatid`（形如 `wr...`），保存后即可用于云端定时主动推送！

### 场景 2：常驻长连接双向互动机器人（Persistent Bot）

```python
from wecom_aibot_ws import BotMessage, WeComAIBotClient

bot = WeComAIBotClient(bot_id="aib_your_bot_id", secret="your_bot_secret")

@bot.on_message
def handle(msg: BotMessage) -> str:
    print(f"收到来自 {msg.chatid} (群聊={msg.is_group}) 的消息: {msg.text}")
    return f"✅ 已收到：**{msg.text}**\n当前会话 `chatid`: `{msg.chatid}`"

bot.run_forever()  # 内置 28s 心跳保活与断线自动重连
```

---

## 🔌 支持的协议帧 (Protocol Coverage)

| 企微协议命令 (`cmd`) | 用途 | 支持状态 |
| :--- | :--- | :---: |
| `aibot_subscribe` | `Bot ID` + `Secret` 长连接订阅鉴权 | ✅ |
| `ping` / WebSocket `Pong` | 28 秒应用层心跳保活与底层控制帧响应 | ✅ |
| `aibot_msg_callback` | 接收群聊 `@机器人` 与单聊私信回调 | ✅ |
| `aibot_respond_msg` | 流式 / 一次性回复用户提问 (`stream`) | ✅ |
| `aibot_send_msg` | 主动向指定群聊 `chatid` 或个人 `userid` 推送 Markdown | ✅ |

---

## 🧪 运行单元测试

```bash
python -m unittest discover -s tests -v
```

---

## 🔗 实战案例与生态项目 (Built With `wecom-aibot-ws`)

- 📡 **[AI WoolRadar (`woolradar`)](https://github.com/tianou10086-create/woolradar)** — 零依赖 AI 免费额度、开发者补贴与拉闸失效预警雷达（使用本库实现 GitHub Actions 云端直推企微群）。
- 🖥️ **[TBOX](https://tboxapp.top)** — Windows 桌面级实时会议/演讲语音辅助与提词助手。

如果这个轻量小轮子帮你省下了折腾企微回调与依赖的时间，欢迎点一颗 **⭐ Star**！
