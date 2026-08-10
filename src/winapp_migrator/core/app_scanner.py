import os
import re
import json
import subprocess
import winreg
from pathlib import Path
from dataclasses import dataclass
from typing import List

from winapp_migrator.utils.helpers import setup_logging, get_directory_size

logger = setup_logging()

# 无控制台程序运行子进程时不弹黑窗口
NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

@dataclass
class AppInfo:
    name: str
    publisher: str
    install_location: Path
    version: str
    app_type: str
    size_bytes: int
    package_name: str = ""
    executable: str = ""

class AppScanner:
    def __init__(self):
        self.apps: List[AppInfo] = []

    def scan_all(self) -> List[AppInfo]:
        self.apps = []
        self._scan_uwp()
        self._scan_win32_registry()
        self._scan_common_folders()
        return sorted(self.apps, key=lambda a: a.name.lower())

    def _scan_uwp(self):
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-AppxPackage | Select-Object Name, PackageFullName, Publisher, "
                    "InstallLocation, Version | ConvertTo-Json -Compress",
                ],
                capture_output=True,
                text=True,
                check=False,
                encoding="utf-8",
                errors="ignore",
                creationflags=NO_WINDOW,
            )
            if result.returncode != 0:
                logger.warning("扫描UWP失败: %s", result.stderr)
                return
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                loc = item.get("InstallLocation")
                if not loc or not Path(loc).exists():
                    continue
                loc_path = Path(loc)
                if self._is_system_path(loc_path):
                    continue
                self.apps.append(AppInfo(
                    name=item.get("Name", "Unknown"),
                    publisher=item.get("Publisher", ""),
                    install_location=loc_path,
                    version=item.get("Version", ""),
                    app_type="UWP",
                    size_bytes=0,
                    package_name=item.get("PackageFullName", ""),
                ))
        except Exception as e:
            logger.exception("UWP扫描异常: %s", e)

    def _scan_win32_registry(self):
        keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        seen = {str(a.install_location).lower() for a in self.apps}
        for hkey, path in keys:
            try:
                with winreg.OpenKey(hkey, path) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        sub_name = winreg.EnumKey(key, i)
                        try:
                            with winreg.OpenKey(key, sub_name) as sub:
                                name = self._reg_value(sub, "DisplayName")
                                if not name:
                                    continue
                                loc = self._reg_value(sub, "InstallLocation")
                                icon = self._reg_value(sub, "DisplayIcon")
                                uninstall = self._reg_value(sub, "UninstallString")
                                loc_path = self._resolve_install_path(loc, icon, uninstall)
                                if not loc_path or not loc_path.exists() or not loc_path.is_dir():
                                    continue
                                if self._is_system_path(loc_path):
                                    continue
                                key_path = str(loc_path).lower()
                                if key_path in seen:
                                    continue
                                seen.add(key_path)
                                self.apps.append(AppInfo(
                                    name=name,
                                    publisher=self._reg_value(sub, "Publisher") or "",
                                    install_location=loc_path,
                                    version=self._reg_value(sub, "DisplayVersion") or "",
                                    app_type="Win32",
                                    size_bytes=get_directory_size(loc_path),
                                    executable=icon,
                                ))
                        except Exception:
                            continue
            except Exception as e:
                logger.warning("注册表扫描失败 %s: %s", path, e)

    def _resolve_install_path(self, loc: str, icon: str, uninstall: str) -> Path | None:
        """按优先级确定安装目录：InstallLocation > DisplayIcon 目录 > UninstallString 目录"""
        candidates = []
        if loc:
            candidates.append(loc)
        for source in (icon, uninstall):
            m = re.search(r'"([^"]+)"', source) or re.search(r"(\S+\.exe)", source, re.IGNORECASE)
            if m:
                exe_path = Path(m.group(1).strip())
                candidates.append(str(exe_path.parent))
        for c in candidates:
            try:
                p = Path(c).expandvars().resolve()
                if p.is_dir():
                    return p
            except (OSError, ValueError):
                continue
        return None

    def _scan_common_folders(self):
        candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        ]
        # 系统保留目录，不可迁移
        system_names = {
            "common files", "windows defender", "windows mail",
            "windows media player", "windows nt", "windows photo viewer",
            "windows portable devices", "windows security", "internet explorer",
            "reference assemblies", "microsoft", "microsoft analysis services",
            "microsoft sql server", "microsoft silverlight", "uninstall information",
        }
        seen = {str(a.install_location).lower() for a in self.apps}
        for base in candidates:
            if not base.exists():
                continue
            try:
                for entry in base.iterdir():
                    if not entry.is_dir():
                        continue
                    if entry.name.lower() in system_names:
                        continue
                    key = str(entry).lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    self.apps.append(AppInfo(
                        name=entry.name,
                        publisher="",
                        install_location=entry,
                        version="",
                        app_type="Win32",
                        size_bytes=0,
                    ))
            except Exception as e:
                logger.warning("扫描文件夹失败 %s: %s", base, e)

    @staticmethod
    def _is_system_path(path: Path) -> bool:
        """过滤不可迁移的系统目录"""
        text = str(path).lower()
        if "\\systemapps\\" in text or text.startswith(str(Path(os.environ.get("SystemRoot", r"C:\Windows"))).lower()):
            return True
        for name in ("common files",):
            if text.endswith(f"\\{name}"):
                return True
        return False

    def _reg_value(self, key, value_name: str) -> str:
        try:
            value, _ = winreg.QueryValueEx(key, value_name)
            return str(value) if value else ""
        except FileNotFoundError:
            return ""
