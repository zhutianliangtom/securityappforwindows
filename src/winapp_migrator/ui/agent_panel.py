"""AI Agent 工具面板

- 流式输出：Agent 思考与操作步骤逐字实时显示
- 每步确认：工具执行前弹窗展示"当前屏幕截图 + 操作 + 风险"，由用户允许/拒绝
- tokens：发送前预计算、响应后累计实际消耗
- MCP：启动时后台连接 mcp_servers.json 中的服务器并聚合工具
- skills/agents：从 ~/.winapp_migrator/agent/*.json 加载
"""

import json
import os
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QSettings, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog, QLabel, QLineEdit, QPushButton, QTextBrowser, QComboBox,
    QVBoxLayout, QHBoxLayout, QMessageBox, QFormLayout,
)

from winapp_migrator.core import agent_llm, agent_engine, agent_skills, agent_sandbox
from winapp_migrator.core.agent_mcp import McpManager
from winapp_migrator.core.agent_screen import capture_screen_data_url
from winapp_migrator.ui.styles import PALETTE


def _app_icon_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", "."), "assets", "icon.ico")
    return str(Path(__file__).resolve().parents[3] / "assets" / "icon.ico")


class _ConfirmDialog(QDialog):
    """工具执行确认：显示当前屏幕截图 + 操作 + 风险等级"""

    def __init__(self, name: str, args: dict, risk: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🤖 AI 请求执行操作")
        self.setMinimumSize(520, 640)
        self.result_ok = False

        lay = QVBoxLayout(self)

        risk_color = {"safe": "#16A34A", "risky": "#D97706", "dangerous": "#DC2626"}
        risk_txt = {"safe": "安全（白名单）", "risky": "需谨慎", "dangerous": "危险（将被沙盒拒绝）"}
        head = QLabel(f"AI 想执行：<b>{name}</b>　风险：<span style='color:{risk_color.get(risk, '#333')}'>"
                      f"{risk_txt.get(risk, risk)}</span>")
        head.setStyleSheet(f"font-size: 14px; color: {PALETTE['text']};")
        lay.addWidget(head)

        arg_txt = QLabel(json.dumps(args, ensure_ascii=False, indent=2))
        arg_txt.setWordWrap(True)
        arg_txt.setStyleSheet(
            "background: #F1F5F9; color: #475569;"
            "padding: 8px; border-radius: 6px; font-size: 12px;")
        lay.addWidget(arg_txt, 1)

        pic_label = QLabel("正在截取当前屏幕…")
        pic_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pic_label.setStyleSheet("background: #F1F5F9; color: gray;")
        lay.addWidget(pic_label, 2)
        try:
            from PyQt6.QtGui import QPixmap
            import base64
            raw = base64.b64decode(capture_screen_data_url().split(",", 1)[1])
            pix = QPixmap()
            pix.loadFromData(raw)
            pix = pix.scaledToWidth(500, Qt.TransformationMode.SmoothTransformation)
            pic_label.setPixmap(pix)
            pic_label.setText("")
        except Exception:
            pic_label.setText("截图不可用")

        btns = QHBoxLayout()
        deny = QPushButton("❌ 拒绝")
        deny.setStyleSheet("background: #DC2626; color: white; font-weight: 700;"
                           "border: none; border-radius: 8px; padding: 8px 20px;")
        deny.clicked.connect(self._deny)
        allow = QPushButton("✅ 允许执行")
        allow.setStyleSheet("background: #16A34A; color: white; font-weight: 700;"
                            "border: none; border-radius: 8px; padding: 8px 20px;")
        allow.clicked.connect(self._allow)
        btns.addWidget(deny)
        btns.addWidget(allow)
        lay.addLayout(btns)

    def _allow(self):
        self.result_ok = True
        self.accept()

    def _deny(self):
        self.result_ok = False
        self.accept()


class AgentPanel(QDialog):
    delta_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    confirm_signal = pyqtSignal(str, str, str)  # name, args_json, risk
    mcp_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🤖 AI Agent 工具面板")
        self.setWindowIcon(QIcon(_app_icon_path()))
        self.setMinimumSize(720, 560)
        self.resize(860, 620)

        self._settings = QSettings("WinAppMigrator", "WinAppMigrator")
        self._engine: agent_engine.AgentEngine = None
        self._confirm_evt = threading.Event()
        self._confirm_result = False
        self._mcp = McpManager()
        self._agents = agent_skills.load_agents()

        self._build_ui()
        self._connect_signals()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_meta)
        self._timer.start(400)

        threading.Thread(target=self._init_mcp, daemon=True).start()

    # ---------- UI ----------
    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)

        top = QHBoxLayout()
        top.addWidget(QLabel("Agent"))
        self.agent_combo = QComboBox()
        for a in self._agents:
            self.agent_combo.addItem(a.get("name", "?"), a.get("name", ""))
        if self.agent_combo.count() == 0:
            self.agent_combo.addItem("桌面助手", "桌面助手")
        top.addWidget(self.agent_combo)

        self.mcp_label = QLabel("MCP: 连接中…")
        self.mcp_label.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px;")
        top.addWidget(self.mcp_label)

        self.token_label = QLabel("tokens: 0")
        self.token_label.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px;")
        top.addWidget(self.token_label)

        set_btn = QPushButton("设置")
        set_btn.clicked.connect(self._open_settings)
        top.addWidget(set_btn)
        top.addStretch(1)
        lay.addLayout(top)

        self.output = QTextBrowser()
        self.output.setOpenExternalLinks(True)
        self.output.setStyleSheet(
            f"background: {PALETTE['bg_secondary']}; color: {PALETTE['text']};"
            "border: 1px solid #E5E7EB; border-radius: 8px; padding: 8px; font-size: 13px;")
        lay.addWidget(self.output, 1)

        bottom = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("描述任务，例如：打开记事本，输入一段文字，再截图给我看")
        self.input.setMinimumHeight(38)
        self.input.returnPressed.connect(self._send)
        bottom.addWidget(self.input, 1)
        self.send_btn = QPushButton("发送")
        self.send_btn.setMinimumHeight(38)
        self.send_btn.setStyleSheet(
            f"background-color: {PALETTE['primary']}; color: white; font-weight: 700;"
            "border: none; border-radius: 8px; padding: 0 18px;")
        self.send_btn.clicked.connect(self._send)
        bottom.addWidget(self.send_btn)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setMinimumHeight(38)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(
            "background: #DC2626; color: white; font-weight: 700;"
            "border: none; border-radius: 8px; padding: 0 18px;")
        self.stop_btn.clicked.connect(self._stop)
        bottom.addWidget(self.stop_btn)
        lay.addLayout(bottom)

        tip = QLabel("提示：每步屏幕操作前都会弹窗由您确认；危险命令（删除/格式化/关机等）会被沙盒拒绝。"
                     "skills/agents/MCP 配置见 ~/.winapp_migrator/agent/")
        tip.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 11px;")
        lay.addWidget(tip)

    def _connect_signals(self):
        self.delta_signal.connect(self._on_delta)
        self.status_signal.connect(self._on_status)
        self.confirm_signal.connect(self._on_confirm)
        self.mcp_signal.connect(self._on_mcp_status)

    # ---------- MCP 初始化 ----------
    def _init_mcp(self):
        servers = agent_skills.load_mcp_servers()
        if not servers:
            self.mcp_signal.emit("MCP: 未配置服务器")
            return
        try:
            tools = self._mcp.connect_all(servers)
            n = len(tools)
            errs = "；".join(self._mcp.errors)
            msg = f"MCP: 已连接 {n} 个工具" + (f"（失败: {errs}）" if errs else "")
        except Exception as e:
            msg = f"MCP: 初始化失败 {e}"
        self.mcp_signal.emit(msg)

    def _on_mcp_status(self, text: str):
        self.mcp_label.setText(text)

    # ---------- 发送 / 停止 ----------
    def _llm_config(self) -> dict:
        return {
            "base_url": str(self._settings.value("agent_base_url", agent_llm.DEFAULT_BASE_URL)),
            "api_key": str(self._settings.value("agent_api_key", "")),
            "model": str(self._settings.value("agent_model", agent_llm.DEFAULT_MODEL)),
        }

    def _send(self):
        text = self.input.text().strip()
        if not text or (self._engine and self._engine._thread and self._engine._thread.is_alive()):
            return
        cfg = self._llm_config()
        if not cfg["api_key"]:
            QMessageBox.information(self, "提示", "请先点击「设置」填写 API Key")
            return
        llm = agent_llm.LLMClient(**cfg)
        self._engine = agent_engine.AgentEngine(
            llm, mcp_manager=self._mcp,
            on_delta=lambda s: self.delta_signal.emit(s),
            on_status=lambda s: self.status_signal.emit(s),
            confirm=self._confirm_tool)
        agent_name = self.agent_combo.currentData() or "桌面助手"
        self.output.append(f"<p style='color:{PALETTE['primary']}'><b>🧑 你：</b>{text}</p>")
        self.output.append(f"<p style='color:{PALETTE['text_secondary']}'><b>🤖 Agent：</b>"
                           f"<span id='ai'>…</span></p>")
        est = agent_llm.estimate_tokens(text)
        self.token_label.setText(f"本次预计 {est} tokens · 累计 0")
        self.input.clear()
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._engine.start(text, agent_name)

    def _stop(self):
        if self._engine:
            self._engine.stop()
        self.stop_btn.setEnabled(False)

    def _refresh_meta(self):
        """轮询刷新 tokens / 发送按钮状态"""
        if self._engine:
            t = self._engine.tokens
            self.token_label.setText(
                f"已用 {t['prompt'] + t['completion']} tokens "
                f"(输入 {t['prompt']} / 输出 {t['completion']})")
        if not (self._engine and self._engine._thread and self._engine._thread.is_alive()):
            if not self.send_btn.isEnabled():
                self.send_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)

    # ---------- 引擎回调（信号槽，主线程） ----------
    def _on_delta(self, s: str):
        self.output.moveCursor(self.output.textCursor().MoveOperation.End)
        self.output.insertPlainText(s)

    def _on_status(self, s: str):
        if s.startswith("错误"):
            self.output.append(f"<p style='color:{PALETTE['danger']}'>❌ {s}</p>")
        elif s.startswith("正在执行") or s.startswith("待执行"):
            self.output.append(f"<p style='color:#D97706'>⚙️ {s}</p>")
        elif s == "完成":
            self.output.append("<p style='color:#16A34A'>✅ 完成</p>")
        elif s == "已停止":
            self.output.append("<p style='color:#6B7280'>⏹ 已停止</p>")
        elif s == "正在思考…":
            self.output.append("<p style='color:#6B7280'>💭 正在思考…</p>")

    # ---------- 每步确认（engine 线程调用 → 信号 → 主线程弹窗） ----------
    def _confirm_tool(self, name: str, args: dict) -> bool:
        level, reason = agent_sandbox.assess_tool(name, args)
        self._confirm_evt.clear()
        self.confirm_signal.emit(name, json.dumps(args, ensure_ascii=False), level)
        self._confirm_evt.wait(timeout=600)
        return self._confirm_result

    def _on_confirm(self, name: str, args_json: str, risk: str):
        try:
            args = json.loads(args_json)
        except json.JSONDecodeError:
            args = {}
        dlg = _ConfirmDialog(name, args, risk, self)
        dlg.exec()
        self._confirm_result = dlg.result_ok
        self._confirm_evt.set()

    # ---------- 设置 ----------
    def _open_settings(self):
        cfg = self._llm_config()
        dlg = QDialog(self)
        dlg.setWindowTitle("Agent 模型设置")
        form = QFormLayout(dlg)
        base = QLineEdit(cfg["base_url"])
        key = QLineEdit(cfg["api_key"])
        key.setEchoMode(QLineEdit.EchoMode.Password)
        model = QLineEdit(cfg["model"])
        form.addRow("Base URL", base)
        form.addRow("API Key", key)
        form.addRow("模型", model)
        btns = QHBoxLayout()
        ok = QPushButton("保存")
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(dlg.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._settings.setValue("agent_base_url", base.text().strip())
            self._settings.setValue("agent_api_key", key.text().strip())
            self._settings.setValue("agent_model", model.text().strip())
            QMessageBox.information(self, "已保存", "模型设置已保存。")

    def closeEvent(self, event):
        if self._engine:
            self._engine.stop()
            self._engine.join(3)
        try:
            self._mcp.close_all()
        except Exception:
            pass
        event.accept()
