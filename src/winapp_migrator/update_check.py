"""客户端自动更新检查：每 30s 轮询服务器更新 API，发现新版本发信号提示。

服务器地址来源（优先级）：
1. QSettings("WinAppMigrator", "WinAppMigrator") 的 update_server
2. 环境变量 UPDATE_SERVER_URL（如 https://example.com）
未配置则自动禁用轮询。
"""
import json
import os
import threading
import urllib.request

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, QSettings

APP_VERSION = "1.0.0"          # 当前客户端版本（发新版时同步修改）
POLL_INTERVAL_MS = 30_000      # 30s 轮询


class UpdateChecker(QObject):
    """轮询更新服务器，发现新版本（未提示过）时发出 update_found 信号"""

    update_found = pyqtSignal(dict)   # latest/notes/size/force/url

    def __init__(self, parent=None):
        super().__init__(parent)
        q = QSettings("WinAppMigrator", "WinAppMigrator")
        server = (q.value("update_server", "") or "").strip().rstrip("/")
        if not server:
            server = os.environ.get("UPDATE_SERVER_URL", "").strip().rstrip("/")
        self.server = server
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self.check)
        self._notified = set()   # 本次运行已提示过的版本，避免重复弹窗

    def start(self):
        """启动轮询；未配置服务器地址则静默禁用"""
        if not self.server:
            return
        self.check()          # 启动立即检查一次
        self._timer.start()

    def check(self):
        if not self.server:
            return
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self):
        try:
            url = (f"{self.server}/api/update/check?"
                   f"version={APP_VERSION}&platform=windows")
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if not data.get("hasUpdate"):
                return
            ver = str(data.get("latest") or "")
            if not ver or ver in self._notified:
                return
            self._notified.add(ver)
            self.update_found.emit({
                "latest": ver,
                "notes": data.get("notes") or "",
                "size": data.get("size") or 0,
                "force": bool(data.get("force")),
                "url": self.server + (data.get("url") or ""),
            })
        except Exception:
            pass   # 网络异常/服务器不可达：静默失败，下轮重试
