import sys
import os

# 确保打包后能找到模块（onedir 与 onefile 兼容）
if getattr(sys, "frozen", False):
    base_dir = os.path.dirname(sys.executable)
    sys.path.insert(0, base_dir)
    internal_dir = os.path.join(base_dir, "_internal")
    if os.path.isdir(internal_dir):
        sys.path.insert(0, internal_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase

from winapp_migrator.ui.main_window import MainWindow
from winapp_migrator.ui.styles import apply_palette


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("WinAppMigrator")
    app.setApplicationDisplayName("WinAppMigrator")

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
