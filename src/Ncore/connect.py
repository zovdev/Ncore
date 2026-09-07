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
import time
import hmac
import struct
import socket
import secrets
import asyncio

from os import urandom
from io import BytesIO
from base64 import b64encode
from random import choice
from hashlib import sha1, sha256
from urllib.parse import urlparse


from .utils import Auth
from .tl_object import CoreMessage
from .ncrypto import AesIge256, AesCtr256
from .webproxy import WebProxyTransport, WebProxySocket


_EE_GREASE = (0x0A0A, 0x1A1A, 0x2A2A, 0x3A3A, 0x4A4A, 0x5A5A, 0x6A6A, 0x7A7A, 0x8A8A, 0x9A9A, 0xAAAA, 0xBABA, 0xCACA, 0xDADA, 0xEAEA, 0xFAFA)
_EE_CHROME_CIPHERS = (0x1301, 0x1302, 0x1303, 0xC02B, 0xC02F, 0xC02C, 0xC030, 0xCCA9, 0xCCA8, 0xC013, 0xC014, 0x009C, 0x009D, 0x002F, 0x0035)
_EE_FIREFOX_CIPHERS = (0x1301, 0x1303, 0x1302, 0xC02B, 0xC02F, 0xCCA9, 0xCCA8, 0xC02C, 0xC030, 0xC00A, 0xC009, 0xC013, 0xC014, 0x009C, 0x009D, 0x002F, 0x0035)


def _grease16():
    return struct.pack(">H", choice(_EE_GREASE))


def fake_tls_clienthello(browser, domain_bytes):
    P = 2 ** 255 - 19
    fake_pubkey = (secrets.randbelow(P) ** 2 % P).to_bytes(32, "little")
    session_id = urandom(32)
    dl = len(domain_bytes)

    def sni():
        return (struct.pack(">HHH", 0x0000, 5 + dl, 3 + dl) + b"\x00" + struct.pack(">H", dl) + domain_bytes)

    alpn = b"\x00\x10\x00\x0e\x00\x0c\x02\x68\x32\x08\x68\x74\x74\x70\x2f\x31\x2e\x31"

    if browser == "firefox":
        ciphers = _EE_FIREFOX_CIPHERS
        exts = b"".join((
            sni(),
            b"\x00\x17\x00\x00",
            b"\xff\x01\x00\x01\x00",
            b"\x00\x0a\x00\x0e\x00\x0c"
            b"\x00\x1d\x00\x17\x00\x18\x00\x19\x01\x00\x01\x01",
            b"\x00\x0b\x00\x02\x01\x00",
            b"\x00\x23\x00\x00",
            alpn,
            b"\x00\x05\x00\x05\x01\x00\x00\x00\x00",
            b"\x00\x22\x00\x08\x04\x03\x05\x03\x06\x03\x02\x03",
            b"\x00\x12\x00\x00",
            b"\x00\x33\x00\x26\x00\x24\x00\x1d\x00\x20" + fake_pubkey,
            b"\x00\x2b\x00\x05\x04\x03\x04\x03\x03",
            b"\x00\x0d\x00\x18\x00\x16\x04\x03\x05\x03\x06\x03\x08\x04"
            b"\x08\x05\x08\x06\x04\x01\x05\x01\x06\x01\x02\x03\x02\x01",
            b"\x00\x2d\x00\x02\x01\x01",
            b"\x00\x1c\x00\x02\x40\x01",
            b"\x00\x1b\x00\x07\x06\x00\x01\x00\x02\x00\x03",
        ))
    else:
        g_ext, g_group, g_version, g_tail = _grease16(), _grease16(), _grease16(), _grease16()
        ciphers = (int.from_bytes(_grease16(), "big"),) + _EE_CHROME_CIPHERS
        exts = b"".join((
            g_ext + b"\x00\x00",
            sni(),
            b"\x00\x17\x00\x00",
            b"\xff\x01\x00\x01\x00",
            b"\x00\x0a\x00\x0a\x00\x08" + g_group +
            b"\x00\x1d\x00\x17\x00\x18",
            b"\x00\x0b\x00\x02\x01\x00",
            b"\x00\x23\x00\x00",
            alpn,
            b"\x00\x05\x00\x05\x01\x00\x00\x00\x00",
            b"\x00\x0d\x00\x12\x00\x10\x04\x03\x08\x04\x04\x01\x05\x03"
            b"\x08\x05\x05\x01\x08\x06\x06\x01",
            b"\x00\x12\x00\x00",
            b"\x00\x33\x00\x2b\x00\x29" + g_group +
            b"\x00\x01\x00\x00\x1d\x00\x20" + fake_pubkey,
            b"\x00\x2d\x00\x02\x01\x01",
            b"\x00\x2b\x00\x0b\x0a" + g_version +
            b"\x03\x04\x03\x03\x03\x02\x03\x01",
            b"\x00\x1b\x00\x03\x02\x00\x02",
            g_tail + b"\x00\x01\x00",
        ))

    body = (b"\x03\x03" + b"\x00" * 32 + b"\x20" + session_id
            + struct.pack(">H", len(ciphers) * 2)
            + b"".join(struct.pack(">H", c) for c in ciphers)
            + b"\x01\x00")
    pad = 508 - 2 - len(body) - len(exts) - 4
    if pad > 0:
        exts += b"\x00\x15" + struct.pack(">H", pad) + b"\x00" * pad
    body += struct.pack(">H", len(exts)) + exts
    return (b"\x16\x03\x01" + struct.pack(">H", 4 + len(body)) + b"\x01" + struct.pack(">I", len(body))[1:] + body)


class Connect:
    __slots__ = (
        "client", "loop", "sock", "address", "send", "recv", "_state", "_isAuth", "session_id", "auth_key", "auth_key_id",
        "__ak_036", "__ak_4076", "__ak_88120", "__ak_844", "__ak_4884", "__ak_96128", "salt",
        "__enc", "__dec", "__dec_buf", "__raw_buf", "__first_app_data",
        "_sock_sendall", "_sock_recv", "_sock_recv_into", "_wp_transport",
    )

    def __init__(self, address: tuple[str, int] | None=None):
        self.address = address
        self._state = 0
        self._isAuth = 0
        self._wp_transport = None

        self.salt = struct.pack("<Q", 0)
        self.session_id = urandom(8)
        self.send = self._send
        self.recv = self._recv

    async def init(self):
        self.loop = self.client.loop
        if self.address is None:
            self.address = {
                1: "149.154.175.53", 2: "149.154.167.51", 3: "149.154.175.100", 4: "149.154.167.91", 5: "91.108.56.130"
            }[self.client.storage["dc_id"]], 443
        if not self.client.storage["auth_key"]:
            self.client.warn("Получение auth_key")
            await Auth(self.client, self)()
            self._isAuth = 1
            self.client.info("Получен auth_key")
        self.auth_key = self.client.storage["auth_key"]
        self.auth_key_id = sha1(self.auth_key).digest()[-8:]
        self.__ak_036 = self.auth_key[0:36]
        self.__ak_4076 = self.auth_key[40:76]
        self.__ak_88120 = self.auth_key[88:120]
        self.__ak_844 = self.auth_key[8:44]
        self.__ak_4884 = self.auth_key[48:84]
        self.__ak_96128 = self.auth_key[96:128]

    def set_salt(self, value):
        self.salt = struct.pack("<Q", value)

    def kdf_pack(self, msg_key):
        h_a = sha256(msg_key)
        h_a.update(self.__ak_036)
        ha = h_a.digest()
        h_b = sha256(self.__ak_4076)
        h_b.update(msg_key)
        hb = h_b.digest()
        return ha[:8] + hb[8:24] + ha[24:32], hb[:8] + ha[8:24] + hb[24:32]

    def kdf_unpack(self, msg_key):
        h_a = sha256(msg_key)
        h_a.update(self.__ak_844)
        ha = h_a.digest()
        h_b = sha256(self.__ak_4884)
        h_b.update(msg_key)
        hb = h_b.digest()
        return ha[:8] + hb[8:24] + ha[24:32], hb[:8] + ha[8:24] + hb[24:32]

    def pack(self, message):
        data = self.salt + self.session_id + message.write()

        padding_len = 16 - (len(data) % 16)

        if padding_len < 12:
            padding_len += 16

        data_padding = data + urandom(padding_len)

        h_msg = sha256(self.__ak_88120)
        h_msg.update(data_padding)

        msg_key = h_msg.digest()[8:24]
        aes_key, aes_iv = self.kdf_pack(msg_key)

        return self.auth_key_id + msg_key + AesIge256(aes_key).encrypt(data_padding, aes_iv)

    def unpack(self, data):
        if data[0:8] != self.auth_key_id:
            raise ValueError("Ошибка безопасности не верный auth_key_id")

        msg_key = data[8:24]
        aes_key, aes_iv = self.kdf_unpack(msg_key)
        decrypted_data = AesIge256(aes_key).decrypt(data[24:24 + (len(data[24:]) // 16) * 16], aes_iv)

        data = decrypted_data[8:]
        if data[0:8] != self.session_id:
            raise ValueError("Ошибка безопасности не верный session_id")

        hm = sha256(self.__ak_96128)
        hm.update(decrypted_data)
        if msg_key != hm.digest()[8:24]:
            raise ValueError("Ошибка безопасности не верный msg_key")

        message = CoreMessage.read(BytesIO(data[8:]))
        payload_len = len(decrypted_data) - 32
        if not 12 <= (payload_len - message.length) <= 1024 or payload_len % 4 != 0 or message.msg_id % 2 == 0:
            raise ValueError("Ошибка безопасности padding/length/msg_id")

        return message

    def disconnect(self):
        try:
            self.sock.close()
        except:
            pass
        self._state = 0

    async def proxy_handshake_socks5(self, address, target_address, username, password):
        await self.loop.sock_connect(self.sock, address)
        if username and password:
            await self._sock_sendall(self.sock, b"\x05\x01\x02")
            if await self._sock_recv(self.sock, 2) != b"\x05\x02":
                self.client.error("Прокси не поддерживает авторизацию")
                raise ConnectionError()
            user_b, pass_b = username.encode(), password.encode()
            u_len, p_len = len(user_b), len(pass_b)
            await self._sock_sendall(self.sock, struct.pack(f"<BB{u_len}sB{p_len}s", 0x01, u_len, user_b, p_len, pass_b))
            if await self._sock_recv(self.sock, 2) != b"\x01\x00":
                self.client.error("Ошибка авторизации прокси")
                raise ConnectionError()
        else:
            await self._sock_sendall(self.sock, b"\x05\x01\x00")
            if await self._sock_recv(self.sock, 2) != b"\x05\x00":
                self.client.error("Прокси требует авторизацию / Не доступен")
                raise ConnectionError()
        await self._sock_sendall(self.sock, struct.pack(">BBBB4sH", 0x05, 0x01, 0x00, 0x01, socket.inet_aton(target_address[0]), target_address[1]))
        conn_res = await self._sock_recv(self.sock, 10)
        if len(conn_res) < 2 or conn_res[1] != 0x00:
            self.client.error(f"Ошибка подключения: {conn_res[1] if len(conn_res)>1 else 'Unknown'}")
            raise ConnectionError()

    async def proxy_handshake_http(self, address, target_address, username, password):
        await self.loop.sock_connect(self.sock, address)
        headers = f"CONNECT {target_address[0]}:{target_address[1]} HTTP/1.1\r\nHost: {target_address[0]}:{target_address[1]}\r\n"
        if username and password: headers += f"Proxy-Authorization: Basic {b64encode(f'{username}:{password}'.encode()).decode()}\r\n"
        await self._sock_sendall(self.sock, (headers + "\r\n").encode())
        response = await self._sock_recv(self.sock, 4096)
        if b" 200" not in response.split(b"\r\n")[0]:
            self.client.error(f"Ошибка прокси: {response.decode(errors='ignore')}")
            raise ConnectionError()

    async def proxy_handshake_mtproxy(self, address, target_address, secret, password):
        if not secret:
            raise ValueError("Не найден/Не передан секрет MTPROXY")
        await self.loop.sock_connect(self.sock, (socket.gethostbyname(address[0]), address[1]))
        await self._mtproxy_obfuscation_handshake(secret)

    def _mtproxy_secret_key(self, secret):
        secret_bytes = bytes.fromhex(secret)
        if secret_bytes[0] in {0xDD, 0xEE}:
            secret_bytes = secret_bytes[1:]
        secret_bytes = secret_bytes[:16]
        if len(secret_bytes) != 16:
            raise ValueError("Не верный секрет")
        return secret_bytes

    async def _mtproxy_obfuscation_handshake(self, secret):
        secret_bytes = self._mtproxy_secret_key(secret)
        ban3, ban4 = {b"220", b"GET", b"\x05\x01\x00", b"\x00\x0e\x38"}, {b"PVrG", b"POST", b"\x05\x02\x00\x02", b"\x01\x00\x00\x00", b"\xee\xee\xee\xee", b"\x00\x00\x00\x00"}
        while True:
            h = urandom(64)
            if h[0] != 0xEF and h[:3] not in ban3 and h[:4] not in ban4:
                break
        handshake = bytearray(h)
        struct.pack_into("<h", handshake, 60, self.client.storage["dc_id"])

        hk_enc = sha256(handshake[8:40])
        hk_enc.update(secret_bytes)
        self.__enc = AesCtr256(hk_enc.digest(), handshake[40:56])

        hk_dec = sha256(handshake[::-1][8:40])
        hk_dec.update(secret_bytes)
        self.__dec = AesCtr256(hk_dec.digest(), handshake[::-1][40:56])

        self.__dec_buf, self.__raw_buf = bytearray(), bytearray()

        if secret.startswith("dd"):
            handshake[56:60] = b"\xdd\xdd\xdd\xdd"
            handshake[56:64] = self.__enc.crypt(handshake)[56:64]
            self.send, self.recv = self.mtproxy_dd_send, self.mtproxy_dd_recv
            await self._sock_sendall(self.sock, handshake)
        elif secret.startswith("ee"):
            secret_bytes = bytes.fromhex(secret[2:])
            secret_key, domain_bytes = secret_bytes[:16], secret_bytes[16:]
            ClientHello = fake_tls_clienthello(choice(("chrome", "firefox")), domain_bytes)
            digest = bytearray(hmac.new(secret_key, ClientHello, sha256).digest())
            now = struct.pack("<I", int(time.time()))
            for i in range(4): digest[28 + i] ^= now[i]
            ClientHello = ClientHello[:11] + digest + ClientHello[43:]
            await self._sock_sendall(self.sock, ClientHello)

            server_hello = bytearray()
            for _ in range(3):
                header = await self._recv_exactly_cold(5)
                server_hello += header + await self._recv_exactly_cold(struct.unpack(">H", header[3:5])[0])

            sh_zero = bytearray(server_hello)
            sh_zero[11:43] = b"\x00" * 32

            hm_ex = hmac.new(secret_key, ClientHello[11:43], sha256)
            hm_ex.update(sh_zero)
            if not hmac.compare_digest(server_hello[11:43], hm_ex.digest()):
                raise ConnectionError("ServerHello HMAC mismatch")

            handshake[56:60] = b"\xdd\xdd\xdd\xdd"
            handshake[56:64] = self.__enc.crypt(handshake)[56:64]
            self.__first_app_data = handshake
            self.send, self.recv = self.mtproxy_ee_send, self.mtproxy_ee_recv
        else:
            handshake[56:60] = b"\xef\xef\xef\xef"
            handshake[56:64] = self.__enc.crypt(handshake)[56:64]
            self.send, self.recv = self.mtproxy_send, self.mtproxy_recv
            await self._sock_sendall(self.sock, handshake)

    async def proxy_handshake_webproxy(self, address, target_address, secret, password=None, insecure=False, browser=None):
        if not secret:
            raise ValueError("Не найден/Не передан секрет WEB proxy")
        hostname, port = address[0], address[1] or 443
        sslctx = ssl.create_default_context()
        if insecure:
            sslctx.check_hostname = False
            sslctx.verify_mode = ssl.CERT_NONE
            self.client.warn("WEB proxy: проверка TLS сертификата отключена (insecure)")
        transport = WebProxyTransport(hostname, port, secret, self.client, sslctx, browser)
        try:
            await transport.connect()
            stream = await transport.open_stream()
            self._wp_transport = transport
            self.sock = WebProxySocket(stream, transport)
            self._sock_sendall = self.sock.sock_sendall
            self._sock_recv = self.sock.sock_recv
            self._sock_recv_into = self.sock.sock_recv_into
            await self._mtproxy_obfuscation_handshake(secret)
        except BaseException:
            transport.close()
            self._wp_transport = None
            raise

    async def connect(self, socket_timeout=10, retrying=3):
        if self._state != 0:
            return self.client.info("Клиент уже подключён")
        mtproxy, webproxy, connp = False, False, ""
        if self.client.proxy:
            proxy_data = urlparse(self.client.proxy)
            ptype = proxy_data.scheme.lower()
            handshake = {
                "socks5": self.proxy_handshake_socks5,
                "http": self.proxy_handshake_http,
                "mtproxy": self.proxy_handshake_mtproxy,
                "webproxy": self.proxy_handshake_webproxy
            }.get(ptype.replace("s", "") if ptype.startswith("http") else ptype)
            if not handshake:
                raise ConnectionError()
            mtproxy = ptype.startswith("mtproxy")
            webproxy = ptype.startswith("webproxy")
        for _ in range(retrying):
            try:
                if webproxy:
                    await handshake((proxy_data.hostname, proxy_data.port or 443), self.address, proxy_data.username, proxy_data.password)
                    connp = f" через WEB proxy {proxy_data.hostname}:{proxy_data.port or 443}"
                else:
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    self.sock.settimeout(socket_timeout)
                    self.sock.setblocking(False)
                    self._sock_sendall = self.loop.sock_sendall
                    self._sock_recv = self.loop.sock_recv
                    self._sock_recv_into = self.loop.sock_recv_into
                    if self.client.proxy:
                        await handshake((proxy_data.hostname, proxy_data.port), self.address, proxy_data.username, proxy_data.password)
                        connp = f" через {proxy_data.hostname}:{proxy_data.port}"
                        if not mtproxy:
                            await self._sock_sendall(self.sock, b"\xef")
                    else:
                        await self.loop.sock_connect(self.sock, self.address)
                        await self._sock_sendall(self.sock, b"\xef")
            except BaseException as ex:
                self.client.error(f"Ошибка подключения -> {ex}")
                await asyncio.sleep(1.5)
            else:
                self.client.info(f"Подключено к {self.address[0]}:{self.address[1]}{connp}")
                self._state = 1
                return
        self.client.error(f"Не подключился к {self.address[0]}:{self.address[1]}{connp}")
        raise ConnectionError()

    async def _send(self, data):
        length = len(data) // 4
        try:
            await self._sock_sendall(self.sock, (struct.pack("<B", length) + data) if length < 127 else (struct.pack("<I", (length << 8) | 0x7f) + data))
        except BaseException as ex:
            self.client.error(f"Ошибка отправки -> {ex}")

    async def _recv(self):
        length = await self._sock_recv(self.sock, 1)
        if not length:
            return None
        if length == b"\x7f":
            length3 = await self._sock_recv(self.sock, 3)
            if not length3:
                return None
            length = struct.unpack("<I", length3 + b"\x00")[0] * 4
        else:
            length = length[0] * 4
        view = memoryview(bytearray(length))
        lbytes = await self._sock_recv_into(self.sock, view)
        if not lbytes:
            return None
        while lbytes < length:
            chunk = await self._sock_recv_into(self.sock, view[lbytes:])
            if not chunk:
                return None
            lbytes += chunk
        return view

    async def mtproxy_send(self, data):
        length = len(data) // 4
        try:
            await self._sock_sendall(self.sock, self.__enc.crypt((struct.pack("<B", length) + data) if length < 127 else (struct.pack("<I", (length << 8) | 0x7f) + data)))
        except BaseException as ex:
            self.client.error(f"Ошибка отправки -> {ex}")

    async def mtproxy_recv(self):
        enc_length_byte = await self._sock_recv(self.sock, 1)
        if not enc_length_byte:
            return None
        length_byte = self.__dec.crypt(enc_length_byte)
        if length_byte == b"\x7f":
            enc_length3 = await self._sock_recv(self.sock, 3)
            if not enc_length3:
                return None
            length = struct.unpack("<I", self.__dec.crypt(enc_length3) + b"\x00")[0] * 4
        else:
            length = length_byte[0] * 4
        view = memoryview(bytearray(length))
        lbytes = await self._sock_recv_into(self.sock, view)
        if not lbytes:
            return None
        while lbytes < length:
            chunk = await self._sock_recv_into(self.sock, view[lbytes:])
            if not chunk:
                return None
            lbytes += chunk
        return memoryview(self.__dec.crypt(view))

    async def mtproxy_dd_send(self, data):
        inner_packet = data + urandom((4 - len(data) % 4) % 4)
        try:
            await self._sock_sendall(self.sock, self.__enc.crypt(struct.pack("<i", len(inner_packet)) + inner_packet))
        except BaseException as ex:
            self.client.error(f"Ошибка отправки DD -> {ex}")

    async def mtproxy_dd_recv(self):
        enc_header = await self._sock_recv(self.sock, 4)
        if not enc_header:
            return None
        enc_body = await self._sock_recv(self.sock, struct.unpack("<i", self.__dec.crypt(enc_header))[0])
        if not enc_body:
            return None
        return memoryview(self.__dec.crypt(enc_body))

    async def _recv_exactly_cold(self, n: int):
        buf = bytearray(n)
        view = memoryview(buf)
        lbytes = 0
        while lbytes < n:
            chunk = await self._sock_recv_into(self.sock, view[lbytes:])
            if not chunk:
                raise ConnectionError("Соединение закрыто сервером")
            lbytes += chunk
        return buf

    async def mtproxy_ee_send(self, data):
        inner_packet = data + urandom((4 - len(data) % 4) % 4)
        encrypted_data = self.__enc.crypt(struct.pack("<i", len(inner_packet)) + inner_packet)
        if self.__first_app_data:
            hs, self.__first_app_data = self.__first_app_data, None
            first_chunk, encrypted_data = encrypted_data[:2878 - len(hs)], encrypted_data[2878 - len(hs):]
            await self._sock_sendall(self.sock, b"\x14\x03\x03\x00\x01\x01\x17\x03\x03" + struct.pack(">H", len(hs) + len(first_chunk)) + hs + first_chunk)
        for i in range(0, len(encrypted_data), 2878):
            chunk = encrypted_data[i:i + 2878]
            await self._sock_sendall(self.sock, b"\x17\x03\x03" + struct.pack(">H", len(chunk)) + chunk)

    async def _recv_decrypted_exactly(self, n: int):
        while len(self.__dec_buf) < n:
            while len(self.__raw_buf) >= 5:
                if self.__raw_buf[:3] != b"\x17\x03\x03":
                    raise ConnectionError("Invalid Fake-TLS header")
                payload_len = struct.unpack(">H", self.__raw_buf[3:5])[0]
                if len(self.__raw_buf) >= 5 + payload_len:
                    self.__dec_buf.extend(self.__dec.crypt(self.__raw_buf[5:5+payload_len]))
                    del self.__raw_buf[:5+payload_len]
                    continue
                break

            if len(self.__dec_buf) >= n:
                break

            chunk = await self._sock_recv(self.sock, 65536)
            if not chunk:
                raise ConnectionError("Соединение закрыто сервером")
            self.__raw_buf.extend(chunk)

        result = self.__dec_buf[:n]
        del self.__dec_buf[:n]
        return result

    async def mtproxy_ee_recv(self):
        dec_header = await self._recv_decrypted_exactly(4)
        if not dec_header: return None

        payload_len = struct.unpack("<i", dec_header)[0]
        dec_body = await self._recv_decrypted_exactly(payload_len)


        if not dec_body: return None
        return memoryview(dec_body)
