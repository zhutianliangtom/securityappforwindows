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
                self.apps.append(AppInfo(
                    name=item.get("Name", "Unknown"),
                    publisher=item.get("Publisher", ""),
                    install_location=Path(loc),
                    version=item.get("Version", ""),
                    app_type="UWP",
                    size_bytes=get_directory_size(Path(loc)),
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
        for hkey, path in keys:
            try:
                with winreg.OpenKey(hkey, path) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        sub_name = winreg.EnumKey(key, i)
                        try:
                            with winreg.OpenKey(key, sub_name) as sub:
                                name = self._reg_value(sub, "DisplayName")
                                loc = self._reg_value(sub, "InstallLocation")
                                publisher = self._reg_value(sub, "Publisher") or ""
                                version = self._reg_value(sub, "DisplayVersion") or ""
                                exe = self._reg_value(sub, "DisplayIcon") or ""
                                if not name or not loc:
                                    continue
                                loc_path = Path(loc)
                                if not loc_path.exists() or not loc_path.is_dir():
                                    continue
                                self.apps.append(AppInfo(
                                    name=name,
                                    publisher=publisher,
                                    install_location=loc_path,
                                    version=version,
                                    app_type="Win32",
                                    size_bytes=get_directory_size(loc_path),
                                    executable=exe,
                                ))
                        except Exception:
                            continue
            except Exception as e:
                logger.warning("注册表扫描失败 %s: %s", path, e)

    def _scan_common_folders(self):
        candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        ]
        seen = {str(a.install_location).lower() for a in self.apps}
        for base in candidates:
            if not base.exists():
                continue
            try:
                for entry in base.iterdir():
                    if not entry.is_dir():
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
                        size_bytes=get_directory_size(entry),
                    ))
            except Exception as e:
                logger.warning("扫描文件夹失败 %s: %s", base, e)

    def _reg_value(self, key, value_name: str) -> str:
        try:
            value, _ = winreg.QueryValueEx(key, value_name)
            return str(value) if value else ""
        except FileNotFoundError:
            return ""
