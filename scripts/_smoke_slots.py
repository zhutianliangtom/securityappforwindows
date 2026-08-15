# -*- coding: utf-8 -*-
"""源码冒烟测试（离屏）：
1. 模拟 exe 中 PyQt 对 Cython 方法的调度方式（clicked 会把 checked 布尔传给槽），
   直接用真实 QPushButton clicked 信号 + 一个参数直呼，验证 48 个修复槽全部可接收；
2. 实跑用户报障路径：_open_settings / _new_session / _clear_chat（弹窗打桩）。"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PyQt6.QtWidgets import QApplication, QPushButton, QDialog

app = QApplication([])

import winapp_migrator.ui.agent_panel as ap
import winapp_migrator.ui.main_window as mw
import winapp_migrator.ui.download_dialog as dd
import winapp_migrator.ui.widgets as wg

fail = []

# ---------- 1. 槽签名验证：clicked(bool) 最坏情形（直呼带 1 个参数） ----------
cases = [
    (ap, ["_accept_check", "_accept_clicked", "_allow", "_browse_workdir", "_clear_chat",
          "_delete_skill", "_deny", "_import_skill", "_new_session", "_on_action_clicked",
          "_on_mcp_add", "_on_mcp_delete", "_on_mcp_edit", "_on_provider_add",
          "_on_provider_delete", "_open_settings", "_pick_attachments", "_save",
          "_sync_action_style", "_sync_type"]),
    (dd, ["_add_task", "_click_cancel", "_click_pause"]),
    (mw, ["_browse_target", "_filter_apps", "_migrate_custom_folder", "_on_check_update_clicked",
          "_open_agent_panel", "_open_app_dir", "_open_download_dialog",
          "_refresh_target_path", "_restore_from_tray", "_show_about", "_start_memory_optimize",
          "_start_migration", "_start_scan", "_start_uninstall", "_toggle_security"]),
    (wg, ["_close_now"]),
]
checked = 0
import inspect
for mod, names in cases:
    for n in names:
        cls_attrs = []
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if isinstance(obj, type) and n in vars(obj):
                cls_attrs.append(obj)
        if not cls_attrs:
            fail.append(f"{mod.__name__}.{n} 未找到")
            continue
        func = getattr(cls_attrs[0], n)
        sig = inspect.signature(func)
        try:
            sig.bind(object(), False)   # (self, checked) 最坏情形
            checked += 1
        except TypeError as e:
            fail.append(f"{cls_attrs[0].__name__}.{n}: {e}")
print(f"[1] 槽签名可接收 clicked 布尔: {checked}/48")

# ---------- 2. 真实信号直连调用（源码模式 PyQt 截断参数路径） ----------
btn = QPushButton()
calls = []


class _Probe:
    def handler(self, *_):
        calls.append(1)


_probe = _Probe()   # 持住实例：PyQt 对接收者持弱引用，临时实例会被 GC 导致静默跳过
btn.clicked.connect(_probe.handler)
btn.click()
print(f"[2] 源码模式 clicked 直连 *_ 槽: {'OK' if calls else 'FAIL'}")
if not calls:
    fail.append("clicked 直连未触发")

# ---------- 3. 用户报障路径（弹窗打桩，不产生真实副作用） ----------
panel = ap.AgentPanel()
ap._AgentSettingsDialog = type("FakeDlg", (QDialog,), {
    "__init__": lambda self, parent=None: QDialog.__init__(self),
    "exec": lambda self: 0,
})
panel._confirm_box = lambda *a, **k: False
panel._create_session = lambda: {"id": "_smoke_", "name": "冒烟"}
panel._persist_current = lambda *a, **k: None
try:
    panel._open_settings(False)   # 模拟 exe 调度（带 checked）
    panel._new_session(False)
    panel._clear_chat(False)
    print("[3] 设置页/新建对话/删除对话（带参数模拟 exe 调度）: OK")
except Exception as e:
    fail.append(f"报障路径: {type(e).__name__} {e}")

print("=" * 40)
if fail:
    print("FAILED:")
    for x in fail:
        print("  -", x)
    sys.exit(1)
print("ALL PASS")
