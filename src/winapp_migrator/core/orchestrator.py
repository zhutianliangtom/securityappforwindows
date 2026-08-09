from pathlib import Path
from typing import Callable, Optional

from winapp_migrator.utils.helpers import setup_logging
from winapp_migrator.core.app_scanner import AppInfo
from winapp_migrator.core.migration import migrate_folder
from winapp_migrator.core.registry import RegistryPathUpdater
from winapp_migrator.core.uwp import UWPManager

logger = setup_logging()

class MigrationOrchestrator:
    def __init__(self):
        self.registry_updater = RegistryPathUpdater()

    def migrate(
        self,
        app: AppInfo,
        target_drive: Path,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        update_registry: bool = True,
    ) -> dict:
        source = app.install_location
        target = target_drive / "WinAppMigrator" / app.app_type / source.name
        target.parent.mkdir(parents=True, exist_ok=True)

        logger.info("开始迁移 %s (%s): %s -> %s", app.name, app.app_type, source, target)

        if app.app_type == "UWP":
            success, message = UWPManager.migrate_package(
                app.package_name or app.name,
                target_drive,
                progress_callback,
            )
            return {
                "success": success,
                "message": message,
                "source": str(source),
                "target": str(target),
                "registry_changed": 0,
            }

        result = migrate_folder(source, target, progress_callback, use_junction=True)
        registry_changed = 0
        registry_errors = 0

        if result.success and update_registry:
            self._notify(progress_callback, 95, "更新注册表路径引用...")
            registry_changed, registry_errors = self.registry_updater.update_paths(source, target)

        self._notify(progress_callback, 100, "完成")
        return {
            "success": result.success,
            "message": result.message,
            "details": result.details,
            "source": str(source),
            "target": str(target),
            "registry_changed": registry_changed,
            "registry_errors": registry_errors,
        }

    def _notify(self, callback, percent: int, message: str):
        logger.info("[%d%%] %s", percent, message)
        if callback:
            callback(percent, message)
