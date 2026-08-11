"""AI Agent 工具面板（深色"星际控制台"风格，无 emoji，矢量图标）

消息气泡（TRAE 风格，单气泡一体化）：
- AI 气泡内依次渲染：思考过程 → 操作步骤 → 最终文本输出，均在同一气泡内
- 用户消息靠右（青色）、AI 消息靠左（深色卡片）
- 上下文：engine 复用保留跨任务对话历史（截图仅保留最近 2 张防膨胀），可一键清空
- 反馈：发送中/停止中按钮状态 + "思考中"点号动画 + tokens 实时统计
- 每步确认：AskBeforeEdit 弹窗确认（确认后危险命令可执行）；YOLO 无确认、危险命令一律拒绝
- MCP / skills / agents：从 ~/.winapp_migrator/agent/*.json 加载
"""

import html as _html
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
    QApplication, QStyle,
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
USER_BG = "#0EA5E9"       # 用户气泡/发送按钮底色（纯色）
AI_BG = "#1A2540"         # AI 气泡底色
OK = "#34D399"
WARN = "#FBBF24"
ERR = "#F87171"


def _app_icon_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", "."), "assets", "icon.ico")
    return str(Path(__file__).resolve().parents[3] / "assets" / "icon.ico")


def _std_icon(sp) -> QIcon:
    """系统矢量图标（无 emoji）"""
    return QApplication.style().standardIcon(sp)


def _esc(s: str) -> str:
    return _html.escape(str(s), quote=False)


class _ConfirmDialog(QDialog):
    """工具执行确认：显示当前屏幕截图 + 操作 + 风险等级"""

    def __init__(self, name: str, args: dict, risk: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 请求执行操作")
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
        risk_txt = {"safe": "安全（白名单）", "risky": "需谨慎", "dangerous": "危险（确认后将执行）"}
        head = QLabel(f"AI 想执行：<b>{_esc(name)}</b>　风险：<span style='color:{risk_color.get(risk, TEXT)}'>"
                      f"{risk_txt.get(risk, risk)}</span>")
        head.setStyleSheet("font-size: 14px;")
        lay.addWidget(head)

        arg_txt = QLabel(json.dumps(args, ensure_ascii=False, indent=2))
        arg_txt.setWordWrap(True)
        arg_txt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
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
        deny = QPushButton(_std_icon(QStyle.StandardPixmap.SP_DialogNoButton), "拒绝")
        deny.setStyleSheet(f"background: {ERR}; color: white;")
        deny.setAutoDefault(False)
        deny.clicked.connect(self._deny)
        allow = QPushButton(_std_icon(QStyle.StandardPixmap.SP_DialogYesButton), "允许执行")
        allow.setStyleSheet(f"background: {OK}; color: #06281B;")
        allow.setAutoDefault(False)
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


# 常用 MCP 服务器模板（选择后预填命令）
_MCP_TEMPLATES = [
    ("自定义", None),
    ("Excel 表格操作", {"command": "npx",
                        "args": ["-y", "@executeautomation/excel-mcp-server"]}),
    ("文件系统操作", {"command": "npx",
                      "args": ["-y", "@modelcontextprotocol/server-filesystem"]}),
    ("WPS 文本操作（需自建服务器）", {"command": "", "args": []}),
]


class _McpServerDialog(QDialog):
    """单个 MCP 服务器配置：stdio（命令+参数）或 SSE（URL）"""

    def __init__(self, server: dict = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑 MCP 服务器" if server else "添加 MCP 服务器")
        self.setMinimumWidth(460)
        self.setStyleSheet(
            f"QDialog {{ background: {PANEL}; }}"
            f"QLabel {{ color: {TEXT}; font-size: 13px; }}"
            f"QLineEdit, QComboBox {{ background: {BG}; color: {TEXT};"
            f"border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 10px; }}")
        self._server = server or {}
        form = QFormLayout(self)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(12)

        self.name_edit = QLineEdit(server.get("name", "") if server else "")
        self.name_edit.setPlaceholderText("服务器名称，如 Excel、WPS")
        form.addRow("名称", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItem("stdio（本地命令）", "stdio")
        self.type_combo.addItem("sse（远程 URL）", "sse")
        if server:
            idx = self.type_combo.findData(server.get("type", "stdio"))
            self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.type_combo.currentIndexChanged.connect(self._sync_type)
        form.addRow("类型", self.type_combo)

        self.template_combo = QComboBox()
        for tpl, _ in _MCP_TEMPLATES:
            self.template_combo.addItem(tpl)
        self.template_combo.currentIndexChanged.connect(self._apply_template)
        form.addRow("模板", self.template_combo)

        self.command_edit = QLineEdit(server.get("command", "") if server else "")
        self.command_edit.setPlaceholderText("如 npx / uvx / python")
        form.addRow("命令", self.command_edit)

        self.args_edit = QLineEdit(" ".join(server.get("args", [])) if server else "")
        self.args_edit.setPlaceholderText("参数，空格分隔，如 -y @executeautomation/excel-mcp-server")
        form.addRow("参数", self.args_edit)

        self.url_edit = QLineEdit(server.get("url", "") if server else "")
        self.url_edit.setPlaceholderText("https://…/sse")
        form.addRow("URL", self.url_edit)

        btns = QHBoxLayout()
        ok = QPushButton(_std_icon(QStyle.StandardPixmap.SP_DialogYesButton), "确定")
        ok.setStyleSheet(f"background: {OK}; color: #06281B;")
        ok.setAutoDefault(False)
        ok.clicked.connect(self._accept_check)
        cancel = QPushButton("取消")
        cancel.setStyleSheet(f"background: {PANEL}; color: {TEXT};"
                             f"border: 1px solid {BORDER};")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        form.addRow(btns)

        self._sync_type()
        if server and server.get("type") == "sse":
            self.template_combo.setCurrentIndex(0)

    def _sync_type(self):
        sse = self.type_combo.currentData() == "sse"
        self.command_edit.setEnabled(not sse)
        self.args_edit.setEnabled(not sse)
        self.url_edit.setEnabled(sse)

    def _apply_template(self, idx):
        tpl = _MCP_TEMPLATES[idx][1]
        if not tpl:
            return
        if tpl.get("command"):
            self.command_edit.setText(tpl["command"])
            self.args_edit.setText(" ".join(tpl["args"]))
            self.type_combo.setCurrentIndex(0)
            self.url_edit.clear()

    def _accept_check(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入服务器名称")
            return
        if self.type_combo.currentData() == "sse":
            if not self.url_edit.text().strip():
                QMessageBox.warning(self, "提示", "SSE 类型需要填写 URL")
                return
        else:
            if not self.command_edit.text().strip():
                QMessageBox.warning(self, "提示", "stdio 类型需要填写命令")
                return
        self.accept()

    def server_data(self) -> dict:
        d = {"name": self.name_edit.text().strip(),
             "type": self.type_combo.currentData()}
        if d["type"] == "sse":
            d["url"] = self.url_edit.text().strip()
        else:
            d["command"] = self.command_edit.text().strip()
            args = [a for a in self.args_edit.text().split() if a.strip()]
            if args:
                d["args"] = args
        return d


class _McpManagerDialog(QDialog):
    """MCP 服务器管理：列表 + 添加/编辑/删除 + 保存并重连"""

    def __init__(self, on_saved, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MCP 服务器配置")
        self.setMinimumSize(520, 420)
        self.on_saved = on_saved
        self.servers = agent_skills.load_mcp_servers()
        self.setStyleSheet(
            f"QDialog {{ background: {PANEL}; }}"
            f"QLabel {{ color: {TEXT}; font-size: 13px; }}"
            f"QListWidget {{ background: {BG}; color: {TEXT}; border: 1px solid {BORDER};"
            "border-radius: 8px; padding: 6px; }}"
            f"QPushButton {{ border: none; border-radius: 8px; padding: 7px 16px;"
            "font-weight: 700; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        head = QLabel("已配置的 MCP 服务器（保存后自动重连，AI 即可调用其工具）")
        head.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        lay.addWidget(head)

        self.list_w = QListWidget()
        self.list_w.setMinimumHeight(220)
        lay.addWidget(self.list_w, 1)

        btns = QHBoxLayout()
        add_b = QPushButton(_std_icon(QStyle.StandardPixmap.SP_FileDialogNewFolder), "添加")
        add_b.setStyleSheet(f"background: {PANEL}; color: {ACCENT};"
                            f"border: 1px solid {ACCENT};")
        add_b.clicked.connect(self._on_add)
        edit_b = QPushButton("编辑")
        edit_b.setStyleSheet(f"background: {PANEL}; color: {TEXT};"
                             f"border: 1px solid {BORDER};")
        edit_b.clicked.connect(self._on_edit)
        del_b = QPushButton("删除")
        del_b.setStyleSheet(f"background: {PANEL}; color: {ERR};"
                            f"border: 1px solid {ERR};")
        del_b.clicked.connect(self._on_delete)
        for b in (add_b, edit_b, del_b):
            b.setAutoDefault(False)
        btns.addWidget(add_b)
        btns.addWidget(edit_b)
        btns.addWidget(del_b)
        btns.addStretch(1)
        lay.addLayout(btns)

        save_b = QPushButton(_std_icon(QStyle.StandardPixmap.SP_DialogYesButton), "保存并重连")
        save_b.setStyleSheet(f"background: {OK}; color: #06281B;")
        save_b.setAutoDefault(False)
        save_b.clicked.connect(self._on_save)
        cancel_b = QPushButton("取消")
        cancel_b.setStyleSheet(f"background: {PANEL}; color: {TEXT};"
                               f"border: 1px solid {BORDER};")
        cancel_b.setAutoDefault(False)
        cancel_b.clicked.connect(self.reject)
        foot = QHBoxLayout()
        foot.addWidget(save_b)
        foot.addWidget(cancel_b)
        lay.addLayout(foot)

        self._reload_list()

    def _reload_list(self):
        self.list_w.clear()
        for s in self.servers:
            typ = "stdio" if s.get("type", "stdio") == "stdio" else "sse"
            detail = s.get("command", "") or s.get("url", "")
            self.list_w.addItem(f"{s.get('name', '?')}  [{typ}]  {detail}")

    def _current_server(self) -> dict:
        row = self.list_w.currentRow()
        if 0 <= row < len(self.servers):
            return self.servers[row]
        return None

    def _on_add(self):
        dlg = _McpServerDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.servers.append(dlg.server_data())
            self._reload_list()

    def _on_edit(self):
        s = self._current_server()
        if s is None:
            QMessageBox.information(self, "提示", "请先选择一个服务器")
            return
        dlg = _McpServerDialog(server=s, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.servers[self.list_w.currentRow()] = dlg.server_data()
            self._reload_list()

    def _on_delete(self):
        row = self.list_w.currentRow()
        if 0 <= row < len(self.servers):
            self.servers.pop(row)
            self._reload_list()

    def _on_save(self):
        if agent_skills.save_mcp_servers(self.servers):
            if self.on_saved:
                self.on_saved()   # 触发后台重连
            QMessageBox.information(self, "已保存", "MCP 配置已保存，正在重新连接…")
            self.accept()
        else:
            QMessageBox.warning(self, "错误", "保存 MCP 配置失败（无写入权限）")


class AgentPanel(QDialog):
    delta_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    confirm_signal = pyqtSignal(str, str, str)  # name, args_json, risk
    mcp_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Agent 工具面板")
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

        # 当前 AI 气泡内容状态（思考区 / 操作区 / 正文区）
        self._ai_bubble = None
        self._think_html = ""
        self._op_list = []        # 操作行（HTML 片段）
        self._body_html = ""
        self._think_idx = 0

        self._build_ui()
        self._connect_signals()

        self._think_timer = QTimer(self)
        self._think_timer.timeout.connect(self._tick_think)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_meta)
        self._timer.start(400)

        threading.Thread(target=self._init_mcp, daemon=True).start()

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # 顶栏：标题 + Agent 选择 + 模式 + MCP + tokens + 清空 + 设置
        top = QHBoxLayout()
        top.setSpacing(10)
        title = QLabel("AI AGENT")
        title.setStyleSheet(f"color: {ACCENT}; font-size: 16px; font-weight: 800;")
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
        self.mode_combo.addItem("AskBeforeEdit（每步确认）", "ask")
        self.mode_combo.addItem("YOLO（无确认直行）", "yolo")
        self.mode_combo.setMinimumWidth(190)
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

        mcp_btn = QPushButton(_std_icon(QStyle.StandardPixmap.SP_ComputerIcon), "MCP")
        mcp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        mcp_btn.setAutoDefault(False)
        mcp_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; color: {ACCENT}; border: 1px solid {ACCENT};"
            "border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #16233C; }}")
        mcp_btn.clicked.connect(self._open_mcp_manager)
        top.addWidget(mcp_btn)

        top.addStretch(1)

        self.token_label = QLabel("tokens: 0")
        self.token_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        top.addWidget(self.token_label)

        clear_btn = QPushButton(_std_icon(QStyle.StandardPixmap.SP_TrashIcon), "清空")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setAutoDefault(False)
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};"
            "border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}")
        clear_btn.clicked.connect(self._clear_chat)
        top.addWidget(clear_btn)

        # 模型/接口/API Key 已写死，无需设置入口
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

        self.send_btn = QPushButton(_std_icon(QStyle.StandardPixmap.SP_ArrowUp), "发送")
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setAutoDefault(False)
        self.send_btn.setMinimumHeight(42)
        self.send_btn.setMinimumWidth(96)
        self.send_btn.setStyleSheet(
            f"QPushButton {{ background: {USER_BG}; color: white; border: none;"
            "border-radius: 10px; padding: 0 16px; font-size: 13px; font-weight: 700; }}"
            f"QPushButton:hover {{ border: 1px solid {ACCENT}; }}"
            f"QPushButton:disabled {{ background: #1A2540; color: {TEXT_DIM}; }}")
        self.send_btn.clicked.connect(self._send)
        bottom.addWidget(self.send_btn)

        self.stop_btn = QPushButton(_std_icon(QStyle.StandardPixmap.SP_MediaStop), "停止")
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setAutoDefault(False)
        self.stop_btn.setMinimumHeight(42)
        self.stop_btn.setMinimumWidth(88)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(
            f"QPushButton {{ background: {ERR}; color: white; border: none;"
            "border-radius: 10px; padding: 0 14px; font-size: 13px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: #EF4444; }}"
            f"QPushButton:disabled {{ background: #1A2540; color: {TEXT_DIM}; }}")
        self.stop_btn.clicked.connect(self._stop)
        bottom.addWidget(self.stop_btn)
        root.addLayout(bottom)

        tip = QLabel("提示：AskBeforeEdit 模式每步操作弹窗确认，确认后危险命令（关机/删除等）也会执行；"
                     "YOLO 模式不弹窗，危险命令一律拒绝。输入 /compact 压缩上下文。"
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
            self._add_status("YOLO 模式：AI 操作不再弹窗确认（危险命令一律拒绝）", WARN)
        else:
            self._add_status("AskBeforeEdit 模式：每步操作弹窗确认", OK)

    # ---------- 消息气泡 ----------
    def _add_bubble(self, text: str, align: str) -> QLabel:
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble.setMaximumWidth(560)
        if align == "user":
            bubble.setTextFormat(Qt.TextFormat.PlainText)   # 用户消息纯文本
            bubble.setStyleSheet(f"background: {USER_BG}; color: white;"
                                 "border-radius: 14px; padding: 10px 14px; font-size: 13px;")
        else:
            bubble.setTextFormat(Qt.TextFormat.RichText)    # AI 消息富文本（思考/操作/正文）
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

    def _add_status(self, text: str, color: str):
        lbl = QLabel(f"<span style='color:{color};'>{_esc(text)}</span>")
        lbl.setStyleSheet(f"font-size: 12px; padding: 2px 4px;")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(lbl)
        row.addStretch(1)
        self.msg_lay.insertLayout(self.msg_lay.count() - 1, row)
        self._scroll_bottom()

    def _scroll_bottom(self):
        # 延迟到布局更新后再滚动，否则 maximum 还是旧值导致滚不到底
        QTimer.singleShot(0, self._do_scroll_bottom)

    def _do_scroll_bottom(self):
        bar = self.msg_area.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ---------- AI 气泡内容（思考 / 操作 / 正文 一体化） ----------
    def _ensure_ai_bubble(self):
        if self._ai_bubble is None or not self._bubble_alive(self._ai_bubble):
            self._ai_bubble = self._add_bubble("", "ai")
        return self._ai_bubble

    @staticmethod
    def _bubble_alive(lbl: QLabel) -> bool:
        try:
            lbl.text()
            return True
        except RuntimeError:
            return False

    def _refresh_ai_html(self):
        if self._ai_bubble is None:
            return
        parts = []
        if self._think_html:
            parts.append(f'<div style="color:{TEXT_DIM};font-size:12px;font-style:italic;">'
                         f'{self._think_html}</div>')
        for op in self._op_list:
            parts.append(f'<div style="color:{ACCENT};font-size:12px;'
                         f'font-family:Consolas;">{op}</div>')
        if self._body_html:
            parts.append(f'<div style="color:{TEXT};font-size:13px;">{self._body_html}</div>')
        try:
            self._ai_bubble.setText("".join(parts))
        except RuntimeError:
            self._ai_bubble = None

    # ---------- "思考中"动画 ----------
    def _start_think(self):
        self._think_idx = 0
        self._think_html = "思考中"
        self._refresh_ai_html()
        self._think_timer.start(350)

    def _tick_think(self):
        self._think_idx += 1
        self._think_html = "思考中" + "." * (self._think_idx % 4)
        self._refresh_ai_html()

    def _stop_think(self):
        self._think_timer.stop()
        # 保留思考行（固定文字），思考区始终位于气泡顶部，下方跟操作与正文
        if self._think_html:
            self._think_html = "思考中"
            self._refresh_ai_html()

    # ---------- MCP 初始化 ----------
    def _init_mcp(self):
        try:
            self._mcp.close_all()   # 重连前关闭旧连接
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

    def _open_mcp_manager(self):
        """打开 MCP 服务器配置面板；保存后后台重连"""
        dlg = _McpManagerDialog(on_saved=self._reconnect_mcp, parent=self)
        dlg.exec()

    def _reconnect_mcp(self):
        threading.Thread(target=self._init_mcp, daemon=True).start()

    # ---------- 发送 / 停止 ----------
    def _llm_config(self) -> dict:
        # 模型、接口与 API Key 全部写死为 Agnes 2.5，禁止用户自定义
        return {
            "base_url": agent_llm.DEFAULT_BASE_URL,
            "model": agent_llm.DEFAULT_MODEL,
            "api_key": agent_llm.DEFAULT_API_KEY,
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
        engine = self._ensure_engine()

        self._add_bubble(text, "user")
        self._ai_bubble = None
        self._think_html = ""
        self._op_list = []
        self._body_html = ""
        self.input.clear()
        self.input.setFocus()

        est = agent_llm.estimate_tokens(text)
        self.token_label.setText(f"本次预计 {est} tokens · 累计 0")

        self.send_btn.setText("发送中…")
        self.send_btn.setEnabled(False)
        self.stop_btn.setText("停止")
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
            self._add_status("当前无可压缩的上下文", TEXT_DIM)
            return
        n = self._engine.compress_history(keep_recent=2)
        if n:
            self._add_status(f"已压缩上下文：{n} 条旧消息合并为摘要（保留最近 2 条完整）", ACCENT)
        else:
            self._add_status("上下文较短，无需压缩", TEXT_DIM)

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
        self._think_lbl = None   # 兼容旧引用（无则忽略）
        self._think_html = ""
        self._op_list = []
        self._body_html = ""
        self._add_status("已清空上下文，开启新对话", TEXT_DIM)

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
            self.send_btn.setText("发送")
            self.send_btn.setEnabled(True)
            self.stop_btn.setText("停止")
            self.stop_btn.setEnabled(False)
            self._stop_think()

    # ---------- 引擎回调（信号槽，主线程） ----------
    def _on_delta(self, s: str):
        self._stop_think()
        self._ensure_ai_bubble()
        self._body_html += _esc(s)
        self._refresh_ai_html()
        self._scroll_bottom()

    def _on_status(self, s: str):
        if s == "正在思考…":
            self._start_think()
        elif s.startswith("待执行工具:"):
            name = s.split(":", 1)[1].strip()
            self._op_list.append(f"▎{_esc(name)}")
            self._refresh_ai_html()
        elif s.startswith("正在执行:"):
            name = s.split(":", 1)[1].strip()
            if self._op_list:
                self._op_list[-1] = f"▎{_esc(name)} …"
            else:
                self._op_list.append(f"▎{_esc(name)} …")
            self._refresh_ai_html()
        elif s == "完成":
            pass   # 正文即最终输出，无需额外标记
        elif s == "已停止":
            self._stop_think()
            self._ensure_ai_bubble()
            self._body_html += f'<br/><span style="color:{TEXT_DIM};">已停止</span>'
            self._refresh_ai_html()
        elif s.startswith("错误"):
            self._stop_think()
            self._ensure_ai_bubble()
            self._body_html += f'<br/><span style="color:{ERR};">{_esc(s)}</span>'
            self._refresh_ai_html()
        elif s == "已达到最大工具轮数，自动结束":
            self._stop_think()
            self._ensure_ai_bubble()
            self._body_html += f'<br/><span style="color:{TEXT_DIM};">{_esc(s)}</span>'
            self._refresh_ai_html()

    # ---------- 每步确认（engine 线程调用 → 信号 → 主线程弹窗） ----------
    def _confirm_tool(self, name: str, args: dict) -> bool:
        level, reason = agent_sandbox.assess_tool(name, args)
        if self._mode == "yolo":
            # YOLO 无人工确认，危险命令（删除/关机等）一律拒绝，保证安全底线
            return level != "dangerous"
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
    # 模型/接口/API Key 已写死，无需设置对话框

    def closeEvent(self, event):
        if self._engine:
            self._engine.stop()
            self._engine.join(3)
        try:
            self._mcp.close_all()
        except Exception:
            pass
        event.accept()
