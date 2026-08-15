"""zhuzhu Copilot 工具面板（深色"星际控制台"风格，无 emoji，矢量图标）

消息气泡（TRAE 风格，单气泡一体化）：
- AI 气泡内依次渲染：思考过程 → 操作步骤 → 最终文本输出，均在同一气泡内
- 用户消息靠右（青色）、AI 消息靠左（深色卡片）
- 上下文：engine 复用保留跨任务对话历史（截图仅保留最近 2 张防膨胀），可一键清空
- 反馈：发送中/停止中按钮状态 + "思考中"点号动画 + tokens 实时统计
- 每步确认：AskBeforeEdit 弹窗确认（确认后危险命令可执行）；YOLO 无确认、危险命令一律拒绝
- MCP / skills / agents：从 ~/.winapp_migrator/agent/*.json 加载
"""

import base64
import ctypes
import html as _html
import json
import math
import os
import re
import sys
import threading
import time
import uuid
import webbrowser
from pathlib import Path

from PyQt6.QtCore import (Qt, QTimer, QSettings, QPropertyAnimation, pyqtSignal, QThread,
                          pyqtProperty, QEasingCurve, QByteArray, QBuffer, QIODevice,
                          QEvent, QRect, QRectF, QSize, QPoint, QPointF, QMimeData, QUrl,
                          QAbstractNativeEventFilter)
from PyQt6.QtGui import (QIcon, QFont, QPainter, QPen, QColor, QPixmap, QImage,
                         QPainterPath, QKeySequence, QTextOption,
                         QDragEnterEvent, QDragMoveEvent, QDropEvent, QCursor)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QDialog, QLabel, QLineEdit, QPushButton, QComboBox, QScrollArea,
    QVBoxLayout, QHBoxLayout, QMessageBox, QFormLayout, QWidget,
    QApplication, QStyle, QListWidget, QGraphicsOpacityEffect,
    QRadioButton, QCheckBox, QListWidgetItem,
    QStackedWidget, QMenu, QFileDialog, QPlainTextEdit, QSlider,
    QLayout, QWidgetItem, QInputDialog, QFrame, QStyledItemDelegate,
    QSizePolicy,
)

from winapp_migrator.core import agent_llm, agent_engine, agent_skills, agent_sandbox, agent_tools, agent_screen, agent_tts
from winapp_migrator.core.agent_mcp import McpManager
from winapp_migrator.ui.widgets import add_brand_footer
from winapp_migrator.utils.helpers import is_admin

# ---------- 深色极简主题（纯黑 / 淡黑 / 白 / 深蓝） ----------
BG = "#000000"            # 纯黑（窗口底色）
BG_BOTTOM = "#0A0A0A"     # 窗口底色渐变收尾（淡黑）
PANEL = "#141414"         # 淡黑（面板/输入框底色）
CARD = "#1E1E1E"          # 淡黑亮一档（卡片/气泡底色）
BORDER = "#000000"        # 边框（纯黑，融入背景）
BORDER_SOFT = "#000000"   # 边框（纯黑）
TEXT = "#F5F5F5"          # 白（主文本）
TEXT_DIM = "#8A8A8A"      # 灰（次要文本）
ACCENT = "#1E40AF"        # 深蓝（强调）
ACCENT_HOVER = "#2563EB"  # 深蓝悬停
LINK_COLOR = "#3B82F6"    # 可点击链接（蓝）
USER_BG = "#1E40AF"       # 用户气泡/发送按钮底色（深蓝）
AI_BG = "#1E1E1E"         # AI 气泡底色（淡黑）
OK = "#34D399"
WARN = "#FBBF24"
ERR = "#F87171"
HOVER = "#262626"         # 幽灵按钮 hover 背景（淡黑亮）

# 面板级控件样式（统一控件语言，避免各处内联重复）
_BTN_GHOST = (f"QPushButton {{ background: transparent; color: {TEXT_DIM};"
              f"border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 12px;"
              f"font-size: 12px; font-weight: 600; }}"
              f"QPushButton:hover {{ border-color: {ACCENT_HOVER}; color: {TEXT};"
              f"background: {HOVER}; }}")
_BTN_GHOST_ACCENT = (f"QPushButton {{ background: transparent; color: {ACCENT_HOVER};"
                     f"border: 1px solid {BORDER_SOFT}; border-radius: 8px;"
                     f"padding: 6px 12px; font-size: 12px; font-weight: 600; }}"
                     f"QPushButton:hover {{ border-color: {ACCENT_HOVER}; background: {HOVER}; }}")
_BTN_PRIMARY = (f"QPushButton {{ background: {ACCENT}; color: #FFFFFF; border: none;"
                f"border-radius: 10px; padding: 0 16px; font-size: 13px; font-weight: 700; }}"
                f"QPushButton:hover {{ background: {ACCENT_HOVER}; }}"
                f"QPushButton:disabled {{ background: {CARD}; color: {TEXT_DIM}; }}")
# 灰蓝：输入框为空时的发送按钮（弱化提示，有内容后切换深蓝 _BTN_PRIMARY）
_BTN_DIM = (f"QPushButton {{ background: #46536B; color: #A9B6CC; border: none;"
            f"border-radius: 10px; padding: 0 16px; font-size: 13px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: #53617C; }}"
            f"QPushButton:disabled {{ background: {CARD}; color: {TEXT_DIM}; }}")
_QCOMBO = (f"QComboBox {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};"
           f"border-radius: 8px; padding: 5px 10px; font-size: 12px; }}"
           f"QComboBox::drop-down {{ border: none; width: 22px; }}"
           f"QComboBox QAbstractItemView {{ background: {PANEL}; color: {TEXT};"
           f"border: 1px solid {BORDER}; selection-background-color: {HOVER};"
           f"selection-color: {TEXT}; }}")
# 纯图标按钮（淡灰线条矢量图标，无文字）
_BTN_ICON = (f"QPushButton {{ background: transparent; border: 1px solid {BORDER};"
             f"border-radius: 8px; }}"
             f"QPushButton:hover {{ background: {HOVER}; border-color: {BORDER_SOFT}; }}")
_BTN_DANGER = (f"QPushButton {{ background: {ERR}; color: #FFFFFF; border: none;"
               f"border-radius: 10px; padding: 0; }}"
               f"QPushButton:hover {{ background: #EF4444; }}"
               f"QPushButton:disabled {{ background: {CARD}; color: {TEXT_DIM}; }}")


def _app_icon_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", "."), "assets", "icon.ico")
    return str(Path(__file__).resolve().parents[3] / "assets" / "icon.ico")


def _dark_titlebar(widget) -> None:
    """把 Windows 系统标题栏设为深色（暗色标题栏 + 纯黑标题栏/边框），与面板纯黑风格统一"""
    try:
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        on = ctypes.c_int(1)
        # DWMWA_USE_IMMERSIVE_DARK_MODE=20（Win10 1903+ / Win11）
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
        black = ctypes.c_int(0x000000)
        # DWMWA_BORDER_COLOR=34 / DWMWA_CAPTION_COLOR=35（Win11 22H2+，旧系统失败自动忽略）
        for attr in (34, 35):
            try:
                dwm.DwmSetWindowAttribute(hwnd, attr,
                                          ctypes.byref(black), ctypes.sizeof(black))
            except Exception:
                pass
    except Exception:
        pass


# 统一给所有 QDialog 子类深色标题栏（AgentPanel 等自实现 showEvent 经 super() 同样生效）
_orig_dialog_show = QDialog.showEvent


def _dialog_show(self, e):
    _orig_dialog_show(self, e)
    _dark_titlebar(self)


QDialog.showEvent = _dialog_show


def _std_icon(sp) -> QIcon:
    """系统矢量图标（无 emoji）"""
    return QApplication.style().standardIcon(sp)


# 齿轮（设置）：Lucide 开源简约线条矢量图（stroke 用 {color} 占位，由 _svg_icon 着色）
_GEAR_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
             'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
             '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08'
             'a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74'
             'l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25'
             'a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25'
             'a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74'
             'v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08'
             'a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>'
             '<circle cx="12" cy="12" r="3"/></svg>')


def _svg_icon(svg: str, size: int = 18, color: str = TEXT_DIM) -> QIcon:
    """渲染内联 SVG 线条矢量图标（开源矢量路径，统一着色，线条风格一致）"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    try:
        r = QSvgRenderer(svg.replace("{color}", color).encode("utf-8"))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r.render(p)
        p.end()
    except Exception:
        pass
    return QIcon(pm)


def _line_icon(kind: str, size: int = 18, color: str = TEXT_DIM) -> QIcon:
    """淡灰色线条简约矢量图标（QPainter 手绘，统一线条风格，不依赖系统图标/emoji）"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    s = float(size)
    if kind == "send":          # 上箭头（发送）
        p.drawLine(QPointF(s * 0.5, s * 0.20), QPointF(s * 0.5, s * 0.80))
        p.drawLine(QPointF(s * 0.26, s * 0.46), QPointF(s * 0.5, s * 0.20))
        p.drawLine(QPointF(s * 0.74, s * 0.46), QPointF(s * 0.5, s * 0.20))
    elif kind == "stop":        # 实心方块（停止）
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        r = s * 0.28
        p.drawRoundedRect(QRectF(s * 0.5 - r, s * 0.5 - r, r * 2, r * 2),
                          s * 0.08, s * 0.08)
    elif kind == "trash":       # 垃圾桶（清空）
        p.drawLine(QPointF(s * 0.22, s * 0.28), QPointF(s * 0.78, s * 0.28))
        p.drawLine(QPointF(s * 0.36, s * 0.28), QPointF(s * 0.36, s * 0.19))
        p.drawLine(QPointF(s * 0.64, s * 0.28), QPointF(s * 0.64, s * 0.19))
        p.drawLine(QPointF(s * 0.40, s * 0.19), QPointF(s * 0.60, s * 0.19))
        p.drawLine(QPointF(s * 0.31, s * 0.34), QPointF(s * 0.36, s * 0.80))
        p.drawLine(QPointF(s * 0.69, s * 0.34), QPointF(s * 0.64, s * 0.80))
        p.drawLine(QPointF(s * 0.36, s * 0.80), QPointF(s * 0.64, s * 0.80))
        p.drawLine(QPointF(s * 0.45, s * 0.40), QPointF(s * 0.46, s * 0.70))
        p.drawLine(QPointF(s * 0.58, s * 0.40), QPointF(s * 0.57, s * 0.70))
    elif kind == "new":         # 新建对话（圆角框 + 加号）
        p.drawRoundedRect(QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64),
                          s * 0.14, s * 0.14)
        p.drawLine(QPointF(s * 0.5, s * 0.32), QPointF(s * 0.5, s * 0.68))
        p.drawLine(QPointF(s * 0.32, s * 0.5), QPointF(s * 0.68, s * 0.5))
    elif kind == "plus":        # 加号（上传附件，精确居中）
        p.drawLine(QPointF(s * 0.5, s * 0.26), QPointF(s * 0.5, s * 0.74))
        p.drawLine(QPointF(s * 0.26, s * 0.5), QPointF(s * 0.74, s * 0.5))
    elif kind == "ok":          # 对勾（保存/确定）
        p.setPen(QPen(QColor(color), 2.2, cap=Qt.PenCapStyle.RoundCap,
                      join=Qt.PenJoinStyle.RoundJoin))
        p.drawLine(QPointF(s * 0.24, s * 0.52), QPointF(s * 0.44, s * 0.72))
        p.drawLine(QPointF(s * 0.44, s * 0.72), QPointF(s * 0.78, s * 0.30))
    elif kind == "no":          # 叉（拒绝）
        p.drawLine(QPointF(s * 0.28, s * 0.28), QPointF(s * 0.72, s * 0.72))
        p.drawLine(QPointF(s * 0.72, s * 0.28), QPointF(s * 0.28, s * 0.72))
    elif kind == "drive":       # 硬盘（通用与记忆）
        p.drawRoundedRect(QRectF(s * 0.16, s * 0.28, s * 0.68, s * 0.44),
                          s * 0.06, s * 0.06)
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(s * 0.32, s * 0.50), s * 0.05, s * 0.05)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(s * 0.44, s * 0.50), QPointF(s * 0.78, s * 0.50))
    elif kind == "list":        # 列表（自定义规则）
        p.drawLine(QPointF(s * 0.22, s * 0.30), QPointF(s * 0.78, s * 0.30))
        p.drawLine(QPointF(s * 0.22, s * 0.50), QPointF(s * 0.78, s * 0.50))
        p.drawLine(QPointF(s * 0.22, s * 0.70), QPointF(s * 0.78, s * 0.70))
    elif kind == "doc":         # 文档（系统提示词）
        p.drawRoundedRect(QRectF(s * 0.22, s * 0.16, s * 0.56, s * 0.68),
                          s * 0.06, s * 0.06)
        p.drawLine(QPointF(s * 0.34, s * 0.36), QPointF(s * 0.66, s * 0.36))
        p.drawLine(QPointF(s * 0.34, s * 0.50), QPointF(s * 0.66, s * 0.50))
        p.drawLine(QPointF(s * 0.34, s * 0.64), QPointF(s * 0.56, s * 0.64))
    elif kind == "bash":        # 终端（bash 白名单）
        p.drawRoundedRect(QRectF(s * 0.16, s * 0.24, s * 0.68, s * 0.52),
                          s * 0.07, s * 0.07)
        p.drawLine(QPointF(s * 0.28, s * 0.40), QPointF(s * 0.40, s * 0.50))
        p.drawLine(QPointF(s * 0.28, s * 0.60), QPointF(s * 0.40, s * 0.50))
        p.drawLine(QPointF(s * 0.48, s * 0.56), QPointF(s * 0.72, s * 0.56))
    elif kind == "net":         # 网络（模型接入）
        p.drawEllipse(QPointF(s * 0.5, s * 0.28), s * 0.10, s * 0.10)
        p.drawArc(QRectF(s * 0.22, s * 0.28, s * 0.56, s * 0.52), 0, 180 * 16)
        p.drawArc(QRectF(s * 0.32, s * 0.28, s * 0.36, s * 0.34), 0, 180 * 16)
    elif kind == "folder":      # 文件夹（技能/浏览）
        p.drawRoundedRect(QRectF(s * 0.16, s * 0.32, s * 0.68, s * 0.46),
                          s * 0.05, s * 0.05)
        p.drawLine(QPointF(s * 0.16, s * 0.42), QPointF(s * 0.42, s * 0.42))
        p.drawLine(QPointF(s * 0.46, s * 0.42), QPointF(s * 0.52, s * 0.32))
        p.drawLine(QPointF(s * 0.84, s * 0.36), QPointF(s * 0.84, s * 0.32))
        p.drawLine(QPointF(s * 0.84, s * 0.32), QPointF(s * 0.76, s * 0.32))
    elif kind == "server":      # 服务器（MCP）
        p.drawRoundedRect(QRectF(s * 0.18, s * 0.20, s * 0.64, s * 0.24),
                          s * 0.05, s * 0.05)
        p.drawRoundedRect(QRectF(s * 0.18, s * 0.56, s * 0.64, s * 0.24),
                          s * 0.05, s * 0.05)
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(s * 0.30, s * 0.32), s * 0.04, s * 0.04)
        p.drawEllipse(QPointF(s * 0.30, s * 0.68), s * 0.04, s * 0.04)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(s * 0.44, s * 0.32), QPointF(s * 0.72, s * 0.32))
        p.drawLine(QPointF(s * 0.44, s * 0.68), QPointF(s * 0.72, s * 0.68))
    elif kind == "mic":       # 麦克风（语音合成音色）
        p.drawRoundedRect(QRectF(s * 0.38, s * 0.14, s * 0.24, s * 0.44), s * 0.06, s * 0.06)
        p.drawLine(QPointF(s * 0.38, s * 0.52), QPointF(s * 0.62, s * 0.52))
        p.drawLine(QPointF(s * 0.38, s * 0.72), QPointF(s * 0.62, s * 0.72))
        p.drawLine(QPointF(s * 0.50, s * 0.52), QPointF(s * 0.50, s * 0.72))
        p.drawArc(QRectF(s * 0.34, s * 0.54, s * 0.32, s * 0.30), 0, 180 * 16)
    p.end()
    return QIcon(pm)


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


def _linkify(s: str) -> str:
    """把（已转义的）文本中的裸 URL / Windows 路径转为蓝色可点击链接。
    文件路径统一用 file:/// 前缀，便于 _on_bubble_link 识别后 os.startfile 打开。"""
    pattern = re.compile(
        r"(?<![\"'\w])("
        r"https?://[^\s<>\"']+|"          # 裸 URL
        r"[A-Za-z]:[\\/][^\s<>\"']*|"     # 盘符绝对路径 C:\... / C:/...
        r"\\\\[^\s<>\"']*"                # UNC 路径 \\server\share
        r")")
    # URL 尾部非法字符（全角标点、中文文本等），ASCII URL 字符白名单
    _tail = re.compile(r"[^A-Za-z0-9/_\-?=&.%#:@+~]+$")

    def _to(m):
        token = m.group(1)
        if token.startswith(("http://", "https://")):
            token = _tail.sub("", token)
            href = token
        elif token.startswith("file://"):
            href = token
        else:
            token = token.rstrip(".,;:!)]}，。；：！？】\"'")
            href = "file:///" + token.replace("\\", "/")
        return (f'<a href="{href}" style="color:{LINK_COLOR};'
                f'text-decoration:underline;">{token}</a>')
    return pattern.sub(_to, s)


def _inline_md(s: str) -> str:
    """行内样式：数学公式 $...$、`code`、**bold**、[text](url)、裸 URL/文件路径"""
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
               r"<code style='background:#141414;color:#60A5FA;padding:1px 5px;"
               r"border-radius:4px;font-family:Consolas;'>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    # [text](url) 先占位，避免其 href/文字被 _linkify 二次加工
    links = {}

    def _cap_link(m):
        idx = f"\x00L{len(links)}\x00"
        links[idx] = (f'<a href="{m.group(2)}" style="color:{LINK_COLOR};'
                      f'text-decoration:underline;">{m.group(1)}</a>')
        return idx
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", _cap_link, s)
    s = _linkify(s)
    for idx, html in links.items():
        s = s.replace(idx, html)
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
    th = ("border:1px solid #2A2A2A;padding:4px 8px;background:#1E1E1E;"
          "color:#F5F5F5;font-weight:600;")
    td = "border:1px solid #2A2A2A;padding:4px 8px;color:#B8B8B8;"
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
                out.append("<pre style='background:#141414;color:#F5F5F5;padding:8px;"
                           "border-radius:6px;font-family:Consolas;font-size:12px;"
                           f"border:1px solid #2A2A2A;'>" + _esc("\n".join(code_buf)) + "</pre>")
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
            out.append(f"<h{lvl} style='margin:8px 0 4px;color:#F5F5F5;"
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
        out.append("<pre style='background:#141414;color:#F5F5F5;padding:8px;"
                   "border-radius:6px;font-family:Consolas;font-size:12px;"
                   f"border:1px solid #2A2A2A;'>" + _esc("\n".join(code_buf)) + "</pre>")
    if in_list:
        out.append("</ul>")
    return "".join(out)


def _render_text(raw: str) -> str:
    """AI 正文渲染：Markdown 解析；流式中代码块未闭合时回退为纯文本"""
    if raw.count("```") % 2 == 1:
        return _linkify(_esc(raw)).replace("\n", "<br/>")
    return _md_to_html(raw)


def _split_md_blocks(raw: str) -> list:
    """把 markdown 文本切成渲染块：代码块整体为一块（可跨空行），
    其余以空行分界。流式输出时只有尾部块会增长，前面的块内容恒定 →
    可按块内容做增量渲染缓存（key 即块字符串）。"""
    blocks, buf, in_code = [], [], False
    for line in raw.split("\n"):
        if in_code:
            buf.append(line)
            if line.strip().startswith("```"):
                blocks.append("\n".join(buf))
                buf, in_code = [], False
            continue
        if line.strip().startswith("```"):
            if buf:
                blocks.append("\n".join(buf))
                buf = []
            buf.append(line)
            in_code = True
            continue
        if not line.strip():
            if buf:
                blocks.append("\n".join(buf))
                buf = []
            continue
        buf.append(line)
    if buf:
        blocks.append("\n".join(buf))
    return blocks


def _render_text_incr(raw: str, cache: dict) -> str:
    """增量渲染：按块缓存已渲染 HTML，只重算增长的尾部块。
    长文本流式时避免每次对整段全量 markdown 重渲染（单次 O(n)、累计 O(n²) 卡顿）。
    输出与 _render_text(整段) 一致：未闭合代码块时直接退化为完整渲染。"""
    if raw.count("```") % 2 == 1:
        return _render_text(raw)
    parts = []
    for b in _split_md_blocks(raw):
        h = cache.get(b)
        if h is None:
            h = _render_text(b)
            cache[b] = h
            if len(cache) > 200:   # 块缓存容量上限（按插入序保留最近 100 项）
                for _k in list(cache)[: len(cache) - 100]:
                    del cache[_k]
        parts.append(h)
    return "".join(parts)


def _seg_sig(seg: dict) -> tuple:
    """段内容签名（用于渲染缓存命中判断）：只取能影响渲染结果的字段，
    流式追加只改尾部 -> O(1) 签名，避免每 tick 对全段做昂贵重渲染"""
    t = seg["type"]
    if t == "text":
        raw = seg["raw"]
        return (t, len(raw), raw[-64:])
    if t == "think":
        h = seg.get("html", "")
        return (t, bool(seg.get("collapsed")), len(h), h[-64:])
    if t == "result":
        return (t, bool(seg.get("collapsed")), seg["html"])
    if t == "progress":
        return (t, seg.get("pct"), seg.get("text"))
    if t == "image":
        return (t, seg.get("url"))
    if t == "sub":
        raw = seg.get("raw", "")
        return (t, seg.get("title"), len(raw), raw[-64:])
    if t in ("op", "mark"):
        return (t, seg["html"])
    return (t,)


class _TypingDots(QWidget):
    """任务执行中 AI 气泡下方的打字指示器动画（iMessage 风格：三点依次弹起，
    相位错开 1/3 循环，随消息流滚动，无 emoji）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 16)
        self._phase = 0.0      # 循环相位 0→1（每点激活时刻错开 1/3）
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(35)

    def _tick(self):
        self._phase += 0.045
        if self._phase >= 1.0:
            self._phase -= 1.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ACCENT))
        for i in range(3):
            # 相位错开 1/3：三点从左到右依次"弹起放大再回落"，形成打字节奏
            t = (self._phase - i / 3.0) % 1.0
            amp = max(0.0, math.sin(t * math.pi))   # t=0.5 时最大
            r = 2.2 + 2.8 * amp                     # 半径随节奏放大
            p.setOpacity((90 + 165 * amp) / 255)    # 同步淡入淡出
            p.drawEllipse(QPointF(5 + i * 13, 8), r, r)
        p.setOpacity(1.0)
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
            from PyQt6.QtGui import QApplication, QPixmap
            # 轻量截屏：直接 grabWindow 取位图再缩放显示。
            # 不走 capture_screen_data_url()（PrintWindow/全屏 PNG 编码 + base64
            # + 坐标网格叠加，高分辨率屏在 UI 线程耗时可达数百毫秒，确认弹窗卡顿）
            pix = QApplication.primaryScreen().grabWindow(0)
            pic_label.setPixmap(
                pix.scaledToWidth(500, Qt.TransformationMode.SmoothTransformation))
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
        add_brand_footer(self)

    def _allow(self, *_):
        self.result_ok = True
        self.accept()

    def _deny(self, *_):
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
    """AI 设置：左侧导航 + 右侧分组设置（通用记忆 / 规则 / 提示词 / bash / 模型 / 技能 / MCP）"""

    # 极简配色：纯黑 / 淡黑 / 白 / 深蓝
    _BG = "#000000"
    _PANEL = "#141414"
    _PANEL2 = "#1E1E1E"
    _TEXT = "#F5F5F5"
    _DIM = "#8A8A8A"
    _ACCENT = "#1E40AF"
    _ACCENT_HOVER = "#2563EB"
    _DANGER = "#DC2626"
    _DANGER_HOVER = "#EF4444"
    _BORDER = "#000000"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 设置")
        self.setMinimumSize(840, 620)
        self.resize(880, 660)
        self.setStyleSheet(
            f"QDialog {{ background: {self._BG}; }}"
            f"QLabel {{ color: {self._TEXT}; font-size: 13px; }}"
            f"QLineEdit, QPlainTextEdit, QComboBox {{ background: {self._PANEL};"
            f"color: {self._TEXT}; border: 1px solid {self._BORDER};"
            "border-radius: 6px; padding: 6px 10px; }}"
            f"QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{"
            f"border: 1px solid {self._ACCENT}; }}"
            f"QComboBox QAbstractItemView {{ background: {self._PANEL};"
            f"color: {self._TEXT}; border: 1px solid {self._BORDER};"
            f"selection-background-color: {self._PANEL2}; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 8px; }}"
            f"QScrollBar::handle:vertical {{ background: {self._BORDER};"
            "border-radius: 4px; min-height: 30px; }}")
        s = agent_skills.load_settings()
        self._mcp_servers = agent_skills.load_mcp_servers()

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------- 左侧导航栏（矢量图标 + 文字） ----------
        self.nav = QListWidget()
        self.nav.setFixedWidth(176)
        self.nav.setStyleSheet(
            f"QListWidget {{ background: {self._PANEL}; border: none;"
            "padding-top: 10px; outline: none; }}"
            f"QListWidget::item {{ color: {self._DIM}; padding: 12px 14px;"
            "font-size: 13px; font-weight: 600; border: none;"
            f"border-left: 3px solid transparent; }}"
            f"QListWidget::item:hover {{ background: {self._PANEL2};"
            f"color: {self._TEXT}; }}"
            f"QListWidget::item:selected {{ background: {self._PANEL2};"
            f"color: {self._ACCENT_HOVER};"
            f"border-left: 3px solid {self._ACCENT_HOVER}; }}")
        for name, kind in (
            ("通用与记忆", "drive"),
            ("自定义规则", "list"),
            ("系统提示词", "doc"),
            ("bash 白名单", "bash"),
            ("模型接入", "net"),
            ("技能", "folder"),
            ("MCP 服务器", "server"),
            ("语音合成", "mic"),
        ):
            self.nav.addItem(QListWidgetItem(_line_icon(kind, 16), name))
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._switch_page)
        root.addWidget(self.nav)

        # ---------- 右侧设置项（堆叠切换） ----------
        right = QVBoxLayout()
        right.setContentsMargins(24, 20, 24, 16)
        right.setSpacing(12)
        self.stack = QStackedWidget()
        for page in (self._build_general_page(s),
                     self._build_rules_page(s),
                     self._build_prompt_page(s),
                     self._build_bash_page(s),
                     self._build_model_page(s),
                     self._build_skill_page(),
                     self._build_mcp_page(),
                     self._build_tts_page()):
            self.stack.addWidget(page)
        right.addWidget(self.stack, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        save = QPushButton(_std_icon(QStyle.StandardPixmap.SP_DialogYesButton), "保存")
        save.setStyleSheet(f"background: {self._ACCENT}; color: #FFFFFF;"
                           "border: none; border-radius: 8px; padding: 8px 28px;"
                           "font-size: 13px; font-weight: 700;")
        save.setAutoDefault(False)
        save.clicked.connect(self._save)
        cancel = QPushButton("取消")
        cancel.setStyleSheet(f"background: {self._PANEL}; color: {self._TEXT};"
                             f"border: 1px solid {self._BORDER}; border-radius: 8px;"
                             "padding: 8px 24px; font-size: 13px; font-weight: 600;")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        btns.addWidget(save)
        btns.addWidget(cancel)
        right.addLayout(btns)
        root.addLayout(right)

        self._reload_mcp_list()

    # ---------- 各分组页面 ----------
    def _page(self, title: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        t = QLabel(title)
        t.setStyleSheet(f"color: {self._TEXT}; font-size: 16px; font-weight: 700;")
        lay.addWidget(t)
        return w

    def _page_body(self, w: QWidget) -> QVBoxLayout:
        return w.layout()

    def _build_general_page(self, s) -> QWidget:
        w = self._page("通用与记忆")
        lay = self._page_body(w)
        self.memory_check = QCheckBox("开启长期记忆（save_memory / load_memory）")
        self.memory_check.setChecked(bool(s.get("memory_enabled", True)))
        self.memory_check.setStyleSheet(f"color: {self._TEXT}; font-size: 13px; spacing: 8px;")
        lay.addWidget(self.memory_check)
        # 隐藏主程序窗口：开启后本窗口（主界面）隐藏，仅显示 AI 面板；重启应用也直接进 AI 面板
        self.hide_main_check = QCheckBox("隐藏主程序窗口，仅显示 AI 面板")
        self.hide_main_check.setChecked(self._hide_main_enabled())
        self.hide_main_check.setStyleSheet(f"color: {self._TEXT}; font-size: 13px; spacing: 8px;")
        self.hide_main_check.toggled.connect(self._on_hide_main_toggled)
        lay.addWidget(self.hide_main_check)
        # 执行模式：AskBeforeEdit / Edit / YOLO（原面板顶栏下拉，迁入设置页）
        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        mode_lbl = QLabel("执行模式")
        mode_lbl.setStyleSheet(f"color: {self._TEXT}; font-size: 13px;")
        mode_lbl.setFixedWidth(70)
        mode_row.addWidget(mode_lbl)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("AskBeforeEdit（每步操作确认）", "ask")
        self.mode_combo.addItem("Edit（仅非白名单 bash 命令确认）", "edit")
        self.mode_combo.addItem("YOLO（无确认直行，危险命令一律拒绝）", "yolo")
        saved_mode = QSettings("WinAppMigrator", "WinAppMigrator").value("agent_mode", "ask")
        mi = self.mode_combo.findData(saved_mode)
        self.mode_combo.setCurrentIndex(mi if mi >= 0 else 0)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_combo, 1)
        lay.addLayout(mode_row)
        # 工作目录：AI 的文件查找/创建/修改/删除/读取与命令优先在此目录执行
        wd_row = QHBoxLayout()
        wd_row.setSpacing(10)
        wd_lbl = QLabel("工作目录")
        wd_lbl.setStyleSheet(f"color: {self._TEXT}; font-size: 13px;")
        wd_lbl.setFixedWidth(70)
        wd_row.addWidget(wd_lbl)
        self.workdir_edit = QLineEdit()
        self.workdir_edit.setPlaceholderText("留空使用默认目录；AI 的文件与命令默认在此执行")
        self.workdir_edit.setText(str(QSettings("WinAppMigrator", "WinAppMigrator")
                                      .value("agent_workdir", "")))
        wd_row.addWidget(self.workdir_edit, 1)
        browse = QPushButton(_line_icon("folder", 16), "浏览…")
        browse.setStyleSheet(f"background: {self._PANEL}; color: {self._TEXT};"
                             f"border: 1px solid {self._BORDER}; border-radius: 8px;"
                             "padding: 6px 14px; font-weight: 600;")
        browse.setAutoDefault(False)
        browse.setToolTip("选择 AI 工作目录，重启后自动恢复")
        browse.clicked.connect(self._browse_workdir)
        wd_row.addWidget(browse)
        lay.addLayout(wd_row)
        tip = QLabel("记忆：AI 可将重要信息写入 memory.md 并在后续任务中读取。")
        tip.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
        lay.addWidget(tip)
        lay.addStretch(1)
        return w

    # ---------- 隐藏主程序窗口 ----------
    def _hide_main_enabled(self) -> bool:
        return str(QSettings("WinAppMigrator", "WinAppMigrator")
                   .value("hide_main_window", "0")).strip().lower() in ("1", "true", "yes")

    def _main_window(self):
        # 本对话框 parent=AgentPanel，AgentPanel 的 parent=MainWindow
        panel = self.parent()
        return panel.parent() if panel is not None else None

    def _on_hide_main_toggled(self, checked: bool):
        """切换时立即持久化并隐藏/显示主程序窗口"""
        QSettings("WinAppMigrator", "WinAppMigrator").setValue(
            "hide_main_window", "1" if checked else "0")
        mw = self._main_window()
        if mw is None:
            return
        if checked:
            mw.hide()
        else:
            mw.show()
            mw.raise_()
            mw.activateWindow()

    def _build_rules_page(self, s) -> QWidget:
        w = self._page("自定义规则")
        lay = self._page_body(w)
        sub = QLabel("每行一条，追加到系统提示词末尾，约束 AI 行为")
        sub.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
        lay.addWidget(sub)
        self.rules_edit = QPlainTextEdit()
        self.rules_edit.setPlaceholderText("如：\n操作注册表前必须先 ask_user 确认\n不要移动正在运行的应用")
        self.rules_edit.setPlainText("\n".join(str(r) for r in (s.get("custom_rules") or [])))
        lay.addWidget(self.rules_edit, 1)
        return w

    def _build_prompt_page(self, s) -> QWidget:
        w = self._page("系统提示词")
        lay = self._page_body(w)
        sub = QLabel("追加到默认人设之后，不覆盖内置角色设定")
        sub.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
        lay.addWidget(sub)
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText("补充的提示词…")
        self.prompt_edit.setPlainText(str(s.get("custom_system_prompt") or ""))
        lay.addWidget(self.prompt_edit, 1)
        return w

    def _build_bash_page(self, s) -> QWidget:
        w = self._page("bash 命令白名单")
        lay = self._page_body(w)
        sub = QLabel("每行一条；白名单命令执行时免确认（其余命令仍按当前模式处理）")
        sub.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
        lay.addWidget(sub)
        self.safe_edit = QPlainTextEdit()
        self.safe_edit.setPlaceholderText("如：\nnpm\npip\npython\ngit")
        self.safe_edit.setPlainText(
            "\n".join(str(c) for c in (s.get("custom_safe_commands") or [])))
        lay.addWidget(self.safe_edit, 1)
        return w

    def _build_model_page(self, s) -> QWidget:
        w = self._page("模型接入")
        lay = self._page_body(w)
        sub = QLabel("多服务商模型：每个服务商一张卡片，点击卡片编辑其地址/Key/模型；"
                    "全部服务商模型统一参与路由与切换，模型名含纯文本关键字（如 deepseek）"
                    "自动禁用图片/截图能力")
        sub.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        m = s.get("model") or {}
        if not isinstance(m, dict):
            m = {}
        cfg = agent_llm.load_model_config()
        self._providers = list(cfg.get("providers") or [])
        # 服务商卡片列表
        self.provider_list = QListWidget()
        self.provider_list.setStyleSheet(
            f"QListWidget {{ background: {self._PANEL}; color: {self._TEXT};"
            f"border: 1px solid {self._BORDER}; border-radius: 8px; padding: 6px; }}"
            f"QListWidget::item {{ border-radius: 8px; margin: 2px; }}"
            f"QListWidget::item:selected {{ background: {self._PANEL2}; }}")
        self.provider_list.itemClicked.connect(self._on_provider_select)
        self.provider_list.itemDoubleClicked.connect(self._on_provider_edit)
        self.provider_list.itemSelectionChanged.connect(self._update_provider_ui)
        lay.addWidget(self.provider_list, 1)
        self._reload_provider_list()
        # 服务商操作按钮
        prow = QHBoxLayout()
        prow.setSpacing(8)
        add_p = QPushButton(_std_icon(QStyle.StandardPixmap.SP_FileDialogNewFolder), "添加服务商")
        add_p.setStyleSheet(f"background: {self._ACCENT}; color: #FFFFFF; border: none;"
                            "border-radius: 8px; padding: 7px 16px; font-weight: 700;")
        add_p.setAutoDefault(False)
        add_p.clicked.connect(self._on_provider_add)
        self.del_provider_btn = QPushButton(_line_icon("trash", 16), "删除")
        self.del_provider_btn.setAutoDefault(False)
        self.del_provider_btn.clicked.connect(self._on_provider_delete)
        prow.addWidget(add_p)
        prow.addWidget(self.del_provider_btn)
        prow.addStretch(1)
        lay.addLayout(prow)
        # 选中提示语（状态栏）
        self.provider_hint = QLabel("点击选中服务商卡片（删除按钮随之变红可用）；双击卡片编辑")
        self.provider_hint.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
        self.provider_hint.setWordWrap(True)
        lay.addWidget(self.provider_hint)
        self._update_provider_ui()
        # 工作力度：拖动切换（low/medium/high/max/ultra）+ 自动按难度开关
        self._effort = cfg.get("effort", "medium")
        self._auto_effort = bool(cfg.get("auto_effort", True))
        eff_row = QHBoxLayout()
        eff_row.setSpacing(10)
        eff_lbl = QLabel("工作力度")
        eff_lbl.setStyleSheet(f"color: {self._TEXT}; font-size: 13px;")
        eff_lbl.setFixedWidth(70)
        eff_row.addWidget(eff_lbl)
        self.effort_slider = QSlider(Qt.Orientation.Horizontal)
        self.effort_slider.setRange(0, len(agent_llm.EFFORTS) - 1)
        self.effort_slider.setFixedWidth(180)
        self.effort_slider.setPageStep(1)
        self.effort_slider.setToolTip("拖动切换工作力度（决定使用哪个模型）："
                                      + " / ".join(agent_llm.EFFORTS))
        self.effort_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ height: 4px; background: {self._BORDER};"
            "border-radius: 2px; }}"
            f"QSlider::sub-page:horizontal {{ background: {self._ACCENT}; border-radius: 2px; }}"
            f"QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -5px 0;"
            f"background: {self._ACCENT}; border: 2px solid {self._BG}; border-radius: 7px; }}"
            f"QSlider::handle:horizontal:hover {{ background: {self._ACCENT_HOVER}; }}")
        self.effort_slider.valueChanged.connect(self._on_effort_changed)
        eff_row.addWidget(self.effort_slider)
        self.effort_label = QLabel(self._effort)
        self.effort_label.setStyleSheet(f"color: {self._ACCENT}; font-size: 13px; font-weight: 700;")
        self.effort_label.setFixedWidth(52)
        eff_row.addWidget(self.effort_label)
        eff_row.addStretch(1)
        lay.addLayout(eff_row)
        self.auto_effort_check = QCheckBox("自动按难度（按任务难度自动选择工作力度）")
        self.auto_effort_check.setStyleSheet(f"color: {self._TEXT}; font-size: 13px; spacing: 8px;")
        self.auto_effort_check.setToolTip("按任务难度自动选择工作力度（智能调用）；关闭后仅手动拖动")
        self.auto_effort_check.toggled.connect(self._on_effort_changed)
        self.auto_effort_check.setChecked(self._auto_effort)
        lay.addWidget(self.auto_effort_check)
        self.effort_slider.blockSignals(True)
        self.effort_slider.setValue(agent_llm.EFFORTS.index(self._effort)
                                    if self._effort in agent_llm.EFFORTS else 0)
        self.effort_slider.blockSignals(False)
        tip = QLabel("工作强度会自动按模型映射：DeepSeek V4 思考模式（high/max）、"
                     "GLM-4.5+ 深度思考、OpenAI o 系列 reasoning_effort，无需手动开启")
        tip.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        lay.addStretch(1)
        return w

    def _build_tts_page(self) -> QWidget:
        w = self._page("语音合成")
        lay = self._page_body(w)
        cfg = agent_tts.load_config()
        tip = QLabel(f"当前音色：{agent_tts.VOICE_DISPLAY_NAME}（AI 回复时自动流式合成语音，"
                     "边生成边播放，无需手动选择音色）")
        tip.setStyleSheet(f"color: {self._TEXT}; font-size: 13px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self.auto_read_check = QCheckBox("AI 回复自动朗读（开关默认开启，关闭后仅显式要求朗读时播放）")
        self.auto_read_check.setChecked(bool(cfg.get("auto_read", True)))
        self.auto_read_check.setStyleSheet(f"color: {self._TEXT}; font-size: 13px; spacing: 8px;")
        lay.addWidget(self.auto_read_check)
        # 语速调节：对齐参考音频节奏（0.5x~1.5x，默认 1.0 = 与参考一致）
        spd_row = QHBoxLayout()
        spd_row.setSpacing(10)
        spd_lbl = QLabel("语速")
        spd_lbl.setStyleSheet(f"color: {self._TEXT}; font-size: 13px;")
        spd_lbl.setFixedWidth(70)
        spd_row.addWidget(spd_lbl)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(50, 150)
        self.speed_slider.setValue(int(float(cfg.get("speech_rate") or 1.0) * 100))
        self.speed_slider.setPageStep(5)
        self.speed_slider.setToolTip("拖动调节语速（100% = 与参考音频一致）")
        self.speed_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ height: 4px; background: {self._BORDER};"
            "border-radius: 2px; }"
            f"QSlider::sub-page:horizontal {{ background: {self._ACCENT}; border-radius: 2px; }}"
            f"QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -5px 0;"
            f"background: {self._ACCENT}; border-radius: 7px; }}"
            f"QSlider::handle:horizontal:hover {{ background: {self._ACCENT_HOVER}; }}")
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        spd_row.addWidget(self.speed_slider, 1)
        self.speed_label = QLabel(f"{self.speed_slider.value()}%")
        self.speed_label.setStyleSheet(f"color: {self._TEXT}; font-size: 13px;")
        self.speed_label.setFixedWidth(48)
        spd_row.addWidget(self.speed_label)
        lay.addLayout(spd_row)
        lay.addStretch(1)
        return w

    def _on_speed_changed(self, v: int):
        """语速滑块变更：立即持久化到 tts.json，下次合成生效"""
        self.speed_label.setText(f"{v}%")
        agent_tts.save_config(speech_rate=round(v / 100.0, 2))

    def _build_skill_page(self) -> QWidget:
        w = self._page("技能")
        lay = self._page_body(w)
        sub = QLabel("导入市场标准技能或删除用户自建技能（内置技能不可删除）")
        sub.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
        lay.addWidget(sub)
        imp = QPushButton(_std_icon(QStyle.StandardPixmap.SP_FileDialogNewFolder),
                          "导入市场标准技能（SKILL.md 或 zip 包）…")
        imp.setStyleSheet(f"background: {self._PANEL}; color: {self._TEXT};"
                          f"border: 1px solid {self._BORDER}; border-radius: 8px;"
                          "padding: 8px 16px; font-weight: 600;")
        imp.setAutoDefault(False)
        imp.setToolTip("选择市场标准的 SKILL.md 文件或含 SKILL.md 的 zip 包，"
                       "导入到技能目录并即时生效（/技能名 或对话描述即可调用）")
        imp.clicked.connect(self._import_skill)
        lay.addWidget(imp)
        del_skill = QPushButton(_std_icon(QStyle.StandardPixmap.SP_TrashIcon), "删除技能…")
        del_skill.setStyleSheet(f"background: {self._PANEL}; color: {self._DIM};"
                                f"border: 1px solid {self._BORDER}; border-radius: 8px;"
                                "padding: 8px 16px; font-weight: 600;")
        del_skill.setAutoDefault(False)
        del_skill.setToolTip("删除用户导入/创建的技能（连同 SKILL.md 与附属文件）；内置技能不可删除")
        del_skill.clicked.connect(self._delete_skill)
        lay.addWidget(del_skill)
        lay.addStretch(1)
        return w

    def _build_mcp_page(self) -> QWidget:
        w = self._page("MCP 服务器")
        lay = self._page_body(w)
        sub = QLabel("配置外部工具服务器（stdio 本地命令 / sse 远程 URL），保存后自动重连，AI 即可调用其工具")
        sub.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        self.mcp_list = QListWidget()
        self.mcp_list.setStyleSheet(
            f"QListWidget {{ background: {self._PANEL}; color: {self._TEXT};"
            f"border: 1px solid {self._BORDER}; border-radius: 8px; padding: 6px; }}"
            f"QListWidget::item {{ padding: 8px 10px; border-radius: 6px; }}"
            f"QListWidget::item:selected {{ background: {self._PANEL2};"
            f"color: {self._ACCENT_HOVER}; }}")
        lay.addWidget(self.mcp_list, 1)
        row = QHBoxLayout()
        row.setSpacing(8)
        add_b = QPushButton(_std_icon(QStyle.StandardPixmap.SP_FileDialogNewFolder), "添加")
        add_b.setStyleSheet(f"background: {self._ACCENT}; color: #FFFFFF;"
                            "border: none; border-radius: 8px; padding: 7px 16px; font-weight: 700;")
        add_b.setAutoDefault(False)
        add_b.clicked.connect(self._on_mcp_add)
        edit_b = QPushButton("编辑")
        edit_b.setStyleSheet(f"background: {self._PANEL}; color: {self._TEXT};"
                             f"border: 1px solid {self._BORDER}; border-radius: 8px;"
                             "padding: 7px 16px; font-weight: 600;")
        edit_b.setAutoDefault(False)
        edit_b.clicked.connect(self._on_mcp_edit)
        del_b = QPushButton(_line_icon("trash", 16), "删除")
        del_b.setStyleSheet(f"background: {self._PANEL}; color: {self._DIM};"
                            f"border: 1px solid {self._BORDER}; border-radius: 8px;"
                            "padding: 7px 16px; font-weight: 600;")
        del_b.setAutoDefault(False)
        del_b.clicked.connect(self._on_mcp_delete)
        row.addWidget(add_b)
        row.addWidget(edit_b)
        row.addWidget(del_b)
        row.addStretch(1)
        lay.addLayout(row)
        return w

    def _switch_page(self, idx: int):
        self.stack.setCurrentIndex(idx)

    # ---------- 服务商卡片操作 ----------
    def _make_provider_card(self, p: dict) -> QWidget:
        card = QWidget()
        card.setStyleSheet(f"background: {self._PANEL}; border-radius: 8px;")
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(8)
        name_text = str(p.get("name", ""))
        if agent_llm.is_default_provider(p):
            name_text += "（内置 · 锁定）"
        name = QLabel(name_text)
        name.setStyleSheet(f"color: {self._TEXT}; font-size: 14px; font-weight: 700;")
        top.addWidget(name)
        top.addStretch(1)
        url = QLabel(str(p.get("base_url", "")))
        url.setStyleSheet(f"color: {self._DIM}; font-size: 11px;")
        url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top.addWidget(url)
        v.addLayout(top)
        mm = set(p.get("multimodal_models") or [])
        models = QLabel("模型：" + ", ".join(
            f"{x}（视觉）" if x in mm else str(x) for x in (p.get("models") or [])))
        models.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
        v.addWidget(models)
        # 保存子标签引用，用于选中时切换纯蓝底+白字
        card._name_lbl = name
        card._url_lbl = url
        card._models_lbl = models
        return card

    def _reload_provider_list(self):
        self.provider_list.clear()
        for p in self._providers:
            p = dict(p)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setSizeHint(QSize(0, 66))
            self.provider_list.addItem(item)
            self.provider_list.setItemWidget(item, self._make_provider_card(p))

    def _current_provider(self) -> dict:
        item = self.provider_list.currentItem()
        if item is not None:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _on_provider_select(self, item):
        """单击卡片：选中（itemSelectionChanged 已触发 UI 刷新），不打开编辑"""
        self._update_provider_ui()

    def _update_provider_ui(self):
        """选中反馈：删除按钮选中时变红可用、未选中灰色；状态栏提示语；卡片高亮描边"""
        if not hasattr(self, "del_provider_btn"):   # 初始化中按钮尚未创建时跳过
            return
        sel = self._current_provider()
        if sel is not None:
            locked = agent_llm.is_default_provider(sel)
            self.del_provider_btn.setEnabled(not locked)
            if locked:
                self.del_provider_btn.setStyleSheet(
                    f"background: {self._PANEL}; color: {self._DIM};"
                    f"border: 1px solid {self._BORDER}; border-radius: 8px;"
                    "padding: 7px 16px; font-weight: 600;")
                self.del_provider_btn.setToolTip("内置默认服务商（agnes）不可删除")
                self.provider_hint.setText(
                    f"「{sel.get('name')}」为内置默认服务商，整行锁定：不可删除、不可编辑")
                self.provider_hint.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
            else:
                self.del_provider_btn.setStyleSheet(
                    f"background: {self._DANGER}; color: #FFFFFF; border: none;"
                    "border-radius: 8px; padding: 7px 16px; font-weight: 700;")
                self.del_provider_btn.setToolTip(f"删除服务商「{sel.get('name')}」")
                models = ", ".join(sel.get("models") or [])
                self.provider_hint.setText(
                    f"已选中「{sel.get('name')}」｜接口 {sel.get('base_url')}｜模型：{models}")
                self.provider_hint.setStyleSheet(
                    f"color: {self._ACCENT_HOVER}; font-size: 12px;")
        else:
            self.del_provider_btn.setEnabled(True)
            self.del_provider_btn.setStyleSheet(
                f"background: {self._PANEL}; color: {self._DIM};"
                f"border: 1px solid {self._BORDER}; border-radius: 8px;"
                "padding: 7px 16px; font-weight: 600;")
            self.del_provider_btn.setToolTip("请先选中一个服务商")
            self.provider_hint.setText("点击选中服务商卡片（删除按钮随之变红可用）；双击卡片编辑")
            self.provider_hint.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
        # 卡片高亮：选中卡片纯蓝底 + 白字（无边框）
        for i in range(self.provider_list.count()):
            it = self.provider_list.item(i)
            w = self.provider_list.itemWidget(it)
            p = it.data(Qt.ItemDataRole.UserRole)
            selected = p is not None and sel is not None and p.get("name") == sel.get("name")
            if w is None:
                continue
            if selected:
                w.setStyleSheet(f"background: {self._ACCENT}; border-radius: 8px;")
                w._name_lbl.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: 700;")
                w._url_lbl.setStyleSheet("color: #FFFFFF; font-size: 11px;")
                w._models_lbl.setStyleSheet("color: #FFFFFF; font-size: 12px;")
            else:
                w.setStyleSheet(f"background: {self._PANEL}; border-radius: 8px;")
                w._name_lbl.setStyleSheet(f"color: {self._TEXT}; font-size: 14px; font-weight: 700;")
                w._url_lbl.setStyleSheet(f"color: {self._DIM}; font-size: 11px;")
                w._models_lbl.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")

    def _on_provider_add(self, *_):
        dlg = _ProviderDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            p = dlg.provider_data()
            if any(x.get("name") == p["name"] for x in self._providers):
                QMessageBox.warning(self, "提示", f"已存在同名服务商「{p['name']}」")
                return
            self._providers.append(p)
            self._reload_provider_list()
            self.provider_list.setCurrentRow(self.provider_list.count() - 1)
            self._update_provider_ui()

    def _on_provider_edit(self, item):
        idx = self.provider_list.row(item)
        if not (0 <= idx < len(self._providers)):
            return
        p = self._providers[idx]
        if agent_llm.is_default_provider(p):
            QMessageBox.information(self, "提示", "内置默认服务商（agnes）不可编辑")
            return
        dlg = _ProviderDialog(provider=p, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        newp = dlg.provider_data()
        self._providers[idx] = newp
        self._reload_provider_list()
        self._update_provider_ui()

    def _on_provider_delete(self, *_):
        item = self.provider_list.currentItem()
        if item is None:
            QMessageBox.information(self, "提示", "请先选中一个服务商")
            return
        idx = self.provider_list.row(item)
        if not (0 <= idx < len(self._providers)):
            return
        p = self._providers[idx]
        if agent_llm.is_default_provider(p):
            QMessageBox.information(self, "提示", "内置默认服务商（agnes）不可删除")
            return
        reply = QMessageBox.question(
            self, "删除服务商", f"确定删除服务商「{p.get('name')}」？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._providers.pop(idx)
        self._reload_provider_list()
        self._update_provider_ui()

    # ---------- MCP 列表操作 ----------
    def _reload_mcp_list(self):
        self.mcp_list.clear()
        for srv in self._mcp_servers:
            typ = "stdio" if srv.get("type", "stdio") == "stdio" else "sse"
            detail = srv.get("command", "") or srv.get("url", "")
            self.mcp_list.addItem(f"{srv.get('name', '?')}   [{typ}]   {detail}")

    def _current_mcp(self) -> dict:
        row = self.mcp_list.currentRow()
        if 0 <= row < len(self._mcp_servers):
            return self._mcp_servers[row]
        return None

    def _on_mcp_add(self, *_):
        dlg = _McpServerDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mcp_servers.append(dlg.server_data())
            self._reload_mcp_list()

    def _on_mcp_edit(self, *_):
        if self._current_mcp() is None:
            QMessageBox.information(self, "提示", "请先选择一个服务器")
            return
        dlg = _McpServerDialog(server=self._current_mcp(), parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mcp_servers[self.mcp_list.currentRow()] = dlg.server_data()
            self._reload_mcp_list()

    def _on_mcp_delete(self, *_):
        row = self.mcp_list.currentRow()
        if 0 <= row < len(self._mcp_servers):
            self._mcp_servers.pop(row)
            self._reload_mcp_list()

    def _on_mode_changed(self, idx):
        """切换执行模式：切到 YOLO 需二次确认，防止误开。
        确认后同步 self._mode 并持久化，并即时更新引擎的 direct 标志，
        避免界面显示 YOLO 而 _confirm_tool 仍按旧模式（ask）弹确认导致命令被拒。"""
        val = self.mode_combo.itemData(idx)
        if val == "yolo":
            ret = QMessageBox.question(
                self, "开启直接工作模式",
                "YOLO 模式：AI 将直接执行任务，不再逐步询问/确认/约束，"
                "仅调用必要的技能与命令完成。\n"
                "删除系统关键目录等危险操作仍会被沙盒拒绝。确定开启？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if ret != QMessageBox.StandardButton.Yes:
                self.mode_combo.blockSignals(True)
                self.mode_combo.setCurrentIndex(0)   # 取消则回到 AskBeforeEdit
                self.mode_combo.blockSignals(False)
                return
        # 同步当前模式并持久化，避免界面与 _mode 不一致
        self._mode = val or "ask"
        self._settings.setValue("agent_mode", self._mode)
        # 即时更新已缓存引擎的 direct（YOLO 直行），无需重建引擎
        for st in self._sess.values():
            eng = st.get("engine")
            if eng is not None:
                eng.direct = (self._mode == "yolo")

    def _browse_workdir(self, *_):
        """弹出目录选择框，写入工作目录输入框（保存时持久化）"""
        start = self.workdir_edit.text().strip() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "选择 AI 工作目录", start)
        if d:
            self.workdir_edit.setText(d)

    def _on_effort_changed(self, *_):
        """力度滑块/自动开关变更：刷新当前力度标签"""
        self._effort = agent_llm.EFFORTS[self.effort_slider.value()]
        self.effort_label.setText(self._effort)

    def _save(self, *_):
        # 多服务商：基于卡片列表持久化，全部服务商统一参与路由
        providers = [dict(p) for p in getattr(self, "_providers", [])]
        if not providers:
            providers = [{"name": "默认服务商",
                          "base_url": agent_llm.DEFAULT_BASE_URL,
                          "api_key": agent_llm.DEFAULT_API_KEY,
                          "models": [agent_llm.DEFAULT_MODEL],
                          "protocol": "chat"}]
        first_models = providers[0].get("models") or [agent_llm.DEFAULT_MODEL]
        model = {
            "providers": providers,
            "model": first_models[0],   # 兼容旧字段
            "models": providers[0].get("models") or [],
            "protocol": providers[0]["protocol"] or "chat",
            "effort": self._effort,
            "auto_effort": self.auto_effort_check.isChecked(),
        }
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
            # 保存 MCP 服务器配置；成功后触发后台重连
            mcp_ok = agent_skills.save_mcp_servers(self._mcp_servers)
            p = self.parent()
            if mcp_ok and p is not None and hasattr(p, "_reconnect_mcp"):
                p._reconnect_mcp()
            # 执行模式 / 工作目录：写入 QSettings，面板在保存后同步读取
            q = QSettings("WinAppMigrator", "WinAppMigrator")
            q.setValue("agent_mode", self.mode_combo.currentData() or "ask")
            q.setValue("agent_workdir", self.workdir_edit.text().strip())
            if not mcp_ok:
                QMessageBox.warning(self, "提示", "MCP 配置保存失败（无写入权限），其余设置已保存")
            # 音色与自动朗读：独立写入 tts.json，避免被 settings.json 覆写
            agent_tts.save_config(auto_read=self.auto_read_check.isChecked(),
                                  speech_rate=round(self.speed_slider.value() / 100.0, 2)
                                  if hasattr(self, "speed_slider") else 1.0,
                                  preferred_name=agent_tts.VOICE_DISPLAY_NAME)
            self.accept()
        else:
            QMessageBox.warning(self, "错误", "保存设置失败（无写入权限）")

    def _import_skill(self, *_):
        """导入市场标准技能文件：SKILL.md 单文件或含 SKILL.md 的 zip 包"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择市场标准技能文件", "",
            "技能文件 (*.md);;压缩包 (*.zip);;所有文件 (*.*)")
        if not path:
            return
        ok, msg = agent_skills.import_skill_file(path)
        if ok:
            QMessageBox.information(self, "导入技能", msg)
        else:
            QMessageBox.warning(self, "导入失败", msg)

    def _delete_skill(self, *_):
        """删除用户技能：下拉选择（排除内置 JSON/md 技能），确认后删除并即时生效"""
        builtin = ({s.get("name") for s in agent_skills.DEFAULT_SKILLS}
                   | set(agent_skills._BUILTIN_MD_SKILLS))
        deletable = [s["name"] for s in agent_skills.load_skills()
                     if s.get("name") and s["name"] not in builtin]
        if not deletable:
            QMessageBox.information(self, "删除技能", "没有可删除的技能（内置技能不可删除）")
            return
        name, ok = QInputDialog.getItem(self, "删除技能", "选择要删除的技能：",
                                        deletable, 0, False)
        if not ok or not name:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除技能「{name}」吗？\n将同时删除其 SKILL.md 与附属文件（resources 等）。")
        if reply != QMessageBox.StandardButton.Yes:
            return
        ok2, msg = agent_skills.delete_skill(name)
        if ok2:
            QMessageBox.information(self, "删除技能", msg)
        else:
            QMessageBox.warning(self, "删除失败", msg)


class _McpServerDialog(QDialog):
    """单个 MCP 服务器配置：stdio（命令+参数）或 SSE（URL）"""
    def __init__(self, server: dict = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑 MCP 服务器" if server else "添加 MCP 服务器")
        self.setMinimumWidth(480)
        A = _AgentSettingsDialog
        self.setStyleSheet(
            f"QDialog {{ background: {A._BG}; }}"
            f"QLabel {{ color: {A._TEXT}; font-size: 13px; }}"
            f"QLineEdit, QComboBox {{ background: {A._PANEL}; color: {A._TEXT};"
            f"border: 1px solid {A._BORDER}; border-radius: 6px; padding: 6px 10px; }}"
            f"QLineEdit:focus, QComboBox:focus {{ border: 1px solid {A._ACCENT}; }}"
            f"QComboBox QAbstractItemView {{ background: {A._PANEL}; color: {A._TEXT};"
            f"border: 1px solid {A._BORDER}; selection-background-color: {A._PANEL2}; }}")
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
        A = _AgentSettingsDialog
        ok = QPushButton(_std_icon(QStyle.StandardPixmap.SP_DialogYesButton), "确定")
        ok.setStyleSheet(f"background: {A._ACCENT}; color: #FFFFFF; border: none;"
                         "border-radius: 8px; padding: 8px 24px; font-weight: 700;")
        ok.setAutoDefault(False)
        ok.clicked.connect(self._accept_check)
        cancel = QPushButton("取消")
        cancel.setStyleSheet(f"background: {A._PANEL}; color: {A._TEXT};"
                             f"border: 1px solid {A._BORDER}; border-radius: 8px;"
                             "padding: 8px 22px; font-weight: 600;")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        form.addRow(btns)
        add_brand_footer(self)

        self._sync_type()
        if server and server.get("type") == "sse":
            self.template_combo.setCurrentIndex(0)

    def _sync_type(self, *_):
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

    def _accept_check(self, *_):
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


class _ConnTestThread(QThread):
    """后台连通性测试线程：真实 API 最小请求验证 base_url + api_key + 模型，结果经信号回主线程"""

    done = pyqtSignal(bool, str)

    def __init__(self, base_url: str, api_key: str, model: str, protocol: str, parent=None):
        super().__init__(parent)
        self._args = (base_url, api_key, model, protocol)

    def run(self):
        try:
            ok, msg = agent_llm.test_provider_connection(*self._args)
            self.done.emit(ok, msg)
        except Exception as e:   # noqa: BLE001
            self.done.emit(False, f"测试异常：{e}")


class _ProviderDialog(QDialog):
    """单个 AI 服务商配置：预设 / 名称 / 接口地址 / API Key / 模型列表 / 接口协议。
    添加/编辑保存前必须通过真实连通性测试（不 mock），确保接入即可用。"""

    _BG = "#0F172A"
    _PANEL = "#1E293B"
    _TEXT = "#F1F5F9"
    _BORDER = "#334155"
    _ACCENT = "#1E40AF"
    _DIM = "#8A8A8A"
    _ERR = "#EF4444"
    _OK = "#22C55E"

    def __init__(self, provider: dict = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑服务商" if provider else "添加服务商")
        self.setMinimumWidth(520)
        self.setStyleSheet(
            f"QDialog {{ background: {self._BG}; }}"
            f"QLabel {{ color: {self._TEXT}; font-size: 13px; }}"
            f"QLineEdit, QComboBox {{ background: {self._PANEL}; color: {self._TEXT};"
            f"border: 1px solid {self._BORDER}; border-radius: 6px; padding: 6px 10px; }}"
            f"QLineEdit:focus, QComboBox:focus {{ border: 1px solid {self._ACCENT}; }}"
            f"QComboBox QAbstractItemView {{ background: {self._PANEL}; color: {self._TEXT};"
            f"border: 1px solid {self._BORDER}; selection-background-color: {self._PANEL}; }}")
        self._provider = provider or {}
        self._test_ok = False
        self._test_thread = None
        form = QFormLayout(self)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(12)

        # 预设服务商：一键填入主流 coding/Agent 服务商（仍需填 Key 并测试）
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("（自定义 / 手动填写）", None)
        for p in agent_llm.PRESET_PROVIDERS:
            self.preset_combo.addItem(p["name"], p)
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        form.addRow("预设服务商", self.preset_combo)
        self.preset_hint = QLabel("")
        self.preset_hint.setWordWrap(True)
        self.preset_hint.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
        form.addRow("", self.preset_hint)

        self.name_edit = QLineEdit(self._provider.get("name", ""))
        self.name_edit.setPlaceholderText("服务商名称，如 火山方舟、智谱、DeepSeek")
        form.addRow("名称", self.name_edit)

        self.base_edit = QLineEdit(self._provider.get("base_url", ""))
        self.base_edit.setPlaceholderText("https://api.example.com/v1")
        form.addRow("接口地址", self.base_edit)

        self.key_edit = QLineEdit(self._provider.get("api_key", ""))
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("sk-xxxxxxxx（必填，用于连通性测试）")
        form.addRow("API Key", self.key_edit)

        self.models_edit = QLineEdit(", ".join(self._provider.get("models", [])))
        self.models_edit.setPlaceholderText("模型名逗号分隔，如 glm-4.7, glm-4.7-flash")
        form.addRow("模型列表", self.models_edit)

        self.multimodal_edit = QLineEdit(", ".join(self._provider.get("multimodal_models", [])))
        self.multimodal_edit.setPlaceholderText(
            "多模态（视觉）模型逗号分隔，留空按模型名自动识别；自动选择模式下视觉任务优先路由到这些模型")
        form.addRow("多模态模型", self.multimodal_edit)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItem("Chat Completions（/v1/chat/completions）", "chat")
        self.protocol_combo.addItem("Responses API（/v1/responses）", "responses")
        pidx = self.protocol_combo.findData(self._provider.get("protocol", "chat"))
        self.protocol_combo.setCurrentIndex(pidx if pidx >= 0 else 0)
        form.addRow("接口协议", self.protocol_combo)

        # 连通性测试：真实请求通过后保存；配置变化需重新测试
        trow = QHBoxLayout()
        self.test_btn = QPushButton("测试连接")
        self.test_btn.setStyleSheet(
            f"background: {self._PANEL}; color: {self._TEXT}; border: 1px solid {self._ACCENT};"
            "border-radius: 8px; padding: 8px 18px; font-weight: 600;")
        self.test_btn.clicked.connect(lambda: self._run_test(from_ok=False))
        self.test_result = QLabel("添加/编辑服务商前必须先通过连通性测试")
        self.test_result.setWordWrap(True)
        self.test_result.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
        trow.addWidget(self.test_btn)
        trow.addWidget(self.test_result, 1)
        form.addRow("", trow)

        row = QHBoxLayout()
        ok = QPushButton("确定")
        ok.setStyleSheet(f"background: {self._ACCENT}; color: #FFFFFF; border: none;"
                         "border-radius: 8px; padding: 8px 24px; font-weight: 700;")
        ok.clicked.connect(self._confirm)
        cancel = QPushButton("取消")
        cancel.setStyleSheet(f"background: {self._PANEL}; color: {self._TEXT};"
                             f"border: 1px solid {self._BORDER}; border-radius: 8px;"
                             "padding: 8px 20px; font-weight: 600;")
        cancel.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(ok)
        form.addRow("", row)

        # 任何配置变化 → 测试结果失效，需重新测试
        for w in (self.name_edit, self.base_edit, self.key_edit,
                  self.models_edit, self.multimodal_edit):
            w.textChanged.connect(self._invalidate)
        self.protocol_combo.currentIndexChanged.connect(self._invalidate)

    def _invalidate(self, *_):
        self._test_ok = False
        self.test_result.setStyleSheet(f"color: {self._DIM}; font-size: 12px;")
        self.test_result.setText("配置已变化，需重新测试连接")

    def _apply_preset(self, idx):
        p = self.preset_combo.itemData(idx)
        if not p:
            self.preset_hint.setText("")
            return
        self.name_edit.setText(p.get("name", ""))
        self.base_edit.setText(p.get("base_url", ""))
        self.key_edit.setText("")   # Key 必须用户填写
        self.models_edit.setText(", ".join(p.get("models") or []))
        self.multimodal_edit.setText(", ".join(p.get("multimodal_models") or []))
        pidx = self.protocol_combo.findData(p.get("protocol", "chat"))
        if pidx >= 0:
            self.protocol_combo.setCurrentIndex(pidx)
        self.preset_hint.setText(p.get("desc", ""))

    def _current_params(self) -> dict:
        models = [x.strip() for x in self.models_edit.text().replace("，", ",").split(",")
                  if x.strip()]
        return {
            "name": self.name_edit.text().strip() or "服务商",
            "base_url": self.base_edit.text().strip(),
            "api_key": self.key_edit.text().strip(),
            "models": models,
            "protocol": self.protocol_combo.currentData() or "chat",
        }

    def _confirm(self, *_):
        """确定：已通过测试直接保存；否则自动先测，通过后再保存"""
        if self._test_ok:
            self.accept()
            return
        self._run_test(from_ok=True)

    def _run_test(self, from_ok: bool):
        if self._test_thread is not None and self._test_thread.isRunning():
            return
        p = self._current_params()
        if not p["base_url"] or not p["api_key"] or not p["models"]:
            self.test_result.setStyleSheet(f"color: {self._ERR}; font-size: 12px;")
            self.test_result.setText("请先填写接口地址、API Key 与至少一个模型名")
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中…")
        self.test_result.setStyleSheet(f"color: {self._ACCENT}; font-size: 12px;")
        self.test_result.setText(f"正在连接 {p['base_url']} 测试模型「{p['models'][0]}」…")
        self._test_thread = _ConnTestThread(p["base_url"], p["api_key"], p["models"][0],
                                            p["protocol"], self)
        self._test_thread.done.connect(
            lambda ok, msg, fo=from_ok: self._on_test_done(ok, msg, fo))
        self._test_thread.finished.connect(self._test_thread.deleteLater)
        self._test_thread.start()

    def _on_test_done(self, ok: bool, msg: str, from_ok: bool):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("测试连接")
        if ok:
            self._test_ok = True
            self.test_result.setStyleSheet(f"color: {self._OK}; font-size: 12px;")
            self.test_result.setText("✓ " + msg)
            if from_ok:
                self.accept()
        else:
            self._test_ok = False
            self.test_result.setStyleSheet(f"color: {self._ERR}; font-size: 12px;")
            self.test_result.setText(msg)
            if from_ok:
                QMessageBox.warning(self, "连通性测试失败", msg)

    def closeEvent(self, e):
        t = self._test_thread
        if t is not None and t.isRunning():
            t.wait(2000)   # 等待后台测试线程收尾，避免 QThread 运行中销毁
        super().closeEvent(e)

    def provider_data(self) -> dict:
        p = self._current_params()
        p["multimodal_models"] = [
            x.strip() for x in self.multimodal_edit.text().replace("，", ",").split(",")
            if x.strip()]
        return p


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
        # 自定义输入框：有选项时默认隐藏（由"其他…"勾选控制显示），无选项时直接作自由回答
        self._free_input = QLineEdit()
        self._free_input.setPlaceholderText("输入自定义内容…")
        self._free_input.hide()
        lay.addWidget(self._free_input)
        if options:
            for opt in options:
                b = QCheckBox(str(opt)) if multi_select else QRadioButton(str(opt))
                b.setAutoExclusive(not multi_select)
                self._choice_btns.append(b)
                lay.addWidget(b)
            # "其他…"选项：勾选后显示输入框，可输入自定义内容
            other = QCheckBox("其他…") if multi_select else QRadioButton("其他…")
            other.setAutoExclusive(not multi_select)
            other.toggled.connect(lambda on: self._free_input.setVisible(on))
            self._choice_btns.append(other)
            lay.addWidget(other)
            self._free_input.setPlaceholderText("输入自定义内容…")
        else:
            self._free_input.setPlaceholderText("输入你的回答…")
            self._free_input.show()

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
        add_brand_footer(self)

    def _accept_clicked(self, *_):
        sel = [b.text() for b in self._choice_btns if b.isChecked()]
        custom = self._free_input.text().strip() if self._free_input.isVisible() else ""
        # 自定义输入内容替换"其他…"选项；未填写的"其他…"直接忽略
        if custom:
            sel = [custom if t.startswith("其他…") else t for t in sel]
        else:
            sel = [t for t in sel if not t.startswith("其他…")]
        if sel:
            self._answer = " / ".join(sel)
        elif custom:
            self._answer = custom
        else:
            self._answer = "（用户未作答）"
        self.accept()

    def answer(self) -> str:
        return self._answer or "（用户取消回答）"


class _ArrowComboBox(QComboBox):
    """带旋转动画下拉箭头的 QComboBox：展开时箭头旋转 180° 指向向上，收起时转回向下。

    深色主题下样式表常把原生下拉箭头覆盖消失，此组件在右侧下拉区自绘箭头，
    并配合 hover/展开状态变色，作为模型选择菜单的微交互点缀。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._arrow_angle = 0.0        # 箭头旋转角度：0=收起，180=展开
        self._arrow_open = False
        self._arrow_hover = False
        self._arrow_anim = QPropertyAnimation(self, b"arrowAngle", self)
        self._arrow_anim.setDuration(160)
        self._arrow_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ---------- 动画属性 ----------
    def get_arrowAngle(self) -> float:
        return self._arrow_angle

    def set_arrowAngle(self, a: float):
        self._arrow_angle = a
        self.update()

    arrowAngle = pyqtProperty(float, get_arrowAngle, set_arrowAngle)

    # ---------- 展开/收起触发旋转动画 ----------
    def showPopup(self):
        super().showPopup()
        self._run_arrow(True)

    def hidePopup(self):
        super().hidePopup()
        self._run_arrow(False)

    def _run_arrow(self, opening: bool):
        self._arrow_open = opening
        self._arrow_anim.stop()
        self._arrow_anim.setStartValue(self._arrow_angle)
        self._arrow_anim.setEndValue(180.0 if opening else 0.0)
        self._arrow_anim.start()

    def enterEvent(self, e):
        self._arrow_hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._arrow_hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        # 在右侧下拉区自绘旋转箭头（∨ 形折线，展开后旋转 180° 变为 ∧）
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        arrow_w = 22   # 与样式表 ::drop-down 宽度一致，预留箭头区域
        cx = self.rect().right() - arrow_w / 2
        cy = self.rect().center().y()
        p.save()
        p.translate(cx, cy)
        p.rotate(self._arrow_angle)
        color = ACCENT if (self._arrow_open or self._arrow_hover) else TEXT_DIM
        pen = QPen(QColor(color))
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        s = 4.0
        path = QPainterPath()
        path.moveTo(-s, -s * 0.5)
        path.lineTo(0.0, s * 0.5)
        path.lineTo(s, -s * 0.5)
        p.drawPath(path)
        p.restore()
        p.end()


class FlowLayout(QLayout):
    """自动换行布局：子项宽度超出可用宽度时自动折行（附件缩略图条用）"""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 8):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addWidget(self, w: QWidget):
        # 必须先 addChildWidget 建立父子关系，否则控件不会随布局显示/定位
        self.addChildWidget(w)
        self.addItem(QWidgetItem(w))

    def addItem(self, item):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return self._do_layout(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        x, y = rect.x() + m.left(), rect.y() + m.top()
        line_h = 0
        for it in self._items:
            w = it.sizeHint().width()
            if x + w > rect.right() - m.right():   # 放不下 → 折行
                x = rect.x() + m.left()
                y += line_h + self.spacing()
                line_h = 0
            if not test_only:
                it.setGeometry(QRect(QPoint(x, y), it.sizeHint()))
            x += w + self.spacing()
            line_h = max(line_h, it.sizeHint().height())
        return y + line_h + m.bottom() - rect.y()


class _DropTextEdit(QPlainTextEdit):
    """多行输入框：自动换行、高度自适应（42~140px）、Enter 发送（Shift+Enter 换行）、
    文件拖放（重写 drag/drop，不依赖事件冒泡）。"""
    submit = pyqtSignal()          # 用户按 Enter（发送）
    fileDropped = pyqtSignal(list)  # 拖入的文件路径列表

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.textChanged.connect(lambda: QTimer.singleShot(0, self._auto_height))
        # 初始校准：QPlainTextEdit 默认尺寸偏高，事件循环启动后立刻按内容压回单行高
        QTimer.singleShot(0, self._auto_height)

    def resizeEvent(self, e):
        # 窗口宽度变化 → 换行变化 → 高度需重新校准（去抖）
        super().resizeEvent(e)
        QTimer.singleShot(0, self._auto_height)

    def _auto_height(self):
        """高度随内容自适应：单行 42px，多行增高，最高 140px（超出内部滚动）"""
        doc = self.document()
        # 文档 textWidth 未设置时按无限宽布局（不换行、恒为单行）→ 对齐视口宽度
        vw = self.viewport().width()
        if vw > 0 and doc.textWidth() != vw:
            doc.setTextWidth(vw)
        # 注意：QPlainTextDocumentLayout.documentSize().height() 返回的是行数（非像素），
        # 需乘以行高换算像素高度，否则单行文本高度恒为 42 不增高
        lines = doc.documentLayout().documentSize().height()
        h = int(lines * self.fontMetrics().lineSpacing()) + 16   # 行高 × 行数 + 内边距
        self.setFixedHeight(min(max(h, 42), 140))

    def keyPressEvent(self, e):
        # Enter 发送；Shift+Enter 换行
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and \
                not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.submit.emit()
            return
        super().keyPressEvent(e)

    def _has_files(self, e) -> bool:
        return e.mimeData().hasUrls()

    def dragEnterEvent(self, e):
        if self._has_files(e):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if self._has_files(e):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if self._has_files(e):
            paths = [u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile()]
            if paths:
                self.fileDropped.emit(paths)
            e.acceptProposedAction()
        else:
            super().dropEvent(e)


# ---------- 管理员权限下的原生拖放（Windows UIPI 绕行） ----------
# UIPI 会拦截普通 Explorer 拖入管理员（High IL）窗口的 OLE 拖放，Qt 常规 DnD 无解。
# 方案：RevokeDragDrop 移除 Qt 的 OLE 注册 → Explorer 回退发送 WM_DROPFILES 消息 →
# 原生事件过滤器解析文件路径与落点，合成 Qt 拖放事件投递给鼠标下方的控件。
_WM_DROPFILES = 0x0233
_WM_COPYDATA = 0x004A
_WM_COPYGLOBALDATA = 0x004D
_MSGFLT_ADD = 1


class _MSG(ctypes.Structure):
    """Win32 MSG 结构（64 位布局）"""
    _fields_ = [("hwnd", ctypes.c_void_p),
                ("message", ctypes.c_uint),
                ("wParam", ctypes.c_void_p),
                ("lParam", ctypes.c_void_p),
                ("time", ctypes.c_uint),
                ("pt_x", ctypes.c_long), ("pt_y", ctypes.c_long)]


def _drag_query_files(hdrop) -> list:
    """从 HDROP 句柄解析拖入的文件路径列表"""
    n = ctypes.windll.shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
    paths = []
    for i in range(n):
        ln = ctypes.windll.shell32.DragQueryFileW(hdrop, i, None, 0)
        buf = ctypes.create_unicode_buffer(ln + 1)
        ctypes.windll.shell32.DragQueryFileW(hdrop, i, buf, ln + 1)
        paths.append(buf.value)
    return paths


def _all_process_hwnds() -> list:
    """当前进程全部窗口句柄（顶层 + 所有后代），用于逐窗口设置 UIPI 放行与撤销 OLE 注册"""
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    pid = ctypes.windll.kernel32.GetCurrentProcessId()
    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def child_cb(hwnd, _lp):
        found.append(hwnd)
        return True

    def top_cb(hwnd, _lp):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid:
            found.append(hwnd)
            user32.EnumChildWindows(hwnd, WNDENUMPROC(child_cb), 0)
        return True

    user32.EnumWindows(WNDENUMPROC(top_cb), 0)
    return found


class _AdminDropFilter(QAbstractNativeEventFilter):
    """把 WM_DROPFILES 转成 Qt 拖放事件，投递给鼠标下方的可接收控件"""

    def __init__(self, panel):
        super().__init__()
        self._panel = panel

    def nativeEventFilter(self, eventType, message):
        try:
            # PyQt6 中 message 为 sip.voidptr，需先转整数地址再按 MSG 结构解析
            msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
            if msg.message != _WM_DROPFILES:
                return False, 0
            print("[dnd] 收到 WM_DROPFILES", flush=True)
            hdrop = ctypes.c_void_p(msg.wParam)
            paths = _drag_query_files(hdrop)
            print("[dnd] 文件列表:", paths, flush=True)
            pt = _POINT()
            ctypes.windll.shell32.DragQueryPoint(hdrop, ctypes.byref(pt))
            ctypes.windll.shell32.DragFinish(hdrop)
            print(f"[dnd] DragQueryPoint=({pt.x},{pt.y}) 光标屏幕={QCursor.pos()}", flush=True)
            if paths:
                # 延迟到主循环投递，避免在原生消息处理中重入 Qt 事件循环
                QTimer.singleShot(0, lambda: self._on_received(paths, pt.x, pt.y))
            return True, 0
        except Exception as e:
            print("[dnd] nativeEventFilter 异常:", repr(e), flush=True)
            return False, 0

    def _on_received(self, paths: list, x: int, y: int):
        """收到系统 WM_DROPFILES：显示诊断状态并投递（证明 OS 已把拖放送达应用）"""
        panel = self._panel
        if panel is not None and hasattr(panel, "_add_status"):
            panel._add_status(f"已接收系统拖放（{len(paths)} 个文件）", TEXT_DIM)
        self._deliver(x, y, paths)

    def _deliver(self, x: int, y: int, paths: list):
        """主循环内投递：用鼠标屏幕坐标定位控件（不依赖 DragQueryPoint 坐标语义），
        找不到可接收控件时回退面板自身；异常打印便于定位"""
        panel = self._panel
        try:
            if panel is None or not paths:
                return
            screen = QCursor.pos()
            w = QApplication.instance().widgetAt(screen)
            if w is None:   # 兜底：按 DragQueryPoint 坐标在面板内查找
                w = panel.childAt(QPoint(x, y))
            while w is not None and not w.acceptDrops():
                w = w.parentWidget()
            if w is None:
                w = panel
            print(f"[dnd] 投递目标: {type(w).__name__} acceptDrops={w.acceptDrops()}", flush=True)
            md = QMimeData()
            md.setUrls([QUrl.fromLocalFile(p) for p in paths])
            local = w.mapFromGlobal(screen)
            app = QApplication.instance()
            for evt in (QDragEnterEvent(local, Qt.DropAction.CopyAction, md,
                                        Qt.MouseButton.LeftButton,
                                        Qt.KeyboardModifier.NoModifier),
                        QDragMoveEvent(local, Qt.DropAction.CopyAction, md,
                                       Qt.MouseButton.LeftButton,
                                       Qt.KeyboardModifier.NoModifier),
                        QDropEvent(QPointF(local), Qt.DropAction.CopyAction, md,
                                   Qt.MouseButton.LeftButton,
                                   Qt.KeyboardModifier.NoModifier)):
                app.sendEvent(w, evt)
            print("[dnd] 已投递 Qt 拖放事件", flush=True)
        except Exception as e:
            print("[dnd] 投递异常:", repr(e), flush=True)


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class TodosPanel(QWidget):
    """左侧 TODOS 可视化面板：AI 使用 update_todo / list_todo 工具时显示任务进度。
    内嵌于 AgentPanel 布局（非独立窗口 → 天然无最小化/最大化/关闭按钮）。
    纯黑+淡灰+白+深蓝四色极简风格，无 emoji，状态用几何标记区分。
    鼠标悬停时右上角显示小 × 可手动清空任务清单。"""

    clear_requested = pyqtSignal()   # 用户手动清空任务清单

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("todosPanel")
        self.setFixedWidth(248)
        self.setStyleSheet(
            f"QWidget#todosPanel {{ background: {PANEL};"
            f"border: 1px solid {ACCENT}; border-radius: 10px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("任务清单")
        title.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: 800;")
        header.addWidget(title)
        self._count = QLabel("")
        self._count.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        header.addWidget(self._count)
        header.addStretch(1)
        # 右上角清空小按钮：鼠标悬停面板时显示
        self._close_btn = QPushButton("×")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setAutoDefault(False)
        self._close_btn.setFixedSize(18, 18)
        self._close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_DIM};"
            "border: none; border-radius: 9px; font-size: 14px; }}"
            f"QPushButton:hover {{ background: #1A2740; color: #FFFFFF; }}")
        self._close_btn.setToolTip("清空任务清单")
        self._close_btn.setVisible(False)
        self._close_btn.clicked.connect(self.clear_requested.emit)
        header.addWidget(self._close_btn)
        lay.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: #000000; width: 6px; }"
            "QScrollBar::handle:vertical { background: #000000;"
            "border-radius: 3px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical"
            "{ background: #000000; width: 0px; height: 0px; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical"
            "{ background: #000000; }")
        self._list = QWidget()
        self._list.setStyleSheet("background: transparent;")
        self._list_lay = QVBoxLayout(self._list)
        self._list_lay.setContentsMargins(2, 0, 2, 0)
        self._list_lay.setSpacing(6)
        self._list_lay.addStretch(1)
        self._scroll.setWidget(self._list)
        lay.addWidget(self._scroll, 1)
        self._limit = 220      # 面板最大高度（约页面 1/3，resizeEvent 随窗口更新）
        self._last_h = -1      # 上次应用的高度，避免重复 relayout
        self.update_todos([])

    def update_todos(self, todos: list):
        """全量刷新任务列表；面板默认常显，无任务时显示提示语占位"""
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        todos = [t for t in todos if isinstance(t, dict) and str(t.get("title") or "").strip()]
        if todos:
            for t in todos:
                self._list_lay.insertWidget(self._list_lay.count() - 1, self._row(t))
        else:
            empty = QLabel("复杂任务进度将会在这显示")
            empty.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list_lay.insertWidget(0, empty)
        done = sum(1 for t in todos if t.get("status") == "completed")
        self._count.setText(f"{done}/{len(todos)}" if todos else "")
        self.setVisible(True)   # 面板默认常显
        self._resize_to_content()

    def enterEvent(self, e):
        super().enterEvent(e)
        self._close_btn.setVisible(True)   # 鼠标悬停面板：显示右上角清空按钮

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._close_btn.setVisible(False)  # 鼠标移出：隐藏清空按钮

    def _content_height(self) -> int:
        """按任务行实际换行高度估算列表自然高度（含行间距）"""
        total, rows = 0, 0
        # 行宽 = 面板宽 - 面板内边距(24) - 列表边距(4) - 行边距(8)
        #           - 状态标记宽(14) - 行内间距(8)
        row_w = max(80, self.width() - 24 - 4 - 8 - 14 - 8 - 4)
        for i in range(self._list_lay.count() - 1):   # 末尾保留 stretch
            w = self._list_lay.itemAt(i).widget()
            if w is None:
                continue
            rows += 1
            lbl = w.findChild(QLabel, "todoTitle")
            h = lbl.heightForWidth(row_w) if lbl is not None else 20
            total += max(20, h + 4)                    # 行高 + 行上下内边距
        total += max(0, rows - 1) * self._list_lay.spacing()
        return total

    def _resize_to_content(self):
        """自适应高度：内容少时矮、内容多时受限高（约窗口一半）内部滚动"""
        total = 28 + self._content_height() + 22       # header + 面板上下内边距
        h = max(56, min(int(total), self._limit))
        if h != self._last_h:
            self._last_h = h
            self.setFixedHeight(h)

    def _row(self, t: dict) -> QWidget:
        title = str(t.get("title") or "")
        st = str(t.get("status") or "pending")
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(4, 2, 4, 2)
        rl.setSpacing(8)
        mark = QLabel("●")
        mark.setFixedWidth(14)
        if st == "completed":
            mark.setText("✓")
            mark.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        elif st == "in_progress":
            mark.setStyleSheet(f"color: {ACCENT_HOVER}; font-size: 12px;")
        else:
            mark.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        rl.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
        lbl = QLabel(_esc(title))
        lbl.setObjectName("todoTitle")
        lbl.setWordWrap(True)
        color = TEXT_DIM if st == "completed" else TEXT
        lbl.setStyleSheet(f"color: {color}; font-size: 12px;")
        rl.addWidget(lbl, 1)
        return row


class QueuePanel(QWidget):
    """排队消息面板：任务运行中发送的多条消息在此排队显示，支持逐条编辑/删除。
    高度自适应：单条单行、多条封顶限高内部滚动；无消息自动隐藏。
    纯黑+淡灰+白+深蓝四色极简风格，无 emoji。"""

    edit_clicked = pyqtSignal(int)     # 编辑第 idx 条排队消息
    delete_clicked = pyqtSignal(int)   # 删除第 idx 条排队消息
    clear_clicked = pyqtSignal()       # 清空全部排队消息

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("queuePanel")
        self.setStyleSheet(
            f"QWidget#queuePanel {{ background: {PANEL};"
            f"border: 1px solid {BORDER}; border-radius: 10px; }}")
        self._limit = 132      # 最大高度（表头 + 约 3 行，超出内部滚动）
        self._last_h = -1      # 上次应用高度，避免重复 relayout
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        tag = QLabel("排队中")
        tag.setStyleSheet(f"color: {ACCENT_HOVER}; font-size: 12px; font-weight: 700;")
        head.addWidget(tag)
        self._count = QLabel("")
        self._count.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        head.addWidget(self._count)
        head.addStretch(1)
        clear_btn = QPushButton("清空")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setAutoDefault(False)
        clear_btn.setStyleSheet(_BTN_GHOST)
        clear_btn.setFixedHeight(22)
        clear_btn.setToolTip("取消全部排队消息")
        clear_btn.clicked.connect(self.clear_all)
        head.addWidget(clear_btn)
        lay.addLayout(head)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: #000000; width: 6px; }"
            "QScrollBar::handle:vertical { background: #000000;"
            "border-radius: 3px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical"
            "{ background: #000000; width: 0px; height: 0px; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical"
            "{ background: #000000; }")
        self._list = QWidget()
        self._list.setStyleSheet("background: transparent;")
        self._list_lay = QVBoxLayout(self._list)
        self._list_lay.setContentsMargins(2, 0, 2, 0)
        self._list_lay.setSpacing(4)
        self._list_lay.addStretch(1)
        self._scroll.setWidget(self._list)
        lay.addWidget(self._scroll, 1)
        self.update_queue([])

    def update_queue(self, items: list):
        """全量刷新排队消息列表；无消息时自动隐藏面板"""
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for i, q in enumerate(items or []):
            self._list_lay.insertWidget(self._list_lay.count() - 1, self._item(i, q))
        self._count.setText(f"{len(items or [])} 条" if items else "")
        self.setVisible(bool(items))
        if items:
            # 排队消息从下至上：自动滚动到底部，最新排队消息始终可见
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        try:
            bar = self._scroll.verticalScrollBar()
            bar.setValue(bar.maximum())
        except RuntimeError:
            pass

    def _item(self, idx: int, q: dict) -> QWidget:
        text = (q.get("text") or "").strip().replace("\n", " ")
        if len(text) > 40:
            text = text[:40] + "…"
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(4, 0, 4, 0)
        rl.setSpacing(8)
        no = QLabel(f"{idx + 1}.")
        no.setFixedWidth(20)
        no.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        rl.addWidget(no)
        lbl = QLabel(f"“{_esc(text)}”")
        lbl.setStyleSheet(f"color: {TEXT}; font-size: 12px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        rl.addWidget(lbl, 1)
        edit = QPushButton("编辑")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.setAutoDefault(False)
        edit.setStyleSheet(_BTN_GHOST)
        edit.setFixedHeight(22)
        edit.setFixedWidth(46)
        edit.setToolTip("回填到输入框修改，发送后回到原队列位置")
        edit.clicked.connect(lambda _=False, i=idx: self.edit_clicked.emit(i))
        rl.addWidget(edit)
        dele = QPushButton("删除")
        dele.setCursor(Qt.CursorShape.PointingHandCursor)
        dele.setAutoDefault(False)
        dele.setStyleSheet(_BTN_GHOST)
        dele.setFixedHeight(22)
        dele.setFixedWidth(46)
        dele.setToolTip("取消该条排队消息")
        dele.clicked.connect(lambda _=False, i=idx: self.delete_clicked.emit(i))
        rl.addWidget(dele)
        row.setFixedHeight(26)
        return row

    def clear_all(self):
        """清空全部排队消息（仅发信号，由 AgentPanel 负责数据与 UI 同步）"""
        self.clear_clicked.emit()


class _SessionStatusDelegate(QStyledItemDelegate):
    """会话下拉项状态绘制：运行中显示转圈动画（深蓝弧线），待确认显示黄色圆点"""

    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self.panel = panel

    def paint(self, painter, option, index):
        sid = index.data(Qt.ItemDataRole.UserRole)
        st = self.panel._sess.get(sid) if isinstance(sid, str) else None
        running = bool(st and st.get("task_active"))
        pending = bool(st and (st.get("pending_confirm") or st.get("pending_ask")))
        name = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        painter.save()
        # 背景：选中 / 悬停
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(HOVER))
        rect = QRect(option.rect)
        left = rect.left() + 4
        cy = rect.center().y()
        # 待确认黄色圆点（最左侧）
        if pending:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(WARN))
            painter.drawEllipse(QRect(left, cy - 4, 8, 8))
            left += 14
        # 运行中转圈（深蓝弧线，随 spin 角度转动）
        if running:
            cx = left + 6
            pen = QPen(QColor(ACCENT_HOVER), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRect(cx - 6, cy - 6, 12, 12),
                            self.panel._spin_angle * 16, 120 * 16)
            left += 16
        # 文本
        painter.setFont(option.font)
        painter.setPen(option.palette.text().color())
        painter.drawText(QRect(left, rect.top(), max(0, rect.width() - (left - rect.left())),
                               rect.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
        painter.restore()

    def sizeHint(self, option, index):
        sz = super().sizeHint(option, index)
        return QSize(sz.width() + 44, sz.height())


class AgentPanel(QDialog):
    confirm_signal = pyqtSignal(str, str, str, str)  # sid, name, args_json, risk
    eval_signal = pyqtSignal(str)          # agnes-2.5-flash 任务难度评估结果（后台线程 → 主线程）
    switch_ready = pyqtSignal(str, object, object, object)  # 会话切换: sid, segs, ums, rows（带 sid，防止过期加载覆盖当前视图）
    ask_signal = pyqtSignal(str, str)      # sid, args_json（ask_user 提问）
    mcp_signal = pyqtSignal(str)
    compact_signal = pyqtSignal(int)   # /compact 压缩完成（后台线程 → 主线程，参数=合并条数）
    evt_signal = pyqtSignal(str, str, object)  # 会话事件路由: sid, kind(delta/status/result/reasoning/sub), payload

    # ---------- 会话感知状态（属性读写当前会话，支撑多对话并发） ----------
    def _cur(self) -> dict:
        """当前会话状态（无则返回空 dict 占位，读默认值）"""
        return self._sess.get(self._session_id) or {}

    @property
    def _task_active(self):
        return bool(self._cur().get("task_active"))

    @_task_active.setter
    def _task_active(self, v):
        st = self._sess.get(self._session_id)
        if st is not None:
            st["task_active"] = bool(v)

    @property
    def _user_stopped(self):
        return bool(self._cur().get("user_stopped"))

    @_user_stopped.setter
    def _user_stopped(self, v):
        st = self._sess.get(self._session_id)
        if st is not None:
            st["user_stopped"] = bool(v)

    @property
    def _end_badge_shown(self):
        return bool(self._cur().get("end_badge_shown"))

    @_end_badge_shown.setter
    def _end_badge_shown(self, v):
        st = self._sess.get(self._session_id)
        if st is not None:
            st["end_badge_shown"] = bool(v)

    @property
    def _think_done(self):
        return bool(self._cur().get("think_done"))

    @_think_done.setter
    def _think_done(self, v):
        st = self._sess.get(self._session_id)
        if st is not None:
            st["think_done"] = bool(v)

    @property
    def _think_start(self):
        return float(self._cur().get("think_start") or 0.0)

    @_think_start.setter
    def _think_start(self, v):
        st = self._sess.get(self._session_id)
        if st is not None:
            st["think_start"] = float(v)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("zhuzhu Copilot")
        self.setWindowIcon(QIcon(_app_icon_path()))
        self.setAcceptDrops(True)   # 支持把图片/文件拖入对话框
        # 排队消息编辑状态（_init_sessions 的 _switch_to 早期即可能访问，须最先初始化）
        self._queue_edit_idx = None
        self._input_placeholder = "描述任务，例如：帮我打开百度搜索天气（输入 / 查看命令）"
        # 窗口可自由调整大小，标题栏带最小化/最大化按钮。
        # Window 标志使其成为独立顶层窗口：任务栏显示独立缩略图，点击任务栏
        # 可定位并恢复/打开 AI 面板（否则作为父窗口子窗口，任务栏无独立入口）
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowType.Window
                            | Qt.WindowType.WindowMinMaxButtonsHint
                            | Qt.WindowType.WindowMaximizeButtonHint
                            | Qt.WindowType.WindowMinimizeButtonHint)
        self.setMinimumSize(1074, 692)
        self.resize(1074, 692)
        self.setFont(QFont("Microsoft YaHei UI", 10))
        self.setStyleSheet(
            f"QDialog {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            f"stop:0 {BG}, stop:1 {BG_BOTTOM}); }}"
            + _QCOMBO
            # 滚动条纯黑色（轨道+滑块+翻页区，垂直右侧 + 水平底部），与窗口背景一起设置避免覆盖
            + "QScrollBar:vertical { background: #000000; width: 8px; }"
              "QScrollBar::handle:vertical { background: #000000;"
              "border-radius: 4px; min-height: 30px; }"
              "QScrollBar:horizontal { background: #000000; height: 8px; }"
              "QScrollBar::handle:horizontal { background: #000000;"
              "border-radius: 4px; min-width: 30px; }"
              "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,"
              "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal"
              "{ background: #000000; }"
              "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,"
              "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal"
              "{ background: #000000; width: 0px; height: 0px; }")
        # 全局悬浮提示：深色底 + 白字 + 描边，避免系统默认纯黑底看不清
        # （QToolTip 无独立 setStyleSheet，需挂到应用级样式表，仅追加一次）
        app = QApplication.instance()
        if app is not None and "QToolTip {" not in (app.styleSheet() or ""):
            app.setStyleSheet(
                (app.styleSheet() or "") +
                f"QToolTip {{ background: {PANEL}; color: {TEXT};"
                f"border: 1px solid {ACCENT}; border-radius: 6px;"
                "padding: 6px 10px; font-size: 12px; }}")

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
        self._model_override_provider = ""   # 手动指定模型所属服务商名（跨服务商切换连接参数）
        # 记住上次手动选择的模型，重启自动恢复
        _last_model = str(self._settings.value("agent_last_model", "")).strip()
        if _last_model:
            self._model_override = _last_model
            self._model_override_provider = self._provider_for_model(_last_model)
        self._refresh_text_only()
        self._memory_enabled = bool(_s.get("memory_enabled", True))
        # 执行模式（ask/edit/yolo）在设置页调整，此处仅从 QSettings 读取
        self._mode = str(self._settings.value("agent_mode", "ask"))

        # 拖入的附件：图片（data URL，发给模型）与非图片文件（路径文本）
        self._pending_images: list = []
        self._pending_files: list = []

        # 当前 AI 气泡段落序列（交织渲染：思考 → 操作 → 正文 → 操作 → 正文…）
        self._ai_bubble = None
        self._segments = []   # [{"type": "think|op|result|text|mark", "html"/"raw": ...}]
        self._seg_cache = {}  # id(seg) -> (签名, 渲染HTML)：流式刷新只重算增长的段

        # 任务进行中的转圈动画行（显示在消息流顶部）
        self._spinner_row = None
        self._spinner = None
        self._spinner_lbl = None
        self._reasoning_lbl = None

        # /compact 压缩中的打字指示器行（与任务转圈独立，互不干扰）
        self._compact_row = None

        # 会话运行时状态存储：属性 _task_active/_user_stopped/_think_* 读写当前会话，
        # 必须先于其初始化（多对话并发：每会话独立引擎/段缓冲/排队消息）
        self._session_id = ""          # 当前会话 id
        self._session_name = "新对话"  # 当前会话名称
        # st = {engine, loaded, segments, history_segments, rows, user_msgs,
        #       sub_segs, user_stopped, end_badge_shown, think_done, think_start,
        #       task_active, queued}
        self._sess: dict = {}
        self._user_msgs: list = []     # 当前会话的用户消息文本（用于切换时重绘）
        self._rows: list = []          # 用户消息与 AI 回复的交错顺序行（[{"type": "user"/"ai", ...}]）

        # 任务结束徽章状态（按会话存于 _sess，属性读写当前会话）
        self._user_stopped = False     # 用户手动点击停止
        self._end_badge_shown = False  # 防止重复显示结束徽章

        # 流式思考过程状态（按会话存于 _sess）
        self._think_start = 0.0        # 本轮思考开始时间（time.time）
        self._think_done = False       # 思考是否已完成（已输出"已思考 x 秒"）

        # 卡死兜底 hooks：最近一次有输出/状态的时间戳（供 UI 反馈，不再自动强停）
        self._last_activity = 0.0      # 最近一次有输出/状态的时间戳
        self._task_active = False      # 是否有任务在执行（结束收尾的可靠依据）
        self._eval_pending = None      # 任务难度评估待启动参数 (sid, ai_text, send_images, skill_names)
        # 管理员权限下的原生拖放（UIPI 绕行，仅提权时启用）
        self._admin_dnd = False
        self._admin_drop_filter = None
        self._scroll_pending = False   # 滚动调度去重标志
        self._bubble_widgets: list = []  # 所有气泡 QLabel（窗口缩放时同步宽度）
        self._bubble_segs: dict = {}     # 气泡 id → 其 AI 段列表（思考折叠/展开局部重渲染用）
        self._html_dirty = False         # 流式刷新节流标志（60ms 批量 setText）

        # 发送/停止按钮转圈动画
        self._action_anim_angle = 0

        self._build_ui()
        self._sync_model_combo()   # 填充输入框右侧模型下拉（设置里的模型列表）
        self._connect_signals()
        self._restore_workdir()   # 恢复上次选择的工作目录（QSettings 持久化）
        self._init_sessions()   # 加载会话列表，默认恢复最近对话（上下文隔离）

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_meta)
        self._timer.start(400)

        # 会话下拉转圈动画：全局角度递进，有运行中会话时刷新下拉视图
        self._spin_angle = 0
        self._combo_anim = QTimer(self)
        self._combo_anim.timeout.connect(self._tick_combo_spin)
        self._combo_anim.setInterval(120)
        self._combo_anim.start()

        self._action_anim = QTimer(self)
        self._action_anim.timeout.connect(self._tick_action_anim)
        self._action_anim.setInterval(80)
        # resize 防抖：窗口尺寸变化停止后统一重渲染气泡（合并连续 resize，避免卡顿）
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(160)
        self._resize_timer.timeout.connect(self._rebuild_bubbles_after_resize)
        self._last_bw = self._last_bmn = -1     # 上次已同步的气泡宽度缓存
        self._last_img_w = -1                   # 上次重渲染时的截图宽度缓存
        self._last_scale = 0.0                  # 上次底部输入行等比缩放系数（0=未初始化）
        self._last_todos_limit = -1             # 上次 todos 面板限高缓存
        self._btn_icon_sz = 16                  # 发送/转圈按钮图标尺寸（随窗口缩放）

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
        self.session_combo.setMinimumWidth(150)
        self.session_combo.setMaximumWidth(200)
        # 自定义 delegate：运行中会话显示转圈、待确认显示黄色圆点
        self.session_combo.setItemDelegate(_SessionStatusDelegate(self))
        self.session_combo.currentIndexChanged.connect(self._on_session_selected)
        # 下拉列表右键菜单：删除对话
        self.session_combo.view().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.session_combo.view().customContextMenuRequested.connect(self._on_session_context_menu)
        top.addWidget(self.session_combo)

        self.new_btn = QPushButton(_line_icon("new"), "")
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.setAutoDefault(False)
        self.new_btn.setFixedSize(34, 34)
        self.new_btn.setIconSize(QSize(18, 18))
        self.new_btn.setToolTip("新对话")
        self.new_btn.setStyleSheet(_BTN_ICON)
        self.new_btn.clicked.connect(self._new_session)
        top.addWidget(self.new_btn)

        self.settings_btn = QPushButton(_svg_icon(_GEAR_SVG, 20, TEXT_DIM), "")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setAutoDefault(False)
        self.settings_btn.setFixedSize(34, 34)
        self.settings_btn.setIconSize(QSize(18, 18))
        self.settings_btn.setToolTip("AI 设置：执行模式 / 工作目录 / 工作力度 / 规则 / 提示词 / 模型接入")
        self.settings_btn.setStyleSheet(_BTN_ICON)
        self.settings_btn.clicked.connect(self._open_settings)
        top.addWidget(self.settings_btn)

        top.addStretch(1)

        self.token_label = QLabel("0 tk")
        self.token_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        self.token_label.setToolTip("已用 tokens")
        top.addWidget(self.token_label)

        clear_btn = QPushButton(_line_icon("trash"), "")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setAutoDefault(False)
        clear_btn.setFixedSize(34, 34)
        clear_btn.setIconSize(QSize(18, 18))
        clear_btn.setToolTip("清空上下文并永久删除该对话（二次弹窗确认，不可恢复）")
        clear_btn.setAutoDefault(False)
        clear_btn.setStyleSheet(_BTN_GHOST)
        clear_btn.clicked.connect(self._clear_chat)
        top.addWidget(clear_btn)

        root.addLayout(top)

        # 主体：左侧 TODOS 可视化面板 + 右侧聊天区。
        # TODOS 内嵌于布局（非独立窗口 → 无最小化/最大化/关闭按钮），
        # 默认隐藏，AI 使用 update_todo / list_todo 工具时自动显示。
        body = QHBoxLayout()
        body.setSpacing(10)
        self.todos_panel = TodosPanel(self)
        self.todos_panel.clear_requested.connect(self._on_todos_clear)
        body.addWidget(self.todos_panel, 0)
        right = QVBoxLayout()
        right.setSpacing(10)

        # 聊天区（气泡）与欢迎页（无对话时居中介绍 AI 功能）用堆叠切换
        self.msg_area = QScrollArea()
        self.msg_area.setWidgetResizable(True)
        # 滚动条纯黑色（轨道+滑块+翻页区）：垂直（右侧）+ 水平（底部）
        self.msg_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: #000000; width: 8px; }"
            "QScrollBar::handle:vertical { background: #000000;"
            "border-radius: 4px; min-height: 30px; }"
            "QScrollBar:horizontal { background: #000000; height: 8px; }"
            "QScrollBar::handle:horizontal { background: #000000;"
            "border-radius: 4px; min-width: 30px; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,"
            "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal"
            "{ background: #000000; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal"
            "{ background: #000000; width: 0px; height: 0px; }")
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
        self.cmd_list.setStyleSheet(self._cmd_list_qss())
        self.cmd_list.hide()
        self.cmd_list.itemClicked.connect(self._on_cmd_selected)
        root.addWidget(self.cmd_list)

        # 附件缩略图条：拖入的图片/文件在此预览（隐藏时无高度；子项自动换行不挤压）
        self._attach_bar = QWidget()
        self._attach_bar.setStyleSheet("background: transparent;")
        self._attach_lay = FlowLayout(self._attach_bar, margin=0, spacing=8)
        self._attach_bar.setVisible(False)
        right.addWidget(self._attach_bar)

        # 排队消息面板：任务运行中发送的多条消息在此排队显示，可逐条编辑/删除。
        # 高度自适应（单条单行、多条限高滚动），无消息自动隐藏。
        self.queue_panel = QueuePanel(self)
        self.queue_panel.hide()
        self.queue_panel.edit_clicked.connect(self._on_queue_edit)
        self.queue_panel.delete_clicked.connect(self._on_queue_delete)
        self.queue_panel.clear_clicked.connect(self._on_queue_clear)
        right.addWidget(self.queue_panel)

        # 输入栏
        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        self.input = _DropTextEdit()
        self.input.setPlaceholderText("描述任务，例如：帮我打开百度搜索天气（输入 / 查看命令）")
        self.input.setMinimumHeight(32)
        self.input.setMaximumHeight(110)
        self.input.setStyleSheet(
            f"QPlainTextEdit {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER};"
            "border-radius: 10px; padding: 5px 10px; font-size: 14px; }}"
            f"QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}")
        self.input.submit.connect(self._send)   # Enter 发送（Shift+Enter 换行）
        self.input.textChanged.connect(self._update_cmd_suggestions)
        self.input.textChanged.connect(self._sync_action_style)
        self.input.textChanged.connect(self._on_input_cancel_edit)
        self.input.installEventFilter(self)   # 拦截 Ctrl+V：剪贴板图片转附件
        self.input.fileDropped.connect(self._on_input_files_dropped)   # 文件拖入 → 附件
        bottom.addWidget(self.input, 1)

        # TTS 语音合成快捷入口


        # 输入框右侧「+」上传按钮：文件选择器多选（也支持拖拽 / Ctrl+V 粘贴）
        self.attach_btn = QPushButton(_line_icon("plus", 20, ACCENT), "")
        self.attach_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attach_btn.setAutoDefault(False)
        self.attach_btn.setFixedSize(42, 42)
        self.attach_btn.setIconSize(QSize(20, 20))
        self.attach_btn.setToolTip("上传文件/图片给 AI（也可拖拽文件到输入框或 Ctrl+V 粘贴截图）")
        self.attach_btn.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; border: 1px solid {BORDER};"
            f"border-radius: 21px; }}"
            f"QPushButton:hover {{ border: 1px solid {ACCENT}; }}")
        self.attach_btn.clicked.connect(self._pick_attachments)
        bottom.addWidget(self.attach_btn)

        # 输入框右侧：手动切换本次使用的模型（选「自动」则按工作力度路由）
        self.model_combo = _ArrowComboBox()
        self.model_combo.setMinimumWidth(150)
        self.model_combo.setMaximumWidth(230)
        self.model_combo.setStyleSheet(_QCOMBO)
        self.model_combo.setToolTip("手动切换本次使用的模型；「自动选择」= 按工作力度路由")
        self.model_combo.currentIndexChanged.connect(self._on_model_combo)
        self.model_combo.setAcceptDrops(False)   # 文件拖放由面板统一接收
        bottom.addWidget(self.model_combo)

        # 发送/停止融合按钮：空闲=发送（深蓝），运行中=转圈可点击停止，停止中=红底转圈
        self.action_btn = QPushButton(_line_icon("send", 16, "#FFFFFF"), "")
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.setAutoDefault(False)
        self.action_btn.setFixedSize(34, 34)
        self.action_btn.setIconSize(QSize(16, 16))
        self.action_btn.setStyleSheet(_BTN_PRIMARY)
        self.action_btn.setToolTip("发送")
        self.action_btn.clicked.connect(self._on_action_clicked)
        bottom.addWidget(self.action_btn)
        # 输入行始终贴底：排队面板显示时由 Expanding 占满，隐藏时由弹性空间撑起
        right.addStretch(1)
        right.addLayout(bottom)
        body.addLayout(right, 1)
        root.addLayout(body, 0)   # 底部区域按内容高度贴底，聊天区占满其余空间
        add_brand_footer(self)

    def _connect_signals(self):
        self.confirm_signal.connect(self._on_confirm)
        self.ask_signal.connect(self._on_ask)
        self.eval_signal.connect(self._on_assess_done)
        self.compact_signal.connect(self._on_compact_done)
        self.switch_ready.connect(self._finish_switch)
        self.evt_signal.connect(self._route)

    # ---------- 欢迎页（无对话时居中介绍 AI 功能） ----------

    def _build_welcome(self) -> QWidget:
        # 无卡片/无边框：QWidget 声明 border 会被 Qt 传播到子 QLabel 造成黑框，
        # 直接居中排版文字，保持纯黑四色极简风格
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.addStretch(1)
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        t = QLabel("zhuzhu Copilot")
        t.setStyleSheet(f"color: {TEXT}; font-size: 22px; font-weight: 800;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(t)
        sub = QLabel("观察你的屏幕，理解你的指令，帮你完成电脑操作")
        sub.setStyleSheet(f"color: {TEXT_DIM}; font-size: 13px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(sub)
        box.addSpacing(10)
        for f in ("▪ 浏览器操控：独立浏览器打开网页、登录、填表、抓取数据",
                  "▪ 文件操作：读取、写入、编辑本地文件",
                  "▪ 快速查找：秒查应用与文件（find_app / search_files）",
                  "▪ 技能命令：输入 / 查看全部技能与工具",
                  "▪ 拖拽图片：把图片拖入对话框让 AI 识别",
                  "▪ 多对话：自动命名、切换隔离、重启恢复"):
            lbl = QLabel(f)
            lbl.setStyleSheet(f"color: {TEXT}; font-size: 13px; padding: 3px 0;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(lbl)
        box.addSpacing(4)
        tip = QLabel("直接输入任务开始，例如：帮我打开抖音网页版并查看热门视频")
        tip.setStyleSheet(f"color: {ACCENT}; font-size: 12px;")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(tip)
        lay.addLayout(box)
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

    # ---------- 多对话并发：会话状态存储 / 引擎路由 / 排队消息 ----------
    def _new_sess_state(self, sid: str) -> dict:
        """新建会话运行时状态（内存段缓冲 + 独立引擎 + 排队消息）"""
        return {
            "engine": None,
            "loaded": False,          # 是否已建立内存态（首次从磁盘加载后置 True）
            "segments": [],
            "history_segments": [],
            "rows": [],
            "user_msgs": [],
            "sub_segs": {},
            "user_stopped": False,
            "end_badge_shown": False,
            "think_done": False,
            "think_start": 0.0,
            "task_active": False,
            "queued": [],         # 排队消息列表（按序发送）：[{text, images, files, ai_text, skill_names, shot}]
            "pending_confirm": None,  # 后台待确认命令：{name, args, risk, answered}（不弹窗打扰，切过去处理）
            "confirm_evt": None,      # 该会话确认等待事件
            "confirm_result": False,  # 该会话最近一次确认结果
            "pending_ask": None,      # 后台待回答提问：{args, answered}
            "ask_evt": None,          # 该会话提问等待事件
            "ask_result": "",         # 该会话最近一次提问回答
        }

    def _bind_sess(self, sid: str):
        """把当前工作属性指向指定会话的内存缓冲（切换会话时调用）"""
        st = self._sess.setdefault(sid, self._new_sess_state(sid))
        self._segments = st["segments"]
        self._history_segments = st["history_segments"]
        self._rows = st["rows"]
        self._user_msgs = st["user_msgs"]
        self._sub_segs = st["sub_segs"]

    def _commit_sess(self):
        """把当前工作属性回写进当前会话状态（在 reassign 后/切换前调用）"""
        st = self._sess.get(self._session_id)
        if st is None:
            return
        st["segments"] = self._segments
        st["history_segments"] = self._history_segments
        st["rows"] = self._rows
        st["user_msgs"] = self._user_msgs
        st["sub_segs"] = self._sub_segs

    def _persist_sid(self, sid: str, st: dict):
        """持久化指定会话到磁盘（后台任务结束/切换时调用，UI 线程轻量快存）"""
        if not sid or not st:
            return
        d = self._sessions_dir()
        d.mkdir(parents=True, exist_ok=True)
        eng = st.get("engine")
        if eng:
            threading.Thread(target=lambda: eng.save_context(d / f"{sid}.json"),
                             daemon=True).start()
        try:
            clean_segments = [
                seg for seg in (st["history_segments"] + st["segments"])
                if not (seg.get("type") == "mark" and seg.get("html") == "已停止")
            ]
            rows = [dict(r, segs=[s for s in r.get("segs") or []
                                  if not (s.get("type") == "mark" and s.get("html") == "已停止")])
                    if r.get("type") == "ai" else r
                    for r in (st["rows"] or [])]
            if st["segments"] and not (rows and rows[-1].get("type") == "ai"):
                rows.append({"type": "ai", "segs": [
                    s for s in st["segments"]
                    if not (s.get("type") == "mark" and s.get("html") == "已停止")]})
            with open(d / f"{sid}.ui.json", "w", encoding="utf-8") as f:
                json.dump({"segments": clean_segments, "user_msgs": st["user_msgs"],
                           "rows": rows}, f, ensure_ascii=False)
        except Exception:
            pass
        lst = self._load_session_list()
        for x in lst:
            if x.get("id") == sid:
                x["updated"] = time.time()
        self._save_session_list(lst)

    def _engine_for(self, sid: str):
        """返回指定会话的引擎（不存在则创建）；当前会话同步 self._engine 引用"""
        st = self._sess.setdefault(sid, self._new_sess_state(sid))
        eng = st.get("engine")
        if eng is None:
            eng = self._build_engine(sid)
            st["engine"] = eng
        if sid == self._session_id:
            self._engine = eng
        return eng

    def _build_engine(self, sid: str):
        """按会话创建独立引擎：事件回调携带 sid 经信号路由到对应会话缓冲
        （后台会话生成不中断、不污染当前视图，实现多对话并发）"""
        cfg = self._llm_config()
        client = agent_llm.LLMClient(
            base_url=cfg.get("base_url"), api_key=cfg.get("api_key"),
            model=cfg.get("model"), protocol=cfg.get("protocol", "chat"))
        return agent_engine.AgentEngine(
            client,
            mcp_manager=self._mcp,
            on_delta=lambda s, _sid=sid: self.evt_signal.emit(_sid, "delta", s),
            on_status=lambda s, _sid=sid: self.evt_signal.emit(_sid, "status", s),
            on_result=lambda n, t, im, _sid=sid: self.evt_signal.emit(_sid, "result", (n, t, im)),
            on_reasoning=lambda s, _sid=sid: self.evt_signal.emit(_sid, "reasoning", s),
            on_sub_event=lambda k, i, t, s, _sid=sid: self.evt_signal.emit(_sid, "sub", (k, i, t, s)),
            confirm=lambda n, a, _sid=sid: self._confirm_tool(_sid, n, a),
            ask_user=lambda a, _sid=sid: self._ask_user_tool(_sid, a),
            text_only=self._text_only,
            memory_enabled=self._memory_enabled,
            direct=self._mode == "yolo")

    def _route(self, sid: str, kind: str, payload):
        """会话事件路由（主线程）：前台会话走渲染，后台会话只更新内存缓冲"""
        if kind == "pending":
            # 后台会话挂起确认/提问：主线程刷新下拉标记 + 优雅通知（不弹窗）
            self._refresh_session_combo()
            self._notify_background(payload[0], payload[1])
            return
        if sid != self._session_id:
            self._bg_event(sid, kind, payload)
            return
        if kind == "delta":
            self._on_delta(payload)
        elif kind == "status":
            self._on_status(payload)
        elif kind == "result":
            name, text, images = payload
            self._on_result(name, text, images)
        elif kind == "reasoning":
            self._on_reasoning(payload)
        elif kind == "sub":
            k, i, t, s = payload
            self._on_sub_event(k, i, t, s)

    def _bg_event(self, sid: str, kind: str, payload):
        """后台会话任务事件：只更新该会话内存缓冲并在结束落盘，不渲染 UI"""
        st = self._sess.get(sid)
        if st is None:
            return
        segs = st["segments"]
        if kind == "delta":
            if segs and segs[-1].get("type") == "text":
                segs[-1]["raw"] += payload
            else:
                segs.append({"type": "text", "raw": payload})
            return
        if kind == "reasoning":
            if segs and segs[0].get("type") == "think":
                segs[0]["html"] += payload
            else:
                segs.insert(0, {"type": "think", "html": payload})
            return
        if kind == "result":
            name, text, images = payload
            shown = (text or "").strip()
            if len(shown) > 20000:
                shown = shown[:20000] + " …（输出过长已截断显示，完整内容已返回模型）"
            shown = _esc(shown).replace("\n", "<br/>")
            segs.append({"type": "result", "html": shown, "collapsed": False})
            for u in images or []:
                segs.append({"type": "image", "url": u, "caption": "已截屏"})
            return
        if kind == "sub":
            k, idx, title, text = payload
            if k == "start":
                seg = {"type": "sub", "title": title, "raw": ""}
                st["sub_segs"][idx] = seg
                segs.append(seg)
            elif k == "delta":
                seg = st["sub_segs"].get(idx)
                if seg is None:
                    for s in reversed(segs):
                        if s.get("type") == "sub" and s.get("title") == title:
                            seg = s
                            break
                if seg is None:
                    seg = {"type": "sub", "title": title, "raw": ""}
                    st["sub_segs"][idx] = seg
                    segs.append(seg)
                seg["raw"] += text
            return
        if kind == "status":
            s = payload
            if s == "正在思考…":
                return
            if s.startswith(("待执行工具:", "正在执行:", "正在调用技能:", "技能已调用:")):
                name = s.split(":", 1)[1].strip()
                segs.append({"type": "op", "html": f"▎{_esc(name)}"})
                return
            if s == "完成" or s == "已停止" or s.startswith("错误"):
                st["task_active"] = False
                self._persist_sid(sid, st)   # 后台任务结束立即落盘，切回即完整
                self._flush_queue(sid)       # 本轮完成 → 自动发送排队消息
            return

    # ---------- 消息排队：任务运行中发消息 → 排队，本轮完成后按序自动发送 ----------
    def _update_queue_bar(self):
        """刷新当前会话的排队消息面板（有多条显示，无则隐藏）"""
        st = self._sess.get(self._session_id)
        self.queue_panel.update_queue((st or {}).get("queued") or [])

    def _on_queue_edit(self, idx: int):
        """编辑第 idx 条排队消息：回填输入框并移除该条，发送后按原队列位置重新排队"""
        st = self._sess.get(self._session_id)
        qs = (st or {}).get("queued") or []
        if idx < 0 or idx >= len(qs):
            return
        q = qs.pop(idx)
        self._queue_edit_idx = idx
        self.input.setPlainText(q.get("text") or "")
        self.input.setPlaceholderText(f"正在编辑第 {idx + 1} 条排队消息，发送后回到原队列位置")
        self._update_queue_bar()
        self.input.setFocus()

    def _on_queue_delete(self, idx: int):
        """删除第 idx 条排队消息"""
        st = self._sess.get(self._session_id)
        qs = (st or {}).get("queued") or []
        if 0 <= idx < len(qs):
            qs.pop(idx)
        if self._queue_edit_idx is not None and idx < self._queue_edit_idx:
            self._queue_edit_idx -= 1   # 列表左移，编辑目标位置同步前移
        self._update_queue_bar()

    def _on_queue_clear(self):
        """清空全部排队消息并复位编辑状态"""
        st = self._sess.get(self._session_id)
        if st:
            st["queued"] = []
        self._cancel_queue_edit()
        self._update_queue_bar()

    def _on_todos_clear(self):
        """用户手动清空 todos：清空清单文件并刷新面板（AI 下次 update_todo 全量恢复）"""
        try:
            agent_tools.TODO_FILE.write_text("[]", encoding="utf-8")
        except OSError:
            pass
        self.todos_panel.update_todos([])

    def _cancel_queue_edit(self):
        """取消编辑状态并恢复输入框占位提示"""
        self._queue_edit_idx = None
        self.input.setPlaceholderText(self._input_placeholder)

    def _on_input_cancel_edit(self):
        """输入框被清空时自动取消编辑状态（避免后续误替换原队列位置）"""
        if self._queue_edit_idx is not None and not self.input.toPlainText().strip():
            self._cancel_queue_edit()

    def _flush_queue(self, sid: str):
        """该会话本轮任务完成后：发送排队消息中最新的一条（一次一条，下轮继续）"""
        st = self._sess.get(sid)
        qs = (st or {}).get("queued") or []
        if not qs:
            return
        eng = st.get("engine")
        if eng and eng._thread and eng._thread.is_alive():
            return     # 该会话仍有任务在跑，继续等待
        q = qs.pop()   # 最新一条优先发送
        if sid == self._session_id:
            self._update_queue_bar()
            self._do_send(q)
        else:
            self._bg_send(sid, q)

    def _build_payload(self, text: str, images: list, files: list):
        """解析输入为发送 payload（排队/直接发送共用）；无法解析返回 None"""
        ai_text = text
        skill_names = []
        skill, skill_prompt = self._match_skill(text)
        if skill:
            self._add_status(f"已调用技能「{skill.get('name')}」", ACCENT)
            skill_names = [skill.get("name")]
            ai_text = skill_prompt or f"请严格按技能「{skill.get('name')}」的流程执行。"
        tool = self._match_tool(text)
        shot = None
        if tool:
            tname, targs = tool
            self._add_status(f"已指定工具「{tname}」", ACCENT)
            if tname == "screenshot":
                try:
                    shot = agent_screen.capture_screen_data_url(grid=False)
                    ai_text = "已截取当前屏幕并展示在对话中，请基于截图内容回答或继续执行。"
                except Exception:
                    shot = None
            else:
                ai_text = (f"请调用工具「{tname}」完成以下任务，参数必须按 JSON 传入。\n"
                           f"工具参数说明：{self._tool_params_hint(tname)}\n"
                           f"参数原始文本：{targs or '(无，可自行确定合理参数，不确定时先 ask_user 澄清)'}")
        if files:
            note = "以下为拖入的附件文件，请按需读取内容：\n" + \
                "\n".join(f"- {p}" for p in files)
            ai_text = (ai_text + "\n\n" if ai_text else "") + note
        return {"text": text, "images": images, "files": files,
                "ai_text": ai_text, "skill_names": skill_names, "shot": shot}

    def _do_send(self, p: dict):
        """按已解析的 payload 发送消息（前台：渲染用户气泡 + 启动任务）"""
        text = p.get("text") or ""
        ai_text = p.get("ai_text") or text
        skill_names = p.get("skill_names") or []
        images = list(p.get("images") or [])
        files = list(p.get("files") or [])
        shot = p.get("shot")
        self._auto_name_session(ai_text)
        # 归档上一轮 AI 回复到历史（须在追加新用户消息前完成，保证交错行顺序正确）
        if self._segments:
            self._history_segments.extend(self._segments)
            self._history_segments.append({"type": "split"})
            self._rows.append({"type": "ai", "segs": list(self._segments)})
        self._ai_bubble = None
        self._segments.clear()
        self._user_msgs.append(text)
        self._rows.append({"type": "user", "text": text})
        self._update_welcome()          # 发消息后欢迎介绍立即消失
        # 用户气泡：文字与拖入的图片/文件一并渲染进同一气泡
        if images or files:
            parts = ([f'<div style="font-size:14px;">{_esc(text).replace(chr(10), "<br/>")}</div>']
                     if text else [])
            parts += [f'<img src="{u}" width="200" style="border-radius:10px;'
                      'border:1px solid #000000;display:block;margin:10px 0;">' for u in images]
            for pth in files:
                fname = os.path.basename(pth)
                fsize = self._file_size_text(pth)
                parts.append(
                    f'<div style="display:inline-block;vertical-align:middle;'
                    f'background:#152036;border:1px solid #000000;border-radius:10px;'
                    'padding:7px 10px;margin:10px 8px 10px 0;">'
                    f'<img src="{self._file_thumb_data_url(pth)}" width="34" height="34" '
                    'style="vertical-align:middle;border-radius:6px;">'
                    f'<span style="vertical-align:middle;margin-left:8px;">'
                    f'<span style="color:{TEXT};font-size:13px;">{_esc(fname[:18])}</span>'
                    f'<br><span style="color:{TEXT_DIM};font-size:10px;">{_esc(fsize or "文件")}</span>'
                    f'</span></div>')
            src = "<br/>".join(parts)
            b = self._add_bubble(self._scale_user_html(src, self._font_scale()), "user", rich=True)
            b.setProperty("rich_src", src)
        else:
            self._add_bubble(text, "user")
        send_images = list(images)
        if shot:
            send_images.append(agent_screen.capture_screen_data_url(grid=True))
        if shot:
            self._segments.append({"type": "image", "url": shot, "caption": "已截屏"})
        self._user_stopped = False
        self._end_badge_shown = False
        self._think_done = False
        self._think_start = 0.0
        self._last_activity = time.time()
        self.input.clear()
        self.input.setFocus()
        est = agent_llm.estimate_tokens(text) + \
            agent_llm.estimate_image_tokens() * len(send_images)
        self.token_label.setText(f"~{est} tk")
        self._set_action_busy()   # 发送后按钮变转圈（可点击停止）
        self._clear_attachments()   # 发送后清空附件条
        self._commit_sess()       # segments 已重建，回写当前会话状态
        self._task_active = True
        # 模型路由：自动选择模式（下拉「自动选择」未手动指定模型）先由内置
        # agnes 评估任务难度（后台线程），评估后按难度+视觉需求自动选合适模型。
        if not self._model_override:
            self._eval_pending = (self._session_id, ai_text, send_images, skill_names)
            threading.Thread(target=self._assess_worker, daemon=True).start()
        else:
            self._launch_task(ai_text, send_images, skill_names,
                              self._resolve_effort(ai_text), sid=self._session_id)

    def _bg_send(self, sid: str, q: dict):
        """后台会话：直接在该会话引擎上启动排队消息任务（不渲染 UI）"""
        st = self._sess.get(sid)
        if not st:
            return
        segs = st["segments"]
        if segs:
            st["history_segments"].extend(segs)
            st["history_segments"].append({"type": "split"})
            st["rows"].append({"type": "ai", "segs": list(segs)})
        st["segments"] = []
        st["user_msgs"].append(q.get("text") or "")
        st["rows"].append({"type": "user", "text": q.get("text") or ""})
        st["task_active"] = True
        ai_text = q.get("ai_text") or q.get("text") or ""
        send_images = list(q.get("images") or [])
        if q.get("shot"):
            try:
                send_images.append(agent_screen.capture_screen_data_url(grid=True))
            except Exception:
                pass
        self._launch_task(ai_text, send_images, q.get("skill_names") or [],
                          self._resolve_effort(ai_text), sid=sid)

    def _persist_current(self):
        """保存当前会话：模型消息 + 界面气泡（segments/用户消息）+ 更新时间。
        模型上下文（含图片压缩，耗时）后台线程异步落盘，UI 线程只做轻量 JSON 快存，
        避免任务结束/切换会话时主线程阻塞。"""
        if not self._session_id:
            return
        d = self._sessions_dir()
        d.mkdir(parents=True, exist_ok=True)
        if self._engine:
            eng, sid = self._engine, self._session_id
            threading.Thread(target=lambda: eng.save_context(d / f"{sid}.json"),
                             daemon=True).start()
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
        """切换会话（多对话并发）：当前会话后台任务不中断；目标会话若已有内存态
        （可能仍在后台生成）直接恢复渲染，首次进入则后台读盘后一次性渲染。"""
        self._commit_sess()
        self._persist_current()
        self._session_id = sid
        lst = self._load_session_list()
        s = next((x for x in lst if x.get("id") == sid), None)
        self._session_name = s.get("name", "新对话") if s else "新对话"
        self._hide_spinner()
        while self.msg_lay.count() > 1:  # 清空消息流（保留末尾 stretch）
            item = self.msg_lay.takeAt(0)
            self._free_layout_item(item)
        self._bubble_widgets = []
        self._bubble_segs = {}
        st = self._sess.get(sid)
        if st is not None and (st["segments"] or st["rows"] or st["queued"]):
            # 内存态有实时内容（新建会话的任务/排队/后台生成中）：直接恢复，不覆盖
            st["loaded"] = True
            self._bind_sess(sid)
            self._render_history_all()
            self._end_badge_shown = False
            self._refresh_session_combo()
            self._update_welcome()
            self._scroll_bottom()
            self._update_queue_bar()
        else:
            # 首次进入（或内存态为空）：新建/复用内存态并后台读盘补齐历史
            st = self._new_sess_state(sid) if st is None else st
            self._sess[sid] = st
            self._bind_sess(sid)
            d = self._sessions_dir()
            eng = self._engine_for(sid)

            def _load():
                try:
                    eng.load_context(d / f"{sid}.json")
                except Exception:
                    pass
                segs, ums, rows = [], [], []
                data = {}
                try:
                    with open(d / f"{sid}.ui.json", encoding="utf-8") as f:
                        data = json.load(f)
                    segs, ums = data.get("segments") or [], data.get("user_msgs") or []
                except Exception:
                    pass
                rows = [r for r in (data.get("rows") or [])
                        if isinstance(r, dict) and r.get("type") in ("user", "ai")]
                self.switch_ready.emit(sid, segs, ums, rows)

            threading.Thread(target=_load, daemon=True).start()
        # 切到该会话后处理其挂起的确认/提问（后台会话不弹窗，切到前台才弹）
        self._flush_pending(sid)
        # 切换对话：复位排队编辑状态；todos 面板常显，刷新为全局任务清单
        self._cancel_queue_edit()
        self.todos_panel.update_todos(agent_tools.load_todos())

    def _finish_switch(self, sid: str, segs: list, ums: list, rows: list):
        """会话切换收尾（主线程）：用后台线程读到的数据一次性渲染"""
        if sid != self._session_id:
            return   # 用户已切走，丢弃过期加载，防止覆盖当前视图
        st = self._sess[sid]
        # 读盘期间用户已发送/排队/后台生成产生了实时内容 → 以实时内容为准，不覆盖
        if st["segments"] or st["rows"] or st["queued"]:
            st["loaded"] = True
            self._bind_sess(sid)
            self._render_history_all()
            self._end_badge_shown = False
            self._refresh_session_combo()
            self._update_welcome()
            self._scroll_bottom()
            self._update_queue_bar()
            return
        st["user_msgs"] = list(ums)
        st["rows"] = list(rows)
        # 加载时过滤掉旧版本中持久化的“已停止”提示小字，避免重启后仍显示
        st["history_segments"] = [
            seg for seg in (segs or [])
            if not (seg.get("type") == "mark" and seg.get("html") == "已停止")
        ]
        st["segments"] = []
        st["loaded"] = True
        self._bind_sess(sid)
        # 旧版文件无 rows：按段流重建交错行，保证本会话后续持久化不回退
        if not self._rows:
            self._rows = self._reconstruct_rows()
        self._commit_sess()
        self._render_history_all()   # 用户气泡与 AI 回复按轮次交错重绘（每条 AI 回复一个气泡）
        self._end_badge_shown = False
        self._refresh_session_combo()
        self._update_welcome()
        self._scroll_bottom()
        self._update_queue_bar()

    def _new_session(self, *_):
        """新开对话：保存当前 → 创建空会话（当前会话后台任务不中断，多对话并发）"""
        self._commit_sess()
        self._persist_current()
        s = self._create_session()
        self._session_id = s["id"]
        self._session_name = "新对话"
        self._sess[s["id"]] = self._new_sess_state(s["id"])
        self._bind_sess(s["id"])
        self._ai_bubble = None
        self._seg_cache.clear()
        self._hide_spinner()
        while self.msg_lay.count() > 1:
            item = self.msg_lay.takeAt(0)
            self._free_layout_item(item)
        self._bubble_widgets = []
        self._bubble_segs = {}
        self._refresh_session_combo()
        self._update_welcome()
        self._add_status("已开启新对话，上下文与旧对话隔离", ACCENT)
        self._scroll_bottom()
        self._update_queue_bar()
        # 新建对话：todos 面板常显，刷新为全局任务清单（无任务显示提示语）
        self.todos_panel.update_todos(agent_tools.load_todos())

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

    # ---------- 工作目录（QSettings 持久化，重启恢复；设置在设置页调整） ----------
    def _restore_workdir(self):
        """启动时恢复上次选择的工作目录；无有效目录则使用默认提示"""
        saved = str(self._settings.value("agent_workdir", ""))
        if saved and os.path.isdir(saved):
            self._apply_workdir(saved)
        else:
            self._apply_workdir("")

    def _apply_workdir(self, d: str):
        """应用工作目录：写入 agent_tools 全局"""
        agent_tools.set_workdir(d)

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
        if wide:
            self.session_combo.setMinimumWidth(180)
            self.session_combo.setMaximumWidth(260)
        else:
            self.session_combo.setMinimumWidth(110)
            self.session_combo.setMaximumWidth(180)
        self._refresh_meta()   # token 文本按当前模式重渲染

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_topbar_layout()
        # 底部输入行等比缩放 + todos 面板限高（随窗口高度变化，全屏自动放大）
        self._apply_bottom_scale()
        self._apply_todos_limit()
        # 气泡宽度同步（轻量 setter）；文本/截图重渲染交给防抖定时器合并。
        # 宽度未变化（仅高度变动）时直接跳过，避免最大化↔正常来回切换时反复遍历气泡
        mw = self._bubble_max_width()
        mn = self._bubble_min_width()
        if mw == self._last_bw and mn == self._last_bmn:
            return
        self._last_bw, self._last_bmn = mw, mn
        for b in self._bubble_widgets:
            try:
                b.setMaximumWidth(mw)
                # 仅 AI 气泡保持半页最小宽度；用户气泡按内容自适应
                if b.property("align") == "ai":
                    b.setMinimumWidth(mn)
                else:
                    b.setMinimumWidth(0)
            except RuntimeError:
                pass
        self._resize_timer.start()

    def _apply_bottom_scale(self):
        """底部输入行等比缩放：普通窗口(基准高660)为紧凑值，窗口越高按比例放大"""
        k = max(1.0, self.height() / 660.0)
        if abs(k - self._last_scale) < 0.01:
            return
        self._last_scale = k
        self._btn_icon_sz = int(16 * k)
        s = int(34 * k)
        self.input.setMinimumHeight(int(32 * k))
        self.input.setMaximumHeight(int(110 * k))
        for b in (self.attach_btn, self.action_btn):
            b.setFixedSize(s, s)
            b.setIconSize(QSize(self._btn_icon_sz, self._btn_icon_sz))

    def _apply_todos_limit(self):
        """todos 面板限高 = 窗口高度约 1/3（底部区域按内容贴底，聊天区占满其余）"""
        limit = max(120, int(self.height() * 0.33))
        if limit != self._last_todos_limit:
            self._last_todos_limit = limit
            self.todos_panel._limit = limit
            self.todos_panel._resize_to_content()

    def _rebuild_bubbles_after_resize(self):
        """resize 停止后重渲染。字体固定 14px 不随窗口缩放（_font_scale 恒 1.0），
        唯一随宽度变化的是截图缩略图宽度（img_w），因此：
        1. img_w 未跨阈值 → 全部跳过；
        2. 只重建含截图（image 段）的 AI 气泡，其余气泡交给 QLabel 自动重排。"""
        img_w = max(200, int(self._bubble_max_width() * 0.4))
        if img_w == self._last_img_w:
            return
        self._last_img_w = img_w
        ai_bubbles = [b for b in self._bubble_widgets
                      if b.property("align") == "ai" and self._bubble_alive(b)]
        for b, g in zip(ai_bubbles, self._split_groups()):
            if not any(seg["type"] == "image" for seg in g):
                continue
            try:
                b.setText(self._build_ai_html(g))
            except RuntimeError:
                pass

    def _ensure_taskbar_entry(self):
        """强制任务栏缩略图：带 parent 的顶层窗口在 Windows 属于 owned window，
        默认不显示任务栏按钮；显式追加 WS_EX_APPWINDOW 扩展样式后，
        最小化也会保留独立任务栏缩略图，可点击定位/恢复面板。"""
        try:
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            if not (ex & WS_EX_APPWINDOW):
                user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex | WS_EX_APPWINDOW)
        except Exception:
            pass

    def showEvent(self, e):
        super().showEvent(e)   # 统一补丁已为 QDialog 深色化标题栏
        # 强制任务栏缩略图（owned window 默认不显示，需手动加 WS_EX_APPWINDOW）
        self._ensure_taskbar_entry()
        # 面板复用（关闭再打开不销毁），滚动位置不会自动重置 → 打开时自动滚到对话底部
        QTimer.singleShot(0, self._scroll_bottom)
        QTimer.singleShot(300, self._scroll_bottom)
        # 默认正常窗口大小（__init__ 中已 resize），不再强制最大化
        # 管理员权限：Windows UIPI 拦截普通 Explorer 的 OLE 拖放，改用 WM_DROPFILES 原生通道
        print(f"[dnd] showEvent is_admin={is_admin()} _admin_dnd={self._admin_dnd}", flush=True)
        if is_admin() and not self._admin_dnd:
            QTimer.singleShot(150, self._setup_admin_dnd)
            QTimer.singleShot(600, self._setup_admin_dnd)   # 兜底重试：窗口完全就绪后再注册一次
        else:
            print("[dnd] 非管理员运行：走 Qt 原生拖放", flush=True)

    def _add_bubble(self, text: str, align: str, rich: bool = False,
                    animate: bool = True) -> QLabel:
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        # 支持文本选择 + 富文本链接点击（思考过程折叠/展开等自定义链接）
        bubble.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.LinksAccessibleByMouse)
        bubble.setMaximumWidth(self._bubble_max_width())
        # 仅 AI 气泡设最小宽度（让截图/内容覆盖半页）；用户气泡按内容自适应，避免短句异常拉长
        if align == "ai":
            bubble.setMinimumWidth(self._bubble_min_width())
            # 右键菜单：朗读这条回复（从气泡段中提取正文文本后台合成播放）
            bubble.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            bubble.customContextMenuRequested.connect(
                lambda pos, b=bubble: self._on_ai_bubble_menu(b, pos))
        bubble.setProperty("align", align)
        self._bubble_widgets.append(bubble)
        if align == "user":
            # 用户消息：默认纯文本；带图片时用富文本渲染缩略图（不显示源文本）
            bubble.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
            bubble.setStyleSheet(f"background: {USER_BG}; color: white;"
                                 "border: none; border-radius: 16px;"
                                 "padding: 10px 14px; font-size: 14px;")
        else:
            bubble.setTextFormat(Qt.TextFormat.RichText)    # AI 消息富文本（思考/操作/正文）
            bubble.setStyleSheet(f"background: rgba(30, 30, 30, 0.78); color: {TEXT};"
                                 f"border: 1px solid {BORDER_SOFT}; border-radius: 16px;"
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
        self._place_spinner_bottom()   # 新气泡加入后动画行移到最底部（AI 气泡下方外侧）
        if animate:
            self._fade_in(bubble, self)   # 历史批量加载跳过动画，避免逐条淡入造成卡顿
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
        self._place_spinner_bottom()   # 动画行始终保持在消息流最底部
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
        self._place_spinner_bottom()   # 动画行始终保持在消息流最底部
        self._scroll_bottom()

    def _place_spinner_bottom(self):
        """把任务动画行移到消息流最底部（AI 气泡在下方滚动不会盖住它）"""
        if self._spinner_row is None:
            return
        for i in range(self.msg_lay.count()):
            if self.msg_lay.itemAt(i).layout() is self._spinner_row:
                self.msg_lay.takeAt(i)
                break
        self.msg_lay.insertLayout(self.msg_lay.count() - 1, self._spinner_row)
        self._scroll_bottom()   # 移动后确保滚到底部，动画行不被遮挡

    # ---------- 发送/停止融合按钮状态与转圈动画 ----------
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

    def _set_action_idle(self):
        """空闲：输入框为空显示灰蓝发送按钮，有内容切换深蓝（可发送）"""
        self._action_anim.stop()
        self.action_btn.setIcon(_line_icon("send", self._btn_icon_sz, "#FFFFFF"))
        self.action_btn.setStyleSheet(
            _BTN_PRIMARY if self.input.toPlainText().strip() else _BTN_DIM)
        self.action_btn.setEnabled(True)
        self.action_btn.setToolTip("发送")

    def _sync_action_style(self, *_):
        """输入框内容变化：空闲时刷新发送按钮配色（空→灰蓝，有内容→深蓝）"""
        ep = self._eval_pending
        if not self._task_active and not (ep is not None and ep[0] == self._session_id):
            self._set_action_idle()

    def _set_action_busy(self):
        """运行中：白色转圈动画（可点击停止）"""
        self._action_anim_angle = 0
        self.action_btn.setStyleSheet(_BTN_PRIMARY)
        self.action_btn.setEnabled(True)
        self.action_btn.setToolTip("停止当前任务")
        self._action_anim.start()

    def _set_action_stopping(self):
        """停止中：红底转圈（禁用）"""
        self._action_anim_angle = 0
        self.action_btn.setStyleSheet(_BTN_DANGER)
        self.action_btn.setEnabled(False)
        self.action_btn.setToolTip("停止中…")
        self._action_anim.start()

    def _tick_action_anim(self):
        self._action_anim_angle += 30
        self.action_btn.setIcon(self._spinner_icon(self._action_anim_angle, "#FFFFFF"))

    def _tick_combo_spin(self):
        """会话下拉转圈动画：有运行中/待确认会话才刷新视图（避免无谓重绘）"""
        busy = False
        for st in self._sess.values():
            if st.get("task_active") or st.get("pending_confirm") or st.get("pending_ask"):
                busy = True
                break
        if not busy:
            return
        self._spin_angle = (self._spin_angle + 30) % 360
        try:
            self.session_combo.view().viewport().update()
        except Exception:
            pass

    def _stop_button_anim(self):
        """任务结束：停止动画并恢复空闲发送状态"""
        self._set_action_idle()

    def _on_action_clicked(self, *_):
        """融合按钮点击：空闲→发送；运行中→停止"""
        ep = self._eval_pending
        if self._task_active or (ep is not None and ep[0] == self._session_id):
            self._stop()
        else:
            self._send()

    def _scroll_bottom(self):
        # 流式高频调用时合并：100ms 定时器批量滚动一次 + 400ms 兜底
        # （气泡高度与布局异步稳定后确保滚到最底部），避免每个 token 触发滚动重排
        if self._scroll_pending:
            return
        self._scroll_pending = True
        QTimer.singleShot(100, self._do_scroll_bottom)
        QTimer.singleShot(400, self._do_scroll_bottom)

    def _do_scroll_bottom(self):
        self._scroll_pending = False
        bar = self.msg_area.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ---------- AI 气泡内容（思考 / 操作 / 正文 一体化） ----------
    def _ensure_ai_bubble(self):
        if self._ai_bubble is None or not self._bubble_alive(self._ai_bubble):
            self._ai_bubble = self._add_bubble("", "ai")
            self._ai_bubble.linkActivated.connect(self._on_bubble_link)
        # 每次同步段列表引用：新回复可能复用旧气泡，注册表必须指向当前 _segments，
        # 否则点击折叠/展开链接会在过期列表里找不到段而失效
        self._bubble_segs[id(self._ai_bubble)] = self._segments
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
        """把一组 AI 段渲染为富文本（思考/操作/结果/截图/正文/标记）。

        性能：每段按内容签名缓存渲染结果（_seg_cache），流式刷新时只重算
        正在增长的段，其余段直接复用，避免整泡每 60ms 全量 markdown 重渲染
        （长回复时 O(n²) 导致输出明显卡顿）。"""
        s = self._font_scale()
        f_main, f_sm, f_op = int(14 * s), int(11 * s), int(13 * s)
        img_w = max(200, int(self._bubble_max_width() * 0.4))   # 截图缩略图随气泡宽度放大（约占内容区半宽）
        parts = []
        for i, seg in enumerate(segs):
            t = seg["type"]
            if t == "split":
                continue
            sig = (i, img_w) + _seg_sig(seg)
            cached = self._seg_cache.get(id(seg))
            if cached is not None and cached[0] == sig:
                parts.append(cached[1])
                continue
            html = self._render_seg_html(seg, i, t, f_main, f_sm, f_op, img_w)
            if html is None:
                continue
            self._seg_cache[id(seg)] = (sig, html)
            if len(self._seg_cache) > 400:
                # 按插入序裁剪只保留最近 200 项：长会话反复加载时缓存不再无限膨胀，
                # 避免大 dict 拖慢哈希查找与占内存（当前气泡的热段始终会重新入缓存）
                for _k in list(self._seg_cache)[: len(self._seg_cache) - 200]:
                    del self._seg_cache[_k]
            parts.append(html)
        return "".join(parts)

    def _render_seg_html(self, seg: dict, i: int, t: str,
                         f_main: int, f_sm: int, f_op: int, img_w: int):
        """渲染单个段为富文本（_build_ai_html 的逐段实现，内容不变时被缓存跳过）"""
        if t == "think":
            body = seg.get("html", "") or ""
            if len(body) > 1500:      # 思考全文过长时显示截断
                body = "…" + body[-1500:]
            if seg.get("collapsed"):
                # 折叠态：一行提示，点击展开
                return (
                    f'<div style="color:{TEXT_DIM};font-size:{f_sm}px;margin-top:2px;">'
                    f'<a href="think:toggle" style="color:{ACCENT};text-decoration:none;">'
                    f'思考过程（已折叠 · 点击展开）</a></div>')
            # 展开态：标题在上，思考内容在下，末尾可收起
            return (
                f'<div style="color:{TEXT_DIM};font-size:{f_sm}px;margin:2px 0;">'
                f'思考过程&nbsp;'
                f'<a href="think:toggle" style="color:{TEXT_DIM};font-size:{f_sm}px;'
                f'text-decoration:none;">收起 ▲</a></div>'
                f'<div style="color:{TEXT_DIM};font-size:{f_sm}px;font-style:italic;'
                f'border-left:2px solid {BORDER};padding:2px 10px;'
                f'margin:0 0 8px 6px;">{body}</div>')
        if t == "op":
            return (f'<div style="color:{ACCENT};font-size:{f_op}px;'
                    f'font-family:Consolas;margin-top:16px;">{seg["html"]}</div>')
        if t == "result":
            # 命令执行结果先输出（默认展开，用户可直接看到），完成后可手动收起/展开
            #（带段索引，支持同气泡多条命令结果独立折叠）
            if seg.get("collapsed"):
                return (
                    f'<div style="color:{TEXT_DIM};font-size:{f_sm}px;margin-top:2px;">'
                    f'<a href="result:toggle:{i}" style="color:{ACCENT};text-decoration:none;">'
                    f'执行结果（已折叠 · 点击展开）</a></div>')
            return (
                f'<div style="color:{TEXT_DIM};font-size:{f_sm}px;margin:2px 0;">'
                f'执行结果&nbsp;'
                f'<a href="result:toggle:{i}" style="color:{TEXT_DIM};font-size:{f_sm}px;'
                f'text-decoration:none;">收起 ▲</a></div>'
                f'<div style="color:{TEXT_DIM};font-size:{f_op}px;font-family:Consolas;'
                f'border-left:3px solid {BORDER};padding:2px 10px;'
                f'margin:0 0 4px 14px;">'
                f'{_linkify(seg["html"])}</div>')
        if t == "progress":
            # 下载进度条：AI 气泡内实时渲染（面板轮询快照更新）
            pct = max(0, min(100, int(seg.get("pct") or 0)))
            bw = 220
            fill = int(bw * pct / 100)
            return (
                f'<div style="margin:12px 0 6px;">'
                f'<div style="background:{BG};border:1px solid {BORDER};border-radius:6px;'
                f'height:10px;width:{bw}px;">'
                f'<div style="background:{ACCENT};height:10px;width:{fill}px;'
                'border-radius:6px;"></div></div>'
                f'<div style="color:{TEXT_DIM};font-size:11px;margin-top:3px;">'
                f'{_esc(seg.get("text") or "下载中…")}</div></div>')
        if t == "image":
            # 截图融入主对话气泡：圆角缩略图 + 细边框，不显示“已截屏”等提示小字
            url = seg.get("url", "")
            return (
                f'<div style="padding-left:30px;">'
                f'<img src="{url}" width="{img_w}" style="border-radius:10px;'
                'border:1px solid #000000;display:block;margin:12px 0 12px 0;"></div>')
        if t == "text":
            seg.setdefault("_rd_cache", {})
            body = _render_text_incr(seg["raw"], seg["_rd_cache"])
            return (f'<div style="color:{TEXT};font-size:{f_main}px;">{body}</div>')
        if t == "mark":
            return (f'<div style="color:{TEXT_DIM};font-size:{f_sm}px;">'
                    f'{_linkify(seg["html"])}</div>')
        if t == "sub":
            # 子 Agent 输出块：与主 Agent 共用同一气泡，深蓝标签 + 缩进内容区分来源
            stitle = _esc(seg.get("title", "子Agent"))
            body = _esc(seg.get("raw", "")).replace("\n", "<br/>")
            return (
                f'<div style="margin:6px 0 2px;">'
                f'<div style="color:{ACCENT};font-size:{f_op}px;">'
                f'子Agent · {stitle}</div>'
                f'<div style="color:{TEXT_DIM};font-size:{f_sm}px;font-family:Consolas;'
                f'border-left:2px solid {ACCENT};padding:2px 10px;'
                f'margin:2px 0 4px 6px;">{body}</div></div>')
        return None

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
        用户消息与 AI 回复天然成对，杜绝数量错位导致的顺序错乱。
        批量插入期间暂停整个滚动区重绘，一次性重建后再统一刷新，
        避免每条气泡插入都触发整窗重排版导致长对话加载卡顿。"""
        viewport = self.msg_area.viewport()
        viewport.setUpdatesEnabled(False)
        try:
            while self.msg_lay.count() > 1:   # 清空消息流（保留末尾 stretch）
                item = self.msg_lay.takeAt(0)
                self._free_layout_item(item)
            self._bubble_widgets = []
            self._bubble_segs = {}
            self._ai_bubble = None
            for r in (self._rows or self._reconstruct_rows()):
                if r.get("type") == "user":
                    self._add_bubble(r.get("text", ""), "user", animate=False)
                else:
                    self._add_ai_group_bubble(r.get("segs") or [], animate=False)
            # 未归档的当前回复段（渲染时恒为空，防御保留）
            if self._segments:
                self._add_ai_group_bubble(self._segments)
        finally:
            viewport.setUpdatesEnabled(True)
            viewport.update()

    def _add_ai_group_bubble(self, segs: list, animate: bool = True):
        """把一组 AI 段渲染为一条独立气泡，并设为当前气泡（新回复流式续接）"""
        b = self._add_bubble("", "ai", animate=animate)
        try:
            b.setText(self._build_ai_html(segs))
        except RuntimeError:
            pass
        self._bubble_segs[id(b)] = segs
        b.linkActivated.connect(self._on_bubble_link)
        self._ai_bubble = b

    # ---------- AI 气泡右键：朗读回复 ----------
    @staticmethod
    def _bubble_read_text(segs: list) -> str:
        """从 AI 气泡段中提取可朗读的正文（text 段 raw 拼接，剔除思考/操作/结果）"""
        parts = []
        for seg in segs or []:
            if seg.get("type") == "text":
                raw = str(seg.get("raw", "") or "").strip()
                if raw:
                    parts.append(raw)
        return "\n".join(parts).strip()

    def _on_ai_bubble_menu(self, bubble, pos):
        """AI 气泡右键菜单：朗读这条回复"""
        segs = self._bubble_segs.get(id(bubble))
        text = self._bubble_read_text(segs)
        menu = QMenu(self)
        read_act = menu.addAction("朗读这条回复")
        if text:
            menu.addSeparator()
            copy_act = menu.addAction("复制全文")
        act = menu.exec(bubble.mapToGlobal(pos))
        if act is read_act:
            if not text:
                self._add_status("该回复没有可朗读的正文", WARN)
                return
            self._read_aloud(text)
        elif text and act is copy_act:
            QApplication.clipboard().setText(text)
            self._add_status("已复制回复全文", ACCENT)

    def _read_aloud(self, text: str):
        """后台线程合成并朗读文本（复用 TTS 播放器，避免阻塞 UI）"""
        def work():
            if not agent_tools._tts_play_start():
                self._add_status("朗读不可用：pygame 未初始化", WARN)
                return
            try:
                agent_tts.synthesize_stream(
                    text, voice_id="", on_chunk=agent_tools._tts_play_chunk)
                agent_tools._tts_play_flush()
                agent_tools._tts_play_finish()
            except Exception as e:
                agent_tools._tts_play_stop()
                self._add_status(f"朗读失败：{e}", ERR)
        self._add_status("正在朗读该回复…", ACCENT)
        threading.Thread(target=work, daemon=True).start()

    def _on_bubble_link(self, url: str):
        """气泡内链接点击：折叠/展开思考过程（仅局部重渲染该气泡）"""
        if url == "think:toggle":
            bubble = self.sender()
            segs = self._bubble_segs.get(id(bubble)) if bubble is not None else None
            if not segs:
                return
            for seg in segs:
                if seg.get("type") == "think":
                    seg["collapsed"] = not seg.get("collapsed", False)
                    break
            try:
                bubble.setText(self._build_ai_html(segs))
            except RuntimeError:
                pass
            return
        if url.startswith("result:toggle"):
            # 链接形如 result:toggle:{段索引}，定位到对应命令结果段（同一气泡可多条命令独立折叠）
            bubble = self.sender()
            segs = self._bubble_segs.get(id(bubble)) if bubble is not None else None
            if not segs:
                return
            try:
                idx = int(url.split(":", 2)[2])
            except (IndexError, ValueError):
                return
            if not (0 <= idx < len(segs)) or segs[idx].get("type") != "result":
                return
            segs[idx]["collapsed"] = not segs[idx].get("collapsed", False)
            try:
                bubble.setText(self._build_ai_html(segs))
            except RuntimeError:
                pass
            return
        # 普通链接：URL 打开浏览器；文件路径用系统默认程序/资源管理器打开
        url = _html.unescape(url)
        try:
            if url.startswith(("http://", "https://")):
                webbrowser.open(url)
            elif url.startswith("file://"):
                s = url[len("file://"):]
                k = len(s) - len(s.lstrip("/"))
                s = s.lstrip("/")
                # UNC（开头 ≥2 个 /）→ \\server\share；盘符 /C:/x → C:\x
                path = ("\\\\" + s.replace("/", os.sep)) if k >= 2 else s.replace("/", os.sep)
                os.startfile(path)
            else:
                os.startfile(url)
        except Exception as e:
            print(f"[agent] 打开链接失败: {url} → {e}")

    def _refresh_ai_html(self):
        """节流刷新 AI 气泡：流式 token 高频调用时合并为批量 setText 一次，
        避免每个 token 全量重建 HTML + 触发整条消息区重排版导致输出卡顿。
        自适应节流：正文越长重排版越贵（Qt 富文本 setText 为全量解析），
        逐步放宽刷新间隔，保长输出流畅。"""
        if self._ai_bubble is None or self._html_dirty:
            return
        self._html_dirty = True
        raw = (self._segments[-1].get("raw", "")
               if self._segments and self._segments[-1].get("type") == "text" else "")
        n = len(raw)
        # 自适应节流：正文越长整段全量 markdown 重渲染越贵（O(n) 每次、累计 O(n²)），
        # 逐步放宽刷新间隔摊薄重算次数，保长输出流畅（dirty 防抖会合并期间的所有增量）
        if n < 8000:
            delay = 60
        elif n < 24000:
            delay = 120
        elif n < 60000:
            delay = 250
        elif n < 150000:
            delay = 400
        else:
            delay = 600
        QTimer.singleShot(delay, self._apply_refresh_ai_html)

    def _apply_refresh_ai_html(self):
        self._html_dirty = False
        if self._ai_bubble is None:
            return
        try:
            self._ai_bubble.setText(self._build_ai_html(self._segments))
        except RuntimeError:
            self._ai_bubble = None

    # ---------- 滑动动画 + 思考过程（思考内容在 AI 气泡开头，完成后折叠） ----------
    def _ensure_spinner(self):
        """创建/显示任务行：••• 来回滑动动画 + 状态文字（位于 AI 气泡底部外侧，随消息流滚动）"""
        if self._spinner_row is not None:
            return
        self._spinner = _TypingDots()
        self._spinner_lbl = QLabel("AI 思考中…")
        self._spinner_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        top.addWidget(self._spinner)
        top.addWidget(self._spinner_lbl)
        top.addStretch(1)

        self._spinner_row = QVBoxLayout()
        self._spinner_row.setContentsMargins(0, 0, 0, 0)
        self._spinner_row.setSpacing(2)
        self._spinner_row.addLayout(top)
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
        self._spinner_row = None

    # ---------- /compact 压缩打字指示器（独立行，与任务转圈互不干扰） ----------
    def _ensure_compact_row(self):
        """压缩上下文期间在消息流中显示打字指示器行"""
        row = self._compact_row
        if row is not None:
            # 会话切换/清空对话可能已把该行从布局移除，引用失效时重建
            if any(self.msg_lay.itemAt(i).layout() is row
                   for i in range(self.msg_lay.count())):
                return
            self._compact_row = None
        dots = _TypingDots()
        lbl = QLabel("正在压缩上下文…")
        lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        top.addWidget(dots)
        top.addWidget(lbl)
        top.addStretch(1)
        self._compact_row = QVBoxLayout()
        self._compact_row.setContentsMargins(0, 0, 0, 0)
        self._compact_row.setSpacing(2)
        self._compact_row.addLayout(top)
        self.msg_lay.insertLayout(self.msg_lay.count() - 1, self._compact_row)
        self._scroll_bottom()

    def _hide_compact_row(self):
        """压缩结束/清空时移除打字指示器行"""
        row = self._compact_row
        self._compact_row = None
        if row is None:
            return
        for i in range(self.msg_lay.count()):
            if self.msg_lay.itemAt(i).layout() is row:
                self._free_layout_item(self.msg_lay.takeAt(i))
                break

    def _start_think(self):
        """任务进行中：显示转圈；首轮思考重置计时"""
        if not self._think_done:
            self._think_start = time.time()
            if self._spinner_lbl is not None:
                self._spinner_lbl.setText("AI 思考中…")
        self._ensure_spinner()

    def _finish_thinking(self):
        """思考完成（开始输出正文/工具调用）：转圈行显示'已思考 x 秒'，气泡内思考自动折叠"""
        if self._think_done:
            return
        self._think_done = True
        if self._spinner_lbl is not None and self._think_start:
            el = int(time.time() - self._think_start)
            self._spinner_lbl.setText(f"已思考 {el} 秒")
        if self._segments and self._segments[0].get("type") == "think":
            self._segments[0]["collapsed"] = True   # 思考完成后自动折叠，可点击展开
            self._refresh_ai_html()

    def _on_reasoning(self, s: str):
        """流式思考过程：追加到当前 AI 气泡开头的思考区块（转义为富文本）"""
        if self._think_done:
            return
        self._last_activity = time.time()
        self._ensure_ai_bubble()
        if not self._segments or self._segments[0].get("type") != "think":
            self._segments.insert(0, {"type": "think", "html": ""})
        self._segments[0]["html"] += _esc(s)
        self._refresh_ai_html()
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

    def _open_settings(self, *_):
        """打开 AI 设置；保存后应用（刷新纯文本/记忆状态，空闲时重建引擎）"""
        dlg = _AgentSettingsDialog(parent=self)
        if dlg.exec():
            self._apply_agent_settings()

    def _apply_agent_settings(self):
        """设置变更后：刷新模式/工作目录/多模型/力度/纯文本状态；
        引擎单例复用，仅更新 LLM 连接参数与运行时开关（保留对话上下文）。"""
        s = agent_skills.load_settings()
        self._model_cfg = agent_llm.load_model_config()
        self._sync_model_combo()   # 模型/服务商变更后即时重建输入框右侧下拉
        self._effort = self._model_cfg.get("effort", "medium")
        self._auto_effort = bool(self._model_cfg.get("auto_effort", True))
        self._mode = str(self._settings.value("agent_mode", "ask"))   # 执行模式在设置页调整后同步
        self._restore_workdir()   # 工作目录在设置页调整后同步
        self._refresh_text_only()
        self._memory_enabled = bool(s.get("memory_enabled", True))
        if self._text_only:
            self._add_status("纯文本模型：已禁用图片上传与截图工具", WARN)
        if self._sess:
            busy = any(st.get("engine") and st["engine"]._thread
                       and st["engine"]._thread.is_alive() for st in self._sess.values())
            if busy:
                self._add_status("当前有任务进行中，新设置将在任务结束后生效", WARN)
                return
            # 复用引擎：仅更新连接参数与开关，不重建 → 对话上下文（_messages）
            # 与 token 统计完整保留；每次发送前 _launch_task 还会按模型路由重设连接参数
            cfg = self._llm_config()
            for st in self._sess.values():
                eng = st.get("engine")
                if not eng:
                    continue
                eng.llm.base_url = (cfg.get("base_url") or agent_llm.DEFAULT_BASE_URL).rstrip("/")
                eng.llm.api_key = cfg.get("api_key") or agent_llm.DEFAULT_API_KEY
                eng.llm.protocol = cfg.get("protocol", "chat")
                eng.llm.model = cfg.get("model") or agent_llm.DEFAULT_MODEL
                eng.text_only = self._text_only
                eng.memory_enabled = self._memory_enabled
                eng.direct = self._mode == "yolo"
            return
        self._ensure_engine()

    # ---------- 工作力度 / 模型路由 ----------
    def _refresh_text_only(self):
        """纯文本模型识别：手动指定模型时以该模型为准；自动模式全部已配置模型
        均为纯文本时才全局禁用视觉（混配模型时按本次实际使用的模型逐次判断）"""
        m = self._model_override
        if m:
            self._text_only = agent_llm.is_text_only_model(m)
            return
        cfg = self._model_cfg
        models = cfg.get("models") or [cfg.get("model") or agent_llm.DEFAULT_MODEL]
        self._text_only = all(agent_llm.is_text_only_model(x) for x in models)


    def _resolve_effort(self, text: str) -> str:
        """本次任务使用的工作力度：自动开关开启时按任务难度估算，否则用手动力度"""
        if self._auto_effort:
            return agent_llm.estimate_effort(text)
        return self._effort


    def _sync_model_combo(self):
        """重建输入框右侧模型下拉：首项「自动选择」+ 所有服务商的全部模型（跨服务商可切换）"""
        cfg = self._model_cfg
        providers = cfg.get("providers") or []
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItem("自动选择", None)
        for p in providers:
            pname = p.get("name", "服务商")
            for x in p.get("models") or []:
                self.model_combo.addItem(f"{pname} - {x}", (pname, x))
        # 恢复当前选中（手动指定模型）
        if self._model_override:
            # 注意：QComboBox.findData 对 Python tuple 的 QVariant 比较不可靠
            # （tuple 会转换后比较失败返回 -1），这里改用 Python 层逐项比较
            target = (self._model_override_provider, self._model_override)
            idx = next((i for i in range(self.model_combo.count())
                        if self.model_combo.itemData(i) == target), -1)
            if idx < 0:      # 手动指定模型已不在列表：清除覆盖回到自动路由
                self._model_override = None
                self._model_override_provider = ""
                self._settings.setValue("agent_last_model", "")
                idx = 0
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setCurrentIndex(0)
        self.model_combo.blockSignals(False)

    def _provider_for_model(self, model: str) -> str:
        """返回包含指定模型的服务商名（找不到返回空串）"""
        for p in (self._model_cfg.get("providers") or []):
            if model in (p.get("models") or []):
                return p.get("name", "")
        return ""

    def _on_model_combo(self, idx):
        """手动切换模型：选中具体模型则本次发送使用其所属服务商；选「自动」回到力度路由"""
        if idx < 0:
            return
        val = self.model_combo.itemData(idx)
        if val:
            self._model_override = val[1]
            self._model_override_provider = val[0]
        else:
            self._model_override = None
            self._model_override_provider = ""
        self._settings.setValue("agent_last_model", self._model_override or "")   # 记住选择，重启恢复
        self._refresh_text_only()   # 切换模型立即更新纯文本判断（粘贴图片/附件过滤实时生效）
        # 切换模型不清空上下文：当前对话历史继续沿用，仅后续轮次使用新模型

    def _reconnect_mcp(self):
        threading.Thread(target=self._init_mcp, daemon=True).start()

    # ---------- 命令补全（/ 展示全部命令 + 内联预测） ----------
    def _all_commands(self) -> list:
        """所有可斜杠调用项：系统命令（/clear、/compact）+ 全部技能（隐藏内置工具命令）"""
        cmds = ["/compact", "/clear"]
        cmds += [f"/{s.get('name')}" for s in agent_skills.load_skills() if s.get("name")]
        return cmds

    def _cmd_desc(self, cmd: str) -> str:
        """命令描述（用于命令条 tooltip）"""
        name = cmd.lstrip("/").lower()
        skills = {s.get("name", "").strip().lower(): s
                  for s in agent_skills.load_skills()}
        s = skills.get(name)
        if s:
            return s.get("description", "")
        for t in agent_tools.TOOLS:
            if t["function"]["name"].lower() == name:
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

    def _update_cmd_suggestions(self, *_):
        # QPlainTextEdit 的 textChanged 无参数，需自行读取当前文本
        text = self.input.toPlainText()
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

    def _cmd_list_qss(self, pad: str = "4px") -> str:
        """命令候选框样式；单行时容器上内边距清零使文字上移"""
        return (
            f"QListWidget {{ background: {PANEL}; color: {ACCENT};"
            f"border: 1px solid {BORDER}; border-radius: 8px;"
            f"font-size: 13px; padding: {pad}; }}"
            f"QListWidget::item {{ padding: 6px 12px 6px 12px; border-radius: 6px; }}"
            f"QListWidget::item:hover {{ background: {HOVER}; }}"
            f"QListWidget::item:selected {{ background: {ACCENT}; color: #FFFFFF; }}")

    def _resize_cmd_list(self):
        """命令列表高度随显示条数自适应：最多 5 行，最少 1 行；单行时去掉容器上内边距，文字上移"""
        count = self.cmd_list.count()
        row_h = self.cmd_list.sizeHintForRow(0)
        if row_h <= 0:
            row_h = 30   # 兜底：13px 字体 + item 上下内边距 12px
        self.cmd_list.setFixedHeight(min(count, 5) * row_h)
        # 单行时容器上内边距 4px→0px，文字整体上移 4px
        self.cmd_list.setStyleSheet(
            self._cmd_list_qss("0px 4px 4px 4px" if count == 1 else "4px"))

    def _on_cmd_selected(self, item):
        """点击候选框选中命令：填入输入框，光标停在命令名末尾（便于继续输入参数）"""
        self._fill_command(item.text())

    def _complete_cmd(self) -> bool:
        """Tab 补全命令：按当前输入前缀补全为首个候选，光标停在命令名末尾"""
        item = self.cmd_list.item(0)
        if item is None:
            return False
        self._fill_command(item.text())
        return True

    def _fill_command(self, cmd: str):
        """把命令写入输入框并把光标移到命令末尾（textChanged 会重建候选列表，随后隐藏）"""
        self.input.setPlainText(cmd)
        cur = self.input.textCursor()
        cur.setPosition(len(cmd))
        self.input.setTextCursor(cur)
        self.input.setFocus()
        self.cmd_list.hide()

    # ---------- 发送 / 停止 ----------
    def _llm_config(self) -> dict:
        # 多模型/接口/API Key 从 settings.json 读取（含同服务商多模型与力度路由）
        return self._model_cfg

    def _ensure_engine(self):
        """复用当前会话的引擎（多对话并发：每会话独立引擎，保留各自上下文）"""
        return self._engine_for(self._session_id)

    def _send(self):
        """发送消息：任务运行中（含评估阶段）则进入排队，本轮完成后自动发送；
        空闲则直接发送。排队消息可在提示条编辑或删除。"""
        text = self.input.toPlainText().strip()
        images = list(self._pending_images)
        files = list(self._pending_files)
        if not text and not images:
            return
        if text.lower().startswith("/compact"):
            self._do_compact()
            return
        if text.lower().startswith("/clear"):
            self._clear_chat()
            return
        payload = self._build_payload(text, images, files)
        if payload is None:
            return
        # 本会话有任务运行中/评估中 → 消息排队
        busy = self._task_active
        ep = self._eval_pending
        if ep is not None and ep[0] == self._session_id:
            busy = True
        eng = self._engine_for(self._session_id)
        if eng._thread and eng._thread.is_alive():
            busy = True
        if busy:
            qs = self._sess[self._session_id]["queued"]
            ei = self._queue_edit_idx
            if ei is not None and 0 <= ei < len(qs):
                qs[ei] = payload          # 编辑后按原队列位置重新排队
            else:
                qs.append(payload)        # 新增排队消息（支持多条按序排队）
            self._cancel_queue_edit()
            self.input.clear()
            self._clear_attachments()
            self._update_queue_bar()
            self._add_status("消息已排队，当前任务完成后按序自动发送（可逐条编辑/删除）", ACCENT)
            return
        self._cancel_queue_edit()
        self._do_send(payload)

    def _launch_task(self, ai_text: str, send_images: list, skill_names: list,
                     effort: str, sid: str = None):
        """按力度/评估结果路由模型并启动任务（评估完成或手动模式时调用）。
        sid：目标会话（默认当前会话）；后台会话（排队消息）也可启动任务"""
        sid = sid or self._session_id
        engine = self._engine_for(sid)
        fg = sid == self._session_id
        cfg = self._llm_config()
        providers = cfg.get("providers") or []
        # 手动选中的模型 → 使用其所属服务商的连接参数；否则当前服务商 + 力度路由
        if self._model_override:
            sel = next((p for p in providers
                        if p.get("name") == self._model_override_provider), None)
            if sel is None:   # 服务商名异常时按模型名回退匹配
                sel = next((p for p in providers
                            if self._model_override in (p.get("models") or [])), None)
            base_url = (sel or {}).get("base_url") or agent_llm.DEFAULT_BASE_URL
            api_key = (sel or {}).get("api_key") or agent_llm.DEFAULT_API_KEY
            protocol = (sel or {}).get("protocol") or "chat"
            model = self._model_override
        else:
            # 视觉任务（带图或需看页面截图）→ 自动切视觉模型
            vision = agent_llm.requires_vision(ai_text, send_images)
            model = agent_llm.resolve_model(cfg, effort, vision_needed=vision)
            sel = agent_llm.provider_for_model(cfg, model)
            base_url = (sel or {}).get("base_url") or agent_llm.DEFAULT_BASE_URL
            api_key = (sel or {}).get("api_key") or agent_llm.DEFAULT_API_KEY
            protocol = (sel or {}).get("protocol") or "chat"
        # agnes 默认模型只在内置默认服务可用：无论手动/自动选中，只要当前连接
        # 不是默认 agnes 服务就同步切过去（避免把该模型名/图片发给不支持的服务器）
        if model == agent_llm.DEFAULT_MODEL and base_url != agent_llm.DEFAULT_BASE_URL:
            base_url = agent_llm.DEFAULT_BASE_URL
            api_key = agent_llm.DEFAULT_API_KEY
        # 自动模式（下拉选「自动选择」）+ 图片：路由模型为纯文本 → 改用
        # agnes 视觉模型（内置默认服务）处理图片而非丢弃
        if (not self._model_override and send_images
                and agent_llm.is_text_only_model(model)):
            if fg:
                self._add_status(
                    f"路由模型 {model} 不支持图片，已改用视觉模型 "
                    f"{agent_llm.DEFAULT_MODEL} 处理图片", WARN)
            model = agent_llm.DEFAULT_MODEL
            base_url = agent_llm.DEFAULT_BASE_URL
            api_key = agent_llm.DEFAULT_API_KEY
        # 同步客户端连接参数（模型可能来自不同服务商）
        engine.llm.base_url = base_url.rstrip("/")
        engine.llm.api_key = api_key
        engine.llm.protocol = protocol
        engine.llm.model = model
        # 工作强度自动调节（Claude Code/Codex 式）：按模型正确映射 thinking/reasoning_effort，
        # 支持的服务商（DeepSeek V4 / GLM-4.5+ / OpenAI o 系列）自动附加参数，其余不发送
        engine.llm.effort_params = agent_llm.build_effort_params(model, effort)
        engine.text_only = agent_llm.is_text_only_model(model)
        # 手动指定纯文本模型时剥离图片（混配模型场景逐次判断）
        if engine.text_only and send_images:
            if fg:
                self._add_status("当前模型为纯文本模型，已忽略图片输入", WARN)
            send_images = []
        engine.start(ai_text, "zhuzhu Copilot", send_images, skills=skill_names)

    def _assess_worker(self):
        """后台线程：用默认 agnes-2.5-flash 评估任务难度（失败回退本地估算）"""
        ai_text = (self._eval_pending or (None, "", [], []))[1]
        try:
            effort = agent_llm.assess_effort(ai_text)
        except Exception:
            effort = agent_llm.estimate_effort(ai_text)
        self.eval_signal.emit(effort)

    def _on_assess_done(self, effort: str):
        """评估完成：按难度路由模型并启动任务（不显示评估文字，保持滑动动画）"""
        if not self._eval_pending:
            return
        sid, ai_text, send_images, skill_names = self._eval_pending
        self._eval_pending = None
        if sid == self._session_id and self._user_stopped:
            # 用户已在评估期间点击停止：放弃启动并复位按钮
            self._task_active = False
            self._hide_spinner()
            self._set_action_idle()
            return
        self._launch_task(ai_text, send_images, skill_names, effort, sid=sid)

    def _stop(self):
        if self._engine:
            self._engine.stop()
        self._user_stopped = True
        self._set_action_stopping()   # 红底转圈（禁用）
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
        st = self._sess.get(self._session_id)
        if st and st.get("engine") is eng:
            st["engine"] = None   # 下次发送时重建全新引擎
        self._engine = None
        self._add_status("AI 线程无法中断，已强制隔离（后台线程已断开，新任务将自动重建）", ERR)
        self._task_active = False
        self._hide_spinner()
        self._set_action_idle()
        if not self._end_badge_shown:
            self._end_badge_shown = True
            self._show_end_badge()
        self._scroll_bottom()

    def _do_compact(self):
        """/compact：由当前模型自主生成摘要压缩上下文（后台线程执行，失败回退启发式）"""
        self.input.clear()
        if not self._engine or not self._engine._messages:
            self._add_status("当前无可压缩的上下文", TEXT_DIM)
            return
        self._ensure_compact_row()
        threading.Thread(target=self._compact_worker, daemon=True).start()

    def _compact_worker(self):
        """后台线程：执行模型自主摘要压缩，完成后发信号回主线程更新状态"""
        try:
            n = self._engine._auto_compress(keep_recent=2)
        except Exception:
            n = 0
        self.compact_signal.emit(int(n or 0))

    def _on_compact_done(self, n: int):
        self._hide_compact_row()
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
        # 停止并清理该会话的独立引擎与内存态
        st = self._sess.pop(sid, None)
        if st:
            # 释放挂起的确认/提问等待，让后台引擎线程及时退出
            if st.get("confirm_evt"):
                st["confirm_evt"].set()
            if st.get("ask_evt"):
                st["ask_evt"].set()
            eng = st.get("engine")
            if eng:
                eng.clear_history()
                eng.clear_context()
                if eng._thread and eng._thread.is_alive():
                    eng.stop()
        if sid == self._session_id:
            # 删除当前对话：清理内存（_session_id 先置空，防止切会话时复活文件）
            self._session_id = None
            self._segments = []
            self._user_msgs = []
            self._ai_bubble = None
            self._bubble_widgets = []
            self._bubble_segs = {}
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
            f"QMessageBox QPushButton:hover {{ background: {HOVER}; border-color: {ACCENT}; }}")
        box.exec()
        return box.clickedButton() is yes

    def _clear_chat(self, *_):
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
        # ---- 执行：停止该会话引擎 + 清空上下文与气泡 + tokens 归零 ----
        old_id = self._session_id
        old_st = self._sess.pop(old_id, None)
        if old_st:
            if old_st.get("confirm_evt"):
                old_st["confirm_evt"].set()
            if old_st.get("ask_evt"):
                old_st["ask_evt"].set()
            eng = old_st.get("engine")
            if eng:
                eng.clear_history()
                eng.clear_context()   # 同时删除磁盘上的持久化上下文
                if eng._thread and eng._thread.is_alive():
                    eng.stop()
        self._ai_bubble = None
        self._segments = []
        self._history_segments = []
        self._seg_cache.clear()
        self._sub_segs.clear()
        self._user_msgs = []
        self._rows = []
        self._hide_spinner()
        self.cmd_list.hide()
        self._stop_button_anim()   # 融合按钮恢复空闲发送状态
        self._task_active = False
        self._user_stopped = False
        self._end_badge_shown = False
        self._think_done = False
        self._think_start = 0.0
        self._last_activity = 0.0
        self._clear_attachments()
        while self.msg_lay.count() > 1:  # 保留末尾 stretch
            item = self.msg_lay.takeAt(0)
            self._free_layout_item(item)
        self._bubble_widgets = []   # 清空气泡引用，避免 resizeEvent 处理已删除对象
        self._bubble_segs = {}
        self.token_label.setText("0 tk")
        # ---- 永久删除该对话，并新开空会话（界面回到欢迎页） ----
        self._delete_session(old_id)
        s = self._create_session()
        self._session_id = s["id"]
        self._session_name = "新对话"
        self._sess[s["id"]] = self._new_sess_state(s["id"])
        self._bind_sess(s["id"])
        self._refresh_session_combo()
        self._update_welcome()
        self._update_queue_bar()
        self._add_status("已清空上下文并永久删除该对话", TEXT_DIM)

    # ---------- 拖拽/粘贴/上传附件（图片/文件） ----------
    _IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")

    # 文件缩略图自定义样式：扩展名 → (徽章文字, 底色)。未收录的扩展名显示其大写形式
    _FILE_THUMB_STYLE = {
        ".py": ("PY", "#3572A5"), ".cs": ("CS", "#178600"),
        ".cpp": ("C++", "#5C8DBC"), ".cc": ("C++", "#5C8DBC"), ".cxx": ("C++", "#5C8DBC"),
        ".c": ("C", "#555555"), ".h": ("H", "#555555"),
        ".java": ("JAVA", "#E76F00"), ".kt": ("KT", "#7F52FF"), ".kts": ("KT", "#7F52FF"),
        ".html": ("HTML", "#E44D26"), ".htm": ("HTML", "#E44D26"), ".css": ("CSS", "#264DE4"),
        ".js": ("JS", "#F0C000"), ".mjs": ("JS", "#F0C000"), ".ts": ("TS", "#3178C6"),
        ".jsx": ("JSX", "#61DAFB"), ".tsx": ("TSX", "#3178C6"), ".vue": ("VUE", "#41B883"),
        ".json": ("JSON", "#7A5BC0"), ".xml": ("XML", "#8A93A6"), ".yaml": ("YAML", "#8A93A6"),
        ".yml": ("YML", "#8A93A6"), ".toml": ("TOML", "#8A93A6"),
        ".md": ("MD", "#4B6BD6"), ".txt": ("TXT", "#8A93A6"), ".rst": ("RST", "#8A93A6"),
        ".sql": ("SQL", "#E38C00"), ".sh": ("SH", "#4EAA25"), ".bash": ("BASH", "#4EAA25"),
        ".bat": ("BAT", "#4EAA25"), ".ps1": ("PS1", "#012456"), ".cmd": ("CMD", "#4EAA25"),
        ".go": ("GO", "#00ADD8"), ".rs": ("RS", "#DEA584"), ".rb": ("RB", "#CC342D"),
        ".php": ("PHP", "#777BB4"), ".swift": ("SWIFT", "#F05138"), ".dart": ("DART", "#0175C2"),
        ".csv": ("CSV", "#27AE60"), ".xlsx": ("XLSX", "#217346"), ".xls": ("XLS", "#217346"),
        ".docx": ("DOCX", "#2B579A"), ".doc": ("DOC", "#2B579A"), ".pptx": ("PPT", "#D24726"),
        ".pdf": ("PDF", "#E74C3C"), ".ipynb": ("IPY", "#F37726"),
        ".zip": ("ZIP", "#B8860B"), ".7z": ("7Z", "#B8860B"), ".rar": ("RAR", "#B8860B"),
        ".tar": ("TAR", "#B8860B"), ".gz": ("GZ", "#B8860B"),
        ".exe": ("EXE", "#3B3B3B"), ".dll": ("DLL", "#3B3B3B"), ".msi": ("MSI", "#3B3B3B"),
        ".iso": ("ISO", "#3B3B3B"), ".apk": ("APK", "#3DDC84"), ".svg": ("SVG", "#FFB13B"),
        ".ico": ("ICO", "#8A93A6"), ".ini": ("INI", "#8A93A6"), ".cfg": ("CFG", "#8A93A6"),
        ".log": ("LOG", "#8A93A6"), ".db": ("DB", "#8A93A6"), ".sqlite": ("DB", "#8A93A6"),
    }

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

    def _setup_admin_dnd(self):
        """管理员权限下启用 WM_DROPFILES 原生拖放通道（UIPI 拦截 OLE 拖放的绕行方案）"""
        if self._admin_dnd:
            return
        print(f"[dnd] 管理员拖放通道 setup（hwnd={int(self.winId())}）", flush=True)
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32
            ole32 = ctypes.windll.ole32
            # 进程级放行（作用于进程内所有窗口）
            for m in (_WM_DROPFILES, _WM_COPYDATA, _WM_COPYGLOBALDATA):
                user32.ChangeWindowMessageFilter(m, _MSGFLT_ADD)
            # Qt 会在每个 setAcceptDrops 控件（含输入框等子控件）上注册 OLE IDropTarget。
            # 只撤销顶层注册时，鼠标悬停在子控件上 Explorer 仍走 OLE 路径、被 UIPI 拦截
            # （表现为"禁用圆圈"拖不进来）。因此对本进程所有窗口：
            # 1) 窗口级放行 WM_DROPFILES/COPYDATA/COPYGLOBALDATA（UIPI 消息过滤）
            # 2) RevokeDragDrop 移除全部 OLE 拖放注册，强制 Explorer 回退 WM_DROPFILES
            _ex = user32.ChangeWindowMessageFilterEx
            _ex.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                            ctypes.c_void_p]
            hwnds = _all_process_hwnds()
            for w in hwnds:
                for m in (_WM_DROPFILES, _WM_COPYDATA, _WM_COPYGLOBALDATA):
                    _ex(w, m, _MSGFLT_ADD, None)
                ole32.RevokeDragDrop(w)
            print(f"[dnd] 已对 {len(hwnds)} 个窗口放行消息并撤销 OLE 拖放注册", flush=True)
            # WM_DROPFILES 只注册在顶层窗口：落点坐标为顶层客户区基准（_deliver 的 childAt 依赖）
            shell32.DragAcceptFiles.restype = None   # 该函数返回 VOID，显式声明避免误读
            shell32.DragAcceptFiles(hwnd, True)
            print("[dnd] DragAcceptFiles(顶层) 完成", flush=True)
            self._admin_drop_filter = _AdminDropFilter(self)
            QApplication.instance().installNativeEventFilter(self._admin_drop_filter)
            self._admin_dnd = True
            print("[dnd] 管理员拖放通道启用成功", flush=True)
        except Exception as e:
            self._admin_dnd = False
            self._add_status(f"管理员拖放通道启用失败：{e}", WARN)
            print("[dnd] 启用失败:", repr(e), flush=True)

    def _on_input_files_dropped(self, paths: list):
        """输入框文件拖入：逐个加入附件（图片/文件，纯文本模型自动过滤图片）"""
        for p in paths or []:
            self._add_attachment(p)

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
            data_url = ("data:image/jpeg;base64,"
                        + base64.b64encode(bytes(ba)).decode())
            self._pending_images.append(data_url)
            self._attach_thumb(QPixmap(path), path, remove=("img", data_url))
        else:
            self._pending_files.append(path)
            self._attach_thumb(self._file_thumb(path), path,
                               name=os.path.basename(path),
                               remove=("file", path))

    @staticmethod
    def _file_thumb(path: str, size: int = 56) -> QPixmap:
        """自定义文件缩略图：按扩展名生成彩色圆角徽章（PY/C++/JAVA/HTML…），
        未收录的扩展名显示其大写形式，替代单调的系统图标"""
        ext = os.path.splitext(path or "")[1].lower()
        label, color = AgentPanel._FILE_THUMB_STYLE.get(
            ext, (ext[1:].upper() or "FILE", "#6B7280"))
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(2, 2, size - 4, size - 4, 10, 10)
        f = QFont("Segoe UI", max(7, int(size * 0.20)))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, label[:5])
        p.end()
        return pm

    def _file_thumb_data_url(self, path: str) -> str:
        """文件徽章缩略图 → PNG data URL（嵌入发送后用户气泡富文本）"""
        pm = self._file_thumb(path)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pm.save(buf, "PNG")
        return "data:image/png;base64," + base64.b64encode(bytes(ba)).decode()

    def _paste_clipboard_image(self) -> bool:
        """Ctrl+V：剪贴板含图片时作为附件加入（多模态模型）；无图返回 False 走默认文本粘贴"""
        clip = QApplication.clipboard()
        if not clip.mimeData().hasImage():
            return False
        img = clip.image()
        if img.isNull():
            return False
        if self._text_only:
            self._add_status("当前为纯文本模型，不支持粘贴图片", WARN)
            return True   # 吞掉事件，避免图片被当文本粘贴进输入框
        if img.width() > 320:
            img = img.scaledToWidth(320, Qt.TransformationMode.SmoothTransformation)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "JPEG", 80)
        data_url = ("data:image/jpeg;base64,"
                    + base64.b64encode(bytes(ba)).decode())
        self._pending_images.append(data_url)
        self._attach_thumb(QPixmap.fromImage(img), "剪贴板截图（Ctrl+V 粘贴）",
                           remove=("img", data_url))
        return True

    def eventFilter(self, obj, event):
        """拦截输入框按键：Tab 补全命令；Ctrl+V 剪贴板图片转附件。
        （文件拖放由面板 dragEnterEvent/dropEvent 统一处理，无需在此接管）"""
        if obj is self.input and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Tab and self.cmd_list.isVisible():
                return self._complete_cmd()
            if event.matches(QKeySequence.StandardKey.Paste) and \
                    self._paste_clipboard_image():
                return True
        return super().eventFilter(obj, event)

    def _pick_attachments(self, *_):
        """「+」上传按钮：文件选择器多选，图片/文件均可（纯文本模型自动过滤图片）"""
        paths, _ = QFileDialog.getOpenFileNames(self, "选择文件/图片发送给 AI")
        for p in paths or []:
            self._add_attachment(p)

    @staticmethod
    def _round_pixmap(src: QPixmap, size: int, radius: int = 8) -> QPixmap:
        """把任意图片按方形圆角裁剪（居中裁切），用于附件卡片/气泡缩略图"""
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, size, size, radius, radius)
        p.setClipPath(path)
        p.drawPixmap(0, 0, src.scaled(size, size,
                                      Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                      Qt.TransformationMode.SmoothTransformation))
        p.end()
        return pm

    @staticmethod
    def _file_size_text(path: str) -> str:
        """文件大小人性化显示（B/KB/MB）"""
        try:
            n = os.path.getsize(path)
        except OSError:
            return ""
        if n < 1024:
            return f"{n} B"
        if n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        return f"{n / 1024 / 1024:.1f} MB"

    def _attach_thumb(self, pixmap: QPixmap, tooltip: str, name: str = "",
                      remove: tuple = None):
        """附件条缩略图卡片：圆角方形缩略图 + 文件名，右上角 × 可单独取消上传。
        remove: (kind, value) —— kind ∈ img/file，value 为 data_url 或文件路径，用于取消时移除"""
        box = QWidget()
        box.setObjectName("attCard")
        box.setToolTip(tooltip)
        box.setFixedSize(78, 86)
        box.setStyleSheet(
            f"#attCard {{ background: #152036; border: 1px solid #000000; border-radius: 10px; }}"
            f"#attCard:hover {{ background: #182644; border: 1px solid {ACCENT}; }}")
        v = QVBoxLayout(box)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(4)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb = QLabel()
        thumb.setFixedSize(44, 44)
        thumb.setPixmap(self._round_pixmap(pixmap, 44))
        thumb.setToolTip(tooltip)
        v.addWidget(thumb, 0, Qt.AlignmentFlag.AlignCenter)
        if name:
            nl = QLabel(name if len(name) <= 9 else name[:8] + "…")
            nl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")
            nl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            nl.setToolTip(tooltip)
            v.addWidget(nl, 0, Qt.AlignmentFlag.AlignCenter)
        # 右上角取消按钮：手动定位（不加入布局），点击移除该附件
        if remove:
            rm = QPushButton("×")
            rm.setFixedSize(18, 18)
            rm.setCursor(Qt.CursorShape.PointingHandCursor)
            rm.setToolTip("取消上传")
            rm.setStyleSheet(
                "QPushButton { background: #2A3A5C; color: #AEB9D0; border: none;"
                " border-radius: 9px; font-size: 12px; font-weight: 700; }"
                "QPushButton:hover { background: #E74C3C; color: white; }")
            rm.clicked.connect(lambda: self._remove_attachment(box, remove[0], remove[1]))
            rm.setParent(box)
            rm.move(57, 3)
        # 插入到 stretch 之前
        self._attach_lay.addWidget(box)
        self._attach_bar.setVisible(True)

    def _remove_attachment(self, box: QWidget, kind: str, value):
        """取消单个附件：从附件条移除缩略图并从待发送列表剔除"""
        for i in range(self._attach_lay.count()):
            it = self._attach_lay.itemAt(i)
            if it and it.widget() is box:
                self._attach_lay.takeAt(i)
                break
        box.deleteLater()
        if kind == "img":
            self._pending_images = [x for x in self._pending_images if x != value]
        else:
            self._pending_files = [x for x in self._pending_files if x != value]
        if not self._pending_images and not self._pending_files:
            self._attach_bar.setVisible(False)

    def _clear_attachments(self):
        while self._attach_lay.count() > 0:
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
        # 评估阶段（引擎线程未启动）同样视为任务进行中，避免误清理禁用停止按钮
        running = bool(self._eval_pending is not None
                       or (self._engine and self._engine._thread
                           and self._engine._thread.is_alive()))
        # 下载任务实时进度：仅当前会话有任务时渲染进其气泡（避免后台会话下载进度串台）
        if self._task_active:
            self._sync_download_progress()
        # 任务结束即清理：只要任务标志开启且线程已退出，就执行收尾
        # （不依赖 spinner/按钮状态判断，避免切换模式等路径下漏清理）
        if not running and self._task_active:
            self._task_active = False
            self._hide_spinner()
            self._set_action_idle()   # 融合按钮恢复空闲发送状态
            if not self._end_badge_shown:
                self._end_badge_shown = True
                self._show_end_badge()
            self._persist_current()   # 任务结束即持久化当前会话（重启可恢复）
            self._flush_queue(self._session_id)   # 本轮完成 → 自动发送排队消息
            self._scroll_bottom()   # 结束执行时自动滚动到最下方

    def _sync_download_progress(self):
        """轮询活跃下载任务，把进度条实时渲染进 AI 气泡（完成后保留最终状态）"""
        task = agent_tools.get_active_download()
        if task is None:
            return
        try:
            snap = task.snapshot()
        except Exception:
            agent_tools.clear_active_download()
            return
        status = snap.get("status") or ""
        total = snap.get("total") or 0
        done = snap.get("done") or 0
        pct = int(done * 100 / total) if total else 0
        name = snap.get("filename") or "下载中"
        self._ensure_ai_bubble()
        seg = next((s for s in reversed(self._segments)
                    if s.get("type") == "progress"), None)
        if seg is None:
            seg = {"type": "progress", "pct": 0, "text": ""}
            self._segments.append(seg)
        seg["pct"] = pct
        seg["text"] = (f"{name} · {self._fmt_bytes(done)}/{self._fmt_bytes(total)}"
                       f" · {status}")
        self._refresh_ai_html()
        if status in ("done", "error", "canceled"):
            agent_tools.clear_active_download()   # 结束：保留最终进度条不再轮询
        self._scroll_bottom()

    @staticmethod
    def _fmt_bytes(n) -> str:
        """字节数人性化显示（B/KB/MB/GB）"""
        try:
            n = max(0, int(n or 0))
        except (TypeError, ValueError):
            n = 0
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024:
                return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} PB"

    def _show_end_badge(self):
        """任务结束后在 AI 气泡外显示结果徽章"""
        state = getattr(self._engine, "end_state", "") if self._engine else ""
        if self._user_stopped or state == "stopped":
            self._add_badge("Stop by user", WARN)
        elif state == "done":
            self._add_badge("Successfully", OK)
        else:   # error 视为异常
            self._add_badge("Error", ERR)

    # ---------- 引擎回调（信号槽，主线程） ----------
    def _ensure_text_segment(self):
        """正文段：末尾不是 text 段则新建，否则复用（操作与正文交织）"""
        if not self._segments or self._segments[-1]["type"] != "text":
            self._segments.append({"type": "text", "raw": ""})

    def _stop_send_spin(self):
        """AI 开始响应/执行后停止转圈（按钮保持可点击停止状态，不再一直转圈误导）"""
        if self._action_anim.isActive():
            self._action_anim.stop()
            self.action_btn.setIcon(_line_icon("stop", 16, "#FFFFFF"))
            self.action_btn.setToolTip("停止当前任务")

    def _on_delta(self, s: str):
        self._finish_thinking()   # 开始输出正文即视为思考完成
        self._stop_send_spin()
        self._last_activity = time.time()
        self._ensure_ai_bubble()
        self._ensure_text_segment()
        self._segments[-1]["raw"] += s
        self._segments[-1]["streaming"] = True   # 流式期间轻量渲染
        self._refresh_ai_html()
        self._scroll_bottom()

    def _on_result(self, name: str, text: str, images: list = None):
        """工具执行完成：输出文本与截图一并渲染进 AI 气泡（截图以缩略图独立成块，不挤压）。
        命令执行结果先输出（默认展开可见），短暂展示后自动折叠为一行，可点击展开/收起。"""
        self._stop_send_spin()
        self._last_activity = time.time()
        self._ensure_ai_bubble()
        # AI 使用任务清单工具时，同步左侧 TODOS 可视化面板（面板常显，实时刷新进度）
        if name in ("update_todo", "list_todo"):
            self.todos_panel.update_todos(agent_tools.load_todos())
        shown = (text or "").strip()
        if len(shown) > 20000:
            shown = shown[:20000] + " …（输出过长已截断显示，完整内容已返回模型）"
        shown = _esc(shown).replace("\n", "<br/>")
        seg = {"type": "result", "html": shown, "collapsed": False}
        self._segments.append(seg)
        # 截图段（AI 主动截图：browser_snapshot 等工具返回的页面截图）渲染进主对话气泡
        for u in images or []:
            self._segments.append({"type": "image", "url": u, "caption": "已截屏"})
        self._refresh_ai_html()
        self._scroll_bottom()
        # 命令结果「先输出再折叠」：短暂展示后自动折叠（与思考过程一致的折叠体验）
        sid = self._session_id
        QTimer.singleShot(1800, lambda: self._auto_collapse_result(sid, seg))

    def _auto_collapse_result(self, sid: str, seg: dict):
        """把已展示过的命令结果段自动折叠为一行（仅当仍是该会话当前气泡时生效）"""
        if sid != self._session_id:
            return
        if not any(s is seg for s in self._segments):
            return
        seg["collapsed"] = True
        self._refresh_ai_html()
        self._scroll_bottom()

    def _on_sub_event(self, kind: str, idx: int, title: str, text: str):
        """子 Agent 事件（与主 Agent 共用同一聊天气泡）：
        start=创建子块；delta=流式输出追加到对应子块。
        多个子任务并发时按 task_idx 定位各自子块，互不覆盖。"""
        self._stop_send_spin()
        self._last_activity = time.time()
        if kind == "start":
            self._ensure_ai_bubble()
            seg = {"type": "sub", "title": title, "raw": ""}
            self._sub_segs[idx] = seg
            self._segments.append(seg)
            self._refresh_ai_html()
            self._scroll_bottom()
            return
        if kind == "delta":
            seg = self._sub_segs.get(idx)
            if seg is None:
                # 兜底：段列表被重建（历史加载/会话重置）导致索引失效时，
                # 定位最后一个同标题 sub 段；仍找不到则新建
                for s in reversed(self._segments):
                    if s.get("type") == "sub" and s.get("title") == title:
                        seg = s
                        break
                if seg is None:
                    self._ensure_ai_bubble()
                    seg = {"type": "sub", "title": title, "raw": ""}
                    self._segments.append(seg)
                self._sub_segs[idx] = seg
            seg["raw"] += text
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
        elif s.startswith("正在调用技能:"):
            name = s.split(":", 1)[1].strip()
            self._ensure_ai_bubble()
            if self._segments and self._segments[-1]["type"] == "op" \
                    and "技能" in self._segments[-1]["html"]:
                self._segments[-1]["html"] = f"▎正在调用技能 {_esc(name)}"
            else:
                self._segments.append({"type": "op", "html": f"▎正在调用技能 {_esc(name)}"})
            self._refresh_ai_html()
            self._scroll_bottom()
        elif s.startswith("技能已调用:"):
            name = s.split(":", 1)[1].strip()
            self._ensure_ai_bubble()
            if self._segments and self._segments[-1]["type"] == "op" \
                    and "技能" in self._segments[-1]["html"]:
                self._segments[-1]["html"] = f"✓ 技能已调用 {_esc(name)}"
            else:
                self._segments.append({"type": "op", "html": f"✓ 技能已调用 {_esc(name)}"})
            self._refresh_ai_html()
            self._scroll_bottom()
        elif s == "完成":
            self._hide_spinner()   # 任务结束，停掉转圈
        elif s.startswith("错误"):
            self._hide_spinner()
            self._ensure_ai_bubble()
            self._segments.append({"type": "mark", "html": _esc(s)})
            self._refresh_ai_html()
            self._scroll_bottom()
        elif s == "已停止" or "已停止" in s:
            self._hide_spinner()   # 用户手动停止/包含“已停止”字样的状态均不输出小字
        else:
            # 其余状态（如"已开启自动朗读"/自动朗读失败/虚拟桌面等）以普通小字输出，
            # 避免朗读相关的提示被静默丢弃导致用户误以为没有生效
            self._add_status(s, TEXT_DIM)

    # ---------- 每步确认 / ask_user 提问（engine 线程调用 → 信号 → 主线程） ----------
    # 前台会话：直接弹窗；后台会话：不弹窗打扰，挂起等待并置「待确认/待回答」标记，
    # 在其他对话优雅通知提醒，用户切到该会话后处理。
    def _confirm_tool(self, sid: str, name: str, args: dict) -> bool:
        st = self._sess.get(sid) or {}
        level, reason = agent_sandbox.assess_tool(name, args)
        if self._mode == "yolo":
            return level != "dangerous"
        if self._mode == "edit":
            if name != "run_command" or level == "safe":
                return True
        if sid != self._session_id:
            # 后台会话：挂起该确认，置待处理标记，优雅通知，不弹窗打扰当前对话
            evt = threading.Event()
            st["pending_confirm"] = {"name": name, "args": args, "risk": level,
                                     "answered": False}
            st["confirm_evt"] = evt
            st["confirm_result"] = False
            self.evt_signal.emit(sid, "pending",
                                 (f"对话「{self._session_label(sid)}」有命令待确认：{name}",
                                  "切换到该对话即可继续"))
            evt.wait(timeout=600)
            return st.get("confirm_result", False)
        # 前台会话：直接弹窗确认
        self._confirm_evt.clear()
        self.confirm_signal.emit(sid, name, json.dumps(args, ensure_ascii=False), level)
        self._confirm_evt.wait(timeout=600)
        return self._confirm_result

    def _on_confirm(self, sid: str, name: str, args_json: str, risk: str):
        try:
            args = json.loads(args_json)
        except json.JSONDecodeError:
            args = {}
        dlg = _ConfirmDialog(name, args, risk, self)
        dlg.exec()
        self._confirm_result = dlg.result_ok
        self._confirm_evt.set()

    def _ask_user_tool(self, sid: str, args: dict) -> str:
        st = self._sess.get(sid) or {}
        if sid != self._session_id:
            # 后台会话：挂起提问，置待处理标记，优雅通知，不弹窗打扰当前对话
            evt = threading.Event()
            st["pending_ask"] = {"args": args, "answered": False}
            st["ask_evt"] = evt
            st["ask_result"] = ""
            self.evt_signal.emit(sid, "pending",
                                 (f"对话「{self._session_label(sid)}」向你提问："
                                  f"{str(args.get('question', ''))[:40]}",
                                  "切换到该对话作答"))
            evt.wait(timeout=600)
            return st.get("ask_result", "")
        self._ask_evt.clear()
        self.ask_signal.emit(sid, json.dumps(args, ensure_ascii=False))
        self._ask_evt.wait(timeout=600)
        return self._ask_result

    def _on_ask(self, sid: str, args_json: str):
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

    def _session_label(self, sid: str) -> str:
        """取会话显示名（用于后台通知）"""
        lst = self._load_session_list()
        s = next((x for x in lst if x.get("id") == sid), None)
        return s.get("name", "新对话") if s else "新对话"

    def _notify_background(self, text: str, hint: str = ""):
        """优雅通知：底部状态条 + 可选任务栏提示（不弹阻塞对话框）"""
        self._add_status(text, WARN)
        if hint:
            self._add_status(hint, TEXT_DIM)
        try:
            from winapp_migrator.ui.main_window import MainWindow
            src = self.parent()
            if isinstance(src, MainWindow) and hasattr(src, "toast"):
                src.toast.show_toast("后台对话提醒", text, True, 5000)
        except Exception:
            pass

    def _flush_pending(self, sid: str):
        """前台处理该会话的挂起确认/提问（切到该会话时调用）"""
        st = self._sess.get(sid)
        if st is None:
            return
        if st.get("pending_confirm"):
            p = st["pending_confirm"]
            dlg = _ConfirmDialog(p["name"], p["args"], p["risk"], self)
            dlg.exec()
            st["confirm_result"] = dlg.result_ok
            st["pending_confirm"] = None
            if st["confirm_evt"]:
                st["confirm_evt"].set()
        if st.get("pending_ask"):
            pa = st["pending_ask"]
            args = pa.get("args") or {}
            dlg = _AskUserDialog(str(args.get("question", "")),
                                 list(args.get("options") or []),
                                 bool(args.get("multi_select", False)), self)
            dlg.exec()
            st["ask_result"] = dlg.answer()
            st["pending_ask"] = None
            if st["ask_evt"]:
                st["ask_evt"].set()
        self._refresh_session_combo()

    # ---------- 设置 ----------
    # 模型/接口/API Key 已写死，无需设置对话框


    def closeEvent(self, event):
        # 隐藏主程序窗口模式下关闭 AI 面板时，恢复显示主窗口，避免应用无可见窗口
        if str(self._settings.value("hide_main_window", "0")).strip().lower() in ("1", "true", "yes"):
            mw = self.parent()
            if mw is not None:
                mw.show()
                mw.raise_()
                mw.activateWindow()
        # 关闭面板：停止所有会话的引擎（多对话并发各自独立）
        for st in self._sess.values():
            eng = st.get("engine")
            if eng:
                eng.stop()
                eng.join(1)   # 缩短等待：持久化改后台线程收尾，避免关闭窗口长时间阻塞
        self._persist_current()   # 关闭前持久化当前会话（上下文异步落盘，UI 只快速保存）
        try:
            self._mcp.close_all()
        except Exception:
            pass
        if self._admin_drop_filter is not None:
            try:
                QApplication.instance().removeNativeEventFilter(self._admin_drop_filter)
            except Exception:
                pass
            self._admin_drop_filter = None
        event.accept()
