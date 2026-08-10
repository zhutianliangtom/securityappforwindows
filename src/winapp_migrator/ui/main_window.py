import os
import sys
import ctypes
from pathlib import Path
from typing import List

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QListWidget, QListWidgetItem, QProgressBar,
    QTextEdit, QMessageBox, QApplication, QSizePolicy, QSpacerItem,
    QFileDialog, QDialog, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QIcon, QFont, QFontDatabase

from winapp_migrator.utils.helpers import setup_logging, is_admin, ensure_admin, format_size, get_directory_size, safe_remove
from winapp_migrator.ui.styles import GLOBAL_QSS, PALETTE, apply_palette
from winapp_migrator.ui.widgets import Card, PrimaryButton, SecondaryButton, AppItemDelegate, DataDirDialog, UninstallConfirmDialog
from winapp_migrator.core.app_scanner import AppScanner, AppInfo
from winapp_migrator.core.data_dirs import detect_data_dirs
from winapp_migrator.core.orchestrator import MigrationOrchestrator
from winapp_migrator.core.uninstaller import Uninstaller
from winapp_migrator.core.memory_optimizer import optimize_memory

logger = setup_logging()

# 常见应用中英文别名，用于搜索匹配（如“微信”↔weixin/wechat）
_SEARCH_ALIAS = {
    "微信": {"weixin", "wechat"},
    "qq": {"腾讯", "tim"},
    "tim": {"腾讯", "qq"},
    "腾讯": {"qq", "tim"},
    "钉钉": {"dingtalk"},
    "网易云音乐": {"netease", "cloudmusic"},
    "google chrome": {"谷歌浏览器", "chrome"},
    "chrome": {"谷歌浏览器"},
    "steam": {"蒸汽"},
    "office": {"办公"},
}

_variant_cache = {}


def _variants(name: str) -> set:
    """返回名称及其全部别名的变体集合（带缓存）"""
    n = name.lower()
    cached = _variant_cache.get(n)
    if cached is not None:
        return cached
    out = {n}
    for key, vals in _SEARCH_ALIAS.items():
        if key.lower() == n or n in {v.lower() for v in vals}:
            out.add(key.lower())
            out.update(v.lower() for v in vals)
    _variant_cache[n] = out
    return out


def _app_matches(app, text: str) -> bool:
    """搜索词匹配：原名子串或中英文别名交集"""
    if not text:
        return True
    t = text.lower()
    if t in app.name.lower():
        return True
    return bool(_variants(app.name) & _variants(t))

class ScanWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def run(self):
        try:
            scanner = AppScanner()
            apps = scanner.scan_all()
            self.finished.emit(apps)
        except Exception as e:
            self.error.emit(str(e))

class SizeWorker(QThread):
    """后台并行计算应用目录大小，避免拖慢扫描"""
    sizes_ready = pyqtSignal(dict)

    def __init__(self, apps: List[AppInfo], parent=None):
        super().__init__(parent)
        self.apps = apps

    def run(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        sizes = {}

        def calc(app):
            try:
                return id(app), get_directory_size(app.install_location)
            except Exception:
                return id(app), 0

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(calc, a) for a in self.apps]
            batch = {}
            for fut in as_completed(futures):
                k, v = fut.result()
                sizes[k] = v
                batch[k] = v
                # 分批推送，列表大小渐进显示而非等全部算完
                if len(batch) >= 15:
                    self.sizes_ready.emit(batch)
                    batch = {}
            if batch:
                self.sizes_ready.emit(batch)

class IconLoaderWorker(QThread):
    """后台预取应用图标源文件（目录遍历 IO），主线程负责创建 QIcon"""
    icon_ready = pyqtSignal(object, str)  # AppInfo, 图标源文件路径

    def __init__(self, apps: List[AppInfo], delegate, parent=None):
        super().__init__(parent)
        self.apps = apps
        self.delegate = delegate

    def run(self):
        from concurrent.futures import ThreadPoolExecutor

        def load(app):
            try:
                return app, self.delegate.preload_icon_source(app) or ""
            except Exception:
                return app, ""

        with ThreadPoolExecutor(max_workers=8) as pool:
            for app, source in pool.map(load, self.apps):
                self.icon_ready.emit(app, source)

class MigrateWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, app: AppInfo, target: Path, extra_dirs=None, parent=None):
        super().__init__(parent)
        self.app = app
        self.target = target
        self.extra_dirs = extra_dirs or []
        self.orchestrator = MigrationOrchestrator()

    def run(self):
        try:
            result = self.orchestrator.migrate(self.app, self.target, self.progress.emit, extra_dirs=self.extra_dirs)
            self.finished.emit(result)
        except Exception as e:
            logger.exception("迁移异常")
            self.finished.emit({"success": False, "message": str(e)})

class BuildPlanWorker(QThread):
    """后台构建卸载清单（含注册表/快捷方式扫描），避免阻塞 UI"""
    plan_ready = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, app: AppInfo, uninstaller, parent=None):
        super().__init__(parent)
        self.app = app
        self.uninstaller = uninstaller

    def run(self):
        try:
            self.plan_ready.emit(self.uninstaller.build_plan(self.app))
        except Exception as e:
            logger.exception("构建卸载清单失败")
            self.error.emit(str(e))

class UninstallWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self.plan = plan
        self.uninstaller = Uninstaller()

    def run(self):
        try:
            result = self.uninstaller.uninstall(self.plan, self.progress.emit)
            self.finished.emit(result)
        except Exception as e:
            logger.exception("卸载异常")
            self.finished.emit({"success": False, "message": str(e)})

class MemoryWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def run(self):
        try:
            result = optimize_memory(self.progress.emit)
            self.finished.emit(result)
        except Exception as e:
            logger.exception("内存优化异常")
            self.finished.emit({"success": False, "message": str(e)})


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WinAppMigrator")
        self.setMinimumSize(960, 720)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self.apps: List[AppInfo] = []
        self.selected_app: AppInfo = None
        self.uninstaller = Uninstaller()

        self._setup_ui()
        # 迁移进度平滑动画
        self.progress_anim = QPropertyAnimation(self.progress, b"value", self)
        self.progress_anim.setDuration(350)
        self.progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._check_admin()
        self._start_scan()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._build_title_bar())
        main_layout.addWidget(self._build_content(), stretch=1)

    def _build_title_bar(self):
        bar = QWidget()
        bar.setFixedHeight(52)
        bar.setStyleSheet(f"background-color: {PALETTE['card']}; border-bottom: 1px solid {PALETTE['border']};")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 16, 0)
        layout.setSpacing(12)

        icon = QLabel("◆")
        icon.setStyleSheet(f"color: {PALETTE['primary']}; font-size: 20px; font-weight: 700;")
        layout.addWidget(icon)

        title = QLabel("WinAppMigrator")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {PALETTE['text']};")
        layout.addWidget(title)

        layout.addStretch()

        self.admin_label = QLabel("⚠ 未提权")
        self.admin_label.setStyleSheet(f"color: {PALETTE['danger']}; font-size: 12px;")
        layout.addWidget(self.admin_label)

        min_btn = QPushButton("—")
        min_btn.setFixedSize(32, 32)
        min_btn.setStyleSheet(self._title_btn_style())
        min_btn.clicked.connect(self.showMinimized)
        layout.addWidget(min_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet(self._title_btn_style(hover_color="#FEE2E2", hover_text="#EF4444"))
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        return bar

    def _title_btn_style(self, hover_color="#EFF6FF", hover_text="#2563EB"):
        return f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
                color: {PALETTE['text_secondary']};
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
                color: {hover_text};
            }}
        """

    def _build_content(self):
        content = QWidget()
        content.setStyleSheet(GLOBAL_QSS)
        layout = QHBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        left = self._build_left_panel()
        right = self._build_right_panel()
        layout.addWidget(left, stretch=2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(right)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }}")
        # 将 Card 的阴影移到 ScrollArea 上，避免被 viewport 裁剪
        right.setGraphicsEffect(None)
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        from PyQt6.QtGui import QColor
        shadow = QGraphicsDropShadowEffect(scroll)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(37, 99, 235, 30))
        shadow.setOffset(0, 4)
        scroll.setGraphicsEffect(shadow)
        layout.addWidget(scroll, stretch=1)
        return content

    def _build_left_panel(self):
        card = Card("选择要迁移的应用")
        layout = card.layout

        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索应用名称...")
        self.search_edit.textChanged.connect(self._filter_apps)
        search_layout.addWidget(self.search_edit)

        self.refresh_btn = SecondaryButton("重新扫描")
        self.refresh_btn.clicked.connect(self._start_scan)
        search_layout.addWidget(self.refresh_btn)
        layout.addLayout(search_layout)

        self.app_list = QListWidget()
        self.app_list.setSpacing(2)
        self.app_list.setItemDelegate(AppItemDelegate(self.app_list))
        self.app_list.setMouseTracking(True)
        self.app_list.itemClicked.connect(self._on_app_selected)
        layout.addWidget(self.app_list)

        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet(f"color: {PALETTE['text_secondary']}; font-size: 12px;")

        # 扫描进行中的忙碌动画条
        self.scan_progress = QProgressBar()
        self.scan_progress.setRange(0, 0)  # busy 模式：持续滚动
        self.scan_progress.setFixedHeight(8)
        self.scan_progress.setTextVisible(False)
        self.scan_progress.hide()

        status_row = QHBoxLayout()
        status_row.addWidget(self.status_label)
        status_row.addWidget(self.scan_progress, stretch=1)
        layout.addLayout(status_row)

        return card

    def _build_right_panel(self):
        card = Card("迁移设置")
        layout = card.layout

        drive_label = QLabel("目标盘符")
        drive_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(drive_label)

        self.drive_combo = QComboBox()
        self._populate_drives()
        layout.addWidget(self.drive_combo)

        target_label = QLabel("目标路径")
        target_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(target_label)

        target_row = QHBoxLayout()
        self.target_path_edit = QLineEdit()
        self.target_path_edit.setPlaceholderText("自动生成，可修改（如 D:\\Apps\\微信）")
        self.drive_combo.currentIndexChanged.connect(self._refresh_target_path)
        target_row.addWidget(self.target_path_edit, stretch=1)
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_target)
        target_row.addWidget(browse_btn)
        layout.addLayout(target_row)

        self.info_label = QTextEdit()
        self.info_label.setReadOnly(True)
        self.info_label.setPlaceholderText("在左侧选择应用后，此处显示详细信息")
        self.info_label.setMaximumHeight(160)
        layout.addWidget(self.info_label)

        self.open_dir_btn = SecondaryButton("打开安装目录")
        self.open_dir_btn.setEnabled(False)
        self.open_dir_btn.clicked.connect(self._open_app_dir)
        layout.addWidget(self.open_dir_btn)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setPlaceholderText("迁移日志...")
        layout.addWidget(self.log_edit)

        self.migrate_btn = PrimaryButton("开始迁移")
        self.migrate_btn.setEnabled(False)
        self.migrate_btn.clicked.connect(self._start_migration)
        layout.addWidget(self.migrate_btn)

        self.uninstall_btn = QPushButton("强力卸载")
        self.uninstall_btn.setEnabled(False)
        self.uninstall_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.uninstall_btn.setMinimumHeight(40)
        self.uninstall_btn.setStyleSheet(
            f"background-color: {PALETTE['danger']}; color: white; font-weight: 700; "
            "border: none; border-radius: 10px; padding: 10px 24px;"
        )
        self.uninstall_btn.clicked.connect(self._start_uninstall)
        layout.addWidget(self.uninstall_btn)

        custom_btn = SecondaryButton("迁移自定义文件夹")
        custom_btn.clicked.connect(self._migrate_custom_folder)
        layout.addWidget(custom_btn)

        self.memory_btn = QPushButton("一键优化内存")
        self.memory_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.memory_btn.setMinimumHeight(40)
        self.memory_btn.setStyleSheet(
            f"background-color: {PALETTE['success']}; color: white; font-weight: 700; "
            "border: none; border-radius: 10px; padding: 10px 24px;"
        )
        self.memory_btn.clicked.connect(self._start_memory_optimize)
        layout.addWidget(self.memory_btn)

        return card

    def _populate_drives(self):
        import string
        from ctypes import windll
        drives = []
        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drives.append(f"{letter}:")
            bitmask >>= 1
        self.drive_combo.clear()
        for d in drives:
            self.drive_combo.addItem(f"{d}\\", d)
        if self.drive_combo.count() == 0:
            self.drive_combo.addItem("C:\\", "C:")

    def _check_admin(self):
        if is_admin():
            self.admin_label.setText("✓ 管理员权限")
            self.admin_label.setStyleSheet(f"color: {PALETTE['success']}; font-size: 12px;")
        else:
            self.admin_label.setText("⚠ 未提权")
            self.admin_label.setStyleSheet(f"color: {PALETTE['danger']}; font-size: 12px;")
            QMessageBox.warning(
                self,
                "需要管理员权限",
                "本工具需要管理员权限才能创建目录联接和修改系统目录。\n请右键以管理员身份运行。",
            )

    def _start_scan(self):
        self.app_list.clear()
        self.status_label.setText("正在扫描已安装应用...")
        self.scan_progress.show()
        self.refresh_btn.setEnabled(False)
        self.scan_worker = ScanWorker()
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.error.connect(self._on_scan_error)
        self.scan_worker.start()

    def _on_scan_finished(self, apps: List[AppInfo]):
        self.apps = apps
        self._filter_apps()
        self.status_label.setText(f"共扫描到 {len(apps)} 个应用")
        self.scan_progress.hide()
        self.refresh_btn.setEnabled(True)
        # 列表先秒出，大小由后台线程补齐
        self.size_worker = SizeWorker(apps, self)
        self.size_worker.sizes_ready.connect(self._on_sizes_ready)
        self.size_worker.start()
        # 图标由后台线程预取源文件，主线程负责创建 QIcon，避免滑动/渲染时阻塞
        delegate = self.app_list.itemDelegate()
        self.icon_worker = IconLoaderWorker(apps, delegate)
        self.icon_worker.icon_ready.connect(self._on_icon_ready)
        self.icon_worker.start()

    def _on_icon_ready(self, app, source: str):
        if app is None:
            return
        delegate = self.app_list.itemDelegate()
        if source:
            delegate.apply_icon(app)
        self.app_list.viewport().update()

    def _on_sizes_ready(self, sizes: dict):
        for i in range(self.app_list.count()):
            item = self.app_list.item(i)
            app = item.data(Qt.ItemDataRole.UserRole) if item else None
            if app and id(app) in sizes:
                app.size_bytes = sizes[id(app)]
        self.app_list.viewport().update()

    def _on_scan_error(self, msg: str):
        self.status_label.setText(f"扫描失败: {msg}")
        self.scan_progress.hide()
        self.refresh_btn.setEnabled(True)

    def _filter_apps(self):
        text = self.search_edit.text().lower()
        # 关闭更新避免逐项插入各自触发重绘
        self.app_list.setUpdatesEnabled(False)
        self.app_list.clear()
        for app in self.apps:
            if text and not _app_matches(app, text):
                continue
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, app)
            item.setSizeHint(QSize(0, AppItemDelegate.ROW_HEIGHT))
            self.app_list.addItem(item)
        self.app_list.setUpdatesEnabled(True)
        self.app_list.viewport().update()

    def _select_app(self, app: AppInfo):
        self.selected_app = app
        self.info_label.setHtml(f"""
        <p style="margin:4px 0;"><b>名称:</b> {app.name}</p>
        <p style="margin:4px 0;"><b>类型:</b> {app.app_type}</p>
        <p style="margin:4px 0;"><b>版本:</b> {app.version or '未知'}</p>
        <p style="margin:4px 0;"><b>大小:</b> {format_size(app.size_bytes)}</p>
        <p style="margin:4px 0;"><b>路径:</b> {app.install_location}</p>
        """)
        self.migrate_btn.setEnabled(True)
        self.uninstall_btn.setEnabled(True)
        self.open_dir_btn.setEnabled(True)
        self._refresh_target_path()

    def _open_app_dir(self):
        """在资源管理器中打开所选应用的安装目录"""
        if not self.selected_app:
            return
        loc = self.selected_app.install_location
        if loc and loc.is_dir():
            try:
                os.startfile(str(loc))
            except Exception as e:
                logger.warning("打开目录失败 %s: %s", loc, e)
                QMessageBox.warning(self, "无法打开", f"无法打开目录：{loc}\n{e}")
        else:
            QMessageBox.warning(self, "无法打开", f"目录不存在：{loc}")

    def _refresh_target_path(self):
        """按选中 app 与目标盘生成默认目标路径（用户手动编辑过则不覆盖）"""
        if not self.selected_app or not hasattr(self, "target_path_edit"):
            return
        if self.target_path_edit.isModified():
            return
        drive = self.drive_combo.currentData() or ""
        self.target_path_edit.setText(
            f"{drive}\\WinAppMigrator\\{self.selected_app.app_type}\\{self.selected_app.name}")

    def _browse_target(self):
        """通过文件夹对话框选择/新建目标位置（支持同盘迁移，选择后在所选目录下创建 app 目录）"""
        app = self.selected_app
        if not app:
            return
        current = self.target_path_edit.text().strip()
        start = str(Path(current).parent) if current and Path(current).parent.is_dir() \
            else str(Path(self.drive_combo.currentData() or "C:\\"))
        folder = QFileDialog.getExistingDirectory(
            self, "选择目标位置（可在对话框内新建文件夹）", start,
            QFileDialog.Option.ShowDirsOnly)
        if not folder:
            return
        self.target_path_edit.setText(str(Path(folder) / app.name))
        self.target_path_edit.setModified(True)  # 用户自定义目标，后续不再自动覆盖

    def _resolve_target(self):
        """解析迁移目标路径：用户自定义或自动生成，并校验合法性"""
        text = self.target_path_edit.text().strip()
        if not text:
            self._refresh_target_path()
            text = self.target_path_edit.text().strip()
        path = Path(text)
        if not path.is_absolute():
            QMessageBox.warning(self, "路径无效", "目标路径必须是绝对路径，例如 D:\\Apps\\微信")
            return None
        # 盘符根目录（如 C:\）作为目标时，自动在其下创建 app 同名目录
        if path.anchor and str(path).rstrip("\\").lower() == path.anchor.rstrip("\\").lower():
            path = path / self.selected_app.name
        # 目标已存在不在此拒绝，交由 _start_migration 提供 覆盖/自动改名 处理
        if path == self.selected_app.install_location:
            QMessageBox.warning(self, "路径无效", "目标路径不能与源路径相同")
            return None
        return path

    def _on_app_selected(self, item: QListWidgetItem):
        app = item.data(Qt.ItemDataRole.UserRole)
        if app:
            self._select_app(app)

    def _start_migration(self):
        if not self.selected_app:
            return
        if not is_admin():
            QMessageBox.warning(self, "权限不足", "请以管理员身份运行本工具。")
            return

        drive = Path(self.drive_combo.currentData())
        target = self._resolve_target()
        if target is None:
            return
        # 目标目录已存在：提供 覆盖/自动改名 处理，避免直接失败
        if target.exists():
            reply = QMessageBox.question(
                self,
                "目标目录已存在",
                f"目标位置已存在：<b>{target}</b>\n\n"
                "选择「覆盖」将删除该目录后迁移（原内容不可恢复）；\n"
                "选择「改名」将自动在名称后加序号迁移到新位置。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                if not safe_remove(target):
                    QMessageBox.warning(self, "无法覆盖", f"无法删除已存在的目标目录：{target}")
                    return
            elif reply == QMessageBox.StandardButton.No:
                n = 1
                while True:
                    cand = Path(f"{target}_{n}")
                    if not cand.exists():
                        target = cand
                        break
                    n += 1
                self.target_path_edit.setText(str(target))
            else:
                return
        reply = QMessageBox.question(
            self,
            "确认迁移",
            f"确定将 <b>{self.selected_app.name}</b> 迁移到 <b>{target}</b> 吗？\n"
            f"迁移后旧安装目录将被删除，注册表与快捷方式将更新到新路径。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        extra_dirs = self._choose_extra_dirs()

        self.migrate_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.progress.setValue(0)
        self.log_edit.clear()

        self.migrate_worker = MigrateWorker(self.selected_app, target, extra_dirs)
        self.migrate_worker.progress.connect(self._on_progress)
        self.migrate_worker.finished.connect(self._on_migrate_finished)
        self.migrate_worker.start()

    def _choose_extra_dirs(self):
        """检测并让用户勾选要一并迁移的数据目录，返回勾选的目录列表"""
        try:
            candidates = detect_data_dirs(self.selected_app)
        except Exception:
            candidates = []
        if not candidates:
            return []
        dlg = DataDirDialog(candidates, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.selected()
        return []

    def _on_progress(self, percent: int, message: str):
        self.log_edit.append(f"[{percent}%] {message}")
        # 进度平滑过渡动画
        self.progress_anim.stop()
        self.progress_anim.setStartValue(self.progress.value())
        self.progress_anim.setEndValue(percent)
        self.progress_anim.start()

    def _warn_360_blocked(self, blocked: list):
        """360 自我保护拦截终止时的引导弹窗"""
        names = "、".join(blocked) if blocked else "360安全卫士相关进程"
        QMessageBox.warning(
            self,
            "360 自我保护",
            "检测到 360 安全卫士的进程无法被强制结束。\n"
            "360 的自我保护会在系统内核层拦截强制终止，属于其正常安全机制。\n\n"
            "请任选其一操作后再重试：\n"
            "1. 右键 360 托盘图标 → 退出 360\n"
            "2. 打开 360 设置 → 防护中心 → 关闭「自我保护」\n\n"
            f"未能结束的进程：{names}",
        )

    def _on_migrate_finished(self, result: dict):
        self.migrate_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        if result.get("blocked_360"):
            self._warn_360_blocked(result.get("blocked") or [])
        if result.get("success"):
            self.progress.setValue(100)
            QMessageBox.information(
                self,
                "迁移成功",
                f"{result['message']}\n\n"
                f"新位置: {result['target']}\n"
                f"注册表更新: {result.get('registry_changed', 0)} 处\n"
                f"快捷方式更新: {result.get('shortcuts_changed', 0)} 个",
            )
        else:
            self.progress.setValue(0)
            QMessageBox.critical(self, "迁移失败", result.get("message", "未知错误"))

    def _start_uninstall(self):
        if not self.selected_app:
            return
        if not is_admin():
            QMessageBox.warning(self, "权限不足", "请以管理员身份运行本工具。")
            return
        # 后台构建卸载清单（注册表/快捷方式预扫描），期间 UI 保持响应
        self.migrate_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.uninstall_btn.setEnabled(False)
        self.status_label.setText("正在分析应用...")
        self.build_worker = BuildPlanWorker(self.selected_app, self.uninstaller)
        self.build_worker.plan_ready.connect(self._on_plan_ready)
        self.build_worker.error.connect(self._on_plan_error)
        self.build_worker.start()

    def _restore_buttons(self):
        self.migrate_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.uninstall_btn.setEnabled(True)
        if hasattr(self, "status_label"):
            self.status_label.setText(f"共扫描到 {len(self.apps)} 个应用" if self.apps else "就绪")

    def _on_plan_ready(self, plan):
        self._restore_buttons()
        dlg = UninstallConfirmDialog(plan, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.progress.setValue(0)
        self.log_edit.clear()
        self.migrate_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.uninstall_btn.setEnabled(False)
        self.uninstall_worker = UninstallWorker(plan)
        self.uninstall_worker.progress.connect(self._on_progress)
        self.uninstall_worker.finished.connect(self._on_uninstall_finished)
        self.uninstall_worker.start()

    def _on_plan_error(self, msg: str):
        self._restore_buttons()
        QMessageBox.critical(self, "分析失败", f"无法分析该应用: {msg}")

    def _on_uninstall_finished(self, result: dict):
        self.migrate_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.uninstall_btn.setEnabled(True)
        if result.get("blocked_360"):
            self._warn_360_blocked(result.get("blocked") or [])
        if result.get("success"):
            self.progress.setValue(100)
            removed = result.get("removed_dirs") or []
            failed = result.get("failed") or []
            msg = (
                f"{result['message']}\n\n"
                f"已删除目录:\n" + ("\n".join(removed) if removed else "（无）") +
                f"\n\n注册表清理: {result.get('registry_removed', 0)} 处\n"
                f"快捷方式清理: {result.get('shortcuts_removed', 0)} 个"
            )
            if failed:
                msg += "\n\n以下删除失败:\n" + "\n".join(failed)
            QMessageBox.information(self, "卸载完成", msg)
            self._start_scan()  # 刷新应用列表
        else:
            self.progress.setValue(0)
            QMessageBox.critical(self, "卸载失败", result.get("message", "未知错误"))

    def _migrate_custom_folder(self):
        if not is_admin():
            QMessageBox.warning(self, "权限不足", "请以管理员身份运行本工具。")
            return
        folder = QFileDialog.getExistingDirectory(self, "选择要迁移的文件夹")
        if not folder:
            return
        drive = Path(self.drive_combo.currentData())
        app = AppInfo(
            name=Path(folder).name,
            publisher="",
            install_location=Path(folder),
            version="",
            app_type="自定义",
            size_bytes=0,
        )
        self.selected_app = app
        self._start_migration()

    def _start_memory_optimize(self):
        """一键优化内存"""
        reply = QMessageBox.question(
            self,
            "确认优化内存",
            "将强制把后台进程/服务的内存页面换出到虚拟内存（硬盘），\n"
            "释放物理 RAM 供前台程序使用。\n\n"
            "不会终止任何进程。后台进程被访问时会从硬盘换回，\n"
            "可能有短暂延迟，不影响前台程序。\n\n确定继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.memory_btn.setEnabled(False)
        self.migrate_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.progress.setValue(0)
        self.log_edit.clear()
        self.status_label.setText("正在优化内存...")

        self.memory_worker = MemoryWorker()
        self.memory_worker.progress.connect(self._on_progress)
        self.memory_worker.finished.connect(self._on_memory_finished)
        self.memory_worker.start()

    def _on_memory_finished(self, result: dict):
        self.memory_btn.setEnabled(True)
        self.migrate_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.status_label.setText(f"共扫描到 {len(self.apps)} 个应用" if self.apps else "就绪")

        if result.get("success"):
            self.progress.setValue(100)
            details = result.get("details", [])
            detail_text = "\n".join(f"  - {d}" for d in details) if details else ""
            QMessageBox.information(
                self,
                "内存优化完成",
                f"{result['message']}\n\n"
                f"优化详情:\n{detail_text}",
            )
        else:
            self.progress.setValue(0)
            QMessageBox.critical(self, "优化失败", result.get("message", "未知错误"))

    def mousePressEvent(self, event):
        # 标题栏区域按下左键时，交给系统原生拖动，避免 DPI 缩放导致的坐标漂移
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 52:
            window = self.windowHandle()
            if window is not None:
                window.startSystemMove()
            event.accept()
