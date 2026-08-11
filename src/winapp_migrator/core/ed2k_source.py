"""ED2K 联网找源（内置，无需服务器）：直连公共 eD2k 服务器查询某文件（fileid）的源节点

对每个内置服务器依次尝试 [明文协议] → [eMule obfuscation 加密协议]，聚合去重返回源。

协议参考：eMule EncryptedStreamSocket.cpp / opcodes.h（GPL）
- 明文：0xE3 + uint32BE(len) + opcode + payload
- 加密：DH(768bit, g=2, p=dh768_p) 协商密钥 S，SendKey=MD5(S+34)、RecvKey=MD5(S+203)，
  RC4 丢弃前 1024 字节；MagicValue=0x835E6FC4
- 操作码：LOGINREQUEST=0x01, GET_SOURCES=0x19, FOUND_SOURCES=0x42
"""

import hashlib
import os
import secrets
import socket
import struct
import time
from typing import List, Optional, Tuple

OP_LOGINREQUEST = 0x01
OP_GETSOURCES = 0x19
OP_FOUND_SOURCES = 0x42
MAGIC_SYNC = 0x835E6FC4
MAGIC_REQUESTER = 34
MAGIC_SERVER = 203
QUERY_TIMEOUT = 12            # 单台服务器找源超时（秒）
MAX_SERVERS = 5               # 每次最多尝试的服务器数
USERHASH = os.urandom(16)     # 会话用户哈希

DH_PRIME = bytes.fromhex(
    "F2BF52C55F587ADD5371A936E886EB3C6217A33EC34CB40DC73A41A643AFFCE7"
    "21FC286366535BDB"
    "CE259F2286DA4A91B207CBAA5255D4F61CCEAED45AD5E0747DF7781828105F34"
    "0F762387F88B289142FB42688F05150F548B5F436AF70DF3"
)

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


class _RC4:
    """纯 Python RC4（KSA + PRGA），加解密同一函数"""
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
    if raw[0] != 0xE3:
        raise IOError("协议头错误")
    length = struct.unpack(">I", raw[1:5])[0]
    if length > 1_000_000:
        raise IOError("非法包长度")
    payload = _read_exact(sock, length)
    if crypt:
        payload = crypt.crypt(payload)
    return payload[0], payload[1:]


def _make_login() -> bytes:
    """eMule 风格 LoginRequest：userhash + clientid + tcp/udp 端口 + 4 个 tag"""
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
            + struct.pack("<I", 4)         # tag 数量
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


def _query_plain(host: str, port: int, fileid: bytes, timeout: float) -> list:
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.settimeout(timeout)
    try:
        tag = (os.urandom(16)
               + struct.pack("<I", 0) + struct.pack("<H", 4662)
               + struct.pack("<H", 4662) + struct.pack("<I", 0x0C39)
               + bytes([2]) + struct.pack("<H", 0))
        sock.sendall(b"\xe3" + struct.pack(">I", len(tag)) + tag)
        _recv_packet(sock)  # 服务器 tag
        _send_packet(sock, OP_LOGINREQUEST, _make_login()[1:])
        for _ in range(10):
            op, _ = _recv_packet(sock)
            if op == 0x40:      # OP_IDCHANGE = 登录成功
                break
        _send_packet(sock, OP_GETSOURCES, fileid)
        for _ in range(20):
            op, payload = _recv_packet(sock)
            if op == OP_FOUND_SOURCES:
                return _parse_found_sources(payload, fileid)
            if op in (0x48, 0x18):
                break
        return []
    finally:
        sock.close()


def _query_obfuscated(host: str, port: int, fileid: bytes, timeout: float) -> list:
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.settimeout(timeout)
    try:
        p = int.from_bytes(DH_PRIME, "big")
        a = secrets.randbits(128)
        ga = pow(2, a, p).to_bytes(96, "big")
        marker = secrets.token_bytes(1)
        while marker[0] in (0xE3, 0xC5, 0xD4, 0xE4, 0xE5):
            marker = secrets.token_bytes(1)
        sock.sendall(marker + ga)
        gb = int.from_bytes(_read_exact(sock, 96), "big")
        s = pow(gb, a, p).to_bytes(96, "big")
        send_key = hashlib.md5(s + bytes([MAGIC_REQUESTER])).digest()
        recv_key = hashlib.md5(s + bytes([MAGIC_SERVER])).digest()
        rc4s, rc4r = _RC4(send_key), _RC4(recv_key)
        rc4s.discard(1024)
        rc4r.discard(1024)
        enc = _read_exact(sock, 7)
        dec = rc4r.crypt(enc)
        if struct.unpack("<I", dec[:4])[0] != MAGIC_SYNC:
            raise IOError("obfuscation 同步校验失败")
        padlen = dec[6]
        if padlen:
            rc4r.crypt(_read_exact(sock, padlen))
        final = struct.pack("<I", MAGIC_SYNC) + bytes([0x00]) + bytes([0x00]) + b""
        login_pkt = b"\xe3" + struct.pack(">I", len(_make_login())) + _make_login()
        sock.sendall(rc4s.crypt(final + login_pkt))
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


def find_sources(fileid_hex: str, size: int,
                 servers: Optional[List[Tuple[str, int]]] = None,
                 timeout: float = QUERY_TIMEOUT) -> List[Tuple[str, int]]:
    """依次尝试各服务器（明文→加密），聚合去重。返回 [(ip, port), ...]"""
    try:
        fileid = bytes.fromhex(fileid_hex)
    except ValueError:
        return []
    if len(fileid) != 16:
        return []
    seen, found = set(), []
    for host, port in (servers or ED2K_SERVERS)[:MAX_SERVERS]:
        try:
            srcs = _query_plain(host, port, fileid, timeout)
        except Exception:
            try:
                srcs = _query_obfuscated(host, port, fileid, timeout)
            except Exception:
                continue
        for item in srcs:
            if item not in seen:
                seen.add(item)
                found.append(item)
        if found:
            return found
    return []
