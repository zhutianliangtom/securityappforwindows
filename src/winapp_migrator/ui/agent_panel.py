"""AI Agent 工具面板（深色"星际控制台"风格，无 emoji，矢量图标）

消息气泡（TRAE 风格，单气泡一体化）：
- AI 气泡内依次渲染：思考过程 → 操作步骤 → 最终文本输出，均在同一气泡内
- 用户消息靠右（青色）、AI 消息靠左（深色卡片）
- 上下文：engine 复用保留跨任务对话历史（截图仅保留最近 2 张防膨胀），可一键清空
- 反馈：发送中/停止中按钮状态 + "思考中"点号动画 + tokens 实时统计
- 每步确认：AskBeforeEdit 弹窗确认（确认后危险命令可执行）；YOLO 无确认、危险命令一律拒绝
- MCP / skills / agents：从 ~/.winapp_migrator/agent/*.json 加载
"""

import base64
import html as _html
import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QSettings, QPropertyAnimation, pyqtSignal, QByteArray, QBuffer, QIODevice, QFileInfo
from PyQt6.QtGui import QIcon, QFont, QPainter, QPen, QColor, QPixmap, QImage
from PyQt6.QtWidgets import (
    QDialog, QLabel, QLineEdit, QPushButton, QComboBox, QScrollArea,
    QVBoxLayout, QHBoxLayout, QMessageBox, QFormLayout, QWidget,
    QApplication, QStyle, QListWidget, QGraphicsOpacityEffect,
    QCompleter, QRadioButton, QCheckBox, QFileIconProvider, QListWidgetItem,
    QStackedWidget,
)

from winapp_migrator.core import agent_llm, agent_engine, agent_skills, agent_sandbox, agent_tools, agent_screen
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


# ---------- 轻量 Markdown → HTML 渲染 ----------
# 数学公式（轻量 LaTeX → Unicode/HTML，零额外依赖）
_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "chi": "χ",
    "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ",
    "Omega": "Ω",
}
_MATH_SYMBOLS = {
    "times": "×", "div": "÷", "pm": "±", "cdot": "·", "le": "≤", "leq": "≤",
    "ge": "≥", "geq": "≥", "neq": "≠", "approx": "≈", "equiv": "≡",
    "rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔", "infty": "∞",
    "sum": "∑", "int": "∫", "prod": "∏", "partial": "∂", "forall": "∀",
    "exists": "∃", "in": "∈", "notin": "∉", "subset": "⊂", "subseteq": "⊆",
    "cup": "∪", "cap": "∩", "emptyset": "∅", "nabla": "∇", "dots": "…",
    "cdots": "⋯", "ldots": "…", "to": "→", "ast": "∗", "propto": "∝",
    "angle": "∠", "perp": "⊥", "parallel": "∥", "therefore": "∴",
    "because": "∵", "mod": " mod ", "circ": "∘", "deg": "°",
}


def _formula_to_html(s: str) -> str:
    """轻量 LaTeX 公式 → HTML：希腊字母/符号/分数/根号/上下标"""
    s = s.strip()
    # 去掉排版命令（\left \right \displaystyle \quad 等）
    s = re.sub(r"\\(?:left|right|displaystyle|textstyle|quad|qquad|,|;|!|:)\b", "", s)
    # 分数 → (分子)/(分母)（参数可为含花括号的表达式，非贪婪逐层处理）
    while True:
        m = re.search(r"\\frac\{(.+?)\}\{(.+?)\}", s)
        if not m:
            break
        s = s[:m.start()] + f"({m.group(1)})/({m.group(2)})" + s[m.end():]
    # 根号：\sqrt[n]{x} → n√(x)；\sqrt{x} → √(x)
    s = re.sub(r"\\sqrt\[([^{}]*)\]\{(.+?)\}",
               lambda m: f"{m.group(1)}√({m.group(2)})", s)
    s = re.sub(r"\\sqrt\{(.+?)\}", r"√(\1)", s)
    # 上下标：^{...} _{...} ^x _x
    s = re.sub(r"\^\{([^{}]*)\}", r"<sup>\1</sup>", s)
    s = re.sub(r"_\{([^{}]*)\}", r"<sub>\1</sub>", s)
    s = re.sub(r"\^([a-zA-Z0-9])", r"<sup>\1</sup>", s)
    s = re.sub(r"_([a-zA-Z0-9])", r"<sub>\1</sub>", s)
    # 命名符号：\pi → π、\times → ×、\text{...} → 原文
    s = re.sub(r"\\text\{([^{}]*)\}", r"\1", s)

    def _sym(m):
        name = m.group(1)
        return _GREEK.get(name) or _MATH_SYMBOLS.get(name) or m.group(0)
    s = re.sub(r"\\([a-zA-Z]+)", _sym, s)
    return s


def _inline_md(s: str) -> str:
    """行内样式：数学公式 $...$、`code`、**bold**、[text](url)"""
    # 先提取行内公式为占位符，避免被转义/加粗等逻辑破坏
    formulas = {}

    def _cap(m):
        idx = f"\x00F{len(formulas)}\x00"
        formulas[idx] = _formula_to_html(m.group(1))
        return idx
    s = re.sub(r"\$([^$\n]+)\$", _cap, s)
    s = _esc(s)
    for idx, html in formulas.items():
        s = s.replace(idx, html)
    s = re.sub(r"`([^`]+)`",
               r"<code style='background:#0B1220;color:#22D3EE;padding:1px 5px;"
               r"border-radius:4px;font-family:Consolas;'>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               r'<a href="\2" style="color:#22D3EE;">\1</a>', s)
    return s


def _md_to_html(raw: str) -> str:
    """块级 Markdown → HTML：代码块、标题、列表、段落"""
    lines = raw.split("\n")
    out = []
    in_code = False
    in_list = False
    code_buf = []
    for line in lines:
        s = line.strip()
        if s.startswith("```"):
            if in_code:
                out.append("<pre style='background:#0B1220;color:#E6EDF7;padding:8px;"
                           "border-radius:6px;font-family:Consolas;font-size:12px;"
                           f"border:1px solid #1E2A44;'>" + _esc("\n".join(code_buf)) + "</pre>")
                code_buf = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_buf.append(line)
            continue
        if not s:
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        # 块级数学公式 $$...$$（单行）→ 居中展示
        m = re.match(r"^\$\$(.+)\$\$\s*$", s)
        if m:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<div style='text-align:center;margin:8px 0;"
                       f"font-family:Georgia,'Times New Roman',serif;font-size:16px;"
                       f"color:{TEXT};'>{_formula_to_html(m.group(1))}</div>")
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", s)
        if m:
            if in_list:
                out.append("</ul>")
                in_list = False
            lvl = len(m.group(1))
            out.append(f"<h{lvl} style='margin:8px 0 4px;color:#E6EDF7;"
                       f"font-size:{max(13, 20 - lvl)}px;'>{_inline_md(m.group(2))}</h{lvl}>")
            continue
        if re.match(r"^[-*+]\s+", s) or re.match(r"^\d+[.)]\s+", s):
            if not in_list:
                out.append("<ul style='margin:4px 0;padding-left:18px;'>")
                in_list = True
            item = re.sub(r"^[-*+]\s+|^\d+[.)]\s+", "", s)
            out.append("<li>" + _inline_md(item) + "</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        out.append("<p style='margin:4px 0;'>" + _inline_md(s) + "</p>")
    if in_code:
        out.append("<pre style='background:#0B1220;color:#E6EDF7;padding:8px;"
                   "border-radius:6px;font-family:Consolas;font-size:12px;"
                   f"border:1px solid #1E2A44;'>" + _esc("\n".join(code_buf)) + "</pre>")
    if in_list:
        out.append("</ul>")
    return "".join(out)


def _render_text(raw: str) -> str:
    """AI 正文渲染：Markdown 解析；流式中代码块未闭合时回退为纯文本"""
    if raw.count("```") % 2 == 1:
        return _esc(raw).replace("\n", "<br/>")
    return _md_to_html(raw)


class _Spinner(QWidget):
    """自绘转圈动画（矢量，无 emoji）：QTimer 驱动圆弧旋转"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(18, 18)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(50)

    def _rotate(self):
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(ACCENT), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(2, 2, 14, 14, -self._angle * 16, 270 * 16)
        p.end()


# 写入类操作：确认弹窗隐藏具体内容，仅提示目标
_HIDE_CONTENT_TOOLS = {"write_file", "edit_file", "save_memory"}


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

        arg_txt = QLabel()
        arg_txt.setWordWrap(True)
        arg_txt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        arg_txt.setStyleSheet(
            f"background: {BG}; color: {TEXT_DIM}; border: 1px solid {BORDER};"
            "border-radius: 8px; padding: 10px; font-size: 12px; font-family: Consolas;")
        if name in _HIDE_CONTENT_TOOLS:
            # 写入类操作：隐藏写入内容正文，仅显示目标路径与操作类型
            if name == "save_memory":
                shown = {"目标": "本地记忆文件 memory.md",
                         "写入量": f"{len(str(args.get('content', '')))} 字符"}
            else:
                shown = {"目标路径": args.get("path", ""),
                         "操作": {"write_file": "覆盖写入", "edit_file": "精确替换"}.get(name, name)}
            arg_txt.setText("（写入内容已隐藏，仅确认是否允许此操作）\n\n"
                            + json.dumps(shown, ensure_ascii=False, indent=2))
        else:
            arg_txt.setText(json.dumps(args, ensure_ascii=False, indent=2))
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


class _AskUserDialog(QDialog):
    """AI 提问弹窗（TRAE 风格）：单选/多选选项或自由回答"""

    def __init__(self, question: str, options: list, multi_select: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 询问")
        self.setMinimumWidth(460)
        self._answer = ""
        self.setStyleSheet(
            f"QDialog {{ background: {PANEL}; }}"
            f"QLabel {{ color: {TEXT}; font-size: 13px; }}"
            f"QRadioButton, QCheckBox {{ color: {TEXT}; font-size: 13px; spacing: 10px; }}"
            f"QLineEdit {{ background: {BG}; color: {TEXT}; border: 1px solid {BORDER};"
            "border-radius: 8px; padding: 8px 12px; font-size: 13px; }}"
            f"QPushButton {{ border: none; border-radius: 8px; padding: 8px 22px;"
            "font-weight: 700; font-size: 13px; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        q_lbl = QLabel(question)
        q_lbl.setWordWrap(True)
        q_lbl.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {TEXT};")
        lay.addWidget(q_lbl)

        self._choice_btns = []
        if options:
            for opt in options:
                b = QCheckBox(str(opt)) if multi_select else QRadioButton(str(opt))
                b.setAutoExclusive(not multi_select)
                self._choice_btns.append(b)
                lay.addWidget(b)
            self._free_input = None
        else:
            self._free_input = QLineEdit()
            self._free_input.setPlaceholderText("输入你的回答…")
            lay.addWidget(self._free_input)

        btns = QHBoxLayout()
        ok = QPushButton(_std_icon(QStyle.StandardPixmap.SP_DialogYesButton), "确定")
        ok.setStyleSheet(f"background: {OK}; color: #06281B;")
        ok.clicked.connect(self._accept_clicked)
        cancel = QPushButton("取消")
        cancel.setStyleSheet(f"background: {PANEL}; color: {TEXT};"
                             f"border: 1px solid {BORDER};")
        cancel.clicked.connect(self.reject)
        for b in (ok, cancel):
            b.setAutoDefault(False)
        btns.addStretch(1)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        lay.addLayout(btns)

    def _accept_clicked(self):
        sel = [b.text() for b in self._choice_btns if b.isChecked()]
        if sel:
            self._answer = " / ".join(sel)
        elif self._free_input is not None:
            self._answer = self._free_input.text().strip()
        if not self._answer:
            self._answer = "（用户未作答）"
        self.accept()

    def answer(self) -> str:
        return self._answer or "（用户取消回答）"


class AgentPanel(QDialog):
    delta_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    result_signal = pyqtSignal(str, str, object)   # 工具名, 执行输出, 截图缩略图列表
    reasoning_signal = pyqtSignal(str)     # 流式思考过程增量
    confirm_signal = pyqtSignal(str, str, str)  # name, args_json, risk
    ask_signal = pyqtSignal(str)           # ask_user 提问（args_json）
    mcp_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Agent 工具面板")
        self.setWindowIcon(QIcon(_app_icon_path()))
        self.setAcceptDrops(True)   # 支持把图片/文件拖入对话框
        # 窗口可自由调整大小，标题栏带最小化/最大化按钮
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowType.WindowMinMaxButtonsHint
                            | Qt.WindowType.WindowMaximizeButtonHint
                            | Qt.WindowType.WindowMinimizeButtonHint)
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
        self._ask_evt = threading.Event()
        self._ask_result = ""
        self._mcp = McpManager()
        self._agents = agent_skills.load_agents()

        # 拖入的附件：图片（data URL，发给模型）与非图片文件（路径文本）
        self._pending_images: list = []
        self._pending_files: list = []

        # 当前 AI 气泡段落序列（交织渲染：思考 → 操作 → 正文 → 操作 → 正文…）
        self._ai_bubble = None
        self._segments = []   # [{"type": "think|op|result|text|mark", "html"/"raw": ...}]

        # 任务进行中的转圈动画行（显示在消息流顶部）
        self._spinner_row = None
        self._spinner = None
        self._spinner_lbl = None
        self._reasoning_lbl = None

        # 任务结束徽章状态
        self._user_stopped = False     # 用户手动点击停止
        self._end_badge_shown = False  # 防止重复显示结束徽章

        # 流式思考过程状态
        self._think_start = 0.0        # 本轮思考开始时间（time.time）
        self._think_done = False       # 思考是否已完成（已输出"已思考 x 秒"）
        self._reasoning_buf = ""       # 思考过程文本缓冲

        # 卡死兜底 hooks：长时间无任何输出则自动停止
        self._last_activity = 0.0      # 最近一次有输出/状态的时间戳
        self._stalled_stop = False     # 是否因卡死自动停止
        self._task_active = False      # 是否有任务在执行（结束收尾的可靠依据）

        # 多对话（会话）状态：切换隔离上下文，AI 自动命名
        self._session_id = ""          # 当前会话 id
        self._session_name = "新对话"  # 当前会话名称
        self._user_msgs: list = []     # 当前会话的用户消息文本（用于切换时重绘）
        self._scroll_pending = False   # 滚动调度去重标志
        self._bubble_widgets: list = []  # 所有气泡 QLabel（窗口缩放时同步宽度）
        self._maximized_once = False   # 首次显示即最大化（默认最大化展示）

        # 发送/停止按钮转圈动画
        self._send_anim_angle = 0
        self._stop_anim_angle = 0

        self._build_ui()
        self._connect_signals()
        self._init_sessions()   # 加载会话列表，默认恢复最近对话（上下文隔离）

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_meta)
        self._timer.start(400)

        self._send_anim = QTimer(self)
        self._send_anim.timeout.connect(self._tick_send_anim)
        self._send_anim.setInterval(80)
        self._stop_anim = QTimer(self)
        self._stop_anim.timeout.connect(self._tick_stop_anim)
        self._stop_anim.setInterval(80)

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

        # 会话选择：切换对话（上下文隔离）+ 新对话按钮
        self.session_combo = QComboBox()
        self.session_combo.setMinimumWidth(150)
        self.session_combo.setMaximumWidth(220)
        self.session_combo.currentIndexChanged.connect(self._on_session_selected)
        top.addWidget(self.session_combo)

        new_btn = QPushButton(_std_icon(QStyle.StandardPixmap.SP_FileDialogNewFolder), "新对话")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setAutoDefault(False)
        new_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; color: {ACCENT}; border: 1px solid {ACCENT};"
            "border-radius: 8px; padding: 6px 10px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #16233C; }}")
        new_btn.clicked.connect(self._new_session)
        top.addWidget(new_btn)

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
        clear_btn.setToolTip("清空上下文并永久删除该对话（二次弹窗确认，不可恢复）")
        clear_btn.setAutoDefault(False)
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};"
            "border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}")
        clear_btn.clicked.connect(self._clear_chat)
        top.addWidget(clear_btn)

        # 模型/接口/API Key 已写死，无需设置入口
        root.addLayout(top)

        # 聊天区（气泡）与欢迎页（无对话时居中介绍 AI 功能）用堆叠切换
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

        self._welcome_page = self._build_welcome()
        self.msg_stack = QStackedWidget()
        self.msg_stack.addWidget(self.msg_area)
        self.msg_stack.addWidget(self._welcome_page)
        root.addWidget(self.msg_stack, 1)

        # 命令提示条：输入 / 时展示可用 skill/命令
        self.cmd_list = QListWidget()
        self.cmd_list.setMaximumHeight(112)
        self.cmd_list.setStyleSheet(
            f"QListWidget {{ background: {PANEL}; color: {ACCENT};"
            f"border: 1px solid {BORDER}; border-radius: 8px;"
            "font-size: 13px; padding: 4px; }}"
            f"QListWidget::item {{ padding: 4px 12px; border-radius: 6px; }}"
            f"QListWidget::item:hover {{ background: #16233C; }}"
            f"QListWidget::item:selected {{ background: {ACCENT}; color: #06281B; }}")
        self.cmd_list.hide()
        self.cmd_list.itemClicked.connect(self._on_cmd_selected)
        root.addWidget(self.cmd_list)

        # 附件缩略图条：拖入的图片/文件在此预览（隐藏时无高度）
        self._attach_bar = QWidget()
        self._attach_bar.setStyleSheet("background: transparent;")
        self._attach_lay = QHBoxLayout(self._attach_bar)
        self._attach_lay.setContentsMargins(0, 0, 0, 0)
        self._attach_lay.setSpacing(8)
        self._attach_lay.addStretch(1)
        self._attach_bar.setVisible(False)
        root.addWidget(self._attach_bar)

        # 输入栏
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.input = QLineEdit()
        self.input.setPlaceholderText("描述任务，例如：打开记事本，输入一段文字，再截图给我看（输入 / 查看命令）")
        self.input.setMinimumHeight(42)
        self.input.setStyleSheet(
            f"QLineEdit {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};"
            "border-radius: 10px; padding: 0 14px; font-size: 14px; }}"
            f"QLineEdit:focus {{ border: 1px solid #4B6BD6; }}")
        self.input.returnPressed.connect(self._send)
        self.input.textChanged.connect(self._update_cmd_suggestions)
        # 内联预测：输入 /com 时半透明显示 /compact 完成部分
        self._completer = QCompleter(self._all_commands(), self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.InlineCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.input.setCompleter(self._completer)
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
        self.result_signal.connect(self._on_result)
        self.reasoning_signal.connect(self._on_reasoning)
        self.confirm_signal.connect(self._on_confirm)
        self.ask_signal.connect(self._on_ask)
        self.mcp_signal.connect(self._on_mcp_status)

    # ---------- 欢迎页（无对话时居中介绍 AI 功能） ----------
    def _build_welcome(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.addStretch(1)
        card = QWidget()
        card.setMaximumWidth(520)
        card.setStyleSheet(
            f"background: {PANEL}; border: none; border-radius: 12px;")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(28, 24, 28, 24)
        cl.setSpacing(10)
        t = QLabel("AI 桌面助手")
        t.setStyleSheet(f"color: {TEXT}; font-size: 20px; font-weight: 800;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(t)
        sub = QLabel("观察你的屏幕，理解你的指令，帮你完成电脑操作")
        sub.setStyleSheet(f"color: {TEXT_DIM}; font-size: 13px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(sub)
        cl.addSpacing(6)
        for f in ("▪ 屏幕操控：截图分析后点击、输入、按键",
                  "▪ 文件操作：读取、写入、编辑本地文件",
                  "▪ 快速查找：秒查应用与文件（find_app / search_files）",
                  "▪ 技能命令：输入 / 查看全部技能与工具",
                  "▪ 拖拽图片：把图片拖入对话框让 AI 识别",
                  "▪ 多对话：自动命名、切换隔离、重启恢复"):
            lbl = QLabel(f)
            lbl.setStyleSheet(f"color: {TEXT}; font-size: 13px; padding: 3px 0;")
            cl.addWidget(lbl)
        cl.addSpacing(4)
        tip = QLabel("直接输入任务开始，例如：打开记事本并输入一段文字")
        tip.setStyleSheet(f"color: {ACCENT}; font-size: 12px;")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(tip)
        lay.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addStretch(1)
        return page

    def _update_welcome(self):
        """无对话内容时显示欢迎页，否则显示聊天区（发消息后立即切换）"""
        has_msg = bool(self._segments or self._user_msgs)
        self.msg_stack.setCurrentWidget(
            self.msg_area if has_msg else self._welcome_page)

    # ---------- 多对话（会话）管理 ----------
    def _sessions_dir(self) -> Path:
        return agent_skills.CONFIG_DIR / "sessions"

    def _load_session_list(self) -> list:
        try:
            with open(self._sessions_dir() / "sessions.json", encoding="utf-8") as f:
                lst = json.load(f)
            return lst if isinstance(lst, list) else []
        except Exception:
            return []

    def _save_session_list(self, lst: list):
        try:
            d = self._sessions_dir()
            d.mkdir(parents=True, exist_ok=True)
            with open(d / "sessions.json", "w", encoding="utf-8") as f:
                json.dump(lst, f, ensure_ascii=False)
        except Exception:
            pass

    def _init_sessions(self):
        """启动时加载会话列表；默认进入最近更新的旧对话（无会话则新建）"""
        lst = self._load_session_list()
        if not lst:
            self._create_session()
            lst = self._load_session_list()
        lst.sort(key=lambda s: s.get("updated", 0))   # 旧的在前，最近对话最后
        self._switch_to(lst[-1]["id"])
        self._update_welcome()

    def _create_session(self) -> dict:
        s = {"id": uuid.uuid4().hex[:12],
             "name": "新对话", "created": time.time(), "updated": time.time()}
        lst = self._load_session_list()
        lst.append(s)
        self._save_session_list(lst)
        return s

    def _persist_current(self):
        """保存当前会话：模型消息 + 界面气泡（segments/用户消息）+ 更新时间"""
        if not self._session_id:
            return
        d = self._sessions_dir()
        d.mkdir(parents=True, exist_ok=True)
        if self._engine:
            self._engine.save_context(d / f"{self._session_id}.json")
        try:
            with open(d / f"{self._session_id}.ui.json", "w", encoding="utf-8") as f:
                json.dump({"segments": self._segments, "user_msgs": self._user_msgs},
                          f, ensure_ascii=False)
        except Exception:
            pass
        lst = self._load_session_list()
        for x in lst:
            if x.get("id") == self._session_id:
                x["updated"] = time.time()
                x["name"] = self._session_name
        self._save_session_list(lst)

    def _refresh_session_combo(self):
        lst = self._load_session_list()
        self.session_combo.blockSignals(True)
        self.session_combo.clear()
        for s in lst:
            self.session_combo.addItem(s.get("name", "新对话"), s.get("id"))
        idx = self.session_combo.findData(self._session_id)
        if idx >= 0:
            self.session_combo.setCurrentIndex(idx)
        self.session_combo.blockSignals(False)

    def _on_session_selected(self, idx):
        sid = self.session_combo.itemData(idx)
        if sid and sid != self._session_id:
            self._switch_to(sid)

    def _switch_to(self, sid: str):
        """切换会话：保存当前 → 加载目标（上下文互相隔离）"""
        self._persist_current()
        self._session_id = sid
        lst = self._load_session_list()
        s = next((x for x in lst if x.get("id") == sid), None)
        self._session_name = s.get("name", "新对话") if s else "新对话"
        self._ai_bubble = None
        self._segments = []
        self._user_msgs = []
        self._hide_spinner()
        while self.msg_lay.count() > 1:  # 清空消息流（保留末尾 stretch）
            item = self.msg_lay.takeAt(0)
            self._free_layout_item(item)
        self._bubble_widgets = []
        d = self._sessions_dir()
        eng = self._ensure_engine()
        eng.load_context(d / f"{sid}.json")
        segs, ums = [], []
        try:
            with open(d / f"{sid}.ui.json", encoding="utf-8") as f:
                data = json.load(f)
            segs, ums = data.get("segments") or [], data.get("user_msgs") or []
        except Exception:
            pass
        self._segments, self._user_msgs = segs, ums
        for u in ums:                       # 重绘用户气泡与 AI 气泡
            self._add_bubble(u, "user")
        if segs:
            self._ensure_ai_bubble()
            self._refresh_ai_html()   # 截图 image 段随气泡富文本渲染（已截屏字样下方缩略图）
        self._end_badge_shown = False
        self._refresh_session_combo()
        self._update_welcome()
        self._add_status(f"已切换到对话「{self._session_name}」", TEXT_DIM)
        self._scroll_bottom()

    def _new_session(self):
        """新开对话：保存当前 → 创建空会话（上下文与旧对话隔离）"""
        if self._engine and self._engine._thread and self._engine._thread.is_alive():
            self._engine.stop()
        self._persist_current()
        s = self._create_session()
        self._session_id = s["id"]
        self._session_name = "新对话"
        if self._engine:
            self._engine.clear_history()
        self._ai_bubble = None
        self._segments = []
        self._user_msgs = []
        self._hide_spinner()
        while self.msg_lay.count() > 1:
            item = self.msg_lay.takeAt(0)
            self._free_layout_item(item)
        self._bubble_widgets = []
        self._refresh_session_combo()
        self._update_welcome()
        self._add_status("已开启新对话，上下文与旧对话隔离", ACCENT)
        self._scroll_bottom()

    def _auto_name_session(self, text: str):
        """AI 自动命名：会话无名称时用首条消息前 20 字命名"""
        if self._session_name != "新对话":
            return
        name = (text or "").strip()[:20]
        if not name:
            return
        self._session_name = name
        lst = self._load_session_list()
        for x in lst:
            if x.get("id") == self._session_id:
                x["name"] = name
        self._save_session_list(lst)
        self._refresh_session_combo()

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
    @staticmethod
    def _fade_in(widget: QWidget, parent: QWidget):
        """气泡淡入动画（增强体验）"""
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", parent)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _bubble_max_width(self) -> int:
        """聊天气泡最大宽度：随窗口自适应（至少 560，最大化时放大）"""
        return max(560, int(self.width() * 0.72))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        mw = self._bubble_max_width()
        for b in self._bubble_widgets:
            try:
                b.setMaximumWidth(mw)
            except RuntimeError:
                pass

    def showEvent(self, e):
        super().showEvent(e)
        if not self._maximized_once:   # 默认最大化展示
            self._maximized_once = True
            QTimer.singleShot(0, self.showMaximized)

    def _add_bubble(self, text: str, align: str, rich: bool = False) -> QLabel:
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble.setMaximumWidth(self._bubble_max_width())
        self._bubble_widgets.append(bubble)
        if align == "user":
            # 用户消息：默认纯文本；带图片时用富文本渲染缩略图（不显示源文本）
            bubble.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
            bubble.setStyleSheet(f"background: {USER_BG}; color: white;"
                                 "border-radius: 14px; padding: 10px 14px; font-size: 14px;")
        else:
            bubble.setTextFormat(Qt.TextFormat.RichText)    # AI 消息富文本（思考/操作/正文）
            bubble.setStyleSheet(f"background: {AI_BG}; color: {TEXT};"
                                 f"border: 1px solid {BORDER}; border-radius: 14px;"
                                 "padding: 10px 14px; font-size: 14px;")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if align == "user":
            row.addStretch(1)
            row.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)
        else:
            row.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)
            row.addStretch(1)
        self.msg_lay.insertLayout(self.msg_lay.count() - 1, row)
        self._fade_in(bubble, self)
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

    def _add_badge(self, text: str, color: str):
        """AI 气泡外的任务结束徽章（Stop by user / Successfully / Error）"""
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {color}; border: 1px solid {color}; border-radius: 10px;"
            "padding: 2px 12px; font-size: 12px; font-weight: 700;")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(lbl)
        row.addStretch(1)
        self.msg_lay.insertLayout(self.msg_lay.count() - 1, row)
        self._scroll_bottom()

    # ---------- 发送/停止按钮转圈动画 ----------
    @staticmethod
    def _spinner_icon(angle: int, color: str, size: int = 16) -> QIcon:
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(1, 1, size - 2, size - 2, -(angle % 360) * 16, 270 * 16)
        p.end()
        return QIcon(pm)

    def _start_send_anim(self):
        self._send_anim_angle = 0
        self._send_anim.start()

    def _tick_send_anim(self):
        self._send_anim_angle += 30
        self.send_btn.setIcon(self._spinner_icon(self._send_anim_angle, "#FFFFFF"))

    def _start_stop_anim(self):
        self._stop_anim_angle = 0
        self._stop_anim.start()

    def _tick_stop_anim(self):
        self._stop_anim_angle += 30
        self.stop_btn.setIcon(self._spinner_icon(self._stop_anim_angle, "#FFFFFF"))

    def _stop_button_anim(self):
        """任务结束：停止按钮动画并恢复原图标"""
        self._send_anim.stop()
        self._stop_anim.stop()
        self.send_btn.setIcon(_std_icon(QStyle.StandardPixmap.SP_ArrowUp))
        self.stop_btn.setIcon(_std_icon(QStyle.StandardPixmap.SP_MediaStop))

    def _scroll_bottom(self):
        # 流式输出高频调用时去重，避免 singleShot 堆积；
        # 0ms 立即滚 + 150ms 兜底（气泡最终高度稳定后再滚一次）
        if self._scroll_pending:
            return
        self._scroll_pending = True
        QTimer.singleShot(0, self._do_scroll_bottom)
        QTimer.singleShot(150, self._do_scroll_bottom)

    def _do_scroll_bottom(self):
        self._scroll_pending = False
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
        for seg in self._segments:
            t = seg["type"]
            if t == "think":
                parts.append(f'<div style="color:{TEXT_DIM};font-size:12px;font-style:italic;">'
                             f'{seg["html"]}</div>')
            elif t == "op":
                parts.append(f'<div style="color:{ACCENT};font-size:13px;'
                             f'font-family:Consolas;">{seg["html"]}</div>')
            elif t == "result":
                parts.append(f'<div style="color:{TEXT_DIM};font-size:13px;font-family:Consolas;'
                             f'border-left:3px solid {BORDER};padding:2px 10px;margin:2px 0 4px 14px;">'
                             f'{seg["html"]}</div>')
            elif t == "image":
                # 截图融入主对话气泡："已截屏"字样下方缩略图（display:block 独立成块，不重叠不窜位）
                url = seg.get("url", "")
                cap = seg.get("caption", "已截屏")
                parts.append(
                    f'<div style="color:{TEXT_DIM};font-size:11px;margin-top:6px;">{_esc(cap)}</div>'
                    f'<img src="{url}" width="240" style="border-radius:8px;display:block;'
                    'margin:4px 0 2px 0;">')
            elif t == "text":
                parts.append(f'<div style="color:{TEXT};font-size:14px;">'
                             f'{_render_text(seg["raw"])}</div>')
            elif t == "mark":
                parts.append(f'<div style="color:{TEXT_DIM};font-size:12px;">{seg["html"]}</div>')
        try:
            self._ai_bubble.setText("".join(parts))
        except RuntimeError:
            self._ai_bubble = None

    # ---------- 转圈动画 + 流式思考过程（AI 任务进行中） ----------
    def _ensure_spinner(self):
        """创建/显示转圈行：第一行[转圈+状态]，下方半透明小字流式思考过程"""
        if self._spinner_row is not None:
            return
        self._spinner = _Spinner()
        self._spinner_lbl = QLabel("AI 思考中…")
        self._spinner_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        top.addWidget(self._spinner)
        top.addWidget(self._spinner_lbl)
        top.addStretch(1)

        self._reasoning_lbl = QLabel("")
        self._reasoning_lbl.setWordWrap(True)
        self._reasoning_lbl.setMaximumWidth(560)
        self._reasoning_lbl.setStyleSheet(
            "color: rgba(138, 155, 184, 170); font-size: 11px;"  # 半透明小字体
            "padding-left: 26px;")

        self._spinner_row = QVBoxLayout()
        self._spinner_row.setContentsMargins(0, 0, 0, 0)
        self._spinner_row.setSpacing(2)
        self._spinner_row.addLayout(top)
        self._spinner_row.addWidget(self._reasoning_lbl)
        self.msg_lay.insertLayout(self.msg_lay.count() - 1, self._spinner_row)
        self._scroll_bottom()

    def _hide_spinner(self):
        """任务结束/清空时移除转圈动画行"""
        if self._spinner_row is None:
            return
        for i in range(self.msg_lay.count()):
            if self.msg_lay.itemAt(i).layout() is self._spinner_row:
                self._free_layout_item(self.msg_lay.takeAt(i))
                break
        self._spinner = None
        self._spinner_lbl = None
        self._reasoning_lbl = None
        self._spinner_row = None

    def _start_think(self):
        """任务进行中：显示转圈；首轮思考重置计时与思考文本"""
        if not self._think_done:
            self._think_start = time.time()
            self._reasoning_buf = ""
            if self._spinner_lbl is not None:
                self._spinner_lbl.setText("AI 思考中…")
            if self._reasoning_lbl is not None:
                self._reasoning_lbl.setText("")
        self._ensure_spinner()

    def _finish_thinking(self):
        """思考完成（开始输出正文/工具调用）：状态改为'已思考 x 秒'"""
        if self._think_done:
            return
        self._think_done = True
        if self._spinner_lbl is not None and self._think_start:
            el = int(time.time() - self._think_start)
            self._spinner_lbl.setText(f"已思考 {el} 秒")

    def _on_reasoning(self, s: str):
        """流式思考过程：半透明小字追加显示在'思考中'下方"""
        if self._think_done:
            return
        self._last_activity = time.time()
        self._ensure_spinner()
        self._reasoning_buf += s
        shown = self._reasoning_buf
        if len(shown) > 800:
            shown = "…" + shown[-800:]
        self._reasoning_lbl.setText(shown)
        self._scroll_bottom()

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

    # ---------- 命令补全（/ 展示全部命令 + 内联预测） ----------
    def _all_commands(self) -> list:
        """所有可斜杠调用项：系统命令 + 全部技能 + 全部内置工具"""
        cmds = ["/compact", "/clear"]
        cmds += [f"/{s.get('name')}" for s in agent_skills.load_skills() if s.get("name")]
        cmds += [f"/{t['function']['name']}" for t in agent_tools.TOOLS]
        return cmds

    def _cmd_desc(self, cmd: str) -> str:
        """命令描述（用于命令条 tooltip）"""
        name = cmd.lstrip("/")
        for s in agent_skills.load_skills():
            if s.get("name", "").strip().lower() == name.lower():
                return s.get("description", "")
        for t in agent_tools.TOOLS:
            if t["function"]["name"] == name:
                return t["function"].get("description", "")
        return ""

    def _match_skill(self, text: str):
        """按名称匹配内置技能（/技能名 手动调用），未匹配返回 None"""
        q = text.lstrip("/").strip().lower()
        for s in agent_skills.load_skills():
            if s.get("name", "").strip().lower() == q:
                return s
        return None

    def _match_tool(self, text: str):
        """/工具名 [参数] → (name, args_text)；支持中文别名（截屏/截图→screenshot）；未匹配返回 None"""
        body = text.lstrip("/").strip()
        parts = body.split(None, 1)
        if not parts:
            return None
        name = parts[0].strip().lower()
        aliases = {"截屏": "screenshot", "截图": "screenshot",
                   "看屏幕": "screenshot", "查看屏幕": "screenshot",
                   "查看桌面": "screenshot", "刷新": "screenshot"}
        name = aliases.get(name, name)
        names = {t["function"]["name"] for t in agent_tools.TOOLS}
        if name not in names:
            return None
        return name, (parts[1].strip() if len(parts) > 1 else "")

    @staticmethod
    def _tool_params_hint(name: str) -> str:
        """工具参数说明（供 AI 解析斜杠参数并转为 JSON）"""
        for t in agent_tools.TOOLS:
            if t["function"]["name"] == name:
                p = t["function"].get("parameters") or {}
                props = p.get("properties") or {}
                req = set(p.get("required") or [])
                if not props:
                    return "(无参数)"
                return ", ".join(
                    f"{k}({v.get('type', 'any')}{'必填' if k in req else '可选'})"
                    for k, v in props.items())
        return "(无参数)"

    def _update_cmd_suggestions(self, text: str):
        if text.startswith("/"):
            matches = [c for c in self._all_commands() if c.startswith(text)]
            if matches:
                self.cmd_list.clear()
                for c in matches:
                    item = QListWidgetItem(c)
                    desc = self._cmd_desc(c)
                    if desc:
                        item.setToolTip(desc)
                    self.cmd_list.addItem(item)
                self.cmd_list.show()
                return
        self.cmd_list.hide()

    def _on_cmd_selected(self, item):
        self.input.setText(item.text())
        self.input.setFocus()
        self.cmd_list.hide()

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
                on_result=lambda n, t, im: self.result_signal.emit(n, t, im),
                on_reasoning=lambda s: self.reasoning_signal.emit(s),
                confirm=self._confirm_tool,
                ask_user=self._ask_user_tool)
        return self._engine

    def _send(self):
        text = self.input.text().strip()
        images = list(self._pending_images)
        files = list(self._pending_files)
        if (not text and not images) or \
                (self._engine and self._engine._thread and self._engine._thread.is_alive()):
            return
        if text.lower().startswith("/compact"):
            self._do_compact()
            return
        if text.lower().startswith("/clear"):
            self._clear_chat()
            return
        # 手动调用内置技能：/技能名 → 把技能指令作为用户消息发送给 AI
        skill = self._match_skill(text)
        if skill:
            self._add_status(f"已调用技能「{skill.get('name')}」", ACCENT)
            text = (f"请使用技能「{skill.get('name')}」，严格按其流程执行。\n\n"
                    f"技能说明：\n{skill.get('instruction', '')}")
        # 手动指定工具：/工具名 [参数] → 转成指令由 AI 调用对应工具
        tool = self._match_tool(text)
        shot = None
        if tool:
            tname, targs = tool
            self._add_status(f"已指定工具「{tname}」", ACCENT)
            if tname == "screenshot":
                # 手动截屏：面板直接截图并展示（不依赖 AI 调用工具，保证必定出图）
                try:
                    shot = agent_screen.capture_screen_data_url()
                    text = "已截取当前屏幕并展示在对话中，请基于截图内容回答或继续执行。"
                except Exception:
                    shot = None
            else:
                text = (f"请调用工具「{tname}」完成以下任务，参数必须按 JSON 传入。\n"
                        f"工具参数说明：{self._tool_params_hint(tname)}\n"
                        f"参数原始文本：{targs or '(无，可自行确定合理参数，不确定时先 ask_user 澄清)'}")
        # 非图片附件：把路径文本附加给 AI（不显示源内容），AI 可按需 read_file
        if files:
            note = "以下为拖入的附件文件，请按需读取内容：\n" + \
                "\n".join(f"- {p}" for p in files)
            text = (text + "\n\n" if text else "") + note
        engine = self._ensure_engine()
        self._auto_name_session(text)   # 无名称会话：用首条消息自动命名
        self._user_msgs.append(text)
        self._update_welcome()          # 发消息后欢迎介绍立即消失

        # 用户气泡：文字与拖拽图片一并渲染进同一气泡（图片缩小缩略图、独立成块，不挤压不窜位）
        if images:
            parts = ([f'<div style="font-size:14px;">{_esc(text).replace(chr(10), "<br/>")}</div>']
                     if text else [])
            parts += [f'<img src="{u}" width="200" style="border-radius:8px;display:block;'
                      'margin:12px 0 12px 0;">' for u in images]
            self._add_bubble("<br/>".join(parts), "user", rich=True)
        else:
            self._add_bubble(text, "user")
        # 手动截屏：截图段进 AI 气泡（"已截屏"字样下方缩略图，融入主对话气泡）
        send_images = list(images)
        if shot:
            send_images.append(shot)
        self._ai_bubble = None
        self._segments = []
        if shot:
            self._segments.append({"type": "image", "url": shot, "caption": "已截屏"})
        self._user_stopped = False
        self._end_badge_shown = False
        self._think_done = False
        self._reasoning_buf = ""
        self._think_start = 0.0
        self._last_activity = time.time()
        self._stalled_stop = False
        self.input.clear()
        self.input.setFocus()

        est = agent_llm.estimate_tokens(text) + \
            agent_llm.estimate_image_tokens() * len(send_images)
        self.token_label.setText(f"本次预计 {est} tokens · 累计 0")

        self.send_btn.setText("发送中…")
        self.send_btn.setEnabled(False)
        self.stop_btn.setText("停止")
        self.stop_btn.setEnabled(True)
        self._start_send_anim()   # 发送按钮转圈动画

        self._clear_attachments()   # 发送后清空附件条
        agent_name = self.agent_combo.currentData() or "桌面助手"
        self._task_active = True
        engine.start(text, agent_name, send_images)

    def _stop(self):
        if self._engine:
            self._engine.stop()
        self._user_stopped = True
        self.stop_btn.setText("停止中…")
        self.stop_btn.setEnabled(False)
        self._start_stop_anim()   # 停止按钮转圈动画
        # 兜底：5 秒后线程仍未退出（卡死）→ 强制隔离
        QTimer.singleShot(5000, self._force_stop_if_stuck)

    def _force_stop_if_stuck(self):
        """强制停止兜底：普通 stop 后线程仍卡死（LLM/MCP 阻塞）时隔离引擎"""
        if not (self._engine and self._engine._thread and self._engine._thread.is_alive()):
            return   # 线程已正常退出，无需兜底
        eng = self._engine
        # 断开 UI 回调，防止后台线程后续输出污染界面
        eng.on_delta = None
        eng.on_status = None
        eng.on_result = None
        eng.on_reasoning = None
        eng._stop.set()
        self._engine = None   # 下次发送时重建全新引擎
        self._add_status("AI 线程无法中断，已强制隔离（后台线程已断开，新任务将自动重建）", ERR)
        self.send_btn.setText("发送")
        self.send_btn.setEnabled(True)
        self.stop_btn.setText("停止")
        self.stop_btn.setEnabled(False)
        self._task_active = False
        self._hide_spinner()
        self._stop_button_anim()
        if not self._end_badge_shown:
            self._end_badge_shown = True
            self._show_end_badge()
        self._scroll_bottom()

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

    def _delete_session(self, sid: str):
        """永久删除会话：移除元数据记录并删除磁盘上的全部会话文件"""
        d = self._sessions_dir()
        for fn in (f"{sid}.json", f"{sid}.ui.json"):
            try:
                (d / fn).unlink(missing_ok=True)
            except Exception:
                pass
        lst = [x for x in self._load_session_list() if x.get("id") != sid]
        self._save_session_list(lst)

    def _confirm_box(self, title: str, text: str) -> bool:
        """暗色主题确认框（白色字体），点"是"返回 True，点"否"返回 False"""
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Question)
        yes = box.addButton("是", QMessageBox.ButtonRole.YesRole)
        box.addButton("否", QMessageBox.ButtonRole.NoRole)
        # 默认焦点给"否"，防误触删除
        no_btn = box.buttons()[1]
        box.setDefaultButton(no_btn)
        box.setStyleSheet(
            f"QMessageBox {{ background: {PANEL}; }}"
            f"QMessageBox QLabel {{ color: {TEXT}; font-size: 13px; }}"
            f"QMessageBox QPushButton {{ color: {TEXT}; background: {AI_BG};"
            f"border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 20px;"
            "font-size: 13px; font-weight: 600; }}"
            f"QMessageBox QPushButton:hover {{ background: #16233C; border-color: {ACCENT}; }}")
        box.exec()
        return box.clickedButton() is yes

    def _clear_chat(self):
        """清空上下文并永久删除当前对话（二次弹窗确认，删除不可恢复）"""
        if not self._session_id:
            return
        # 第一次确认：清空上下文与聊天记录
        if not self._confirm_box("清空对话",
                                 "确定要清空当前对话吗？\n将清空全部上下文与聊天记录。"):
            return
        # 第二次确认：永久删除该对话（不可恢复）
        if not self._confirm_box("永久删除对话",
                                 "该对话将连同所有记录被永久删除，无法恢复！\n确定继续吗？"):
            return
        # ---- 执行：停止引擎 + 清空上下文与气泡 + tokens 归零 ----
        old_id = self._session_id
        if self._engine:
            self._engine.clear_history()
            self._engine.clear_context()   # 同时删除磁盘上的持久化上下文
            if self._engine._thread and self._engine._thread.is_alive():
                self._engine.stop()
        self._ai_bubble = None
        self._segments = []
        self._user_msgs = []
        self._hide_spinner()
        self.cmd_list.hide()
        self._stop_button_anim()
        # 任务进行中清空时，显式恢复按钮与任务标志，避免残留禁用/转圈
        self.send_btn.setText("发送")
        self.send_btn.setEnabled(True)
        self.stop_btn.setText("停止")
        self.stop_btn.setEnabled(False)
        self._task_active = False
        self._user_stopped = False
        self._end_badge_shown = False
        self._think_done = False
        self._reasoning_buf = ""
        self._think_start = 0.0
        self._last_activity = 0.0
        self._stalled_stop = False
        self._clear_attachments()
        while self.msg_lay.count() > 1:  # 保留末尾 stretch
            item = self.msg_lay.takeAt(0)
            self._free_layout_item(item)
        self._bubble_widgets = []   # 清空气泡引用，避免 resizeEvent 处理已删除对象
        self.token_label.setText("tokens: 0")
        # ---- 永久删除该对话，并新开空会话（界面回到欢迎页） ----
        self._delete_session(old_id)
        s = self._create_session()
        self._session_id = s["id"]
        self._session_name = "新对话"
        self._refresh_session_combo()
        self._update_welcome()
        self._add_status("已清空上下文并永久删除该对话", TEXT_DIM)

    # ---------- 拖拽附件（图片/文件） ----------
    _IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if p:
                self._add_attachment(p)
        e.acceptProposedAction()

    def _add_attachment(self, path: str):
        path = os.path.abspath(path)
        if not os.path.exists(path):
            self._add_status(f"文件不存在: {path}", WARN)
            return
        if os.path.splitext(path)[1].lower() in self._IMG_EXTS:
            img = QImage(path)
            if img.isNull():
                self._add_status(f"无法读取图片: {path}", WARN)
                return
            # 压缩为 ≤320px JPEG data URL 发送给模型（缩略图预览用原图）
            if img.width() > 320:
                img = img.scaledToWidth(320, Qt.TransformationMode.SmoothTransformation)
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "JPEG", 80)
            self._pending_images.append(
                "data:image/jpeg;base64," + base64.b64encode(bytes(ba)).decode())
            self._attach_thumb(QPixmap(path), path)
        else:
            self._pending_files.append(path)
            icon = QFileIconProvider().icon(QFileInfo(path)).pixmap(40, 40)
            self._attach_thumb(icon, path, name=os.path.basename(path))

    def _attach_thumb(self, pixmap: QPixmap, tooltip: str, name: str = ""):
        box = QWidget()
        box.setToolTip(tooltip)
        box.setStyleSheet(
            f"QWidget {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; }}")
        v = QVBoxLayout(box)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(3)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb = QLabel()
        thumb.setPixmap(pixmap.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        thumb.setToolTip(tooltip)
        v.addWidget(thumb, 0, Qt.AlignmentFlag.AlignCenter)
        if name:
            nl = QLabel(name if len(name) <= 12 else name[:11] + "…")
            nl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")
            nl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(nl, 0, Qt.AlignmentFlag.AlignCenter)
        # 插入到 stretch 之前
        self._attach_lay.insertWidget(self._attach_lay.count() - 1, box)
        self._attach_bar.setVisible(True)

    def _clear_attachments(self):
        while self._attach_lay.count() > 1:
            item = self._attach_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._pending_images = []
        self._pending_files = []
        self._attach_bar.setVisible(False)

    def _free_layout_item(self, item):
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            while item.layout().count():
                self._free_layout_item(item.layout().takeAt(0))
            item.layout().deleteLater()

    def _refresh_meta(self):
        """轮询刷新 tokens / 按钮反馈状态 / 卡死兜底"""
        if self._engine:
            t = self._engine.tokens
            self.token_label.setText(
                f"已用 {t['prompt'] + t['completion']} tokens "
                f"(输入 {t['prompt']} / 输出 {t['completion']})")
        running = bool(self._engine and self._engine._thread and self._engine._thread.is_alive())
        # 卡死兜底：任务进行中超过 60 秒无任何输出/状态 → 强制停止
        if running and self._last_activity and not self._stalled_stop \
                and time.time() - self._last_activity > 60:
            self._stalled_stop = True
            self._add_status("AI 长时间无响应（>60 秒），已自动停止（卡死兜底）", WARN)
            self._engine.stop()
        # 任务结束即清理：只要任务标志开启且线程已退出，就执行收尾
        # （不依赖 spinner/按钮状态判断，避免切换模式等路径下漏清理）
        if not running and self._task_active:
            self._task_active = False
            self.send_btn.setText("发送")
            self.send_btn.setEnabled(True)
            self.stop_btn.setText("停止")
            self.stop_btn.setEnabled(False)
            self._hide_spinner()
            self._stop_button_anim()
            if not self._end_badge_shown:
                self._end_badge_shown = True
                self._show_end_badge()
            self._persist_current()   # 任务结束即持久化当前会话（重启可恢复）
            self._scroll_bottom()   # 结束执行时自动滚动到最下方

    def _show_end_badge(self):
        """任务结束后在 AI 气泡外显示结果徽章"""
        if self._stalled_stop:
            self._add_badge("Error", ERR)
            return
        state = getattr(self._engine, "end_state", "") if self._engine else ""
        if self._user_stopped or state == "stopped":
            self._add_badge("Stop by user", WARN)
        elif state == "done":
            self._add_badge("Successfully", OK)
        else:   # error / max_rounds 视为异常
            self._add_badge("Error", ERR)

    # ---------- 引擎回调（信号槽，主线程） ----------
    def _ensure_text_segment(self):
        """正文段：末尾不是 text 段则新建，否则复用（操作与正文交织）"""
        if not self._segments or self._segments[-1]["type"] != "text":
            self._segments.append({"type": "text", "raw": ""})

    def _on_delta(self, s: str):
        self._finish_thinking()   # 开始输出正文即视为思考完成
        self._last_activity = time.time()
        self._ensure_ai_bubble()
        self._ensure_text_segment()
        self._segments[-1]["raw"] += s
        self._refresh_ai_html()
        self._scroll_bottom()

    def _on_result(self, name: str, text: str, images: list = None):
        """工具执行完成：输出文本与截图一并渲染进 AI 气泡（截图在'已截屏'字样下方，缩略图不挤压）"""
        self._last_activity = time.time()
        self._ensure_ai_bubble()
        shown = (text or "").strip()
        if len(shown) > 2000:
            shown = shown[:2000] + " …（输出过长已截断显示，完整内容已返回模型）"
        shown = _esc(shown).replace("\n", "<br/>")
        self._segments.append({"type": "result", "html": shown})
        # 截图段（screenshot/get_screen_size 工具结果或操作后自动验证截图）渲染进主对话气泡
        for u in images or []:
            self._segments.append({"type": "image", "url": u, "caption": "已截屏"})
        self._refresh_ai_html()
        self._scroll_bottom()

    def _on_status(self, s: str):
        self._last_activity = time.time()
        if s == "正在思考…":
            self._start_think()
        elif s.startswith("待执行工具:"):
            name = s.split(":", 1)[1].strip()
            self._ensure_ai_bubble()
            self._segments.append({"type": "op", "html": f"▎{_esc(name)}"})
            self._refresh_ai_html()
            self._scroll_bottom()
        elif s.startswith("正在执行:"):
            name = s.split(":", 1)[1].strip()
            self._ensure_ai_bubble()
            if self._segments and self._segments[-1]["type"] == "op":
                self._segments[-1]["html"] = f"▎{_esc(name)} …"
            else:
                self._segments.append({"type": "op", "html": f"▎{_esc(name)} …"})
            self._refresh_ai_html()
            self._scroll_bottom()
        elif s == "完成":
            self._hide_spinner()   # 任务结束，停掉转圈
        elif s in ("已停止", "已达到最大工具轮数，自动结束") or s.startswith("错误"):
            self._hide_spinner()
            self._ensure_ai_bubble()
            self._segments.append({"type": "mark", "html": _esc(s)})
            self._refresh_ai_html()
            self._scroll_bottom()

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

    # ---------- ask_user 提问（engine 线程 → 信号 → 主线程弹窗） ----------
    def _ask_user_tool(self, args: dict) -> str:
        """阻塞式提问：engine 线程等待主线程弹窗选择结果"""
        self._ask_evt.clear()
        self.ask_signal.emit(json.dumps(args, ensure_ascii=False))
        self._ask_evt.wait(timeout=600)
        return self._ask_result

    def _on_ask(self, args_json: str):
        try:
            args = json.loads(args_json)
        except json.JSONDecodeError:
            args = {}
        dlg = _AskUserDialog(str(args.get("question", "")),
                             list(args.get("options") or []),
                             bool(args.get("multi_select", False)), self)
        dlg.exec()
        self._ask_result = dlg.answer()
        self._ask_evt.set()

    # ---------- 设置 ----------
    # 模型/接口/API Key 已写死，无需设置对话框

    def closeEvent(self, event):
        if self._engine:
            self._engine.stop()
            self._engine.join(3)
        self._persist_current()   # 关闭前持久化当前会话（重启可恢复）
        try:
            self._mcp.close_all()
        except Exception:
            pass
        event.accept()
