"""Unit tests for wecom-aibot-ws."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wecom_aibot_ws import (  # noqa: E402
    BotMessage,
    WeComAIBotClient,
    WeComBotError,
    send_oneshot_markdown,
)


class FakeWS:
    def __init__(self, auth_errcode: int = 0, send_errcode: int = 0) -> None:
        self.auth_errcode = auth_errcode
        self.send_errcode = send_errcode
        self.sent: list[dict] = []
        self.queue: list[dict] = []
        self.closed = False

    def connect(self, timeout: float = 12.0) -> None:
        pass

    def send_json(self, obj: dict) -> None:
        self.sent.append(obj)
        req_id = (obj.get("headers") or {}).get("req_id", "")
        if obj.get("cmd") == "aibot_subscribe":
            self.queue.append({"headers": {"req_id": req_id}, "errcode": self.auth_errcode, "errmsg": "ok"})
        elif obj.get("cmd") == "aibot_send_msg":
            # Inject an unrelated callback frame before ack to verify robust frame filtering
            self.queue.append({"cmd": "aibot_event_callback", "body": {}})
            self.queue.append({"headers": {"req_id": req_id}, "errcode": self.send_errcode, "errmsg": "ok"})

    def recv_json(self) -> dict | None:
        return self.queue.pop(0) if self.queue else None

    def close(self) -> None:
        self.closed = True


class TestWeComAIBotWS(unittest.TestCase):
    def test_oneshot_markdown_delivery_and_close(self) -> None:
        holder: list[FakeWS] = []

        def factory() -> FakeWS:
            ws = FakeWS()
            holder.append(ws)
            return ws

        ack = send_oneshot_markdown(
            bot_id="aib_demo",
            secret="sec_demo",
            chatid="wr_group_demo",
            content="**Hello** world",
            ws_factory=factory,
        )
        self.assertEqual(ack["errcode"], 0)
        self.assertTrue(holder[0].closed)
        self.assertEqual(holder[0].sent[0]["cmd"], "aibot_subscribe")
        self.assertEqual(holder[0].sent[1]["cmd"], "aibot_send_msg")
        self.assertEqual(holder[0].sent[1]["body"]["chatid"], "wr_group_demo")

    def test_oneshot_auth_error_raises(self) -> None:
        with self.assertRaises(WeComBotError):
            send_oneshot_markdown(
                bot_id="aib_bad",
                secret="sec_bad",
                chatid="wr_group",
                content="hi",
                ws_factory=lambda: FakeWS(auth_errcode=40001),
            )

    def test_on_message_decorator_handles_group_and_single(self) -> None:
        bot = WeComAIBotClient("aib_1", "sec_1")
        captured: list[BotMessage] = []

        @bot.on_message
        def reply(msg: BotMessage) -> str:
            captured.append(msg)
            return f"ack:{msg.chatid}:{msg.is_group}"

        ws = FakeWS()
        bot._handle_frame(
            ws,
            {
                "cmd": "aibot_msg_callback",
                "headers": {"req_id": "req_100"},
                "body": {
                    "chattype": "group",
                    "chatid": "wr_team_01",
                    "from": {"userid": "alice"},
                    "msgtype": "text",
                    "text": {"content": "@Bot status"},
                },
            },
        )
        self.assertEqual(len(captured), 1)
        self.assertTrue(captured[0].is_group)
        self.assertEqual(captured[0].chatid, "wr_team_01")
        self.assertEqual(ws.sent[0]["cmd"], "aibot_respond_msg")
        self.assertEqual(ws.sent[0]["body"]["stream"]["content"], "ack:wr_team_01:True")

    def test_client_send_markdown_falls_back_to_oneshot_when_idle(self) -> None:
        ws = FakeWS()
        bot = WeComAIBotClient("aib_1", "sec_1", ws_factory=lambda: ws)
        ack = bot.send_markdown("wr_team_01", "**Alert**")
        self.assertEqual(ack["errcode"], 0)
        self.assertTrue(ws.closed)


if __name__ == "__main__":
    unittest.main()
