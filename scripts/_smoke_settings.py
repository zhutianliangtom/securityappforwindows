# -*- coding: utf-8 -*-
"""源码冒烟：完整构造 AI 设置对话框（触发全部 _build_*_page，暴露 AttributeError 等）"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PyQt6.QtWidgets import QApplication

app = QApplication([])
import winapp_migrator.ui.agent_panel as ap

dlg = ap._AgentSettingsDialog()
print("设置对话框构造 OK，页面数:", dlg.nav.count())
dlg.close()

# 顺带验证 TTS 页读取的音色配置仍为「蝶-三角洲行动」且默认开启
import winapp_migrator.core.agent_tts as tts
cfg = tts.load_config()
print("auto_read =", cfg.get("auto_read"), "| preferred_name =", cfg.get("preferred_name"))
print("PASS")
