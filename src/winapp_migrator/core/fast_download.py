"""多线程分段高速下载（纯标准库 urllib，无第三方依赖）

原理：HTTP Range 将文件切成 N 段并发下载，完成后按序合并（IDM/迅雷同款思路）。
- 默认 16 段并发，速度通常为浏览器单连接的 2-3 倍以上
- 服务器不支持 Range / 文件过小时自动回退单线程
- 支持取消；分片写 .part 临时文件，完成后合并删除
"""

import os
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_SEGMENTS = 32
MIN_SEGMENT_BYTES = 1024 * 1024   # 小于 1MB 不分段（分片开销大于收益）
SEGMENT_RETRY = 2                 # 每段失败重试次数
READ_CHUNK = 1024 * 1024          # 1MB 读缓冲，减少锁竞争与 IO 次数
_TIMEOUT = 60
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _sanitize_name(name: str) -> str:
    """清理 Windows 非法文件名符号，保留扩展名"""
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip().strip(".")
    return name or f"download_{int(time.time())}.bin"


def _filename_from(url: str, content_disp: str = "") -> str:
    """解析文件名：Content-Disposition > URL 最后一段 > 时间戳"""
    if content_disp:
        for part in content_disp.split(";"):
            part = part.strip()
            if part.lower().startswith("filename="):
                name = part.split("=", 1)[1].strip('"').strip("'")
                if name:
                    return _sanitize_name(name)
    name = url.split("?")[0].rstrip("/").split("/")[-1]
    return _sanitize_name(name)


class DownloadTask:
    """一个下载任务。状态字段线程安全，UI 侧轮询 snapshot() 刷新"""

    def __init__(self, url: str, dest_dir: str, segments: int = DEFAULT_SEGMENTS):
        self.url = url
        self.dest_dir = dest_dir
        self.filename = ""            # 探测后确定
        self.path = ""                # 最终文件完整路径
        self.total = 0
        self.done = 0                 # 已下载字节
        self.status = "pending"       # pending/downloading/done/error/canceled
        self.error = ""
        self.mode = "single"          # multi=分段并行 / single=单线程（探测后更新）
        self._segments = segments
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
                "mode": self.mode, "segments": self._segments,
            }

    @property
    def _cancelled(self) -> bool:
        return self._cancel.is_set()

    # ---------- 下载 ----------
    def _open(self, method: str = "GET", headers: Optional[dict] = None):
        h = {"User-Agent": _UA}
        if headers:
            h.update(headers)
        req = urllib.request.Request(self.url, method=method, headers=h)
        return urllib.request.urlopen(req, timeout=_TIMEOUT)

    def _probe_head(self) -> bool:
        """HEAD 探测大小与 Range 支持"""
        try:
            with self._open("HEAD") as resp:
                headers = dict(resp.headers)
        except (urllib.error.HTTPError, urllib.error.URLError):
            return False
        length = headers.get("Content-Length")
        self.total = int(length) if length and length.isdigit() else 0
        self.filename = _filename_from(self.url, headers.get("Content-Disposition", ""))
        return headers.get("Accept-Ranges", "").lower() == "bytes" and self.total > 0

    def _probe_range(self) -> bool:
        """GET Range: bytes=0-0 探测（HEAD 不可用时的回退）"""
        try:
            with self._open("GET", {"Range": "bytes=0-0"}) as resp:
                if resp.status != 206:
                    return False
                cr = resp.headers.get("Content-Range", "")
                total = cr.rsplit("/", 1)[-1] if "/" in cr else ""
                self.total = int(total) if total.isdigit() else 0
                self.filename = _filename_from(self.url, resp.headers.get("Content-Disposition", ""))
                return self.total > 0
        except (urllib.error.HTTPError, urllib.error.URLError):
            return False

    def _run(self):
        try:
            self._set_status("downloading")
            range_ok = self._probe_head() or self._probe_range()
            if not range_ok or self.total <= MIN_SEGMENT_BYTES:
                self.mode = "single"
                self._download_single()
            else:
                self.mode = "multi"
                self._download_multi()
        except urllib.error.HTTPError as e:
            self._set_status("error", f"HTTP {e.code} {e.reason}")
        except urllib.error.URLError as e:
            self._set_status("error", f"网络错误 {e.reason}")
        except Exception as e:
            self._set_status("error", str(e))

    def _cleanup(self, paths):
        items = paths if isinstance(paths, (list, tuple)) else [paths]
        for p in items:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

    def _download_single(self):
        self.path = os.path.join(self.dest_dir, self.filename)
        tmp = self.path + ".part"
        try:
            with self._open() as resp, open(tmp, "wb") as f:
                while True:
                    if self._cancelled:
                        raise InterruptedError("已取消")
                    chunk = resp.read(READ_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    self._update_done(len(chunk))
            os.replace(tmp, self.path)
            self._set_status("done")
        except InterruptedError:
            self._cleanup(tmp)
            self._set_status("canceled")

    def _download_multi(self):
        self.path = os.path.join(self.dest_dir, self.filename)
        n = min(self._segments, self.total)
        seg_size = (self.total + n - 1) // n
        ranges = [(i * seg_size, min((i + 1) * seg_size - 1, self.total - 1)) for i in range(n)]
        part_paths = [f"{self.path}.part{i}" for i in range(n)]

        threads = [threading.Thread(target=self._download_segment, args=(start, end, pp), daemon=True)
                   for (start, end), pp in zip(ranges, part_paths)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if self._cancelled:
            self._cleanup(part_paths)
            self._set_status("canceled")
            return

        # 失败段串行补下：服务器限制单 IP 并发数时，32 段中部分会失败，
        # 这里降级为串行续传保证不整体失败（比限并发下的多段重试更稳更快）
        for i, (start, end) in enumerate(ranges):
            if self._cancelled:
                break
            if not os.path.exists(part_paths[i]) or \
                    os.path.getsize(part_paths[i]) < end - start + 1:
                self._repair_segment(start, end, part_paths[i])
        if self._cancelled:
            self._cleanup(part_paths)
            self._set_status("canceled")
            return
        # 严格校验每段完整，避免合并出损坏文件
        for i, (start, end) in enumerate(ranges):
            if not os.path.exists(part_paths[i]) or \
                    os.path.getsize(part_paths[i]) < end - start + 1:
                self._cleanup(part_paths)
                self._set_status("error", "分片下载失败（服务器限制连接数或中断连接）")
                return
        try:
            with open(self.path, "wb") as out:
                for pp in part_paths:
                    with open(pp, "rb") as f:
                        while True:
                            chunk = f.read(READ_CHUNK)
                            if not chunk:
                                break
                            out.write(chunk)
                    os.remove(pp)
            self._set_status("done")
        except InterruptedError:
            self._cleanup(part_paths)
            self._set_status("canceled")
        except OSError as e:
            self._cleanup(part_paths)
            self._set_status("error", f"合并失败 {e}")

    def _download_segment(self, start: int, end: int, part_path: str):
        headers = {"Range": f"bytes={start}-{end}"}
        for _ in range(SEGMENT_RETRY + 1):
            if self._cancelled:
                return
            try:
                with self._open("GET", headers) as resp, open(part_path, "wb") as f:
                    while True:
                        if self._cancelled:
                            return
                        chunk = resp.read(READ_CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        self._update_done(len(chunk))
                if os.path.getsize(part_path) >= end - start + 1:
                    return  # 该段完整下载完成
            except Exception:
                time.sleep(0.5)
        # 重试耗尽：段可能不完整，由补下阶段处理

    def _repair_segment(self, start: int, end: int, part_path: str):
        """单线程续传补下失败段：从已写位置继续 Range 下载"""
        for _ in range(SEGMENT_RETRY + 1):
            if self._cancelled:
                return
            written = os.path.getsize(part_path) if os.path.exists(part_path) else 0
            if written >= end - start + 1:
                return
            try:
                headers = {"Range": f"bytes={start + written}-{end}"}
                with self._open("GET", headers) as resp, open(part_path, "ab") as f:
                    while True:
                        if self._cancelled:
                            return
                        chunk = resp.read(READ_CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        self._update_done(len(chunk))
            except Exception:
                time.sleep(0.5)
