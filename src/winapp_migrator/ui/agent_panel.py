"""AI Agent 工具面板（深色"星际控制台"风格）

- 聊天气泡：用户消息靠右（青色渐变）、AI 消息靠左（深色卡片），流式逐字输出
- 上下文：engine 复用保留跨任务对话历史（截图仅保留最近 2 张防膨胀），可一键清空
- 反馈：发送中/停止中按钮状态 + "思考中"逐点动画 + tokens 实时统计
- 每步确认：工具执行前弹窗展示"当前屏幕截图 + 操作 + 风险"，用户允许/拒绝
- MCP / skills / agents：从 ~/.winapp_migrator/agent/*.json 加载
"""

import json
import os
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QSettings, pyqtSignal
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtWidgets import (
    QDialog, QLabel, QLineEdit, QPushButton, QComboBox, QScrollArea,
    QVBoxLayout, QHBoxLayout, QMessageBox, QFormLayout, QWidget,
)

from winapp_migrator.core import agent_llm, agent_engine, agent_skills, agent_sandbox
from winapp_migrator.core.agent_mcp import McpManager
from winapp_migrator.core.agent_screen import capture_screen_data_url

# ---------- 深色"星际控制台"主题 ----------
BG = "#0B1220"            # 窗口底色（深蓝黑）
PANEL = "#111A2E"         # 面板底色
BORDER = "#1E2A44"        # 边框
TEXT = "#E6EDF7"          # 主文本
TEXT_DIM = "#8A9BB8"      # 次要文本
ACCENT = "#22D3EE"        # 强调（青）
USER_BG = ("qlineargradient(x1:0, y1:0, x2:1, y2:1, "
           "stop:0 #2563EB, stop:1 #0EA5E9)")   # 用户气泡渐变
AI_BG = "#1A2540"         # AI 气泡底色
OK = "#34D399"
WARN = "#FBBF24"
ERR = "#F87171"


def _app_icon_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", "."), "assets", "icon.ico")
    return str(Path(__file__).resolve().parents[3] / "assets" / "icon.ico")


class _ConfirmDialog(QDialog):
    """工具执行确认：显示当前屏幕截图 + 操作 + 风险等级"""

    def __init__(self, name: str, args: dict, risk: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🤖 AI 请求执行操作")
        self.setMinimumSize(520, 620)
        self.result_ok = False

        self.setStyleSheet(
            f"QDialog {{ background: {PANEL}; }}"
            f"QLabel {{ color: {TEXT}; font-size: 13px; }}"
            f"QPushButton {{ border: none; border-radius: 10px; "
            f"padding: 9px 22px; font-weight: 700; font-size: 13px; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        risk_color = {"safe": OK, "risky": WARN, "dangerous": ERR}
        risk_txt = {"safe": "安全（白名单）", "risky": "需谨慎", "dangerous": "危险（将被沙盒拒绝）"}
        head = QLabel(f"AI 想执行：<b>{name}</b>　风险：<span style='color:{risk_color.get(risk, TEXT)}'>"
                      f"{risk_txt.get(risk, risk)}</span>")
        head.setStyleSheet("font-size: 14px;")
        lay.addWidget(head)

        arg_txt = QLabel(json.dumps(args, ensure_ascii=False, indent=2))
        arg_txt.setWordWrap(True)
        arg_txt.setStyleSheet(
            f"background: {BG}; color: {TEXT_DIM}; border: 1px solid {BORDER};"
            "border-radius: 8px; padding: 10px; font-size: 12px; font-family: Consolas;")
        lay.addWidget(arg_txt, 1)

        pic_label = QLabel("正在截取当前屏幕…")
        pic_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pic_label.setStyleSheet(f"background: {BG}; color: {TEXT_DIM};"
                                f"border: 1px solid {BORDER}; border-radius: 8px;")
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
        deny.setStyleSheet(f"background: {ERR}; color: white;")
        deny.clicked.connect(self._deny)
        allow = QPushButton("✅ 允许执行")
        allow.setStyleSheet(f"background: {OK}; color: #06281B;")
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
        self.setMinimumSize(760, 600)
        self.resize(900, 660)
        self.setFont(QFont("Microsoft YaHei UI", 10))
        self.setStyleSheet(
            f"QDialog {{ background: {BG}; }}"
            f"QComboBox {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};"
            f"border-radius: 8px; padding: 5px 10px; font-size: 12px; }}"
            f"QComboBox::drop-down {{ border: none; width: 22px; }}"
            f"QComboBox QAbstractItemView {{ background: {PANEL}; color: {TEXT};"
            f"border: 1px solid {BORDER}; selection-background-color: {ACCENT};"
            f"selection-color: #06281B; }}")

        self._settings = QSettings("WinAppMigrator", "WinAppMigrator")
        self._engine: agent_engine.AgentEngine = None
        self._confirm_evt = threading.Event()
        self._confirm_result = False
        self._mcp = McpManager()
        self._agents = agent_skills.load_agents()

        self._ai_bubble = None       # 当前流式输出的 AI 气泡
        self._think_lbl = None       # "思考中"动画行
        self._think_idx = 0

        self._build_ui()
        self._connect_signals()

        self._think_timer = QTimer(self)
        self._think_timer.timeout.connect(self._tick_think)
        self._think_frames = ["💭 思考中 ●○○", "💭 思考中 ○●○", "💭 思考中 ○○●"]

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_meta)
        self._timer.start(400)

        threading.Thread(target=self._init_mcp, daemon=True).start()

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # 顶栏：标题 + Agent 选择 + MCP 状态 + tokens + 清空 + 设置
        top = QHBoxLayout()
        top.setSpacing(10)
        title = QLabel("⚡ AI AGENT")
        title.setStyleSheet(f"color: {ACCENT}; font-size: 16px; font-weight: 800;"
                            "letter-spacing: 1px;")
        top.addWidget(title)

        self.agent_combo = QComboBox()
        for a in self._agents:
            self.agent_combo.addItem(a.get("name", "?"), a.get("name", ""))
        if self.agent_combo.count() == 0:
            self.agent_combo.addItem("桌面助手", "桌面助手")
        self.agent_combo.setMinimumWidth(130)
        top.addWidget(self.agent_combo)

        # 执行模式：AskBeforeEdit（默认，每步确认） / YOLO（无确认直行）
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("🔒 AskBeforeEdit（每步确认）", "ask")
        self.mode_combo.addItem("🔥 YOLO（无确认直行）", "yolo")
        self.mode_combo.setMinimumWidth(210)
        saved_mode = str(self._settings.value("agent_mode", "ask"))
        idx = self.mode_combo.findData(saved_mode)
        self.mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._mode = self.mode_combo.currentData()
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._apply_mode_style()
        top.addWidget(self.mode_combo)

        self.mcp_label = QLabel("MCP: 连接中…")
        self.mcp_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        top.addWidget(self.mcp_label)

        top.addStretch(1)

        self.token_label = QLabel("tokens: 0")
        self.token_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        top.addWidget(self.token_label)

        clear_btn = QPushButton("🧹 清空")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};"
            "border-radius: 8px; padding: 6px 14px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}")
        clear_btn.clicked.connect(self._clear_chat)
        top.addWidget(clear_btn)

        set_btn = QPushButton("⚙ 设置")
        set_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        set_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};"
            "border-radius: 8px; padding: 6px 14px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}")
        set_btn.clicked.connect(self._open_settings)
        top.addWidget(set_btn)
        root.addLayout(top)

        # 聊天区（气泡）
        self.msg_area = QScrollArea()
        self.msg_area.setWidgetResizable(True)
        self.msg_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self.msg_lay = QVBoxLayout(container)
        self.msg_lay.setContentsMargins(6, 6, 6, 6)
        self.msg_lay.setSpacing(10)
        self.msg_lay.addStretch(1)   # 末尾弹性空间，消息自顶向下堆叠
        self.msg_area.setWidget(container)
        root.addWidget(self.msg_area, 1)

        # 输入栏
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.input = QLineEdit()
        self.input.setPlaceholderText("描述任务，例如：打开记事本，输入一段文字，再截图给我看")
        self.input.setMinimumHeight(42)
        self.input.setStyleSheet(
            f"QLineEdit {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};"
            "border-radius: 10px; padding: 0 14px; font-size: 13px; }}"
            f"QLineEdit:focus {{ border: 1px solid #4B6BD6; }}")
        self.input.returnPressed.connect(self._send)
        bottom.addWidget(self.input, 1)

        self.send_btn = QPushButton("🚀 发送")
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setMinimumHeight(42)
        self.send_btn.setMinimumWidth(96)
        self.send_btn.setStyleSheet(
            f"QPushButton {{ background: {USER_BG}; color: white; border: none;"
            "border-radius: 10px; padding: 0 18px; font-size: 13px; font-weight: 700; }}"
            f"QPushButton:hover {{ border: 1px solid {ACCENT}; }}"
            f"QPushButton:disabled {{ background: #1A2540; color: {TEXT_DIM}; }}")
        self.send_btn.clicked.connect(self._send)
        bottom.addWidget(self.send_btn)

        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setMinimumHeight(42)
        self.stop_btn.setMinimumWidth(88)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(
            f"QPushButton {{ background: {ERR}; color: white; border: none;"
            "border-radius: 10px; padding: 0 16px; font-size: 13px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: #EF4444; }}"
            f"QPushButton:disabled {{ background: #1A2540; color: {TEXT_DIM}; }}")
        self.stop_btn.clicked.connect(self._stop)
        bottom.addWidget(self.stop_btn)
        root.addLayout(bottom)

        tip = QLabel("提示：每步屏幕操作前都会弹窗由您确认；危险命令（删除/格式化/关机等）会被沙盒拒绝。"
                     "skills/agents/MCP 配置见 ~/.winapp_migrator/agent/")
        tip.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        root.addWidget(tip)

    def _connect_signals(self):
        self.delta_signal.connect(self._on_delta)
        self.status_signal.connect(self._on_status)
        self.confirm_signal.connect(self._on_confirm)
        self.mcp_signal.connect(self._on_mcp_status)

    # ---------- 执行模式 ----------
    def _apply_mode_style(self):
        yolo = self._mode == "yolo"
        border = ERR if yolo else ACCENT
        self.mode_combo.setStyleSheet(
            f"QComboBox {{ background: {PANEL}; color: {border}; border: 1px solid {border};"
            "border-radius: 8px; padding: 5px 10px; font-size: 12px; font-weight: 700; }}"
            f"QComboBox::drop-down {{ border: none; width: 22px; }}")

    def _on_mode_changed(self, idx):
        self._mode = self.mode_combo.currentData()
        self._settings.setValue("agent_mode", self._mode)   # 记住设置，下次启动恢复
        self._apply_mode_style()
        if self._mode == "yolo":
            self._add_status("🔥 YOLO 模式：AI 操作不再弹窗确认（危险命令仍被沙盒硬拒绝）", WARN)
        else:
            self._add_status("🔒 AskBeforeEdit 模式：每步操作弹窗确认", OK)

    # ---------- 消息气泡 ----------
    def _add_bubble(self, text: str, align: str) -> QLabel:
        bubble = QLabel(text)
        bubble.setTextFormat(Qt.TextFormat.PlainText)   # 纯文本，防止 LLM 输出被当 HTML
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble.setMaximumWidth(560)
        if align == "user":
            bubble.setStyleSheet(f"background: {USER_BG}; color: white;"
                                 "border-radius: 14px; padding: 10px 14px; font-size: 13px;")
        else:
            bubble.setStyleSheet(f"background: {AI_BG}; color: {TEXT};"
                                 f"border: 1px solid {BORDER}; border-radius: 14px;"
                                 "padding: 10px 14px; font-size: 13px;")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if align == "user":
            row.addStretch(1)
            row.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)
        else:
            row.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)
            row.addStretch(1)
        self.msg_lay.insertLayout(self.msg_lay.count() - 1, row)
        self._scroll_bottom()
        return bubble

    def _add_status(self, text_html: str, color: str):
        lbl = QLabel(text_html)
        lbl.setStyleSheet(f"color: {color}; font-size: 12px; padding: 2px 4px;")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(lbl)
        row.addStretch(1)
        self.msg_lay.insertLayout(self.msg_lay.count() - 1, row)
        self._scroll_bottom()

    def _scroll_bottom(self):
        bar = self.msg_area.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ---------- "思考中"动画 ----------
    def _start_think(self):
        if self._think_lbl is None:
            self._think_lbl = QLabel()
            self._think_lbl.setStyleSheet(f"color: {ACCENT}; font-size: 12px; padding: 2px 4px;")
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(self._think_lbl)
            row.addStretch(1)
            self.msg_lay.insertLayout(self.msg_lay.count() - 1, row)
        self._think_idx = 0
        self._think_lbl.setText(self._think_frames[0])
        self._think_timer.start(350)

    def _tick_think(self):
        self._think_idx = (self._think_idx + 1) % len(self._think_frames)
        self._think_lbl.setText(self._think_frames[self._think_idx])

    def _stop_think(self):
        self._think_timer.stop()
        if self._think_lbl is not None:
            self._think_lbl.setText("")

    # ---------- MCP 初始化 ----------
    def _init_mcp(self):
        try:
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
        except Exception as e:
            msg = f"MCP: 初始化异常 {e}"
        self.mcp_signal.emit(msg)

    def _on_mcp_status(self, text: str):
        color = OK if "已连接" in text or "未配置" in text else WARN
        self.mcp_label.setText(text)
        self.mcp_label.setStyleSheet(f"color: {color}; font-size: 12px;")

    # ---------- 发送 / 停止 ----------
    def _llm_config(self) -> dict:
        return {
            "base_url": str(self._settings.value("agent_base_url", agent_llm.DEFAULT_BASE_URL)),
            "api_key": str(self._settings.value("agent_api_key", "")),
            "model": str(self._settings.value("agent_model", agent_llm.DEFAULT_MODEL)),
        }

    def _ensure_engine(self):
        """复用同一引擎：保留跨任务对话上下文"""
        if self._engine is None:
            cfg = self._llm_config()
            self._engine = agent_engine.AgentEngine(
                agent_llm.LLMClient(**cfg),
                mcp_manager=self._mcp,
                on_delta=lambda s: self.delta_signal.emit(s),
                on_status=lambda s: self.status_signal.emit(s),
                confirm=self._confirm_tool)
        return self._engine

    def _send(self):
        text = self.input.text().strip()
        if not text or (self._engine and self._engine._thread and self._engine._thread.is_alive()):
            return
        if text.lower().startswith("/compact"):
            self._do_compact()
            return
        if not self._llm_config()["api_key"]:
            QMessageBox.information(self, "提示", "请先点击「设置」填写 API Key")
            return
        engine = self._ensure_engine()

        self._add_bubble(text, "user")
        self._ai_bubble = None
        self.input.clear()
        self.input.setFocus()

        est = agent_llm.estimate_tokens(text)
        self.token_label.setText(f"本次预计 {est} tokens · 累计 0")

        self.send_btn.setText("发送中…")
        self.send_btn.setEnabled(False)
        self.stop_btn.setText("⏹ 停止")
        self.stop_btn.setEnabled(True)

        agent_name = self.agent_combo.currentData() or "桌面助手"
        engine.start(text, agent_name)

    def _stop(self):
        if self._engine:
            self._engine.stop()
        self.stop_btn.setText("停止中…")
        self.stop_btn.setEnabled(False)

    def _do_compact(self):
        """/compact：压缩上下文，把旧消息合并为摘要"""
        self.input.clear()
        if not self._engine or not self._engine._messages:
            self._add_status("ℹ️ 当前无可压缩的上下文", TEXT_DIM)
            return
        n = self._engine.compress_history(keep_recent=2)
        if n:
            self._add_status(f"🧬 已压缩上下文：{n} 条旧消息合并为摘要（保留最近 2 条完整）", ACCENT)
        else:
            self._add_status("ℹ️ 上下文较短，无需压缩", TEXT_DIM)

    def _clear_chat(self):
        """清空上下文：停止引擎、清空历史与气泡、tokens 归零"""
        if self._engine:
            self._engine.clear_history()
            if self._engine._thread and self._engine._thread.is_alive():
                self._engine.stop()
        self._stop_think()
        while self.msg_lay.count() > 1:  # 保留末尾 stretch
            item = self.msg_lay.takeAt(0)
            self._free_layout_item(item)
        self.token_label.setText("tokens: 0")
        self._ai_bubble = None
        self._add_status("🧹 已清空上下文，开启新对话", TEXT_DIM)

    def _free_layout_item(self, item):
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            while item.layout().count():
                self._free_layout_item(item.layout().takeAt(0))
            item.layout().deleteLater()

    def _refresh_meta(self):
        """轮询刷新 tokens / 按钮反馈状态"""
        if self._engine:
            t = self._engine.tokens
            self.token_label.setText(
                f"已用 {t['prompt'] + t['completion']} tokens "
                f"(输入 {t['prompt']} / 输出 {t['completion']})")
        running = bool(self._engine and self._engine._thread and self._engine._thread.is_alive())
        if not running and not self.send_btn.isEnabled():
            self.send_btn.setText("🚀 发送")
            self.send_btn.setEnabled(True)
            self.stop_btn.setText("⏹ 停止")
            self.stop_btn.setEnabled(False)
            self._stop_think()

    # ---------- 引擎回调（信号槽，主线程） ----------
    def _on_delta(self, s: str):
        self._stop_think()
        if self._ai_bubble is None:
            self._ai_bubble = self._add_bubble("", "ai")
        self._ai_bubble.setText(self._ai_bubble.text() + s)
        self._scroll_bottom()

    def _on_status(self, s: str):
        self._stop_think()
        if s == "正在思考…":
            self._start_think()
        elif s.startswith("错误"):
            self._add_status(f"❌ {s}", ERR)
        elif s.startswith("待执行") or s.startswith("正在执行"):
            self._add_status(f"⚙️ {s}", WARN)
        elif s == "完成":
            self._add_status("✅ 完成", OK)
        elif s == "已停止":
            self._add_status("⏹ 已停止", TEXT_DIM)
        elif s == "已达到最大工具轮数，自动结束":
            self._add_status(f"⚠️ {s}", WARN)

    # ---------- 每步确认（engine 线程调用 → 信号 → 主线程弹窗） ----------
    def _confirm_tool(self, name: str, args: dict) -> bool:
        if self._mode == "yolo":
            return True   # YOLO 模式：无确认直行（危险命令仍由沙盒硬拒绝）
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
        dlg.setStyleSheet(
            f"QDialog {{ background: {PANEL}; }}"
            f"QLabel {{ color: {TEXT}; font-size: 13px; }}"
            f"QLineEdit {{ background: {BG}; color: {TEXT}; border: 1px solid {BORDER};"
            "border-radius: 6px; padding: 6px 10px; }}"
            f"QPushButton {{ border: none; border-radius: 8px; padding: 7px 18px;"
            "font-weight: 700; }}")
        form = QFormLayout(dlg)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(12)
        base = QLineEdit(cfg["base_url"])
        key = QLineEdit(cfg["api_key"])
        key.setEchoMode(QLineEdit.EchoMode.Password)
        model = QLineEdit(cfg["model"])
        form.addRow("Base URL", base)
        form.addRow("API Key", key)
        form.addRow("模型", model)
        btns = QHBoxLayout()
        ok = QPushButton("✅ 保存")
        ok.setStyleSheet(f"background: {OK}; color: #06281B;")
        ok.clicked.connect(dlg.accept)
        cancel = QPushButton("取消")
        cancel.setStyleSheet(f"background: {PANEL}; color: {TEXT};"
                             f"border: 1px solid {BORDER};")
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
