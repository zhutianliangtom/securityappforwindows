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
    QStackedWidget, QMenu, QFileDialog, QPlainTextEdit, QSlider,
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


def _md_table_to_html(lines: list) -> str:
    """Markdown 表格行列表 → HTML 表格；非表格（无分隔行）返回空串"""
    rows = []
    for line in lines:
        body = line.strip()
        if body.startswith("|"):
            body = body[1:]
        if body.endswith("|"):
            body = body[:-1]
        rows.append([c.strip() for c in body.split("|")])
    if len(rows) < 2:
        return ""
    sep = rows[1]
    if not all(re.match(r"^:?-+:?$", c) for c in sep):
        return ""
    ncol = max(len(rows[0]), len(sep), max(len(r) for r in rows[2:])) if rows[2:] else \
        max(len(rows[0]), len(sep))
    th = ("border:1px solid #1E2A44;padding:4px 8px;background:#0B1220;"
          "color:#E6EDF7;font-weight:600;")
    td = "border:1px solid #1E2A44;padding:4px 8px;color:#C9D6EA;"
    out = ["<table style='border-collapse:collapse;margin:6px 0;font-size:13px;'>"]
    out.append("<tr>")
    for c in range(ncol):
        out.append(f"<th style='{th}'>{_inline_md(rows[0][c] if c < len(rows[0]) else '')}</th>")
    out.append("</tr>")
    for r in rows[2:]:
        out.append("<tr>")
        for c in range(ncol):
            out.append(f"<td style='{td}'>{_inline_md(r[c] if c < len(r) else '')}</td>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def _md_to_html(raw: str) -> str:
    """块级 Markdown → HTML：代码块、标题、列表、段落、表格"""
    lines = raw.split("\n")
    out = []
    in_code = False
    in_list = False
    code_buf = []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if s.startswith("```"):
            if in_code:
                out.append("<pre style='background:#0B1220;color:#E6EDF7;padding:8px;"
                           "border-radius:6px;font-family:Consolas;font-size:12px;"
                           f"border:1px solid #1E2A44;'>" + _esc("\n".join(code_buf)) + "</pre>")
                code_buf = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(lines[i])
            i += 1
            continue
        if not s:
            if in_list:
                out.append("</ul>")
                in_list = False
            i += 1
            continue
        # Markdown 表格：| 单元格 | ... + 分隔行 + 数据行
        if s.startswith("|") and s.count("|") >= 3:
            tbl = [s]
            i += 1
            while i < n and lines[i].strip().startswith("|"):
                tbl.append(lines[i].strip())
                i += 1
            table = _md_table_to_html(tbl)
            if table:
                if in_list:
                    out.append("</ul>")
                    in_list = False
                out.append(table)
            else:   # 不是表格，按普通段落逐行渲染
                if in_list:
                    out.append("</ul>")
                    in_list = False
                for ln in tbl:
                    out.append("<p style='margin:4px 0;'>" + _inline_md(ln) + "</p>")
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
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", s)
        if m:
            if in_list:
                out.append("</ul>")
                in_list = False
            lvl = len(m.group(1))
            out.append(f"<h{lvl} style='margin:8px 0 4px;color:#E6EDF7;"
                       f"font-size:{max(13, 20 - lvl)}px;'>{_inline_md(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if re.match(r"^[-*+]\s+", s) or re.match(r"^\d+[.)]\s+", s):
            if not in_list:
                out.append("<ul style='margin:4px 0;padding-left:18px;'>")
                in_list = True
            item = re.sub(r"^[-*+]\s+|^\d+[.)]\s+", "", s)
            out.append("<li>" + _inline_md(item) + "</li>")
            i += 1
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        out.append("<p style='margin:4px 0;'>" + _inline_md(s) + "</p>")
        i += 1
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


def _split_args(s: str) -> list:
    """按空格拆分命令行参数；引号包裹的空格路径视为单个参数（引号剥离、反斜杠保留）"""
    out, cur, quote = [], "", None
    for ch in s:
        if quote:
            if ch == quote:
                quote = None
            else:
                cur += ch
        elif ch in ('"', "'"):
            quote = ch
        elif ch.isspace():
            if cur:
                out.append(cur)
                cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


class _AgentSettingsDialog(QDialog):
    """AI 设置：自定义规则 / 系统提示词 / bash 白名单 / 记忆开关 / 模型接入"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 设置")
        self.setMinimumSize(560, 640)
        self.setStyleSheet(
            f"QDialog {{ background: {PANEL}; }}"
            f"QLabel {{ color: {TEXT}; font-size: 13px; }}"
            f"QLineEdit, QPlainTextEdit {{ background: {BG}; color: {TEXT};"
            f"border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 8px; }}")
        s = agent_skills.load_settings()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        def _lbl(text, bold=False):
            lb = QLabel(text)
            lb.setStyleSheet(f"color: {TEXT}; font-size: 13px;"
                             + ("font-weight: 700;" if bold else ""))
            return lb

        # 自定义规则
        root.addWidget(_lbl("自定义规则（每行一条，追加到系统提示词末尾）"))
        self.rules_edit = QPlainTextEdit()
        self.rules_edit.setPlaceholderText("如：\n操作注册表前必须先 ask_user 确认\n不要移动正在运行的应用")
        self.rules_edit.setPlainText("\n".join(str(r) for r in (s.get("custom_rules") or [])))
        self.rules_edit.setFixedHeight(72)
        root.addWidget(self.rules_edit)

        # 自定义系统提示词
        root.addWidget(_lbl("自定义系统提示词（追加，不覆盖默认人设）"))
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText("补充的提示词…")
        self.prompt_edit.setPlainText(str(s.get("custom_system_prompt") or ""))
        self.prompt_edit.setFixedHeight(84)
        root.addWidget(self.prompt_edit)

        # bash 白名单
        root.addWidget(_lbl("自定义 bash 命令白名单（每行一条，白名单命令免确认）"))
        self.safe_edit = QPlainTextEdit()
        self.safe_edit.setPlaceholderText("如：\nnpm\npip\npython\ngit")
        self.safe_edit.setPlainText(
            "\n".join(str(c) for c in (s.get("custom_safe_commands") or [])))
        self.safe_edit.setFixedHeight(72)
        root.addWidget(self.safe_edit)

        # 记忆开关
        self.memory_check = QCheckBox("开启长期记忆（save_memory / load_memory）")
        self.memory_check.setChecked(bool(s.get("memory_enabled", True)))
        self.memory_check.setStyleSheet(f"color: {TEXT}; font-size: 13px; spacing: 8px;")
        root.addWidget(self.memory_check)

        # 模型接入（同服务商多模型，按工作力度路由）
        root.addWidget(_lbl("模型接入（同服务商多模型；模型名含纯文本关键字如 deepseek "
                            "自动禁用图片/截图能力）", bold=True))
        m = s.get("model") or {}
        if not isinstance(m, dict):
            m = {}
        cfg = agent_llm.load_model_config()   # 规范化：models / effort / auto 等
        form = QFormLayout()
        form.setSpacing(8)
        self.base_edit = QLineEdit(str(m.get("base_url") or ""))
        self.base_edit.setPlaceholderText("https://api.example.com/v1（示例地址）")
        form.addRow("接口地址", self.base_edit)
        self.key_edit = QLineEdit(str(m.get("api_key") or ""))
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("sk-xxxxxxxx（示例，填写真实 Key）")
        form.addRow("API Key", self.key_edit)
        self.models_edit = QLineEdit(", ".join(cfg["models"]))
        self.models_edit.setPlaceholderText("模型名逗号分隔，如 deepseek-v4-pro, deepseek-v4-flash")
        form.addRow("模型列表", self.models_edit)
        self.protocol_combo = QComboBox()
        self.protocol_combo.setStyleSheet(
            f"QComboBox {{ background: {BG}; color: {TEXT};"
            f"border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 8px; }}")
        self.protocol_combo.addItem("Chat Completions（/v1/chat/completions）", "chat")
        self.protocol_combo.addItem("Responses API（/v1/responses）", "responses")
        pidx = self.protocol_combo.findData(cfg.get("protocol", "chat"))
        self.protocol_combo.setCurrentIndex(pidx if pidx >= 0 else 0)
        form.addRow("接口协议", self.protocol_combo)
        root.addLayout(form)

        # 推理参数（工作力度与自动按难度开关统一在面板左上角调整）
        self.send_effort_check = QCheckBox(
            "向 API 发送 reasoning_effort 参数（仅支持该参数的服务商开启，如 OpenAI o 系列 / Qwen）")
        self.send_effort_check.setStyleSheet(f"color: {TEXT}; font-size: 13px; spacing: 8px;")
        self.send_effort_check.setChecked(cfg.get("send_effort", False))
        root.addWidget(self.send_effort_check)

        btns = QHBoxLayout()
        ok = QPushButton(_std_icon(QStyle.StandardPixmap.SP_DialogYesButton), "保存")
        ok.setStyleSheet(f"background: {OK}; color: #06281B;")
        ok.setAutoDefault(False)
        ok.clicked.connect(self._save)
        cancel = QPushButton("取消")
        cancel.setStyleSheet(f"background: {PANEL}; color: {TEXT};"
                             f"border: 1px solid {BORDER};")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        root.addLayout(btns)

    def _save(self):
        base_url = self.base_edit.text().strip()
        api_key = self.key_edit.text().strip()
        models = [x.strip() for x in self.models_edit.text().replace("，", ",").split(",")
                  if x.strip()]
        if not models:
            models = [agent_llm.DEFAULT_MODEL]
        # 力度与自动按难度开关由面板左上角滑块持久化，设置页不覆盖；力度→模型用默认路由
        model = {
            "model": models[0],          # 兼容旧字段：主模型 = 首个
            "models": models,
            "send_effort": self.send_effort_check.isChecked(),
            "protocol": self.protocol_combo.currentData() or "chat",
        }
        if base_url:
            model["base_url"] = base_url
        if api_key:
            model["api_key"] = api_key
        data = {
            "custom_rules": [ln.strip() for ln in self.rules_edit.toPlainText().splitlines()
                             if ln.strip()],
            "custom_system_prompt": self.prompt_edit.toPlainText().strip(),
            "custom_safe_commands": [ln.strip() for ln in self.safe_edit.toPlainText().splitlines()
                                     if ln.strip()],
            "memory_enabled": self.memory_check.isChecked(),
            "model": model,
        }
        if agent_skills.save_settings(data):
            self.accept()
        else:
            QMessageBox.warning(self, "错误", "保存设置失败（无写入权限）")


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
            # 引号包裹的空格路径视为单个参数（剥离引号、保留反斜杠）
            args = [a for a in _split_args(self.args_edit.text()) if a.strip()]
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
            # 选择圆圈/复选框：未选中白色边框，选中填充强调色
            "QRadioButton::indicator, QCheckBox::indicator { width: 14px; height: 14px;"
            f" border: 1.5px solid #FFFFFF; background: transparent; }}"
            "QRadioButton::indicator { border-radius: 8px; }"
            "QCheckBox::indicator { border-radius: 3px; }"
            f"QRadioButton::indicator:checked, QCheckBox::indicator:checked {{"
            f" background: {ACCENT}; border-color: {ACCENT}; }}"
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
        # 用户设置：多模型/工作力度/纯文本模型自动识别、记忆开关
        _s = agent_skills.load_settings()
        self._model_cfg = agent_llm.load_model_config()   # 规范化多模型/力度路由配置
        self._effort = self._model_cfg.get("effort", "medium")
        self._auto_effort = bool(self._model_cfg.get("auto_effort", True))
        self._model_override = None      # 输入框右侧手动指定的模型（None=按力度路由）
        self._refresh_text_only()
        self._memory_enabled = bool(_s.get("memory_enabled", True))

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
        self._rows: list = []          # 用户消息与 AI 回复的交错顺序行（[{"type": "user"/"ai", ...}]，持久化保证重启顺序正确）
        self._scroll_pending = False   # 滚动调度去重标志
        self._bubble_widgets: list = []  # 所有气泡 QLabel（窗口缩放时同步宽度）
        self._maximized_once = False   # 首次显示即最大化（默认最大化展示）

        # 发送/停止按钮转圈动画
        self._send_anim_angle = 0
        self._stop_anim_angle = 0

        self._build_ui()
        self._sync_effort_ui()   # 把 settings 里的力度/自动开关同步到滑块与模型下拉
        self._connect_signals()
        self._restore_workdir()   # 恢复上次选择的工作目录（QSettings 持久化）
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

        # 顶栏：标题 + Agent/会话/模式 + MCP + tokens + 清空（随窗口宽度自适应，宽窗完整/窄窗紧凑）
        top = QHBoxLayout()
        top.setSpacing(8)
        self.title = QLabel("AI AGENT")
        self.title.setStyleSheet(f"color: {ACCENT}; font-size: 16px; font-weight: 800;")
        top.addWidget(self.title)

        # 会话选择：切换对话（上下文隔离）+ 新对话按钮
        self.session_combo = QComboBox()
        self.session_combo.setMinimumWidth(110)
        self.session_combo.setMaximumWidth(180)
        self.session_combo.currentIndexChanged.connect(self._on_session_selected)
        # 下拉列表右键菜单：删除对话
        self.session_combo.view().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.session_combo.view().customContextMenuRequested.connect(self._on_session_context_menu)
        top.addWidget(self.session_combo)

        self.new_btn = QPushButton(_std_icon(QStyle.StandardPixmap.SP_FileDialogNewFolder), "新")
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.setAutoDefault(False)
        self.new_btn.setToolTip("新对话")
        self.new_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; color: {ACCENT}; border: 1px solid {ACCENT};"
            "border-radius: 8px; padding: 6px 10px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #16233C; }}")
        self.new_btn.clicked.connect(self._new_session)
        top.addWidget(self.new_btn)

        # 工作目录：AI 的文件查找/创建/修改/删除/读取与命令优先在此目录执行
        # （选择后 QSettings 持久化，重启自动恢复）
        self.workdir_btn = QPushButton(_std_icon(QStyle.StandardPixmap.SP_DirOpenIcon), "选择工作目录")
        self.workdir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.workdir_btn.setAutoDefault(False)
        self.workdir_btn.setToolTip(
            "选择 AI 工作目录：文件查找/创建/修改/删除/读取与命令默认在此目录执行，重启后自动恢复")
        self.workdir_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};"
            "border-radius: 8px; padding: 6px 10px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}")
        self.workdir_btn.clicked.connect(self._choose_workdir)
        top.addWidget(self.workdir_btn)

        # 执行模式：AskBeforeEdit（每步确认）/ Edit（仅非白名单 bash 弹确认）/ YOLO（无确认）
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("每步确认", "ask")
        self.mode_combo.addItem("Edit 模式", "edit")
        self.mode_combo.addItem("无确认直行", "yolo")
        self.mode_combo.setMinimumWidth(110)
        self.mode_combo.setMaximumWidth(140)
        saved_mode = str(self._settings.value("agent_mode", "ask"))
        idx = self.mode_combo.findData(saved_mode)
        self.mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._mode = self.mode_combo.currentData()
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._apply_mode_style()
        top.addWidget(self.mode_combo)

        self.mcp_label = QLabel("MCP: 连接中…")
        self.mcp_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        self.mcp_label.setMaximumWidth(120)
        top.addWidget(self.mcp_label)

        self.mcp_btn = QPushButton(_std_icon(QStyle.StandardPixmap.SP_ComputerIcon), "MCP")
        self.mcp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mcp_btn.setAutoDefault(False)
        self.mcp_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; color: {ACCENT}; border: 1px solid {ACCENT};"
            "border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #16233C; }}")
        self.mcp_btn.clicked.connect(self._open_mcp_manager)
        top.addWidget(self.mcp_btn)

        self.settings_btn = QPushButton(_std_icon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "设置")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setAutoDefault(False)
        self.settings_btn.setToolTip("AI 设置：规则 / 系统提示词 / bash 白名单 / 记忆 / 模型接入")
        self.settings_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; color: {ACCENT}; border: 1px solid {ACCENT};"
            "border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #16233C; }}")
        self.settings_btn.clicked.connect(self._open_settings)
        top.addWidget(self.settings_btn)

        top.addStretch(1)

        self.token_label = QLabel("0 tk")
        self.token_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        self.token_label.setToolTip("已用 tokens")
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

        root.addLayout(top)

        # 工作力度行：拖动切换（low/medium/high/max/ultra）+ 自动按难度开关 + 当前路由模型
        effort_row = QHBoxLayout()
        effort_row.setSpacing(8)
        eff_lbl = QLabel("工作力度")
        eff_lbl.setStyleSheet(f"color: {TEXT}; font-size: 12px;")
        effort_row.addWidget(eff_lbl)
        self.effort_slider = QSlider(Qt.Orientation.Horizontal)
        self.effort_slider.setRange(0, len(agent_llm.EFFORTS) - 1)
        self.effort_slider.setFixedWidth(140)
        self.effort_slider.setPageStep(1)
        self.effort_slider.setToolTip("拖动切换工作力度（决定使用哪个模型）："
                                      + " / ".join(agent_llm.EFFORTS))
        self.effort_slider.valueChanged.connect(self._on_effort_changed)
        effort_row.addWidget(self.effort_slider)
        self.effort_label = QLabel("medium")
        self.effort_label.setStyleSheet(f"color: {ACCENT}; font-size: 12px; font-weight: 700;")
        self.effort_label.setFixedWidth(52)
        effort_row.addWidget(self.effort_label)
        self.auto_effort_check = QCheckBox("自动按难度")
        self.auto_effort_check.setStyleSheet(f"color: {TEXT}; font-size: 12px; spacing: 6px;")
        self.auto_effort_check.setToolTip("按任务难度自动选择工作力度（智能调用）；关闭后仅手动拖动")
        self.auto_effort_check.toggled.connect(self._on_effort_changed)
        effort_row.addWidget(self.auto_effort_check)
        self.route_model_label = QLabel("")
        self.route_model_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        effort_row.addWidget(self.route_model_label)
        effort_row.addStretch(1)
        root.addLayout(effort_row)

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

        # 命令提示条：输入 / 时展示可用 skill/命令（高度随显示条数自适应）
        self.cmd_list = QListWidget()
        self.cmd_list.setStyleSheet(
            f"QListWidget {{ background: {PANEL}; color: {ACCENT};"
            f"border: 1px solid {BORDER}; border-radius: 8px;"
            "font-size: 13px; padding: 4px; }}"
            f"QListWidget::item {{ padding: 2px 12px 4px 12px; border-radius: 6px; }}"
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
        self.input.textChanged.connect(self._refresh_route_label)
        # 内联预测：输入 /com 时半透明显示 /compact 完成部分
        self._completer = QCompleter(self._all_commands(), self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.InlineCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.input.setCompleter(self._completer)
        bottom.addWidget(self.input, 1)

        # 输入框右侧：手动切换本次使用的模型（选「自动」则按工作力度路由）
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(150)
        self.model_combo.setMaximumWidth(230)
        self.model_combo.setStyleSheet(
            f"QComboBox {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};"
            "border-radius: 10px; padding: 6px 10px; font-size: 12px; }}"
            f"QComboBox::drop-down {{ border: none; width: 22px; }}"
            f"QComboBox QAbstractItemView {{ background: {PANEL}; color: {TEXT};"
            "border: 1px solid #4B6BD6; selection-background-color: #16233C; }}")
        self.model_combo.setToolTip("手动切换本次使用的模型；「自动」= 按工作力度路由")
        self.model_combo.currentIndexChanged.connect(self._on_model_combo)
        bottom.addWidget(self.model_combo)

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
        has_msg = bool(self._segments or self._history_segments or self._user_msgs)
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
            # 完整对话流 = 历史段（含 split 边界）+ 当前回复段；过滤“已停止”提示小字
            clean_segments = [
                seg for seg in (self._history_segments + self._segments)
                if not (seg.get("type") == "mark" and seg.get("html") == "已停止")
            ]
            # 交错行（用户/AI 顺序）优先使用内存维护值；旧会话无 rows 时按段流重建，
            # 未归档的当前回复段作为最后一个 AI 行追加
            rows = [dict(r, segs=[s for s in r.get("segs") or []
                                  if not (s.get("type") == "mark" and s.get("html") == "已停止")])
                    if r.get("type") == "ai" else r
                    for r in (self._rows or self._reconstruct_rows())]
            if self._segments and not (rows and rows[-1].get("type") == "ai"):
                rows.append({"type": "ai", "segs": [
                    s for s in self._segments
                    if not (s.get("type") == "mark" and s.get("html") == "已停止")]})
            with open(d / f"{self._session_id}.ui.json", "w", encoding="utf-8") as f:
                json.dump({"segments": clean_segments, "user_msgs": self._user_msgs,
                           "rows": rows}, f, ensure_ascii=False)
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
        self._history_segments = []
        self._user_msgs = []
        self._rows = []
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
        self._user_msgs = ums
        # 交错行：新版文件直接使用持久化顺序；旧版文件（无 rows）置空，稍后按段流重建
        self._rows = [r for r in (data.get("rows") or [])
                      if isinstance(r, dict) and r.get("type") in ("user", "ai")]
        # 加载时过滤掉旧版本中持久化的“已停止”提示小字，避免重启后仍显示
        self._history_segments = [
            seg for seg in (segs or [])
            if not (seg.get("type") == "mark" and seg.get("html") == "已停止")
        ]
        self._segments = []
        # 旧版文件无 rows：按段流重建交错行，保证本会话后续持久化不回退
        if not self._rows:
            self._rows = self._reconstruct_rows()
        self._render_history_all()   # 用户气泡与 AI 回复按轮次交错重绘（每条 AI 回复一个气泡）
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
        self._history_segments = []
        self._user_msgs = []
        self._rows = []
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
        elif self._mode == "edit":
            self._add_status("Edit 模式：仅非白名单 bash 命令弹确认，其余操作直接执行", OK)
        else:
            self._add_status("AskBeforeEdit 模式：每步操作弹窗确认", OK)

    # ---------- 工作目录（QSettings 持久化，重启恢复） ----------
    def _restore_workdir(self):
        """启动时恢复上次选择的工作目录；无有效目录则显示默认提示"""
        saved = str(self._settings.value("agent_workdir", ""))
        if saved and os.path.isdir(saved):
            self._apply_workdir(saved)
        else:
            self._apply_workdir("")

    def _choose_workdir(self):
        """弹出目录选择框，设置 AI 工作目录并持久化"""
        start = agent_tools.get_workdir() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "选择 AI 工作目录", start)
        if not d:
            return
        self._apply_workdir(d)
        self._settings.setValue("agent_workdir", d)
        self._add_status(f"工作目录已设置为 {d}，AI 的文件/搜索/命令将优先在此目录执行", OK)

    def _apply_workdir(self, d: str):
        """应用工作目录：写入 agent_tools 全局 + 更新按钮文本"""
        agent_tools.set_workdir(d)
        if d:
            name = os.path.basename(d.rstrip("\\/")) or d
            self.workdir_btn.setText(f"📁 {name}"[:24])
        else:
            self.workdir_btn.setText("选择工作目录")
        self.workdir_btn.setToolTip(d or "选择 AI 工作目录")

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

    def _bubble_min_width(self) -> int:
        """聊天气泡最小宽度：全屏时至少覆盖半页宽（不超过最大宽度）"""
        return min(self._bubble_max_width(), int(self.width() * 0.5))

    def _topbar_wide(self) -> bool:
        """窗口足够宽（≥1100px）时顶栏显示完整文案，否则紧凑防挤压"""
        return self.width() >= 1100

    def _apply_topbar_layout(self):
        """顶部工具栏随窗口宽度自适应：宽窗口显示完整文字，窄窗口紧凑"""
        wide = self._topbar_wide()
        self.new_btn.setText("新对话" if wide else "新")
        self.mcp_btn.setText("MCP 管理" if wide else "MCP")
        self.mcp_label.setMaximumWidth(1200 if wide else 120)
        # MCP 状态：完整或截断（截断逻辑与 _on_mcp_status 保持一致）
        full = getattr(self, "_mcp_full", "MCP: 连接中…")
        self.mcp_label.setText(full if wide else (full[:10] + "…" if len(full) > 10 else full))
        if wide:
            self.session_combo.setMinimumWidth(180)
            self.session_combo.setMaximumWidth(260)
            self.workdir_btn.setMaximumWidth(300)
            self.mode_combo.setMinimumWidth(190)
            self.mode_combo.setMaximumWidth(240)
            self.mode_combo.setItemText(0, "AskBeforeEdit（每步确认）")
            self.mode_combo.setItemText(1, "Edit（仅 bash 需确认）")
            self.mode_combo.setItemText(2, "YOLO（无确认直行）")
        else:
            self.session_combo.setMinimumWidth(110)
            self.session_combo.setMaximumWidth(180)
            self.workdir_btn.setMaximumWidth(180)
            self.mode_combo.setMinimumWidth(110)
            self.mode_combo.setMaximumWidth(140)
            self.mode_combo.setItemText(0, "每步确认")
            self.mode_combo.setItemText(1, "Edit")
            self.mode_combo.setItemText(2, "无确认直行")
        self._refresh_meta()   # token 文本按当前模式重渲染

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_topbar_layout()
        mw = self._bubble_max_width()
        mn = self._bubble_min_width()
        s = self._font_scale()
        for b in self._bubble_widgets:
            try:
                b.setMaximumWidth(mw)
                # 仅 AI 气泡保持半页最小宽度；用户气泡按内容自适应
                if b.property("align") == "ai":
                    b.setMinimumWidth(mn)
                else:
                    b.setMinimumWidth(0)
                src = b.property("rich_src")   # 用户富文本气泡（含图片）随全屏放大
                if src:
                    b.setText(self._scale_user_html(src, s))
            except RuntimeError:
                pass
        # AI 气泡随全屏缩放重渲染文本（按分组顺序对应，不重建布局避免 resize 卡顿）
        ai_bubbles = [b for b in self._bubble_widgets
                      if b.property("align") == "ai" and self._bubble_alive(b)]
        for b, g in zip(ai_bubbles, self._split_groups()):
            try:
                b.setText(self._build_ai_html(g))
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
        # 仅 AI 气泡设最小宽度（让截图/内容覆盖半页）；用户气泡按内容自适应，避免短句异常拉长
        if align == "ai":
            bubble.setMinimumWidth(self._bubble_min_width())
        bubble.setProperty("align", align)
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

    def _font_scale(self) -> float:
        """全屏/非全屏字体始终保持原 5 号大小（14px），不随窗口缩放"""
        return 1.0

    def _scale_user_html(self, src: str, s: float) -> str:
        """把用户气泡原始富文本按缩放系数放大（字号 14px、图片 200px）"""
        return src.replace("font-size:14px", f"font-size:{int(14 * s)}px") \
                  .replace('width="200"', f'width="{int(200 * s)}"')

    def _build_ai_html(self, segs: list) -> str:
        """把一组 AI 段渲染为富文本（思考/操作/结果/截图/正文/标记）"""
        s = self._font_scale()
        f_main, f_dim, f_sm, f_op = int(14 * s), int(12 * s), int(11 * s), int(13 * s)
        img_w = max(200, int(self._bubble_max_width() * 0.4))   # 截图缩略图随气泡宽度放大（约占内容区半宽）
        parts = []
        for seg in segs:
            t = seg["type"]
            if t == "think":
                parts.append(f'<div style="color:{TEXT_DIM};font-size:{f_sm}px;font-style:italic;">'
                             f'{seg["html"]}</div>')
            elif t == "op":
                parts.append(f'<div style="color:{ACCENT};font-size:{f_op}px;'
                             f'font-family:Consolas;margin-top:16px;">{seg["html"]}</div>')
            elif t == "result":
                parts.append(f'<div style="color:{TEXT_DIM};font-size:{f_op}px;font-family:Consolas;'
                             f'border-left:3px solid {BORDER};padding:2px 10px;'
                             'margin:16px 0 4px 14px;">'
                             f'{seg["html"]}</div>')
            elif t == "image":
                # 截图融入主对话气泡：下方缩略图，不显示“已截屏”等提示小字
                url = seg.get("url", "")
                parts.append(
                    f'<div style="padding-left:30px;">'
                    f'<img src="{url}" width="{img_w}" style="border-radius:8px;display:block;'
                    'margin:12px 0 12px 0;"></div>')
            elif t == "text":
                parts.append(f'<div style="color:{TEXT};font-size:{f_main}px;">'
                             f'{_render_text(seg["raw"])}</div>')
            elif t == "mark":
                parts.append(f'<div style="color:{TEXT_DIM};font-size:{f_sm}px;">{seg["html"]}</div>')
        return "".join(parts)

    def _segments_full(self) -> list:
        """完整对话流 = 历史段（含 split 边界）+ 当前回复段"""
        return self._history_segments + self._segments

    def _split_groups(self) -> list:
        """按 split 边界把完整段流切分为「每条 AI 回复一组」"""
        groups, cur = [], []
        for seg in self._segments_full():
            if seg["type"] == "split":
                if cur:
                    groups.append(cur)
                    cur = []
            else:
                cur.append(seg)
        if cur:
            groups.append(cur)
        return groups

    def _reconstruct_rows(self) -> list:
        """旧版会话（无 rows 字段）回退重建显示顺序。

        按段流分组得到 AI 回复组；若会话末尾不是 split（最后一条消息的回复未归档），
        说明最后一条消息必有回复 → 最后一条消息配最后一组，其余前向配对，
        避免 user_msgs 与 AI 组数量错位导致用户消息被排到 AI 回复下方；否则直接前向配对。
        """
        groups = self._split_groups()
        n, q = len(self._user_msgs), len(groups)
        full = self._segments_full()
        tail_has_reply = bool(full) and full[-1].get("type") != "split"
        rows = []
        if q and n and tail_has_reply:
            for i, u in enumerate(self._user_msgs[:-1]):
                rows.append({"type": "user", "text": u})
                if i < q - 1:
                    rows.append({"type": "ai", "segs": groups[i]})
            rows.append({"type": "user", "text": self._user_msgs[-1]})
            rows.append({"type": "ai", "segs": groups[-1]})
        else:
            for i, u in enumerate(self._user_msgs):
                rows.append({"type": "user", "text": u})
                if i < q:
                    rows.append({"type": "ai", "segs": groups[i]})
            for g in groups[n:]:
                rows.append({"type": "ai", "segs": g})
        return rows

    def _render_history_all(self):
        """全量重建消息流：按持久化交错行渲染（加载会话/全屏缩放时调用），
        用户消息与 AI 回复天然成对，杜绝数量错位导致的顺序错乱"""
        while self.msg_lay.count() > 1:   # 清空消息流（保留末尾 stretch）
            item = self.msg_lay.takeAt(0)
            self._free_layout_item(item)
        self._bubble_widgets = []
        self._ai_bubble = None
        for r in (self._rows or self._reconstruct_rows()):
            if r.get("type") == "user":
                self._add_bubble(r.get("text", ""), "user")
            else:
                self._add_ai_group_bubble(r.get("segs") or [])
        # 未归档的当前回复段（渲染时恒为空，防御保留）
        if self._segments:
            self._add_ai_group_bubble(self._segments)

    def _add_ai_group_bubble(self, segs: list):
        """把一组 AI 段渲染为一条独立气泡，并设为当前气泡（新回复流式续接）"""
        b = self._add_bubble("", "ai")
        try:
            b.setText(self._build_ai_html(segs))
        except RuntimeError:
            pass
        self._ai_bubble = b

    def _refresh_ai_html(self):
        """只更新当前（流式）AI 气泡内容，用于思考/操作/正文逐段追加"""
        if self._ai_bubble is None:
            return
        try:
            self._ai_bubble.setText(self._build_ai_html(self._segments))
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
        self._reasoning_lbl.setMaximumWidth(self._bubble_max_width())
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
        self._mcp_full = text   # 保存完整文本，由 _apply_topbar_layout 按窗口宽度决定完整/截断
        self.mcp_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._apply_topbar_layout()

    def _open_mcp_manager(self):
        """打开 MCP 服务器配置面板；保存后后台重连"""
        dlg = _McpManagerDialog(on_saved=self._reconnect_mcp, parent=self)
        dlg.exec()

    def _open_settings(self):
        """打开 AI 设置；保存后应用（刷新纯文本/记忆状态，空闲时重建引擎）"""
        dlg = _AgentSettingsDialog(parent=self)
        if dlg.exec():
            self._apply_agent_settings()
            self._add_status("AI 设置已保存并生效", OK)

    def _apply_agent_settings(self):
        """设置变更后：刷新多模型/力度/纯文本状态；引擎空闲则重建以应用新配置"""
        s = agent_skills.load_settings()
        self._model_cfg = agent_llm.load_model_config()
        self._effort = self._model_cfg.get("effort", "medium")
        self._auto_effort = bool(self._model_cfg.get("auto_effort", True))
        self._refresh_text_only()
        self._memory_enabled = bool(s.get("memory_enabled", True))
        self._sync_effort_ui()
        if self._text_only:
            self._add_status("纯文本模型：已禁用图片上传与截图工具", WARN)
        if self._engine is not None:
            busy = self._engine._thread and self._engine._thread.is_alive()
            if busy:
                self._add_status("当前有任务进行中，新设置将在任务结束后生效", WARN)
                return
            self._engine = None   # 空闲：丢弃旧引擎，重建应用新模型/开关
        self._ensure_engine()

    # ---------- 工作力度 / 模型路由 ----------
    def _refresh_text_only(self):
        """纯文本模型识别：全部已配置模型均为纯文本时才全局禁用视觉（
        混配模型时按本次实际使用的模型逐次判断，见 _send）"""
        cfg = self._model_cfg
        models = cfg.get("models") or [cfg.get("model") or agent_llm.DEFAULT_MODEL]
        self._text_only = all(agent_llm.is_text_only_model(x) for x in models)

    def _on_effort_changed(self, *_):
        """力度滑块/自动开关变更：刷新标签与路由显示，持久化力度与开关"""
        self._effort = agent_llm.EFFORTS[self.effort_slider.value()]
        self.effort_label.setText(self._effort)
        self._sync_model_combo()   # 重建输入框右侧模型下拉
        self._refresh_route_label()
        s = agent_skills.load_settings()
        m = dict(s.get("model") or {})
        m["effort"] = self._effort
        m["auto_effort"] = self.auto_effort_check.isChecked()
        s["model"] = m
        agent_skills.save_settings(s)

    def _sync_effort_ui(self):
        """把 settings 里的力度/自动开关同步到控件（初始化/设置保存后调用）"""
        idx = agent_llm.EFFORTS.index(self._effort)
        self.effort_slider.blockSignals(True)
        self.effort_slider.setValue(idx)
        self.effort_slider.blockSignals(False)
        self.auto_effort_check.blockSignals(True)
        self.auto_effort_check.setChecked(self._auto_effort)
        self.auto_effort_check.blockSignals(False)
        self.effort_label.setText(self._effort)
        self._sync_model_combo()   # 初始化/设置保存后重建输入框右侧模型下拉
        self._refresh_route_label()

    def _resolve_effort(self, text: str) -> str:
        """本次任务使用的工作力度：自动开关开启时按任务难度估算，否则用手动力度"""
        if self._auto_effort:
            return agent_llm.estimate_effort(text)
        return self._effort

    def _refresh_route_label(self, *_):
        """显示当前路由模型（手动指定显示指定模型；自动模式随输入实时估算）"""
        cfg = self._model_cfg
        if self._model_override:
            self.route_model_label.setText(f"模型: {self._model_override}")
            return
        effort = self._resolve_effort(self.input.text())
        model = agent_llm.resolve_model(cfg, effort)
        tag = "自动·" if self._auto_effort else ""
        self.route_model_label.setText(f"{tag}模型: {model}")
        # 输入框右侧下拉首项同步显示当前路由模型（仅自动模式）
        if not self._model_override and self.model_combo.count():
            self.model_combo.setItemText(0, f"自动 · {model}")

    def _sync_model_combo(self, routed: str = None):
        """重建输入框右侧模型下拉：首项「自动(按力度)」+ 全部模型名"""
        cfg = self._model_cfg
        models = cfg.get("models") or [cfg.get("model") or agent_llm.DEFAULT_MODEL]
        routed = routed or agent_llm.resolve_model(cfg, self._resolve_effort(self.input.text()))
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItem(f"自动 · {routed}", None)
        for x in models:
            self.model_combo.addItem(x, x)
        if self._model_override:
            idx = self.model_combo.findData(self._model_override)
            if idx < 0:      # 手动指定模型已不在列表：清除覆盖回到自动路由
                self._model_override = None
                idx = 0
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setCurrentIndex(0)
        self.model_combo.blockSignals(False)

    def _on_model_combo(self, idx):
        """手动切换模型：选中具体模型则本次发送使用之；选「自动」回到力度路由"""
        if idx < 0:
            return
        val = self.model_combo.itemData(idx)
        self._model_override = val if val else None
        self._refresh_route_label()

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
        """解析 /技能名 [提示]：按技能名匹配，返回 (技能dict, 提示文本)；未匹配返回 (None, "")"""
        if not text.startswith("/"):
            return None, ""
        parts = text[1:].split(None, 1)
        if not parts:
            return None, ""
        q = parts[0].strip().lower()
        for s in agent_skills.load_skills():
            if s.get("name", "").strip().lower() == q:
                return s, (parts[1].strip() if len(parts) > 1 else "")
        return None, ""

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
        # 空 "/" 时禁用内联补全（禁止预测 /compact），输入字符后恢复
        if text == "/":
            if self.input.completer() is not None:
                self.input.setCompleter(None)
        elif self.input.completer() is None:
            self.input.setCompleter(self._completer)
        # 输入 "/" 时展示全部可调用项（系统命令 + 全部技能 + 全部内置工具）；否则按前缀过滤
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
                self._resize_cmd_list()
                self.cmd_list.show()
                return
        self.cmd_list.hide()

    def _resize_cmd_list(self):
        """命令列表高度随显示条数自适应：最多 5 行，最少 1 行"""
        count = self.cmd_list.count()
        row_h = self.cmd_list.sizeHintForRow(0)
        if row_h <= 0:
            row_h = 26   # 兜底：13px 字体 + item 内边距
        self.cmd_list.setFixedHeight(min(count, 5) * row_h)

    def _on_cmd_selected(self, item):
        self.input.setText(item.text())
        self.input.setFocus()
        self.cmd_list.hide()

    # ---------- 发送 / 停止 ----------
    def _llm_config(self) -> dict:
        # 多模型/接口/API Key 从 settings.json 读取（含同服务商多模型与力度路由）
        return self._model_cfg

    def _ensure_engine(self):
        """复用同一引擎：保留跨任务对话上下文"""
        if self._engine is None:
            cfg = self._llm_config()
            client = agent_llm.LLMClient(
                base_url=cfg.get("base_url"), api_key=cfg.get("api_key"),
                model=cfg.get("model"), protocol=cfg.get("protocol", "chat"))
            self._engine = agent_engine.AgentEngine(
                client,
                mcp_manager=self._mcp,
                on_delta=lambda s: self.delta_signal.emit(s),
                on_status=lambda s: self.status_signal.emit(s),
                on_result=lambda n, t, im: self.result_signal.emit(n, t, im),
                on_reasoning=lambda s: self.reasoning_signal.emit(s),
                confirm=self._confirm_tool,
                ask_user=self._ask_user_tool,
                text_only=self._text_only,
                memory_enabled=self._memory_enabled)
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
        ai_text = text                       # 传给 AI 的文本（默认=原文）；原文用于用户气泡显示
        skill_names = []
        # 手动调用内置技能：/技能名 [提示] → 技能 instruction 注入本次系统提示词，提示作为用户消息
        skill, skill_prompt = self._match_skill(text)
        if skill:
            self._add_status(f"已调用技能「{skill.get('name')}」", ACCENT)
            skill_names = [skill.get("name")]
            ai_text = skill_prompt or f"请严格按技能「{skill.get('name')}」的流程执行。"
        # 手动指定工具：/工具名 [参数] → 转成指令由 AI 调用对应工具
        tool = self._match_tool(text)
        shot = None
        if tool:
            tname, targs = tool
            self._add_status(f"已指定工具「{tname}」", ACCENT)
            if tname == "screenshot":
                # 手动截屏：面板直接截图并展示（不依赖 AI 调用工具，保证必定出图）
                try:
                    shot = agent_screen.capture_screen_data_url(grid=False)   # 展示用干净原图
                    ai_text = "已截取当前屏幕并展示在对话中，请基于截图内容回答或继续执行。"
                except Exception:
                    shot = None
            else:
                ai_text = (f"请调用工具「{tname}」完成以下任务，参数必须按 JSON 传入。\n"
                           f"工具参数说明：{self._tool_params_hint(tname)}\n"
                           f"参数原始文本：{targs or '(无，可自行确定合理参数，不确定时先 ask_user 澄清)'}")
        # 非图片附件：把路径文本附加给 AI（不显示源内容），AI 可按需 read_file
        if files:
            note = "以下为拖入的附件文件，请按需读取内容：\n" + \
                "\n".join(f"- {p}" for p in files)
            ai_text = (ai_text + "\n\n" if ai_text else "") + note
        # 工作力度 → 模型路由：自动按任务难度估算（开关开启）或用手动力度；输入框右侧可手动指定
        effort = self._resolve_effort(ai_text)
        cfg = self._llm_config()
        model = self._model_override or agent_llm.resolve_model(cfg, effort)
        engine = self._ensure_engine()
        engine.llm.model = model
        engine.llm.reasoning_effort = (agent_llm.reasoning_effort_for(effort)
                                       if cfg.get("send_effort") else None)
        engine.text_only = agent_llm.is_text_only_model(model)
        self._auto_name_session(ai_text)   # 无名称会话：用首条消息自动命名
        # 归档上一轮 AI 回复到历史（须在追加新用户消息前完成，保证交错行顺序正确）
        if self._segments:
            self._history_segments.extend(self._segments)
            self._history_segments.append({"type": "split"})
            self._rows.append({"type": "ai", "segs": list(self._segments)})
        self._ai_bubble = None
        self._segments = []
        self._user_msgs.append(text)
        self._rows.append({"type": "user", "text": text})
        self._update_welcome()          # 发消息后欢迎介绍立即消失

        # 用户气泡：文字与拖拽图片一并渲染进同一气泡（图片缩小缩略图、独立成块，不挤压不窜位）
        if images:
            src = ("<br/>".join(
                ([f'<div style="font-size:14px;">{_esc(text).replace(chr(10), "<br/>")}</div>']
                 if text else []) +
                [f'<img src="{u}" width="200" style="border-radius:8px;display:block;'
                 'margin:12px 0 12px 0;">' for u in images]))
            b = self._add_bubble(self._scale_user_html(src, self._font_scale()),
                                 "user", rich=True)
            b.setProperty("rich_src", src)   # 存未缩放原文，窗口全屏时按缩放系数重渲染
        else:
            self._add_bubble(text, "user")
        # 手动截屏：截图段进 AI 气泡（缩略图融入主对话气泡，不额外显示提示小字）
        send_images = list(images)
        if shot:
            # 喂给模型时带坐标网格（精确点击定位），展示用干净原图
            send_images.append(agent_screen.capture_screen_data_url(grid=True))
        # 本次路由的模型为纯文本时剥离图片（混配模型场景逐次判断）
        if engine.text_only and send_images:
            self._add_status("当前模型为纯文本模型，已忽略图片输入", WARN)
            send_images = []
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
        self.token_label.setText(f"~{est} tk")

        self.send_btn.setText("发送中…")
        self.send_btn.setEnabled(False)
        self.stop_btn.setText("停止")
        self.stop_btn.setEnabled(True)
        self._start_send_anim()   # 发送按钮转圈动画

        self._clear_attachments()   # 发送后清空附件条
        self._task_active = True
        engine.start(ai_text, "桌面助手", send_images, skills=skill_names)

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

    def _on_session_context_menu(self, pos):
        """对话下拉列表右键菜单：提供删除对话入口"""
        view = self.session_combo.view()
        idx = view.indexAt(pos)
        if not idx.isValid():
            return
        sid = self.session_combo.itemData(idx.row())
        if not sid:
            return
        name = self.session_combo.itemText(idx.row())
        orig = self.session_combo.currentIndex()   # 记录原索引，防止 popup 关闭误切换对话
        menu = QMenu(self)
        del_act = menu.addAction(f"删除对话「{name}」")
        act = menu.exec(view.viewport().mapToGlobal(pos))
        # 菜单/下拉关闭时 QComboBox 会把高亮项同步为当前项，误触发 _on_session_selected：
        # 屏蔽信号恢复原索引，避免右键一下却切进了被点的对话
        if self.session_combo.currentIndex() != orig:
            self.session_combo.blockSignals(True)
            self.session_combo.setCurrentIndex(orig)
            self.session_combo.blockSignals(False)
        if act == del_act:
            self._remove_session(sid, name)

    def _remove_session(self, sid: str, name: str):
        """右键删除对话：确认后删除文件；若删除的是当前对话则清理并切到最近对话/新建"""
        if not self._confirm_box("永久删除对话",
                                 f"确定永久删除对话「{name}」吗？\n所有记录将无法恢复！"):
            return
        self._delete_session(sid)
        if sid == self._session_id:
            # 删除当前对话：停止引擎并清理内存（_session_id 先置空，防止切会话时复活文件）
            if self._engine:
                self._engine.clear_history()
                self._engine.clear_context()
                if self._engine._thread and self._engine._thread.is_alive():
                    self._engine.stop()
            self._session_id = None
            self._segments = []
            self._user_msgs = []
            self._ai_bubble = None
            self._bubble_widgets = []
            self._hide_spinner()
            self._stop_button_anim()
            self._task_active = False
            self._user_stopped = False
            self._end_badge_shown = False
            self._clear_attachments()
            self.cmd_list.hide()
            while self.msg_lay.count() > 1:
                item = self.msg_lay.takeAt(0)
                self._free_layout_item(item)
            lst = self._load_session_list()
            if lst:
                lst.sort(key=lambda s: s.get("updated", 0))
                self._switch_to(lst[-1]["id"])
            else:
                self._new_session()
        else:
            self._refresh_session_combo()
        self._add_status(f"已删除对话「{name}」", TEXT_DIM)

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
        self._history_segments = []
        self._user_msgs = []
        self._rows = []
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
        self.token_label.setText("0 tk")
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
        if self._text_only and os.path.splitext(path)[1].lower() in self._IMG_EXTS:
            self._add_status("当前为纯文本模型，不支持图片输入，已忽略", WARN)
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
            used = t['prompt'] + t['completion']
            if self._topbar_wide():
                cache_txt = f" · 缓存命中 {t['cache_hit']}" if t.get('cache_hit') else ""
                self.token_label.setText(
                    f"已用 {used} tokens（输入 {t['prompt']} / 输出 {t['completion']}{cache_txt}）")
            else:
                self.token_label.setText(f"{used} tk")
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

    def _stop_send_spin(self):
        """AI 开始响应/执行后停止发送按钮转圈（任务中保持禁用，不再一直转圈误导）"""
        if self._send_anim.isActive():
            self._send_anim.stop()
            self.send_btn.setIcon(_std_icon(QStyle.StandardPixmap.SP_ArrowUp))
            self.send_btn.setText("发送")

    def _on_delta(self, s: str):
        self._finish_thinking()   # 开始输出正文即视为思考完成
        self._stop_send_spin()
        self._last_activity = time.time()
        self._ensure_ai_bubble()
        self._ensure_text_segment()
        self._segments[-1]["raw"] += s
        self._refresh_ai_html()
        self._scroll_bottom()

    def _on_result(self, name: str, text: str, images: list = None):
        """工具执行完成：输出文本与截图一并渲染进 AI 气泡（截图以缩略图独立成块，不挤压）"""
        self._stop_send_spin()
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
        self._stop_send_spin()
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
        elif s == "已达到最大工具轮数，自动结束" or s.startswith("错误"):
            self._hide_spinner()
            self._ensure_ai_bubble()
            self._segments.append({"type": "mark", "html": _esc(s)})
            self._refresh_ai_html()
            self._scroll_bottom()
        elif s == "已停止" or "已停止" in s:
            self._hide_spinner()   # 用户手动停止/包含“已停止”字样的状态均不输出小字

    # ---------- 每步确认（engine 线程调用 → 信号 → 主线程弹窗） ----------
    def _confirm_tool(self, name: str, args: dict) -> bool:
        level, reason = agent_sandbox.assess_tool(name, args)
        if self._mode == "yolo":
            # YOLO 无人工确认，危险命令（删除/关机等）一律拒绝，保证安全底线
            return level != "dangerous"
        if self._mode == "edit":
            # Edit 模式：仅非白名单 bash 命令弹确认；白名单命令与其他工具直接执行
            if name != "run_command" or level == "safe":
                return True
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
