"""ED2K 找源代理服务（部署到公网 Linux VPS，python3 零依赖运行）

作用：替客户端连 eD2k 网络（公共服务器）查询某文件（fileid）的源节点列表，
对外提供 HTTP API，客户端拿到源后在本机直连下载。

API：
    GET /sources?fileid=<32位hex>&size=<字节数>
    请求头（可选）：X-Token: <PROXY_TOKEN>
    响应：{"sources": [["ip", port], ...], "query": "ip:port"}

找源流程：对每个内置服务器依次尝试 [明文协议] → [eMule obfuscation 加密协议]，
聚合去重所有源后返回。

部署（Linux VPS）：
    python3 ed2k_proxy_server.py [port]
    建议配 systemd 常驻 + 防火墙仅放行该端口。

协议参考：eMule EncryptedStreamSocket.cpp / opcodes.h（GPL）
- 明文：0xE3 + uint32BE(len) + opcode + payload
- 加密：DH(768bit, g=2, p=dh768_p) 协商密钥 S，SendKey=MD5(S+34)、RecvKey=MD5(S+203)，
  RC4 丢弃前 1024 字节；MagicValue=0x835E6FC4
- 操作码：LOGINREQUEST=0x01, GET_SOURCES=0x19, FOUND_SOURCES=0x42
"""

import hashlib
import json
import os
import secrets
import socket
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# ---------------- 配置 ----------------
PROXY_TOKEN = ""               # 客户端请求头 X-Token 校验值；置空则不校验
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8080
QUERY_TIMEOUT = 12             # 单台服务器找源超时（秒）
MAX_SERVERS = 5                # 每次最多尝试的服务器数

# 2026-08 活跃 eD2k 服务器（来源：emule-security.org / 社区列表），可按需增删
ED2K_SERVERS = [
    ("176.123.5.89", 4725),    # eMule Sunrise
    ("77.42.68.79", 4232),     # Nordic Server
    ("85.121.5.137", 4232),    # Sharing-Devils No.2
    ("91.208.162.87", 4232),   # Sharing-Devils No.4
    ("213.141.198.207", 4232), # Mazinga
    ("193.187.90.12", 4661),   # Drunken Donkey（老式明文端口）
    ("45.82.80.155", 5687),    # eMule Security
]

# ---------------- eMule 常量 ----------------
PROTO_EDONKEY = 0xE3
OP_LOGINREQUEST = 0x01
OP_GETSOURCES = 0x19
OP_FOUND_SOURCES = 0x42
MAGIC_SYNC = 0x835E6FC4
MAGIC_REQUESTER = 34
MAGIC_SERVER = 203
DH_PRIME = bytes.fromhex(
    "F2BF52C55F587ADD5371A936E886EB3C6217A33EC34CB40DC73A41A643AFFCE7"
    "21FC286366535BDB"  # 48
    "CE259F2286DA4A91B207CBAA5255D4F61CCEAED45AD5E0747DF7781828105F34"
    "0F762387F88B289142FB42688F05150F548B5F436AF70DF3"
)
USERHASH = os.urandom(16)      # 会话用户哈希（随机即可，非持久身份）


# ---------------- RC4（纯 Python，零依赖） ----------------
class _RC4:
    def __init__(self, key: bytes):
        self._s = list(range(256))
        j = 0
        for i in range(256):
            j = (j + self._s[i] + key[i % len(key)]) & 0xFF
            self._s[i], self._s[j] = self._s[j], self._s[i]
        self._i = self._j = 0

    def _gen(self, n: int) -> bytes:
        out = bytearray()
        for _ in range(n):
            self._i = (self._i + 1) & 0xFF
            self._j = (self._j + self._s[self._i]) & 0xFF
            self._s[self._i], self._s[self._j] = self._s[self._j], self._s[self._i]
            out.append(self._s[(self._s[self._i] + self._s[self._j]) & 0xFF])
        return bytes(out)

    def discard(self, n: int):
        self._gen(n)

    def crypt(self, data: bytes) -> bytes:
        ks = self._gen(len(data))
        return bytes(a ^ b for a, b in zip(data, ks))


# ---------------- 底层 IO ----------------
def _read_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf += chunk
    if len(buf) < n:
        raise IOError("连接提前断开")
    return bytes(buf)


def _send_packet(sock: socket.socket, opcode: int, body: bytes = b"", crypt=None):
    pkt = b"\xe3" + struct.pack(">I", len(body) + 1) + bytes([opcode]) + body
    sock.sendall(crypt.crypt(pkt) if crypt else pkt)


def _recv_packet(sock: socket.socket, crypt=None) -> tuple:
    raw = _read_exact(sock, 5)
    if crypt:
        raw = crypt.crypt(raw)
    if raw[0] != PROTO_EDONKEY:
        raise IOError("协议头错误")
    length = struct.unpack(">I", raw[1:5])[0]
    if length > 1_000_000:
        raise IOError("非法包长度")
    payload = _read_exact(sock, length)
    if crypt:
        payload = crypt.crypt(payload)
    return payload[0], payload[1:]


def _make_login() -> bytes:
    """eMule 风格 LoginRequest：userhash + clientid + tcp/udp 端口 + 3 个 tag"""
    def tag_u32(name: int, val: int) -> bytes:
        return bytes([0x03]) + struct.pack("<H", name) + struct.pack("<I", val)

    def tag_str(name: int, s: str) -> bytes:
        b = s.encode("utf-8", "replace")[:40]
        return bytes([0x02]) + struct.pack("<H", name) + struct.pack("<H", len(b)) + b

    tags = (tag_str(0x01, "WinAppMigrator")
            + tag_u32(0x11, 0x3C)          # EDONKEYVERSION
            + tag_u32(0x20, 0x00000001)    # flags（支持压缩）
            + tag_u32(0xFB, 0x00020C39))   # eMule 0.50a
    body = (USERHASH
            + struct.pack("<I", 0)         # clientid（未入网）
            + struct.pack("<H", 4662)      # tcpport
            + struct.pack("<H", 4662)      # udpport
            + struct.pack("<I", len(tags) and 4)  # tag 数量
            + tags)
    return bytes([OP_LOGINREQUEST]) + body


def _parse_found_sources(payload: bytes, fileid: bytes) -> list:
    """FOUND_SOURCES(0x42) = fileid(16) + count(2 LE) + count×(ip4 + port2 LE)"""
    if len(payload) < 18 or payload[:16] != fileid:
        return []
    count = struct.unpack("<H", payload[16:18])[0]
    srcs, off = [], 18
    for _ in range(min(count, 200)):
        if off + 6 > len(payload):
            break
        ip = socket.inet_ntoa(payload[off:off + 4])
        port = struct.unpack("<H", payload[off + 4:off + 6])[0]
        srcs.append((ip, port))
        off += 6
    return srcs


# ---------------- 明文找源 ----------------
def _query_plain(host: str, port: int, fileid: bytes, timeout: float) -> list:
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.settimeout(timeout)
    try:
        # 握手：客户端 tag（0xE3 + tag）
        tag = (os.urandom(16)
               + struct.pack("<I", 0) + struct.pack("<H", 4662)
               + struct.pack("<H", 4662) + struct.pack("<I", 0x0C39)
               + bytes([2]) + struct.pack("<H", 0))
        sock.sendall(b"\xe3" + struct.pack(">I", len(tag)) + tag)
        _recv_packet(sock)  # 服务器 tag
        _send_packet(sock, OP_LOGINREQUEST, _make_login()[1:])
        # 等待登录结果（最多读 10 个包或 ID_CHANGE）
        for _ in range(10):
            op, _ = _recv_packet(sock)
            if op == 0x40:      # OP_IDCHANGE = 登录成功
                break
        _send_packet(sock, OP_GETSOURCES, fileid)
        for _ in range(20):
            op, payload = _recv_packet(sock)
            if op == OP_FOUND_SOURCES:
                return _parse_found_sources(payload, fileid)
            if op in (0x48, 0x18):  # 断开/错误
                break
        return []
    finally:
        sock.close()


# ---------------- obfuscation 找源 ----------------
def _query_obfuscated(host: str, port: int, fileid: bytes, timeout: float) -> list:
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.settimeout(timeout)
    try:
        # 1. DH：生成 a，发送 marker + G^A
        p = int.from_bytes(DH_PRIME, "big")
        a = secrets.randbits(128)
        ga = pow(2, a, p).to_bytes(96, "big")
        marker = secrets.token_bytes(1)
        while marker[0] in (0xE3, 0xC5, 0xD4, 0xE4, 0xE5):
            marker = secrets.token_bytes(1)
        sock.sendall(marker + ga)
        # 2. 收 G^B，算 S
        gb = int.from_bytes(_read_exact(sock, 96), "big")
        s = pow(gb, a, p).to_bytes(96, "big")
        send_key = hashlib.md5(s + bytes([MAGIC_REQUESTER])).digest()
        recv_key = hashlib.md5(s + bytes([MAGIC_SERVER])).digest()
        rc4s, rc4r = _RC4(send_key), _RC4(recv_key)
        rc4s.discard(1024)
        rc4r.discard(1024)
        # 3. 读服务器加密应答（4 magic + 1 methods + 1 preferred + 1 padlen + pad）
        enc = _read_exact(sock, 7)
        dec = rc4r.crypt(enc)
        if struct.unpack("<I", dec[:4])[0] != MAGIC_SYNC:
            raise IOError("obfuscation 同步校验失败")
        padlen = dec[6]
        if padlen:
            rc4r.crypt(_read_exact(sock, padlen))
        # 4. 发送客户端加密应答（可延迟到首个 payload：与 login 一并发送）
        final = struct.pack("<I", MAGIC_SYNC) + bytes([0x00]) + bytes([0x00]) + b""
        login_pkt = b"\xe3" + struct.pack(">I", len(_make_login())) + _make_login()
        sock.sendall(rc4s.crypt(final + login_pkt))
        # 5. 等待登录结果 + GET_SOURCES
        for _ in range(10):
            op, _ = _recv_packet(sock, rc4r)
            if op == 0x40:
                break
        _send_packet(sock, OP_GETSOURCES, fileid, rc4s)
        for _ in range(20):
            op, payload = _recv_packet(sock, rc4r)
            if op == OP_FOUND_SOURCES:
                return _parse_found_sources(payload, fileid)
            if op in (0x48, 0x18):
                break
        return []
    finally:
        sock.close()


# ---------------- 对外查询 ----------------
def find_sources(fileid_hex: str, size: int) -> tuple:
    """依次尝试各服务器（明文→加密），聚合去重。返回 (sources, 命中的服务器)"""
    try:
        fileid = bytes.fromhex(fileid_hex)
    except ValueError:
        return [], ""
    if len(fileid) != 16:
        return [], ""
    seen, found = set(), []
    for host, port in ED2K_SERVERS[:MAX_SERVERS]:
        srcs = []
        try:
            srcs = _query_plain(host, port, fileid, QUERY_TIMEOUT)
        except Exception:
            try:
                srcs = _query_obfuscated(host, port, fileid, QUERY_TIMEOUT)
            except Exception:
                continue
        for item in srcs:
            if item not in seen:
                seen.add(item)
                found.append(list(item))
        if found:
            return found, f"{host}:{port}"
    return [], ""


# ---------------- HTTP 服务 ----------------
class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _ok(self, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if PROXY_TOKEN:
            if self.headers.get("X-Token") != PROXY_TOKEN:
                self.send_error(403, "Forbidden")
                return
        parsed = urlparse(self.path)
        if parsed.path != "/sources":
            self.send_error(404)
            return
        q = parse_qs(parsed.query)
        fileid = (q.get("fileid") or [""])[0].lower()
        size = int((q.get("size") or ["0"])[0])
        if not fileid:
            self.send_error(400, "missing fileid")
            return
        sources, hit = find_sources(fileid, size)
        self._ok({"sources": sources, "query": hit})


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else LISTEN_PORT
    srv = ThreadingHTTPServer((LISTEN_HOST, port), _Handler)
    print(f"[ed2k-proxy] 监听 {LISTEN_HOST}:{port}，服务器列表 {len(ED2K_SERVERS)} 个",
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
