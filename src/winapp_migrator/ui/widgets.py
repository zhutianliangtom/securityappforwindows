import re
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QSizePolicy, QGraphicsDropShadowEffect, QStyledItemDelegate, QStyle,
    QFileIconProvider
)
from PyQt6.QtCore import Qt, QSize, QRect, QFileInfo
from PyQt6.QtGui import QColor, QPainter, QIcon, QFont, QFontMetrics

from winapp_migrator.ui.styles import PALETTE

class Card(QWidget):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QWidget#card {{
                background-color: {PALETTE['card']};
                border-radius: 16px;
                border: 1px solid {PALETTE['border']};
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(37, 99, 235, 30))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(12)

        if title:
            title_label = QLabel(title)
            title_label.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {PALETTE['text']};")
            self.layout.addWidget(title_label)

class PrimaryButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(40)

class SecondaryButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("secondary")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(40)


class AppItemDelegate(QStyledItemDelegate):
    """自绘应用列表项：真实图标/首字符、类型标签、名称、路径、大小，选中态完整渲染"""
    ROW_HEIGHT = 68

    def __init__(self, parent=None):
        super().__init__(parent)
        self._provider = QFileIconProvider()
        self._icon_cache = {}  # id(app) -> QIcon
        self._exe_cache = {}   # id(app) -> str | None

    def sizeHint(self, option, index):
        return QSize(0, self.ROW_HEIGHT)

    def paint(self, painter, option, index):
        app = index.data(Qt.ItemDataRole.UserRole)
        if not app:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect

        # --- 背景（选中/悬停/默认）---
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        bg_rect = QRect(rect.left() + 3, rect.top() + 3, rect.width() - 6, rect.height() - 6)
        if selected:
            painter.setBrush(QColor(PALETTE["primary_light"]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bg_rect, 10, 10)
            # 左侧选中指示条
            painter.setBrush(QColor(PALETTE["primary"]))
            painter.drawRoundedRect(QRect(rect.left() + 3, rect.top() + 14, 4, rect.height() - 28), 2, 2)
        elif hovered:
            painter.setBrush(QColor("#F3F7FF"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bg_rect, 10, 10)

        # --- 图标 ---
        icon_rect = QRect(rect.left() + 16, rect.top() + (rect.height() - 36) // 2, 36, 36)
        icon = self._icon_for(app)
        if icon is not None and not icon.isNull():
            painter.drawPixmap(icon_rect, icon.pixmap(36, 36))
        else:
            # 首字符圆形占位
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(PALETTE["primary"]))
            painter.drawEllipse(icon_rect)
            painter.setPen(QColor("white"))
            char_font = painter.font()
            char_font.setBold(True)
            char_font.setPixelSize(16)
            painter.setFont(char_font)
            first = (app.name[0] if app.name else "?").upper()
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, first)

        # --- 文本区 ---
        text_left = rect.left() + 64
        text_right = rect.right() - 14
        text_top = rect.top() + (rect.height() - 40) // 2

        # 第二行：类型标签 + 路径
        type_color = PALETTE["primary"] if app.app_type == "Win32" else PALETTE["warning"]
        if app.app_type == "自定义":
            type_color = PALETTE["text_secondary"]
        tag_width, tag_height = 38, 16
        tag_rect = QRect(text_left, text_top + 26, tag_width, tag_height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(type_color))
        painter.drawRoundedRect(tag_rect, 3, 3)
        painter.setPen(QColor("white"))
        tag_font = painter.font()
        tag_font.setPixelSize(10)
        tag_font.setBold(True)
        painter.setFont(tag_font)
        painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, app.app_type)

        # 路径（elide）
        path_x = tag_rect.right() + 8
        path_font = QFont(painter.font())
        path_font.setPixelSize(11)
        path_metrics = QFontMetrics(path_font)
        path_text = str(app.install_location)
        path_width = text_right - path_x
        elided_path = path_metrics.elidedText(path_text, Qt.TextElideMode.ElideMiddle, max(0, path_width))
        painter.setPen(QColor(PALETTE["text_secondary"]))
        painter.setFont(path_font)
        painter.drawText(QRect(path_x, text_top + 23, max(0, path_width), 20),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_path)

        # 第一行：名称（elide）
        size_text = self._format_size(app.size_bytes)
        size_font = QFont(painter.font())
        size_font.setPixelSize(11)
        size_metrics = QFontMetrics(size_font)
        size_width = size_metrics.horizontalAdvance(size_text) + 4
        name_font = QFont(painter.font())
        name_font.setPixelSize(13)
        name_font.setBold(True)
        name_metrics = QFontMetrics(name_font)
        name_max = text_right - text_left - size_width - 8
        elided_name = name_metrics.elidedText(app.name, Qt.TextElideMode.ElideRight, max(0, name_max))
        painter.setPen(QColor(PALETTE["text"]))
        painter.setFont(name_font)
        painter.drawText(QRect(text_left, text_top, max(0, name_max), 22),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_name)

        # 大小（右对齐）
        painter.setPen(QColor(PALETTE["text_secondary"]))
        painter.setFont(size_font)
        painter.drawText(QRect(text_right - size_width, text_top, size_width, 22),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, size_text)

        painter.restore()

    def _icon_for(self, app) -> QIcon:
        key = id(app)
        if key in self._icon_cache:
            return self._icon_cache[key]
        icon = self._resolve_icon(app)
        self._icon_cache[key] = icon
        return icon

    def _resolve_icon(self, app) -> QIcon:
        exe = self._find_exe(app)
        if exe:
            try:
                icon = self._provider.icon(QFileInfo(exe))
                if not icon.isNull():
                    return icon
            except Exception:
                pass
        return QIcon()

    def _find_exe(self, app) -> str | None:
        key = id(app)
        if key in self._exe_cache:
            return self._exe_cache[key]
        result = None
        exe = app.executable or ""
        m = re.search(r'"([^"]+)"', exe) or re.search(r'([^",]+)', exe)
        if m:
            p = Path(m.group(1).strip())
            if p.is_file():
                result = str(p)
        if not result:
            try:
                for f in app.install_location.iterdir():
                    if f.is_file() and f.suffix.lower() == ".exe":
                        result = str(f)
                        break
            except Exception:
                pass
        self._exe_cache[key] = result
        return result

    @staticmethod
    def _format_size(size):
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
