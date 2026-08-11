"""ED2K 直连下载（实验性）：解析 ed2k 链接内嵌 sources 并直连源节点分块下载

协议：eDonkey2000 TCP 传输（eMule 明文兼容模式）
- 连接：TCP 到源节点端口（sources 中指定，通常 4661+）
- 握手：OP_EDONKEYHEADER(0xE3) + Client Tag，双向交换
- 下载请求：OP_FILEREQUEST(0x46) = fileid(16) + partnum(1)
- 数据响应：OP_REQPARTS(0x47) = partnum(1) + chunk 数据
- 分块：PART_SIZE = 9,728,000 字节（9.28 MiB），传输 chunk 10,240 字节
- 完成后用 ED2K 文件哈希（MD4 Merkle）校验

局限：仅能下载链接内嵌 sources 的地址；无 sources 的链接协议上无法发现
源节点（需 Kad/服务器搜索，属另一完整协议栈），此时请使用 HTTP 镜像或本机
迅雷/eMule 客户端。
"""

import json
import os
import re
import select
import socket
import struct
import threading
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

from winapp_migrator.core.fast_download import ED2K_PART_SIZE, _ed2k_file_hash

OP_FILEREQUEST = 0x46
OP_REQPARTS = 0x47
CHUNK_SIZE = 10240
_CONNECT_TIMEOUT = 8
_MAX_PACKET = 10_000_000


def find_sources_via_proxy(fileid_hex: str, size: int, proxy_url: str,
                           timeout: float = 25.0) -> List[Tuple[str, int]]:
    """调用找源代理 API 获取源列表。返回 [(ip, port), ...]，失败返回空。
    代理地址支持 http://host:port 或 http://host:port?token=xxx（token 作为 X-Token 请求头）"""
    try:
        u = urllib.parse.urlparse(proxy_url.strip())
        base = f"{u.scheme}://{u.netloc}"
        token = (urllib.parse.parse_qs(u.query).get("token") or [""])[0]
        url = f"{base}/sources?fileid={fileid_hex}&size={int(size)}"
        req = urllib.request.Request(url, headers={"X-Token": token} if token else {})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        return [tuple(s) for s in data.get("sources", []) if len(s) == 2]
    except Exception:
        return []


def _sanitize_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip().strip(".")
    return name or f"ed2k_{int(time.time())}.bin"


def parse_ed2k_full(url: str) -> Optional[dict]:
    """解析 ed2k 链接，返回 {filename, size, md4, fileid, sources}。

    sources 从链接尾部内嵌段提取，格式：|sources,ip1:port1,ip2:port2|
    """
    try:
        body = url.split("ed2k://", 1)[1]
        parts = body.split("|")
        if len(parts) < 6 or parts[1] != "file":
            return None
        md4 = parts[4].lower()
        if not re.fullmatch(r"[0-9a-f]{32}", md4):
            return None
        sources: List[Tuple[str, int]] = []
        for seg in parts[5:]:
            seg = seg.strip()
            if seg.startswith("sources,"):
                for item in seg[len("sources,"):].split(","):
                    item = item.strip()
                    if ":" in item:
                        ip, _, port = item.rpartition(":")
                        if port.isdigit():
                            sources.append((ip, int(port)))
                break
        return {
            "filename": _sanitize_name(parts[2]),
            "size": int(parts[3]) if parts[3].isdigit() else 0,
            "md4": md4,
            "fileid": bytes.fromhex(md4),
            "sources": sources,
        }
    except (ValueError, IndexError):
        return None


def _read_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return bytes(buf)


class Ed2kTask:
    """ED2K 直连下载任务。状态字段线程安全，UI 侧轮询 snapshot() 刷新"""

    def __init__(self, link: str, dest_dir: str, proxy_url: str = ""):
        info = parse_ed2k_full(link)
        if not info:
            raise ValueError("ed2k 链接格式无效")
        if not info["sources"] and not proxy_url:
            raise ValueError("ed2k 链接无内嵌源地址（sources），且未配置找源代理")
        self.link = link
        self.dest_dir = dest_dir
        self.filename = info["filename"]
        self.path = os.path.join(dest_dir, info["filename"])
        self.total = info["size"]
        self.md4 = info["md4"]
        self._fileid = info["fileid"]
        self._sources = list(info["sources"])
        self._proxy = proxy_url.strip()
        self.done = 0
        self.status = "pending"
        self.error = ""
        self.mode = "ed2k"
        self.segments = len(self._sources)
        self.md4_ok = False
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    # ---------- 线程安全访问 ----------
    def _update_done(self, n: int):
        with self._lock:
            self.done += n

    def _set_status(self, s: str, err: str = ""):
        with self._lock:
            self.status = s
            self.error = err

    def cancel(self):
        self._cancel.set()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def join(self, timeout: Optional[float] = None):
        if self._thread:
            self._thread.join(timeout)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self.status, "total": self.total, "done": self.done,
                "filename": self.filename, "path": self.path, "error": self.error,
                "mode": self.mode, "segments": self.segments,
                "display_name": self.filename, "md4_ok": self.md4_ok,
            }

    @property
    def _cancelled(self) -> bool:
        return self._cancel.is_set()

    # ---------- 下载 ----------
    def _run(self):
        if not self._sources and self._proxy:
            # 无内嵌源地址 → 通过找源代理联网查源
            self._set_status("finding")
            self._sources = find_sources_via_proxy(
                self._fileid.hex(), self.total, self._proxy)
            if self._cancelled:
                self._set_status("canceled")
                return
            if not self._sources:
                self._set_status("error", "找源代理未发现该文件的源节点（文件可能已无人在线分享），"
                                          "可尝试 HTTP 镜像或本机迅雷/eMule")
                return
        self._set_status("downloading")
        try:
            if self.total <= 0:
                raise ValueError("ed2k 链接文件大小无效")
            last_err = "所有源节点连接失败"
            ok = False
            for ip, port in self._sources:
                if self._cancelled:
                    self._set_status("canceled")
                    return
                err = self._try_source(ip, port)
                if err is None:
                    ok = True
                    break
                last_err = f"{ip}:{port} → {err}"
            if self._cancelled:
                self._set_status("canceled")
                return
            if not ok:
                self._set_status("error", f"ED2K 直连失败：{last_err}（可尝试 HTTP 镜像或本机迅雷/eMule）")
                return
            # 下载完成 → MD4 Merkle 哈希校验（与 ed2k 链接哈希算法一致）
            if _ed2k_file_hash(self.path).lower() == self.md4:
                with self._lock:
                    self.status = "done"
                    self.md4_ok = True
            else:
                try:
                    os.remove(self.path)
                except OSError:
                    pass
                self._set_status("error", "文件 MD4 哈希校验失败，下载内容不完整或源数据有误")
        except Exception as e:
            self._set_status("error", str(e))

    def _try_source(self, ip: str, port: int) -> Optional[str]:
        """尝试从一个源节点完整下载；成功返回 None，失败返回错误描述"""
        try:
            sock = socket.create_connection((ip, port), timeout=_CONNECT_TIMEOUT)
        except OSError as e:
            return f"连接失败 {e}"
        try:
            self._send_handshake(sock)
            self._read_handshake(sock)
            num_parts = (self.total + ED2K_PART_SIZE - 1) // ED2K_PART_SIZE
            # 分片文件按序累积，断源重连时从已写位置续传
            with open(self.path, "wb") as f:
                for part in range(num_parts):
                    if self._cancelled:
                        return "已取消"
                    self._download_part(sock, part, f)
            return None
        except InterruptedError:
            return "已取消"
        except Exception as e:
            return str(e)
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _download_part(self, sock: socket.socket, part: int, f):
        """下载单个 9.28MB 分块（请求一次 part，循环收 0x47 数据块）"""
        part_size = min(ED2K_PART_SIZE, self.total - part * ED2K_PART_SIZE)
        written = 0
        while written < part_size:
            if self._cancelled:
                raise InterruptedError("已取消")
            self._send_packet(sock, OP_FILEREQUEST, self._fileid + bytes([part]))
            op, payload = self._read_packet(sock)
            if op != OP_REQPARTS:
                raise IOError(f"源返回意外操作码 0x{op:02x}")
            data = payload[1:] if payload else b""  # payload = partnum + 数据块
            if not data:
                raise IOError("收到空数据块")
            f.seek(part * ED2K_PART_SIZE + written)
            f.write(data)
            written += len(data)
            self._update_done(len(data))

    # ---------- 协议 ----------
    def _read_packet(self, sock: socket.socket) -> Tuple[int, bytes]:
        hdr = _read_exact(sock, 5)
        if len(hdr) < 5 or hdr[0] != 0xE3:
            raise IOError("协议头错误或连接已断开")
        length = struct.unpack(">I", hdr[1:5])[0]
        if length > _MAX_PACKET:
            raise IOError("非法包长度")
        payload = _read_exact(sock, length)
        if len(payload) < length:
            raise IOError("数据不完整")
        return payload[0], payload[1:]

    def _send_packet(self, sock: socket.socket, op: int, body: bytes):
        sock.sendall(b"\xe3" + struct.pack(">I", len(body) + 1) + bytes([op]) + body)

    def _send_handshake(self, sock: socket.socket):
        """发送 eMule 兼容 Client Tag：hash16 + clientid + tcpport + udpport + version + proto + flags"""
        tag = (os.urandom(16)              # 会话哈希（客户端标识）
               + struct.pack("<I", 0)      # clientid（未入网为 0）
               + struct.pack("<H", 4662)   # tcpport
               + struct.pack("<H", 4662)   # udpport
               + struct.pack("<I", 0x0C39) # 客户端版本（eMule 兼容）
               + bytes([2])                # 协议扩展：2 = eMule
               + struct.pack("<H", 0))     # 能力 flags
        sock.sendall(b"\xe3" + struct.pack(">I", len(tag)) + tag)

    def _read_handshake(self, sock: socket.socket):
        """读取对方握手（非强制，3 秒内无数据则跳过）"""
        r, _, _ = select.select([sock], [], [], 3)
        if r:
            try:
                self._read_packet(sock)
            except Exception:
                pass
