"""Pure-stdlib RFC 6455 TLS WebSocket client & WeCom AI Bot SDK.

Protocol endpoint: wss://openws.work.weixin.qq.com
Zero third-party dependencies — works out of the box on Python 3.10+ across
Windows, Linux, macOS, Docker, Termux, AWS Lambda, and GitHub Actions.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import struct
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

WECOM_WS_HOST = "openws.work.weixin.qq.com"
WECOM_WS_PORT = 443
WECOM_WS_PATH = "/"


class WeComBotError(RuntimeError):
    """Raised when WeCom WebSocket authentication or message delivery fails."""


@dataclass(frozen=True)
class BotMessage:
    """Normalized incoming message from WeCom `aibot_msg_callback`."""

    req_id: str
    chatid: str
    userid: str
    chattype: str
    msgtype: str
    text: str
    raw: dict[str, Any]

    @property
    def is_group(self) -> bool:
        return self.chattype == "group"


class MinimalWebSocketClient:
    """Pure-stdlib RFC 6455 client-side TLS WebSocket implementation."""

    def __init__(
        self,
        host: str = WECOM_WS_HOST,
        port: int = WECOM_WS_PORT,
        path: str = WECOM_WS_PATH,
    ) -> None:
        self.host = host
        self.port = port
        self.path = path
        self._sock: ssl.SSLSocket | None = None
        self._send_lock = threading.Lock()
        self._recv_buf = bytearray()

    def connect(self, timeout: float = 15.0) -> None:
        raw = socket.create_connection((self.host, self.port), timeout=timeout)
        ctx = ssl.create_default_context()
        self._sock = ctx.wrap_socket(raw, server_hostname=self.host)
        self._sock.settimeout(timeout)

        ws_key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {ws_key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "User-Agent: wecom-aibot-ws/0.1.0\r\n\r\n"
        )
        self._sock.sendall(req.encode("ascii"))

        header_bytes = bytearray()
        while b"\r\n\r\n" not in header_bytes:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("WebSocket handshake closed unexpectedly")
            header_bytes.extend(chunk)
            if len(header_bytes) > 65536:
                raise ConnectionError("WebSocket handshake header too large")

        sep_idx = header_bytes.index(b"\r\n\r\n") + 4
        head_text = header_bytes[:sep_idx].decode("utf-8", errors="replace")
        self._recv_buf = bytearray(header_bytes[sep_idx:])

        status_line = head_text.splitlines()[0] if head_text else ""
        if "101" not in status_line:
            raise ConnectionError(f"WebSocket handshake failed: {status_line}")

        self._sock.settimeout(65.0)

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        if not self._sock:
            raise ConnectionError("WebSocket is not connected")
        length = len(payload)
        header = bytearray([0x80 | (opcode & 0x0F)])
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))

        mask_key = os.urandom(4)
        header.extend(mask_key)
        masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        with self._send_lock:
            self._sock.sendall(bytes(header) + masked)

    def send_json(self, obj: dict[str, Any]) -> None:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send_frame(0x01, raw)

    def _read_exact(self, n: int) -> bytes:
        assert self._sock is not None
        while len(self._recv_buf) < n:
            chunk = self._sock.recv(max(4096, n - len(self._recv_buf)))
            if not chunk:
                raise EOFError("WebSocket connection closed")
            self._recv_buf.extend(chunk)
        out = bytes(self._recv_buf[:n])
        del self._recv_buf[:n]
        return out

    def recv_json(self) -> dict[str, Any] | None:
        fragments: list[bytes] = []
        while True:
            b1, b2 = self._read_exact(2)
            fin = bool(b1 & 0x80)
            opcode = b1 & 0x0F
            masked = bool(b2 & 0x80)
            length = b2 & 0x7F

            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]

            mask_key = self._read_exact(4) if masked else b""
            payload = self._read_exact(length) if length > 0 else b""
            if masked:
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

            if opcode == 0x08:
                raise EOFError("Server sent Close frame")
            if opcode == 0x09:
                self._send_frame(0x0A, payload)
                continue
            if opcode == 0x0A:
                continue
            if opcode in (0x01, 0x00):
                fragments.append(payload)
                if fin:
                    text = b"".join(fragments).decode("utf-8", errors="replace")
                    return json.loads(text) if text.strip() else None

    def close(self) -> None:
        sock = self._sock
        self._sock = None
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def send_oneshot_markdown(
    bot_id: str,
    secret: str,
    chatid: str,
    content: str,
    timeout: float = 12.0,
    ws_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Connect, authenticate, push one Markdown message, and cleanly close.

    Ideal for stateless environments such as GitHub Actions, cron jobs, and cloud functions.
    """
    if not bot_id.strip() or not secret.strip():
        raise WeComBotError("bot_id and secret are required")
    if not chatid.strip():
        raise WeComBotError("chatid is required")

    ws = (ws_factory or MinimalWebSocketClient)()
    try:
        ws.connect(timeout=max(timeout, 5.0))
        sub_req = f"aibot_subscribe_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        ws.send_json(
            {
                "cmd": "aibot_subscribe",
                "headers": {"req_id": sub_req},
                "body": {"bot_id": bot_id.strip(), "secret": secret.strip()},
            }
        )
        auth_resp = _wait_for_ack(ws, sub_req)
        if not auth_resp or int(auth_resp.get("errcode", -1)) != 0:
            raise WeComBotError(f"Authentication failed: {auth_resp}")

        msg_req = f"aibot_send_msg_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        ws.send_json(
            {
                "cmd": "aibot_send_msg",
                "headers": {"req_id": msg_req},
                "body": {
                    "chatid": chatid.strip(),
                    "msgtype": "markdown",
                    "markdown": {"content": content},
                },
            }
        )
        ack = _wait_for_ack(ws, msg_req)
        if not ack or int(ack.get("errcode", -1)) != 0:
            raise WeComBotError(f"Message delivery failed: {ack}")
        return ack
    finally:
        ws.close()


def _wait_for_ack(ws: Any, expected_req_id: str, max_frames: int = 12) -> dict[str, Any] | None:
    for _ in range(max_frames):
        frame = ws.recv_json()
        if not frame:
            continue
        if (frame.get("headers") or {}).get("req_id") == expected_req_id or "errcode" in frame:
            return frame
    return None


class WeComAIBotClient:
    """Persistent & serverless-ready client for WeCom AI Bot WebSocket API."""

    def __init__(
        self,
        bot_id: str,
        secret: str,
        heartbeat_interval: float = 28.0,
        ws_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.bot_id = bot_id.strip()
        self.secret = secret.strip()
        self.heartbeat_interval = heartbeat_interval
        self._ws_factory = ws_factory or MinimalWebSocketClient
        self._ws: Any | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._pending_lock = threading.Lock()
        self._pending_reqs: dict[str, tuple[threading.Event, dict[str, Any]]] = {}
        self._handlers: list[Callable[[BotMessage], str | None]] = []

        self.is_connected = False
        self.is_authenticated = False
        self.last_error = ""

    def on_message(self, func: Callable[[BotMessage], str | None]) -> Callable[[BotMessage], str | None]:
        """Decorator to register a handler for incoming group or direct messages."""
        self._handlers.append(func)
        return func

    def start_background(self) -> None:
        """Start the persistent WebSocket listener in a daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run_forever, name="WeComAIBotWS", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the background loop and close the active WebSocket."""
        self._stop_event.set()
        if self._ws:
            self._ws.close()

    def run_forever(self) -> None:
        """Blocking loop with auto-reconnect and 28s ping keepalive."""
        backoff = 2.0
        while not self._stop_event.is_set():
            ws = self._ws_factory()
            self._ws = ws
            try:
                ws.connect(timeout=15.0)
                self.is_connected = True
                self.last_error = ""

                sub_req = f"aibot_subscribe_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
                ws.send_json(
                    {
                        "cmd": "aibot_subscribe",
                        "headers": {"req_id": sub_req},
                        "body": {"bot_id": self.bot_id, "secret": self.secret},
                    }
                )
                auth_resp = _wait_for_ack(ws, sub_req)
                if not auth_resp or int(auth_resp.get("errcode", -1)) != 0:
                    raise WeComBotError(f"Authentication failed: {auth_resp}")

                self.is_authenticated = True
                backoff = 2.0

                hb_stop = threading.Event()
                threading.Thread(target=self._heartbeat_loop, args=(ws, hb_stop), daemon=True).start()
                try:
                    while not self._stop_event.is_set():
                        frame = ws.recv_json()
                        if frame:
                            self._handle_frame(ws, frame)
                finally:
                    hb_stop.set()
            except Exception as exc:
                self.is_connected = False
                self.is_authenticated = False
                self.last_error = str(exc)
            finally:
                ws.close()
                self._ws = None

            if not self._stop_event.is_set():
                self._stop_event.wait(timeout=backoff)
                backoff = min(30.0, backoff * 1.8)

    def _heartbeat_loop(self, ws: Any, hb_stop: threading.Event) -> None:
        while not hb_stop.is_set() and not self._stop_event.is_set():
            hb_stop.wait(timeout=self.heartbeat_interval)
            if hb_stop.is_set() or self._stop_event.is_set():
                break
            try:
                ws.send_json(
                    {
                        "cmd": "ping",
                        "headers": {"req_id": f"ping_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"},
                    }
                )
            except Exception:
                ws.close()
                break

    def _handle_frame(self, ws: Any, frame: dict[str, Any]) -> None:
        cmd = str(frame.get("cmd") or "")
        headers = frame.get("headers") or {}
        req_id = str(headers.get("req_id") or "")

        if req_id:
            with self._pending_lock:
                entry = self._pending_reqs.get(req_id)
            if entry:
                ev, box = entry
                box.update(frame)
                ev.set()

        if cmd == "aibot_msg_callback":
            body = frame.get("body") or {}
            chattype = str(body.get("chattype") or "single")
            userid = str((body.get("from") or {}).get("userid") or "")
            chatid = str(body.get("chatid") or userid or "").strip()
            if chattype != "group" and userid:
                chatid = userid
            msg = BotMessage(
                req_id=req_id,
                chatid=chatid,
                userid=userid,
                chattype=chattype,
                msgtype=str(body.get("msgtype") or "text"),
                text=str((body.get("text") or {}).get("content") or "").strip(),
                raw=frame,
            )
            for handler in self._handlers:
                reply = handler(msg)
                if reply and req_id:
                    ws.send_json(
                        {
                            "cmd": "aibot_respond_msg",
                            "headers": {"req_id": req_id},
                            "body": {
                                "msgtype": "stream",
                                "stream": {
                                    "id": f"st_{uuid.uuid4().hex[:10]}",
                                    "finish": True,
                                    "content": reply,
                                },
                            },
                        }
                    )
                    break

    def send_markdown(self, chatid: str, content: str, timeout: float = 10.0) -> dict[str, Any]:
        """Proactively push Markdown via active connection, or fallback to one-shot WebSocket."""
        if not self._ws or not self.is_authenticated:
            if self._thread and self._thread.is_alive():
                raise WeComBotError("Persistent WebSocket is still connecting")
            return send_oneshot_markdown(
                bot_id=self.bot_id,
                secret=self.secret,
                chatid=chatid,
                content=content,
                timeout=timeout,
                ws_factory=self._ws_factory,
            )

        req_id = f"aibot_send_msg_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        ev = threading.Event()
        box: dict[str, Any] = {}
        with self._pending_lock:
            self._pending_reqs[req_id] = (ev, box)
        try:
            self._ws.send_json(
                {
                    "cmd": "aibot_send_msg",
                    "headers": {"req_id": req_id},
                    "body": {
                        "chatid": chatid.strip(),
                        "msgtype": "markdown",
                        "markdown": {"content": content},
                    },
                }
            )
            if not ev.wait(timeout=timeout):
                raise TimeoutError(f"Timed out waiting for WeCom ack ({chatid})")
            if int(box.get("errcode", -1)) != 0:
                raise WeComBotError(f"Delivery failed: {box}")
            return box
        finally:
            with self._pending_lock:
                self._pending_reqs.pop(req_id, None)
