"""强力卸载：删除应用根目录、注册表关联项、快捷方式、数据/存档/聊天记录目录"""
from pathlib import Path
from typing import List, Optional, Callable

from winapp_migrator.utils.helpers import setup_logging, safe_remove
from winapp_migrator.core.app_scanner import AppInfo
from winapp_migrator.core.data_dirs import detect_data_dirs
from winapp_migrator.core.registry import scan_app_entries, remove_app_entries
from winapp_migrator.core.shortcut import scan_shortcuts, remove_shortcuts
from winapp_migrator.core.uwp import UWPManager
from winapp_migrator.core.migration import _terminate_processes, is_360_self_protection

logger = setup_logging()


class UninstallPlan:
    """卸载清单：确认对话框中展示的将删除内容"""

    def __init__(self, app: AppInfo):
        self.app = app
        self.is_uwp = app.app_type == "UWP"
        self.root = app.install_location
        self.package_name = app.package_name or app.name
        self.data_dirs: List[Path] = []
        self.registry_entries: List = []
        self.shortcuts: List[str] = []


class Uninstaller:
    def build_plan(self, app: AppInfo) -> UninstallPlan:
        """构建卸载清单（UWP 只记包名；Win32 检测数据目录、注册表、快捷方式）"""
        plan = UninstallPlan(app)
        if plan.is_uwp:
            return plan
        plan.data_dirs = detect_data_dirs(app)
        hints = [app.publisher, Path(app.executable or "").stem, app.name]
        plan.registry_entries = scan_app_entries(app.install_location, app.name, hints)
        plan.shortcuts = scan_shortcuts(app.install_location)
        return plan

    def uninstall(
        self,
        plan: UninstallPlan,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> dict:
        def notify(percent: int, msg: str):
            logger.info("[%d%%] %s", percent, msg)
            if progress_callback:
                progress_callback(percent, msg)

        if plan.is_uwp:
            notify(30, "正在卸载 UWP 应用...")
            ok, msg = UWPManager.uninstall_package(plan.package_name)
            notify(100, "完成")
            return {
                "success": ok,
                "message": msg,
                "removed_dirs": [],
                "registry_removed": 0,
                "shortcuts_removed": 0,
                "failed": [] if ok else [msg],
            }

        result = {
            "success": True,
            "message": "强力卸载完成",
            "removed_dirs": [],
            "registry_removed": 0,
            "shortcuts_removed": 0,
            "failed": [],
        }

        notify(10, "强制结束占用进程...")
        blocked = _terminate_processes(plan.root)
        result["blocked"] = blocked
        result["blocked_360"] = is_360_self_protection(blocked, plan.root)
        if blocked:
            result["failed"].append("以下进程无法自动结束（可能受保护）: " + ", ".join(blocked))

        notify(20, "删除快捷方式...")
        result["shortcuts_removed"] = remove_shortcuts(plan.root)

        notify(40, "清理注册表关联项...")
        result["registry_removed"] = remove_app_entries(plan.registry_entries)

        notify(60, "删除数据/存档/聊天记录目录...")
        for d in plan.data_dirs:
            if safe_remove(d):
                result["removed_dirs"].append(str(d))
            else:
                result["failed"].append(f"数据目录删除失败: {d}")

        notify(80, "删除安装根目录...")
        if safe_remove(plan.root):
            result["removed_dirs"].append(str(plan.root))
        else:
            result["failed"].append(f"根目录删除失败: {plan.root}")

        notify(100, "完成")
        return result
