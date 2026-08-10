import os
import re
import json
import subprocess
import winreg
import xml.etree.ElementTree as ET
from pathlib import Path
from dataclasses import dataclass
from typing import List

from winapp_migrator.utils.helpers import setup_logging

logger = setup_logging()

# UWP AppxManifest 命名空间
_APPX_NS = {"x": "http://schemas.microsoft.com/appx/manifest/foundation/windows10"}

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
                    name=self._uwp_display_name(loc_path, item.get("Name", "Unknown")),
                    publisher=item.get("Publisher", ""),
                    install_location=loc_path,
                    version=item.get("Version", ""),
                    app_type="UWP",
                    size_bytes=0,
                    package_name=item.get("PackageFullName", ""),
                ))
        except Exception as e:
            logger.exception("UWP扫描异常: %s", e)

    @staticmethod
    def _uwp_display_name(install_location: Path, fallback: str) -> str:
        """从 AppxManifest.xml 读取显示名（多为中文），ms-resource 引用时回退包名"""
        try:
            manifest = install_location / "AppxManifest.xml"
            if not manifest.is_file():
                return fallback
            root = ET.parse(str(manifest)).getroot()
            display = root.findtext("x:Properties/x:DisplayName", namespaces=_APPX_NS)
            if display and not display.lower().startswith("ms-resource"):
                return display.strip()
        except Exception:
            pass
        return fallback

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
                                    size_bytes=0,  # 大小由 UI 层 SizeWorker 异步统计
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
                # 去掉包裹路径的引号并展开环境变量，再解析为绝对路径
                p = Path(os.path.expandvars(str(c).strip('"'))).resolve()
                if p.is_dir():
                    return p
            except (OSError, ValueError):
                continue
        return None

    def _scan_common_folders(self):
        """扫描所有盘符上的常见安装目录与非系统盘根目录，作为 Win32 app 候选"""
        # 系统保留目录，不可迁移
        system_names = {
            "common files", "common", "windows defender", "windows mail",
            "windows media player", "windows nt", "windows photo viewer",
            "windows portable devices", "windows security", "internet explorer",
            "reference assemblies", "microsoft", "microsoft analysis services",
            "microsoft sql server", "microsoft silverlight", "uninstall information",
        }
        seen = {str(a.install_location).lower() for a in self.apps}
        system_root = str(Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve()).lower()

        for drive in self._get_drives():
            root = Path(f"{drive}\\")
            # 1. 常见安装目录的一级子目录
            for sub in ("Program Files", "Program Files (x86)", "Programs", "Software",
                        "Apps", "App", "Application", "工具", "软件", "应用"):
                self._scan_folder(root / sub, seen, system_names)
            # 2. 非系统盘根目录递归扫描（C 盘根目录含大量系统目录，跳过）
            if str(root.resolve()).lower() == system_root:
                continue
            self._scan_folder(root, seen, system_names, top=True, max_depth=3)

    def _scan_folder(self, base: Path, seen: set, system_names: set, top: bool = False, max_depth: int = 1):
        if not base.exists():
            return
        try:
            for entry in base.iterdir():
                if not entry.is_dir():
                    continue
                low = entry.name.lower()
                if top and (low in system_names or low in {
                    "$recycle.bin", "system volume information", "windows",
                    "users", "programdata", "perflogs", "recovery", "sources",
                    "drivers", "intel", "amd", "nvidia", "dell",
                }):
                    continue
                if not top and low in system_names:
                    continue
                key = str(entry).lower()
                if key in seen:
                    continue
                # 容器目录（无 exe 且未达深度上限）：继续向下寻找真实应用目录
                if max_depth > 1 and not self._dir_has_exe(entry):
                    self._scan_folder(entry, seen, system_names, top=False, max_depth=max_depth - 1)
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
        except (PermissionError, OSError) as e:
            # 拒绝访问等容错：记录并跳过该目录，不影响其余扫描
            logger.warning("扫描目录失败 %s: %s", base, e)

    @staticmethod
    def _dir_has_exe(path: Path) -> bool:
        """判断目录内是否直接包含可执行文件（含 exe 的目录视为应用目录）"""
        try:
            for entry in path.iterdir():
                if entry.is_file() and entry.suffix.lower() == ".exe":
                    return True
        except OSError:
            return False
        return False

    @staticmethod
    def _get_drives():
        """枚举本机所有逻辑盘符（如 C: D:）"""
        import string
        from ctypes import windll
        bitmask = windll.kernel32.GetLogicalDrives()
        drives = []
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drives.append(f"{letter}:")
            bitmask >>= 1
        return drives

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
