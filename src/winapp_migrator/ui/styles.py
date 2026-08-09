from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtCore import Qt

PALETTE = {
    "bg_top": "#F8FAFF",
    "bg_bottom": "#EFF6FF",
    "card": "#FFFFFF",
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "primary_light": "#DBEAFE",
    "text": "#1E293B",
    "text_secondary": "#64748B",
    "border": "#E2E8F0",
    "success": "#10B981",
    "warning": "#F59E0B",
    "danger": "#EF4444",
}

GLOBAL_QSS = f"""
QMainWindow, QWidget {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {PALETTE['bg_top']}, stop:1 {PALETTE['bg_bottom']});
    color: {PALETTE['text']};
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 14px;
}}

QLabel {{
    color: {PALETTE['text']};
}}

QLabel#title {{
    font-size: 24px;
    font-weight: 700;
    color: {PALETTE['primary']};
}}

QLabel#subtitle {{
    font-size: 13px;
    color: {PALETTE['text_secondary']};
}}

QPushButton {{
    background-color: {PALETTE['primary']};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 24px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {PALETTE['primary_hover']};
}}

QPushButton:pressed {{
    background-color: {PALETTE['primary']};
}}

QPushButton:disabled {{
    background-color: {PALETTE['border']};
    color: {PALETTE['text_secondary']};
}}

QPushButton#secondary {{
    background-color: white;
    color: {PALETTE['primary']};
    border: 1px solid {PALETTE['primary_light']};
}}

QPushButton#secondary:hover {{
    background-color: {PALETTE['primary_light']};
}}

QLineEdit, QComboBox {{
    background-color: white;
    border: 1px solid {PALETTE['border']};
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 20px;
}}

QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {PALETTE['primary']};
}}

QComboBox::drop-down {{
    border: none;
    width: 30px;
}}

QComboBox QAbstractItemView {{
    border: 1px solid {PALETTE['border']};
    border-radius: 8px;
    background-color: white;
    selection-background-color: {PALETTE['primary_light']};
}}

QProgressBar {{
    border: none;
    border-radius: 6px;
    background-color: {PALETTE['border']};
    text-align: center;
    height: 16px;
}}

QProgressBar::chunk {{
    border-radius: 6px;
    background-color: {PALETTE['primary']};
}}

QListWidget {{
    background-color: white;
    border: 1px solid {PALETTE['border']};
    border-radius: 12px;
    padding: 8px;
    outline: none;
}}

QListWidget::item {{
    border-bottom: 1px solid {PALETTE['border']};
    padding: 12px;
    border-radius: 8px;
}}

QListWidget::item:selected {{
    background-color: {PALETTE['primary_light']};
    color: {PALETTE['text']};
}}

QListWidget::item:hover {{
    background-color: {PALETTE['bg_top']};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background: {PALETTE['border']};
    border-radius: 4px;
    min-height: 40px;
}}

QScrollBar::handle:vertical:hover {{
    background: {PALETTE['text_secondary']};
}}

QTextEdit {{
    background-color: white;
    border: 1px solid {PALETTE['border']};
    border-radius: 12px;
    padding: 12px;
}}
"""

def apply_palette(app):
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(PALETTE["bg_top"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(PALETTE["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(PALETTE["card"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(PALETTE["bg_bottom"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(PALETTE["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(PALETTE["primary"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("white"))
    app.setPalette(palette)
