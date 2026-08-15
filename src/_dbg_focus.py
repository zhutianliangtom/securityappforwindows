import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_focus.log")

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import QTimer

app = QApplication([])

from winapp_migrator.ui.agent_panel import AgentPanel, _AgentSettingsDialog


def log(name, v):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{name}: {v}\n")


def dump(tag):
    p = AgentPanel._last
    tw = p.todos_win
    log(tag, f"todos visible={tw.isVisible()} isActive={tw.isActiveWindow()} "
             f"panel_active={p.isActiveWindow()}")


mw = QMainWindow()
mw.show()
app.processEvents()
p = AgentPanel(mw)
AgentPanel._last = p
p.show()
app.processEvents()
p.showMaximized()
app.processEvents()
dump("INIT")

# 1. 点击 todos → 再点击主窗口
QTimer.singleShot(300, lambda: (p.todos_win.activateWindow(), None))
QTimer.singleShot(600, lambda: dump("AFTER_CLICK_TODOS"))
QTimer.singleShot(900, lambda: (p.activateWindow(), None))
QTimer.singleShot(1200, lambda: dump("AFTER_CLICK_MAIN"))
# 2. 再点 todos，然后打开设置对话框
QTimer.singleShot(1500, lambda: (p.todos_win.activateWindow(), None))
QTimer.singleShot(1800, lambda: dump("AFTER_CLICK_TODOS2"))
QTimer.singleShot(2100, lambda: open_settings())
QTimer.singleShot(2400, lambda: dump("AFTER_OPEN_SETTINGS"))
QTimer.singleShot(2700, app.quit)

_settings_dlg = None
def open_settings():
    global _settings_dlg
    _settings_dlg = _AgentSettingsDialog(parent=p)
    _settings_dlg.show()

sys.exit(app.exec())
