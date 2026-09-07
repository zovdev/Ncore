# Copyright 2026 zovdev
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import ssl
import gzip
import zlib
import hmac
import struct
import asyncio

from re import compile as re_compile
from time import monotonic, time
from random import random, choice
from os import urandom
from collections import deque
from base64 import b64encode, urlsafe_b64encode
from hashlib import sha1, sha256
from urllib.parse import parse_qs, unquote


OPEN, DATA, CLOSE, WINDOW = 0x01, 0x02, 0x03, 0x04
PING, PONG, HELLO, WELCOME, BYE = 0x05, 0x06, 0x10, 0x11, 0x1F

FRAME_HEADER = 8
MAX_PAYLOAD = 1 << 20
MAX_BATCH_FRAMES = 4096
DATA_CHUNK = 64 << 10
INITIAL_WINDOW = 4 << 20
MAX_STREAM_ID = 0xFFFFFF
DEFAULT_BATCH = 2 << 20
MIN_BATCH = 256 << 10

CARRIER_MODES = {"https", "https-lanes", "websocket", "websocket-lanes"}

_BRIDGE_LABEL = b"tdesktop-web-proxy-bridge-v1\n"
_WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

_BRIDGE_BOOTSTRAP_RE = re_compile(rb'bootstrap="([A-Za-z0-9_-]{43})"')
_BRIDGE_MODE_RE = re_compile(rb'carrierMode="([a-z-]+)"')
_BRIDGE_BATCH_RE = re_compile(rb'batchLimit=(\d{1,8})')


_UA_PROFILES = (
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "brands": '"Chromium";v="140", "Not/A)Brand";v="24", '
                  '"Google Chrome";v="140"',
        "platform": "Windows",
    },
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "brands": '"Chromium";v="140", "Not/A)Brand";v="24", '
                  '"Google Chrome";v="140"',
        "platform": "macOS",
    },
    {
        "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "brands": '"Chromium";v="140", "Not/A)Brand";v="24", '
                  '"Google Chrome";v="140"',
        "platform": "Linux",
    },
)

_NAVIGATE_ACCEPT = ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,image/apng,*/*;q=0.8,"
                    "application/signed-exchange;v=b3;q=0.7")


def _pick_browser_profile():
    return choice(_UA_PROFILES)


def _browser_headers(kind, origin, profile):
    headers = [
        ("Accept", _NAVIGATE_ACCEPT if kind == "navigate" else "*/*"),
        ("Accept-Encoding", "gzip, deflate"),
        ("Accept-Language", "en-US,en;q=0.9"),
        ("sec-ch-ua", profile["brands"]),
        ("sec-ch-ua-mobile", "?0"),
        ("sec-ch-ua-platform", '"%s"' % profile["platform"]),
        ("User-Agent", profile["ua"]),
    ]
    if kind == "navigate":
        headers += [
            ("Sec-Fetch-Dest", "document"),
            ("Sec-Fetch-Mode", "navigate"),
            ("Sec-Fetch-Site", "none"),
            ("Sec-Fetch-User", "?1"),
            ("Upgrade-Insecure-Requests", "1"),
        ]
    else:
        headers += [
            ("Origin", origin),
            ("Sec-Fetch-Dest", "empty"),
            ("Sec-Fetch-Mode", "cors"),
            ("Sec-Fetch-Site", "same-origin"),
        ]
    return headers


def _decode_content(body, encoding):
    enc = (encoding or "").split(",", 1)[0].strip().lower()
    if not body:
        return body
    if enc in ("gzip", "x-gzip"):
        return gzip.decompress(body)
    if enc == "deflate":
        try:
            return zlib.decompress(body)
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS)
    return body


def frame_encode(ftype, stream_id, payload=b""):
    return struct.pack(">II", (ftype << 24) | stream_id, len(payload)) + payload


def frames_parse(data):
    frames = []
    offset, total = 0, len(data)
    while offset < total:
        if total - offset < FRAME_HEADER:
            raise ValueError("WEB proxy: неполный фрейм в batch")
        head, length = struct.unpack_from(">II", data, offset)
        end = offset + FRAME_HEADER + length
        if length > MAX_PAYLOAD or end > total or (head >> 24 == DATA and length == 0):
            raise ValueError("WEB proxy: некорректный фрейм в batch")
        frames.append((head >> 24, head & MAX_STREAM_ID, data[offset + FRAME_HEADER:end]))
        offset = end
    if not frames:
        raise ValueError("WEB proxy: пустой batch фреймов")
    return frames


def derive_bridge_capability(hostname, secret_hex):
    context = _BRIDGE_LABEL + hostname.lower().encode("utf-8")
    digest = hmac.new(bytes.fromhex(secret_hex), context, sha256).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _xor_mask(data, mask):
    n = len(data)
    if n == 0:
        return b""
    full = (mask * ((n + 3) >> 2))[:n]
    return (int.from_bytes(data, "big") ^ int.from_bytes(full, "big")).to_bytes(n, "big")


def _retry_after_seconds(headers):
    value = headers.get("retry-after")
    if not value:
        return 0.0
    try:
        return min(max(float(value), 0.0), 30.0)
    except ValueError:
        from email.utils import parsedate_to_datetime
        try:
            delta = parsedate_to_datetime(value).timestamp() - time()
        except (TypeError, ValueError):
            return 0.0
        return min(max(delta, 0.0), 30.0)


class HTTP11:
    __slots__ = ("host", "port", "sslctx", "host_header", "reader", "writer", "alive", "profile")

    def __init__(self, host, port, sslctx=None, profile=None):
        self.host = host
        self.port = port
        self.sslctx = sslctx
        self.profile = profile
        self.host_header = host if port in (443, 80, None) else f"{host}:{port}"
        self.reader = None
        self.writer = None
        self.alive = False

    async def connect(self):
        if self.alive:
            return
        self.reader, self.writer = await asyncio.open_connection(
            self.host, self.port, ssl=self.sslctx,
            server_hostname=self.host if self.sslctx is not None else None)
        self.alive = True

    def close(self):
        self.alive = False
        if self.writer is not None:
            try:
                self.writer.close()
            except BaseException:
                pass
            self.writer = None
            self.reader = None

    async def request(self, method, path, headers=(), body=None, timeout=30.0, kind="fetch"):
        if not self.alive:
            await self.connect()
        try:
            return await asyncio.wait_for(
                self._exchange(method, path, headers, body, kind), timeout)
        except BaseException:
            self.close()
            raise

    async def _exchange(self, method, path, headers, body, kind="fetch"):
        lines = [f"{method} {path} HTTP/1.1", f"Host: {self.host_header}"]
        if self.profile is not None:
            for name, value in _browser_headers(
                    kind, f"https://{self.host_header}", self.profile):
                lines.append(f"{name}: {value}")
        if body is None:
            if method == "DELETE":
                lines.append("Content-Length: 0")
        else:
            if body:
                lines.append("Content-Type: application/octet-stream")
            lines.append(f"Content-Length: {len(body)}")
        for name, value in headers:
            lines.append(f"{name}: {value}")
        packet = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
        if body:
            packet += bytes(body)
        self.writer.write(packet)
        await self.writer.drain()

        status_line = await self.reader.readline()
        parts = status_line.split(None, 2)
        if len(parts) < 2 or not parts[0].startswith(b"HTTP/"):
            raise ConnectionError("WEB proxy: некорректный HTTP статус")
        status = int(parts[1])

        rheaders = {}
        while True:
            line = await self.reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            name, _, value = line.decode("latin-1").partition(":")
            name = name.strip().lower()
            if name and name not in rheaders:
                rheaders[name] = value.strip()

        if rheaders.get("connection", "").lower() == "close":
            self.alive = False
        rbody = await self._read_body(status, rheaders)
        if rbody and "content-encoding" in rheaders:
            rbody = _decode_content(rbody, rheaders["content-encoding"])
        return status, rheaders, rbody

    async def _read_body(self, status, rheaders):
        if status in (204, 304) or 100 <= status < 200:
            return b""
        if "chunked" in rheaders.get("transfer-encoding", "").lower():
            chunks = []
            while True:
                line = await self.reader.readline()
                if not line:
                    raise ConnectionError("WEB proxy: обрыв chunked ответа")
                size = int(line.split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    while True:
                        tail = await self.reader.readline()
                        if not tail or tail in (b"\r\n", b"\n"):
                            break
                    break
                chunks.append(await self.reader.readexactly(size))
                await self.reader.readexactly(2)
            return b"".join(chunks)
        length = rheaders.get("content-length")
        if length is not None:
            count = int(length)
            return await self.reader.readexactly(count) if count else b""
        self.alive = False
        return await self.reader.read(-1)


_IMPERSONATE_CHAINS = {
    "chrome": ("chrome", "chrome150", "chrome145", "chrome142", "chrome136",
               "chrome131", "chrome124", "chrome120", "chrome116", "chrome110"),
    "firefox": ("firefox147", "firefox144", "firefox135", "firefox133"),
}


def _supported_impersonate_targets():
    try:
        from typing import get_args
        from curl_cffi.requests.impersonate import BrowserTypeLiteral
        return get_args(BrowserTypeLiteral)
    except BaseException:
        return ()


def resolve_impersonate(browser):
    if not browser:
        return None
    name = str(browser).strip().lower()
    supported = _supported_impersonate_targets()
    if not supported:
        return None
    if name in supported:
        return name
    chain = _IMPERSONATE_CHAINS.get(name)
    if chain is None:
        raise ValueError(
            f"WEB proxy: неизвестный browser={browser!r} "
            "(ожидается chrome | firefox | цель curl_cffi)")
    for target in chain:
        if target in supported:
            return target
    return None


class ImpersonateHTTP:
    __slots__ = ("host", "port", "impersonate", "insecure", "host_header", "_session", "alive")

    def __init__(self, host, port, impersonate, insecure=False):
        self.host = host
        self.port = port
        self.impersonate = impersonate
        self.insecure = insecure
        self.host_header = host if port in (443, 80, None) else f"{host}:{port}"
        self._session = None
        self.alive = False

    async def connect(self):
        if self._session is None:
            from curl_cffi.requests import AsyncSession
            self._session = AsyncSession()
            self.alive = True

    def close(self):
        session, self._session, self.alive = self._session, None, False
        if session is not None:
            async def _close():
                try:
                    await session.close()
                except BaseException:
                    pass
            try:
                asyncio.get_event_loop().create_task(_close())
            except RuntimeError:
                pass

    async def request(self, method, path, headers=(), body=None, timeout=30.0, kind="fetch"):
        if self._session is None:
            await self.connect()
        send = {}
        if kind == "fetch":
            send.update({
                "Accept": "*/*",
                "Origin": f"https://{self.host_header}",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": None,
                "Upgrade-Insecure-Requests": None,
            })
        if body == b"":
            send["Content-Type"] = None
        for name, value in headers:
            send[name] = value
        try:
            response = await self._session.request(
                method, f"https://{self.host_header}{path}", data=body,
                headers=send, timeout=timeout, allow_redirects=False,
                verify=not self.insecure, impersonate=self.impersonate)
        except asyncio.TimeoutError:
            raise
        except BaseException as ex:
            raise ConnectionError(f"WEB proxy: {ex}") from None
        rheaders = {}
        for name, value in response.headers.items():
            key = name.lower()
            if key not in rheaders:
                rheaders[key] = value if isinstance(value, str) else str(value)
        return response.status_code, rheaders, bytes(response.content or b"")


class ImpersonateWS:
    __slots__ = ("host", "port", "path", "subprotocol", "impersonate", "insecure", "host_header", "_session", "_ws", "closed")

    KEEPALIVE = 20.0

    def __init__(self, host, port, path, subprotocol, impersonate, insecure=False):
        self.host = host
        self.port = port
        self.path = path
        self.subprotocol = subprotocol
        self.impersonate = impersonate
        self.insecure = insecure
        self.host_header = host if port in (443, 80, None) else f"{host}:{port}"
        self._session = None
        self._ws = None
        self.closed = True

    async def connect(self, timeout=15.0):
        from curl_cffi.requests import AsyncSession
        self._session = AsyncSession()
        self._ws = await self._session.ws_connect(
            f"wss://{self.host_header}{self.path}",
            impersonate=self.impersonate, verify=not self.insecure,
            timeout=timeout,
            headers={"Sec-WebSocket-Protocol": self.subprotocol})
        self.closed = False

    async def send(self, data):
        if self.closed or self._ws is None:
            raise ConnectionError("WEB proxy: WebSocket закрыт")
        await self._ws.send(bytes(data))

    async def recv(self, timeout=95.0):
        if self.closed or self._ws is None:
            return None
        from curl_cffi.requests.websockets import (
            WebSocketClosed as _Closed, WebSocketTimeout as _Timeout)
        deadline = monotonic() + timeout
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError()
            try:
                payload, _flags = await self._ws.recv(
                    timeout=min(remaining, self.KEEPALIVE))
                return bytes(payload)
            except _Timeout:
                try:
                    await self._ws.send(frame_encode(PONG, 0))
                except BaseException:
                    pass
            except _Closed:
                self.closed = True
                return None
            except BaseException as ex:
                raise ConnectionError(f"WEB proxy: WebSocket -> {ex}") from None

    def close(self):
        ws, session = self._ws, self._session
        self._ws, self._session, self.closed = None, None, True
        if ws is None and session is None:
            return
        async def _close():
            if ws is not None:
                try:
                    await ws.close()
                except BaseException:
                    pass
            if session is not None:
                try:
                    await session.close()
                except BaseException:
                    pass
        try:
            asyncio.get_event_loop().create_task(_close())
        except RuntimeError:
            pass


class WSConnection:
    __slots__ = ("host", "port", "path", "subprotocol", "sslctx", "host_header", "reader", "writer", "closed", "profile")

    def __init__(self, host, port, path, subprotocol, sslctx=None, profile=None):
        self.host = host
        self.port = port
        self.path = path
        self.subprotocol = subprotocol
        self.sslctx = sslctx
        self.profile = profile
        self.host_header = host if port in (443, 80, None) else f"{host}:{port}"
        self.reader = None
        self.writer = None
        self.closed = True

    async def connect(self, timeout=15.0):
        self.reader, self.writer = await asyncio.open_connection(
            self.host, self.port, ssl=self.sslctx,
            server_hostname=self.host if self.sslctx is not None else None)
        key = b64encode(urandom(16)).decode("ascii")
        head = [
            f"GET {self.path} HTTP/1.1",
            f"Host: {self.host_header}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
            f"Sec-WebSocket-Protocol: {self.subprotocol}",
        ]
        if self.profile is not None:
            head += [
                "Accept-Encoding: gzip, deflate",
                "Accept-Language: en-US,en;q=0.9",
                "Cache-Control: no-cache",
                f"Origin: https://{self.host_header}",
                "Pragma: no-cache",
                "Sec-Fetch-Dest: websocket",
                "Sec-Fetch-Mode: websocket",
                "Sec-Fetch-Site: same-origin",
                f"User-Agent: {self.profile['ua']}",
            ]
        request = "\r\n".join(head + ["", ""])
        self.writer.write(request.encode("ascii"))
        await self.writer.drain()

        status_line = await asyncio.wait_for(self.reader.readline(), timeout)
        if not status_line.startswith(b"HTTP/1.1 101"):
            raise ConnectionError(
                f"WEB proxy: WS upgrade отклонён ({status_line.split()[1:2]})")
        accept, proto = None, None
        while True:
            line = await self.reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            name, _, value = line.decode("latin-1").partition(":")
            name, value = name.strip().lower(), value.strip()
            if name == "sec-websocket-accept":
                accept = value
            elif name == "sec-websocket-protocol":
                proto = value
        expected = b64encode(sha1(key.encode("ascii") + _WS_GUID).digest()).decode("ascii")
        if accept != expected:
            raise ConnectionError("WEB proxy: неверный Sec-WebSocket-Accept")
        if proto != self.subprotocol:
            raise ConnectionError("WEB proxy: WebSocket под-протокол не подтверждён")
        self.closed = False

    async def send(self, data):
        if self.closed:
            raise ConnectionError("WEB proxy: WebSocket закрыт")
        count = len(data)
        mask = urandom(4)
        header = bytearray((0x82, 0x80 | (126 if 126 <= count < 65536 else 127 if count >= 65536 else count)))
        if 126 <= count < 65536:
            header += struct.pack(">H", count)
        elif count >= 65536:
            header += struct.pack(">Q", count)
        header += mask
        self.writer.write(bytes(header) + _xor_mask(bytes(data), mask))
        await self.writer.drain()

    async def recv(self, timeout=95.0):
        if self.closed:
            return None
        message = None
        while True:
            head = await asyncio.wait_for(self.reader.readexactly(2), timeout)
            fin, opcode = head[0] & 0x80, head[0] & 0x0F
            length = head[1] & 0x7F
            if length == 126:
                length = struct.unpack(">H", await self.reader.readexactly(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", await self.reader.readexactly(8))[0]
            mask = await self.reader.readexactly(4) if head[1] & 0x80 else b""
            payload = await self.reader.readexactly(length) if length else b""
            if mask:
                payload = _xor_mask(payload, mask)

            if opcode in (0x2, 0x0):
                if opcode == 0x2:
                    if fin:
                        return payload
                    message = bytearray(payload)
                else:
                    if message is None:
                        raise ConnectionError("WEB proxy: WS continuation без начала")
                    message += payload
                    if fin:
                        return bytes(message)
            elif opcode == 0x9:
                await self._send_control(0x0A, payload)
            elif opcode == 0xA:
                continue
            elif opcode == 0x8:
                self.closed = True
                try:
                    self._send_control_now(0x8, struct.pack(">H", 1000))
                except BaseException:
                    pass
                return None
            else:
                raise ConnectionError(f"WEB proxy: неверный WS опкод {opcode:#x}")

    async def _send_control(self, opcode, payload):
        if self.closed:
            return
        try:
            self._send_control_now(opcode, payload)
            await self.writer.drain()
        except BaseException:
            self.closed = True
            raise

    def _send_control_now(self, opcode, payload):
        mask = urandom(4)
        header = bytearray((0x80 | opcode, 0x80 | len(payload))) + mask
        self.writer.write(bytes(header) + _xor_mask(payload, mask))

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self._send_control_now(0x8, struct.pack(">H", 1000))
        except BaseException:
            pass
        try:
            self.writer.close()
        except BaseException:
            pass


class WebProxyStream:
    __slots__ = ("transport", "id", "_buf", "_event", "_eof", "_closed", "_send_window", "_window_event", "_credit")

    def __init__(self, transport, stream_id):
        self.transport = transport
        self.id = stream_id
        self._buf = bytearray()
        self._event = asyncio.Event()
        self._eof = False
        self._closed = False
        self._send_window = INITIAL_WINDOW
        self._window_event = asyncio.Event()
        self._credit = 0

    async def sock_sendall(self, sock, data):
        await self.sendall(data)

    async def sock_recv(self, sock, n=65536):
        return await self.recv(n)

    async def sock_recv_into(self, sock, view):
        return await self.recv_into(view)

    async def sendall(self, data):
        total, offset = len(data), 0
        while offset < total:
            if self._closed or self._eof:
                raise ConnectionError("WEB proxy: поток закрыт")
            chunk = bytes(data[offset:offset + DATA_CHUNK])
            offset += len(chunk)
            while not self._window_ready(len(chunk)):
                self._window_event.clear()
                if self._window_ready(len(chunk)):
                    break
                await self._window_event.wait()
            if self._closed or self._eof:
                raise ConnectionError("WEB proxy: поток закрыт")
            self._send_window -= len(chunk)
            self.transport._enqueue(DATA, self.id, chunk)

    async def recv(self, n=65536):
        while True:
            self._event.clear()
            if self._buf:
                data = bytes(self._buf[:n])
                del self._buf[:n]
                self._release_credit(len(data))
                return data
            if self._eof:
                return b""
            await self._event.wait()

    async def recv_into(self, view):
        while True:
            self._event.clear()
            if self._buf:
                count = min(len(view), len(self._buf))
                view[:count] = self._buf[:count]
                del self._buf[:count]
                self._release_credit(count)
                return count
            if self._eof:
                return 0
            await self._event.wait()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._eof = True
        self._event.set()
        self._window_event.set()
        if self.transport is not None:
            try:
                self.transport._enqueue(CLOSE, self.id)
            except BaseException:
                pass

    def _window_ready(self, count):
        return self._send_window >= count or self._eof or self._closed

    def _feed(self, payload):
        if self._closed or self._eof:
            return
        self._buf.extend(payload)
        self._event.set()

    def _remote_close(self):
        self._eof = True
        self._event.set()
        self._window_event.set()

    def _grant_send_window(self, delta):
        self._send_window += delta
        self._window_event.set()

    def _release_credit(self, consumed):
        self._credit += consumed
        if self._credit >= 16384 or not self._buf:
            if self._credit:
                self.transport._enqueue(WINDOW, self.id, struct.pack(">I", self._credit))
                self._credit = 0


class WebProxySocket:
    __slots__ = ("stream", "transport")

    def __init__(self, stream, transport):
        self.stream = stream
        self.transport = transport

    async def sock_sendall(self, sock, data):
        await self.stream.sendall(data)

    async def sock_recv(self, sock, n=65536):
        return await self.stream.recv(n)

    async def sock_recv_into(self, sock, view):
        return await self.stream.recv_into(view)

    def close(self):
        try:
            self.stream.close()
        except BaseException:
            pass
        try:
            self.transport.close()
        except BaseException:
            pass


class WebProxyTransport:
    __slots__ = (
        "hostname", "port", "secret", "client", "sslctx", "carrier_mode", "batch_limit", "session_token", "bootstrap",
        "streams", "_next_stream_id", "_up_queue", "_up_event", "_up_seq", "_down_cursor", "_lanes", "_ws_lanes", "_tasks",
        "_closed", "_failed", "websocket", "_profile", "_impersonate"
    )

    def __init__(self, hostname, port, secret, client, sslctx=None, browser=None):
        self.hostname = hostname
        self.port = port or 443
        self.secret = secret
        self.client = client
        self.sslctx = sslctx if sslctx is not None else ssl.create_default_context()
        self._profile = _pick_browser_profile()
        self._impersonate = resolve_impersonate(browser)
        if browser and self._impersonate is None:
            try:
                self.client.warn("WEB proxy: curl_cffi не установлен — TLS-имперсонация недоступна, используется обычный TLS (OpenSSL)")
            except BaseException:
                pass
        elif self._impersonate is not None:
            try:
                self.client.info(f"WEB proxy: TLS-имперсонация браузера ({self._impersonate})")
            except BaseException:
                pass
        self.carrier_mode = "https"
        self.batch_limit = DEFAULT_BATCH
        self.session_token = ""
        self.bootstrap = ""
        self.streams = {}
        self._next_stream_id = 1
        self._up_queue = deque()
        self._up_event = None
        self._up_seq = 1
        self._down_cursor = "0"
        self._lanes = {}
        self._ws_lanes = {}
        self._tasks = []
        self._closed = False
        self._failed = False
        self.websocket = None

    def _new_http(self):
        if self._impersonate is not None:
            return ImpersonateHTTP(
                self.hostname, self.port, self._impersonate,
                insecure=self.sslctx.verify_mode == ssl.CERT_NONE)
        return HTTP11(self.hostname, self.port, self.sslctx, self._profile)

    def _new_ws(self, subprotocol):
        if self._impersonate is not None:
            return ImpersonateWS(
                self.hostname, self.port, "/api/v1/ws", subprotocol,
                self._impersonate,
                insecure=self.sslctx.verify_mode == ssl.CERT_NONE)
        return WSConnection(
            self.hostname, self.port, "/api/v1/ws", subprotocol,
            self.sslctx, self._profile)

    async def connect(self):
        loop = asyncio.get_event_loop()
        capability = derive_bridge_capability(self.hostname, self.secret)
        conn = self._new_http()
        try:
            status, headers, body = await self._request(
                conn, "GET", f"/?bridge={capability}", timeout=30.0,
                kind="navigate")
            if status != 200:
                raise ConnectionError(f"WEB proxy: bridge не получен ({status})")
            match = _BRIDGE_BOOTSTRAP_RE.search(body)
            if not match:
                raise ConnectionError(
                    "WEB proxy: bridge не содержит bootstrap токен (неверный секрет?)")
            self.bootstrap = match.group(1).decode("ascii")
            mode_match = _BRIDGE_MODE_RE.search(body)
            page_mode = mode_match.group(1).decode("ascii") if mode_match else "https"
            batch_match = _BRIDGE_BATCH_RE.search(body)
            if batch_match:
                self.batch_limit = max(MIN_BATCH, min(int(batch_match.group(1)), DEFAULT_BATCH))

            status, headers, body = await self._request(
                conn, "POST", "/api/v1/session",
                headers=(("Authorization", f"Bearer {self.bootstrap}"),),
                body=frame_encode(HELLO, 0, b"\x01"), timeout=30.0)
        finally:
            conn.close()

        if status != 200:
            raise ConnectionError(f"WEB proxy: сессия не создана ({status})")
        self.session_token = headers.get("x-session-token", "")
        self.carrier_mode = headers.get("x-carrier-mode", "https")
        self._down_cursor = headers.get("x-down-cursor", "0")
        if not self.session_token:
            raise ConnectionError("WEB proxy: токен сессии не получен")
        if self.carrier_mode not in CARRIER_MODES:
            raise ConnectionError(f"WEB proxy: неизвестный carrier {self.carrier_mode}")
        if self.carrier_mode != page_mode:
            raise ConnectionError(f"WEB proxy: несоответствие carrier ({self.carrier_mode} != {page_mode})")
        if frames_parse(body)[0][0] != WELCOME:
            raise ConnectionError("WEB proxy: ожидается WELCOME фрейм")

        self._up_event = asyncio.Event()
        if self.carrier_mode == "https":
            self._tasks.append(loop.create_task(self._https_up_worker()))
            self._tasks.append(loop.create_task(self._https_down_worker()))
        elif self.carrier_mode == "https-lanes":
            self._create_https_lane(0)
        elif self.carrier_mode == "websocket":
            self.websocket = self._new_ws(f"tproxy-v1.{self.session_token}")
            await self.websocket.connect()
            self._tasks.append(loop.create_task(self._ws_up_worker()))
            self._tasks.append(loop.create_task(self._ws_down_worker()))

    async def open_stream(self):
        if self._closed or self._failed:
            raise ConnectionError("WEB proxy: транспорт закрыт")
        stream_id = self._next_stream_id
        if stream_id > MAX_STREAM_ID:
            raise ConnectionError("WEB proxy: идентификаторы потоков исчерпаны")
        self._next_stream_id += 1

        stream = WebProxyStream(self, stream_id)
        self.streams[stream_id] = stream

        if self.carrier_mode == "https-lanes":
            self._create_https_lane(stream_id)
            self._enqueue(OPEN, stream_id)
        elif self.carrier_mode == "websocket-lanes":
            await self._create_ws_lane(stream_id)
        else:
            self._enqueue(OPEN, stream_id)
        return stream

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._shutdown()

    def _enqueue(self, ftype, stream_id, payload=b""):
        if self._closed or self._failed:
            return
        if self.carrier_mode == "https-lanes":
            lane = 0 if stream_id == 0 else stream_id
            state = self._lanes.get(lane)
            if state is None:
                return
            state["queue"].append(frame_encode(ftype, stream_id, payload))
            state["event"].set()
        elif self.carrier_mode == "websocket-lanes":
            state = self._ws_lanes.get(stream_id)
            if state is None:
                return
            state["queue"].append(frame_encode(ftype, stream_id, payload))
            state["event"].set()
        else:
            self._up_queue.append(frame_encode(ftype, stream_id, payload))
            if self._up_event is not None:
                self._up_event.set()

    def _route(self, frames):
        for ftype, stream_id, payload in frames:
            if ftype == DATA:
                stream = self.streams.get(stream_id)
                if stream is not None:
                    stream._feed(payload)
            elif ftype == WINDOW:
                stream = self.streams.get(stream_id)
                if stream is not None:
                    stream._grant_send_window(int.from_bytes(payload, "big"))
            elif ftype == CLOSE:
                stream = self.streams.pop(stream_id, None)
                if stream is not None:
                    stream._remote_close()
            elif ftype == PING:
                self._enqueue(PONG, 0, bytes(payload))
            elif ftype == BYE:
                self._fail("сессия закрыта сервером (BYE)")
                return

    def _create_https_lane(self, lane_id):
        if self._lanes.get(lane_id) is not None or self._closed:
            return
        loop = asyncio.get_event_loop()
        state = {
            "queue": deque(), "event": asyncio.Event(),
            "seq": 1, "cursor": "0", "conn": None
        }
        self._lanes[lane_id] = state
        self._tasks.append(loop.create_task(self._https_up_worker(lane_id)))
        self._tasks.append(loop.create_task(self._https_down_worker(lane_id)))

    async def _https_up_worker(self, lane_id=None):
        state = self._lanes.get(lane_id) if lane_id is not None else None
        queue = state["queue"] if state is not None else self._up_queue
        event = state["event"] if state is not None else self._up_event
        conn = self._new_http()
        if state is not None:
            state["conn"] = conn
        try:
            await conn.connect()
            while not self._closed and not self._failed:
                event.clear()
                if not queue:
                    await event.wait()
                    if self._closed or self._failed:
                        return
                    continue
                batch = [queue.popleft()]
                total = len(batch[0])
                while queue and len(batch) < MAX_BATCH_FRAMES \
                        and total + len(queue[0]) <= self.batch_limit:
                    item = queue.popleft()
                    batch.append(item)
                    total += len(item)
                body = b"".join(batch)
                seq = state["seq"] if state is not None else self._up_seq
                headers = [
                    ("Authorization", f"Bearer {self.session_token}"),
                    ("X-Up-Seq", str(seq))
                ]
                if lane_id is not None:
                    headers.append(("X-Lane-ID", str(lane_id)))
                status, rheaders, _ = await self._request(
                    conn, "POST", "/api/v1/up", headers, body, timeout=90.0)
                if status != 204 or rheaders.get("x-up-ack") != str(seq):
                    raise ConnectionError(f"WEB proxy: uplink отклонён ({status})")
                if state is not None:
                    state["seq"] += 1
                else:
                    self._up_seq += 1
        except BaseException as ex:
            if not self._closed:
                self._fail(f"https uplink[{lane_id}] -> {ex}")
        finally:
            conn.close()

    async def _https_down_worker(self, lane_id=None):
        state = self._lanes.get(lane_id) if lane_id is not None else None
        conn = self._new_http()
        try:
            await conn.connect()
            while not self._closed and not self._failed:
                cursor = state["cursor"] if state is not None else self._down_cursor
                headers = [
                    ("Authorization", f"Bearer {self.session_token}"),
                    ("X-Down-Cursor", str(cursor))
                ]
                if lane_id is not None:
                    headers.append(("X-Lane-ID", str(lane_id)))
                status, rheaders, rbody = await self._request(
                    conn, "POST", "/api/v1/down", headers, b"", timeout=95.0)
                if status == 204:
                    if state is not None and rheaders.get("x-lane-closed") == "1":
                        self._lanes.pop(lane_id, None)
                        return
                    continue
                if status != 200:
                    raise ConnectionError(f"WEB proxy: downlink отклонён ({status})")
                next_cursor = rheaders.get("x-down-cursor", "")
                if not next_cursor or not rbody:
                    raise ConnectionError("WEB proxy: некорректный downlink ответ")
                if state is not None:
                    state["cursor"] = next_cursor
                else:
                    self._down_cursor = next_cursor
                self._route(frames_parse(rbody))
        except BaseException as ex:
            if not self._closed:
                self._fail(f"https downlink[{lane_id}] -> {ex}")
        finally:
            conn.close()

    async def _ws_up_worker(self):
        try:
            while not self._closed and not self._failed:
                self._up_event.clear()
                if not self._up_queue:
                    await self._up_event.wait()
                    if self._closed or self._failed:
                        return
                    continue
                batch = [self._up_queue.popleft()]
                total = len(batch[0])
                while self._up_queue and len(batch) < MAX_BATCH_FRAMES \
                        and total + len(self._up_queue[0]) <= self.batch_limit:
                    item = self._up_queue.popleft()
                    batch.append(item)
                    total += len(item)
                await self.websocket.send(b"".join(batch))
        except BaseException as ex:
            if not self._closed:
                self._fail(f"ws uplink -> {ex}")

    async def _ws_down_worker(self):
        try:
            while not self._closed and not self._failed:
                data = await self.websocket.recv()
                if data is None:
                    raise ConnectionError("WEB proxy: WebSocket закрыт сервером")
                self._route(frames_parse(data))
        except BaseException as ex:
            if not self._closed:
                self._fail(f"ws downlink -> {ex}")

    async def _create_ws_lane(self, stream_id):
        if self._ws_lanes.get(stream_id) is not None or self._closed:
            raise ConnectionError("WEB proxy: WS lane уже существует")
        loop = asyncio.get_event_loop()
        ws = self._new_ws(f"tproxy-lane-v1.{self.session_token}.{stream_id}")
        await ws.connect()
        await ws.send(frame_encode(OPEN, stream_id))
        state = {"queue": deque(), "event": asyncio.Event(), "ws": ws}
        self._ws_lanes[stream_id] = state
        self._tasks.append(loop.create_task(self._ws_lane_up_worker(state, stream_id)))
        self._tasks.append(loop.create_task(self._ws_lane_down_worker(state, stream_id)))

    async def _ws_lane_up_worker(self, state, lane_id):
        queue, event, ws = state["queue"], state["event"], state["ws"]
        try:
            while not self._closed and not self._failed:
                event.clear()
                if not queue:
                    await event.wait()
                    if self._closed or self._failed:
                        return
                    continue
                batch = [queue.popleft()]
                total = len(batch[0])
                while queue and len(batch) < MAX_BATCH_FRAMES \
                        and total + len(queue[0]) <= self.batch_limit:
                    item = queue.popleft()
                    batch.append(item)
                    total += len(item)
                await ws.send(b"".join(batch))
        except BaseException as ex:
            stream = self.streams.get(lane_id)
            if not self._closed and stream is not None and not stream._closed:
                self._fail(f"ws lane uplink -> {ex}")

    async def _ws_lane_down_worker(self, state, lane_id):
        ws = state["ws"]
        try:
            while not self._closed and not self._failed:
                data = await ws.recv()
                if data is None:
                    stream = self.streams.get(lane_id)
                    if stream is None or stream._closed:
                        return
                    raise ConnectionError("WEB proxy: WS lane закрыт сервером")
                self._route(frames_parse(data))
        except BaseException as ex:
            stream = self.streams.get(lane_id)
            if not self._closed and stream is not None and not stream._closed:
                self._fail(f"ws lane downlink -> {ex}")

    async def _request(self, conn, method, path, headers=(), body=None, timeout=30.0, budget=90.0, kind="fetch"):
        deadline = monotonic() + budget
        delay, errors = 0.25, 0
        while True:
            try:
                status, rheaders, rbody = await conn.request(
                    method, path, headers, body, timeout, kind)
                if status != 503:
                    return status, rheaders, rbody
                wait = _retry_after_seconds(rheaders)
            except (ConnectionError, OSError, asyncio.TimeoutError, EOFError) as ex:
                errors += 1
                if errors >= 9:
                    raise ConnectionError(f"WEB proxy: {method} {path} -> {ex}") from None
                wait = 0.0
            if monotonic() >= deadline:
                raise ConnectionError(f"WEB proxy: {method} {path} бюджет повторов исчерпан")
            await asyncio.sleep(wait if wait else delay + random() * delay * 0.25)
            if not wait:
                delay = min(delay * 2, 5.0)

    def _fail(self, reason):
        if self._failed or self._closed:
            return
        self._failed = True
        try:
            self.client.error(f"WEB proxy: {reason}")
        except BaseException:
            pass
        self._shutdown()

    def _shutdown(self):
        for stream in self.streams.values():
            stream._remote_close()
        for state in self._lanes.values():
            state["event"].set()
            conn = state.get("conn")
            if conn is not None:
                conn.close()
        for state in self._ws_lanes.values():
            state["event"].set()
            state["ws"].close()
        self._ws_lanes.clear()
        if self._up_event is not None:
            self._up_event.set()
        for task in self._tasks:
            task.cancel()
        if self.websocket is not None:
            self.websocket.close()
        if not self._failed and self.session_token:
            try:
                asyncio.get_event_loop().create_task(self._delete_session())
            except RuntimeError:
                pass

    async def _delete_session(self):
        conn = self._new_http()
        try:
            await conn.request(
                "DELETE", "/api/v1/session",
                headers=(("Authorization", f"Bearer {self.session_token}"),),
                timeout=10.0
            )
        except BaseException:
            pass
        finally:
            conn.close()
