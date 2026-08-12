import sys
import os
import ctypes

# 确保打包后能找到模块（onedir 与 onefile 兼容）
if getattr(sys, "frozen", False):
    base_dir = os.path.dirname(sys.executable)
    sys.path.insert(0, base_dir)
    internal_dir = os.path.join(base_dir, "_internal")
    if os.path.isdir(internal_dir):
        sys.path.insert(0, internal_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase, QIcon

from winapp_migrator.ui.main_window import MainWindow, _app_icon_path
from winapp_migrator.ui.styles import apply_palette
from winapp_migrator.utils.helpers import install_excepthook


def main():
    install_excepthook()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("WinAppMigrator")
    app.setApplicationDisplayName("WinAppMigrator")

    # Windows 任务栏独立图标：不设 AppUserModelID 时任务栏会把应用并入 python.exe 并显示默认图标
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WinAppMigrator.App")
        except Exception:
            pass
    # 应用级图标：主窗口与所有对话框（QMessageBox 等）左上角图标均继承自此
    app.setWindowIcon(QIcon(_app_icon_path()))

    default_families = ["Microsoft YaHei UI", "Segoe UI", "PingFang SC"]
    available_families = QFontDatabase.families()
    family = next((f for f in default_families if f in available_families), "Arial")
    app.setFont(QFont(family, 10))

    apply_palette(app)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
