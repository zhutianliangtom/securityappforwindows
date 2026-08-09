from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QSizePolicy, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor

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

class AppListItem(QWidget):
    clicked = pyqtSignal()

    def __init__(self, app_info, parent=None):
        super().__init__(parent)
        self.app_info = app_info
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(16)

        type_color = PALETTE["primary"] if app_info.app_type == "Win32" else PALETTE["warning"]
        type_label = QLabel(app_info.app_type)
        type_label.setStyleSheet(
            f"background-color: {type_color}; color: white; "
            f"border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
        )
        type_label.setFixedWidth(48)
        type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(type_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        name = QLabel(app_info.name)
        name.setStyleSheet("font-size: 14px; font-weight: 600;")
        text_layout.addWidget(name)

        path = QLabel(str(app_info.install_location))
        path.setStyleSheet(f"font-size: 12px; color: {PALETTE['text_secondary']};")
        path.setToolTip(str(app_info.install_location))
        text_layout.addWidget(path)
        layout.addLayout(text_layout, stretch=1)

        size = QLabel(self._format_size(app_info.size_bytes))
        size.setStyleSheet(f"font-size: 12px; color: {PALETTE['text_secondary']};")
        size.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(size)

    def _format_size(self, size):
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)
