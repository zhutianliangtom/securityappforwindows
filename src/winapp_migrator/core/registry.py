import re
import winreg
from pathlib import Path
from typing import List, Tuple

from winapp_migrator.utils.helpers import setup_logging

logger = setup_logging()

class RegistryPathUpdater:
    def __init__(self):
        self.changed: List[Tuple[str, str, str, str]] = []
        self.scanned: List[Tuple[str, str, str]] = []

    def update_paths(self, old_path: Path, new_path: Path) -> Tuple[int, int]:
        self.changed = []
        self.scanned = []
        changed_count = 0
        error_count = 0

        roots = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE"),
        ]

        old_str = str(old_path)
        new_str = str(new_path)

        for root, subpath in roots:
            try:
                with winreg.OpenKey(root, subpath, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                    self._scan_key(key, subpath, old_str, new_str, root)
            except Exception as e:
                logger.warning("无法打开注册表键 %s: %s", subpath, e)
                error_count += 1

        for hkey, subpath, value_name, value_data in self.scanned:
            try:
                self._write_value(hkey, subpath, value_name, value_data.replace(old_str, new_str))
                self.changed.append((self._root_name(hkey), subpath, value_name, value_data))
                changed_count += 1
            except Exception as e:
                logger.warning("写入注册表失败 %s\\%s: %s", subpath, value_name, e)
                error_count += 1

        return changed_count, error_count

    def _scan_key(self, key, path: str, old_str: str, new_str: str, root):
        try:
            for i in range(winreg.QueryInfoKey(key)[1]):
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    text = self._value_to_string(value)
                    if old_str.lower() in text.lower():
                        self.scanned.append((root, path, name, text))
                except Exception:
                    continue
        except Exception as e:
            logger.debug("扫描键值失败 %s: %s", path, e)

        try:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub_name = winreg.EnumKey(key, i)
                    sub_path = f"{path}\\{sub_name}"
                    with winreg.OpenKey(key, sub_name, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as sub:
                        self._scan_key(sub, sub_path, old_str, new_str, root)
                except Exception:
                    continue
        except Exception as e:
            logger.debug("枚举子键失败 %s: %s", path, e)

    def _value_to_string(self, value) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, bytes):
            try:
                return value.decode("utf-16-le").rstrip("\x00")
            except Exception:
                return ""
        if isinstance(value, list):
            return ";".join(str(x) for x in value)
        return str(value)

    def _write_value(self, hkey, subpath: str, value_name: str, new_data: str):
        access = winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY
        with winreg.OpenKey(hkey, subpath, 0, access) as key:
            try:
                _, typ = winreg.QueryValueEx(key, value_name)
            except FileNotFoundError:
                typ = winreg.REG_SZ
            if typ == winreg.REG_SZ or typ == winreg.REG_EXPAND_SZ:
                winreg.SetValueEx(key, value_name, 0, typ, new_data)
            elif typ == winreg.REG_MULTI_SZ:
                winreg.SetValueEx(key, value_name, 0, typ, new_data.split(";"))

    def _root_name(self, hkey) -> str:
        if hkey == winreg.HKEY_LOCAL_MACHINE:
            return "HKLM"
        if hkey == winreg.HKEY_CURRENT_USER:
            return "HKCU"
        return "HK?"
