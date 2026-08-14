"""WinAppMigrator 自写安装器 / 卸载器（PyQt6）

单一源码，两种模式：
  - 安装模式（默认）：向导式安装，复制主应用、创建快捷方式、写入卸载注册表
  - 卸载模式（--uninstall 参数或程序名为 uninstall.exe）：确认后删除

打包方式（PyInstaller）：
  - WinAppMigrator_Setup.exe : onefile + uac_admin，通过 Tree() 嵌入 dist/WinAppMigrator
  - uninstall.exe             : onefile + uac_admin，无数据负载
"""

import os
import sys
import shutil
import time
import tempfile
import subprocess
import winreg
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QCheckBox, QProgressBar, QStackedWidget,
    QMessageBox, QFrame,
)

APP_NAME = "zhuzhu Copilot"
APP_VERSION = "3.0.0"
APP_PUBLISHER = "zhutianliang"
UNINSTALL_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\zhuzhu Copilot"

# ------------------------------------------------------------
# 模式判断
# ------------------------------------------------------------
# 卸载器 exe 名为 uninstall* 时直接进入卸载模式（无需参数）
_IS_UNINSTALL_EXE = os.path.basename(sys.executable).lower().startswith("uninstall")
IS_UNINSTALL = "--uninstall" in sys.argv or _IS_UNINSTALL_EXE
IS_RESUME = "--resume" in sys.argv  # 卸载器 temp 副本静默执行

# ------------------------------------------------------------
# 配色（与主程序一致的蓝白主题）
# ------------------------------------------------------------
PALETTE = {
    "bg_top": "#F8FAFF", "bg_bottom": "#EFF6FF", "card": "#FFFFFF",
    "primary": "#2563EB", "primary_hover": "#1D4ED8", "primary_light": "#DBEAFE",
    "text": "#1E293B", "text_secondary": "#64748B", "border": "#E2E8F0",
    "success": "#10B981", "warning": "#F59E0B", "danger": "#EF4444",
}

GLOBAL_QSS = f"""
QMainWindow, QWidget {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {PALETTE['bg_top']}, stop:1 {PALETTE['bg_bottom']});
    color: {PALETTE['text']};
    font-family: "Microsoft YaHei UI", "Segoe UI", "Segoe UI Emoji", sans-serif;
    font-size: 14px;
}}
QLabel {{ color: {PALETTE['text']}; background: transparent; }}
QFrame#nav {{ background: white; border: 1px solid {PALETTE['border']}; border-radius: 14px; }}
QLabel#title {{ font-size: 22px; font-weight: 700; color: {PALETTE['primary']}; }}
QLabel#hint {{ font-size: 13px; color: {PALETTE['text_secondary']}; }}
QLabel#bigEmoji {{ font-size: 40px; }}
QLabel#doneTitle {{ font-size: 24px; font-weight: 700; color: {PALETTE['success']}; }}
QPushButton {{
    background-color: {PALETTE['primary']}; color: white; border: none;
    border-radius: 8px; padding: 10px 26px; font-weight: 600; font-size: 14px;
}}
QPushButton:hover {{ background-color: {PALETTE['primary_hover']}; }}
QPushButton:disabled {{ background-color: {PALETTE['border']}; color: {PALETTE['text_secondary']}; }}
QPushButton#ghost {{
    background: transparent; color: {PALETTE['text_secondary']};
    border: 1px solid {PALETTE['border']};
}}
QPushButton#ghost:hover {{ color: {PALETTE['primary']}; border-color: {PALETTE['primary']}; }}
QLineEdit {{
    background: white; border: 1px solid {PALETTE['border']}; border-radius: 8px;
    padding: 8px 12px; min-height: 20px;
}}
QLineEdit:focus {{ border: 1px solid {PALETTE['primary']}; }}
QCheckBox {{ font-size: 14px; background: transparent; }}
QProgressBar {{
    border: none; border-radius: 6px; background-color: {PALETTE['border']};
    text-align: center; height: 18px; font-size: 12px;
}}
QProgressBar::chunk {{ border-radius: 6px; background-color: {PALETTE['primary']}; }}
"""


# ------------------------------------------------------------
# 工具函数（真实 Win32/COM/注册表 API）
# ------------------------------------------------------------
def app_source() -> Path:
    """主应用数据源：打包后取 _MEIPASS/app，开发模式取 dist/WinAppMigrator"""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", "."))
        p = base / "app"
        if p.is_dir():
            return p
    return Path(__file__).resolve().parent.parent / "dist" / "zhuzhu Copilot"


def default_install_dir() -> str:
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    return str(Path(pf) / APP_NAME)


def _program_data_dirs() -> tuple[Path, Path]:
    """返回 (开始菜单程序目录, 公共桌面目录)"""
    program_data = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    start_menu = program_data / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    public = Path(os.environ.get("PUBLIC", r"C:\Users\Public"))
    desktop = public / "Desktop"
    return start_menu, desktop


def create_shortcut(lnk_path: Path, target_exe: str, icon_exe: str = "", description: str = ""):
    """通过 WScript.Shell COM 创建 .lnk 快捷方式（真实 API）"""
    import win32com.client
    lnk_path.parent.mkdir(parents=True, exist_ok=True)
    shell = win32com.client.Dispatch("WScript.Shell")
    sc = shell.CreateShortCut(str(lnk_path))
    sc.TargetPath = target_exe
    sc.WorkingDirectory = str(Path(target_exe).parent)
    sc.IconLocation = icon_exe or target_exe
    if description:
        sc.Description = description
    sc.Save()


def remove_shortcuts():
    """删除开始菜单与桌面的快捷方式"""
    start_menu, desktop = _program_data_dirs()
    for lnk in (start_menu / f"{APP_NAME}.lnk", desktop / f"{APP_NAME}.lnk"):
        try:
            if lnk.exists():
                lnk.unlink()
        except OSError:
            pass


def write_uninstall_reg(install_dir: str):
    """写入卸载注册表（HKLM Uninstall 键）"""
    key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_REG_PATH)
    exe = os.path.join(install_dir, f"{APP_NAME}.exe")
    uninstaller = os.path.join(install_dir, "uninstall.exe")
    est = 0
    try:
        for root, dirs, files in os.walk(install_dir):
            est += sum(os.path.getsize(os.path.join(root, f)) for f in files)
    except OSError:
        pass
    values = {
        "DisplayName": APP_NAME,
        "DisplayVersion": APP_VERSION,
        "Publisher": APP_PUBLISHER,
        "InstallLocation": install_dir,
        "UninstallString": f'"{uninstaller}"',
        "DisplayIcon": exe,
        "EstimatedSize": str(est // 1024),
        "NoModify": "1",
        "NoRepair": "1",
    }
    for k, v in values.items():
        winreg.SetValueEx(key, k, 0, winreg.REG_SZ, v)
    winreg.CloseKey(key)


def remove_uninstall_reg():
    """删除卸载注册表键"""
    try:
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_REG_PATH)
    except FileNotFoundError:
        pass


def remove_user_data():
    """彻底删除应用全部用户数据（~/.winapp_migrator）：
    用户技能（skills/、skills.json）、对话记录（sessions/、context.json）、
    全部配置（settings.json/tts.json/todos.json/memory.md/mcp_servers.json 等）、
    浏览器登录态（browser_profile）。重试处理文件占用，最后用 rd /s /q 兜底。"""
    root = Path.home() / ".winapp_migrator"
    if not root.exists():
        return
    for _ in range(10):   # 被占用文件重试（0.5s 间隔）
        try:
            shutil.rmtree(root)
            return
        except OSError:
            time.sleep(0.5)
    # 仍失败：cmd 延迟强制清除（文件释放后自动清理）
    try:
        subprocess.Popen(
            f'ping -n 4 127.0.0.1 > nul & rd /s /q "{root}"',
            shell=True, creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True,
        )
    except OSError:
        pass


def _kill_main_app():
    """强制结束主程序进程（否则会锁住用户数据/安装目录）"""
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", f"{APP_NAME}.exe"],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10,
        )
    except OSError:
        pass


def read_install_location() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_REG_PATH) as key:
            val, _ = winreg.QueryValueEx(key, "InstallLocation")
        p = Path(val)
        return p if p.is_dir() else None
    except OSError:
        return None


def walk_files(src: Path) -> list[Path]:
    """列出源目录全部文件（真实遍历）"""
    return [p for p in src.rglob("*") if p.is_file()]


# ------------------------------------------------------------
# 安装工作线程
# ------------------------------------------------------------
class InstallWorker(QThread):
    progress = pyqtSignal(int, int, str)   # 已复制数, 总数, 当前文件
    done = pyqtSignal(bool, str)

    def __init__(self, src: Path, dst: Path, desktop_icon: bool, parent=None):
        super().__init__(parent)
        self.src, self.dst = src, dst
        self.desktop_icon = desktop_icon

    def run(self):
        try:
            files = walk_files(self.src)
            total = len(files)
            for i, f in enumerate(files, 1):
                rel = f.relative_to(self.src)
                target = self.dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
                if i == total or i % 5 == 0:
                    self.progress.emit(i, total, f"正在搬运 {rel.name} …")
            self.progress.emit(total, total, "正在安家落户：创建快捷方式 …")
            start_menu, _ = _program_data_dirs()
            create_shortcut(start_menu / f"{APP_NAME}.lnk", str(self.dst / f"{APP_NAME}.exe"))
            if self.desktop_icon:
                _, desktop = _program_data_dirs()
                create_shortcut(desktop / f"{APP_NAME}.lnk", str(self.dst / f"{APP_NAME}.exe"))
            self.progress.emit(total, total, "正在登记卸载信息 …")
            write_uninstall_reg(str(self.dst))
            self.done.emit(True, "")
        except Exception as e:  # noqa: BLE001
            self.done.emit(False, str(e))


# ------------------------------------------------------------
# 卸载工作线程（实时进度 + 百分比）
# ------------------------------------------------------------
# 各步骤权重（总计 100%）
_UNINSTALL_STEPS = [
    (5,  "正在结束主程序进程"),        # 0-5%
    (5,  "正在删除快捷方式"),          # 5-10%
    (5,  "正在清理卸载注册表"),        # 10-15%
    (15, "正在删除用户数据"),          # 15-30%
    (10, "正在准备最终清理"),          # 30-40%
    (55, "正在删除安装目录"),          # 40-95%
    (5,  "清理完成"),                 # 95-100%
]


class UninstallWorker(QThread):
    progress = pyqtSignal(int, str)   # 百分比, 状态文本
    done = pyqtSignal(bool, str)

    def __init__(self, install_dir: Path, parent=None):
        super().__init__(parent)
        self.install_dir = install_dir

    def _emit(self, pct: int, msg: str):
        self.progress.emit(pct, msg)
        time.sleep(0.05)

    def run(self):
        try:
            base = 0
            self._emit(base, _UNINSTALL_STEPS[0][1])
            _kill_main_app()
            base += _UNINSTALL_STEPS[0][0]

            self._emit(base, _UNINSTALL_STEPS[1][1])
            remove_shortcuts()
            base += _UNINSTALL_STEPS[1][0]

            self._emit(base, _UNINSTALL_STEPS[2][1])
            remove_uninstall_reg()
            base += _UNINSTALL_STEPS[2][0]

            self._emit(base, _UNINSTALL_STEPS[3][1])
            remove_user_data()
            base += _UNINSTALL_STEPS[3][0]

            self._emit(base, _UNINSTALL_STEPS[4][1])
            temp_copy = Path(tempfile.gettempdir()) / f"uninstall_{APP_NAME}_{os.getpid()}.exe"
            shutil.copy2(sys.executable, temp_copy)
            subprocess.Popen(
                [str(temp_copy), "--uninstall", "--resume", str(self.install_dir)],
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=True,
            )
            base += _UNINSTALL_STEPS[4][0]

            self._emit(base, _UNINSTALL_STEPS[5][1])
            step_pct = _UNINSTALL_STEPS[5][0]
            deadline = time.time() + 90
            start = time.time()
            while time.time() < deadline and self.install_dir.exists():
                elapsed = time.time() - start
                sub_pct = min(elapsed / 30.0, 1.0) * 0.8
                self._emit(int(base + step_pct * sub_pct),
                           f"正在删除安装目录… ({int(elapsed)}s)")
                time.sleep(0.5)
            if self.install_dir.exists():
                self._emit(int(base + step_pct * 0.9), "强制清理残留目录…")
                try:
                    subprocess.Popen(
                        f'ping -n 4 127.0.0.1 > nul & rd /s /q "{self.install_dir}"',
                        shell=True, creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True,
                    )
                except OSError:
                    pass
                for _ in range(10):
                    time.sleep(1)
                    if not self.install_dir.exists():
                        break
                if self.install_dir.exists():
                    raise RuntimeError("安装目录删除超时，请手动删除残留目录")

            self._emit(100, _UNINSTALL_STEPS[6][1])
            self.done.emit(True, str(temp_copy))
        except Exception as e:
            self.done.emit(False, str(e))


# ------------------------------------------------------------
# 安装向导 UI
# ------------------------------------------------------------
class InstallWizard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} 安装向导")
        self.setMinimumSize(820, 600)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)

        self.install_dir = default_install_dir()
        self.install_worker = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(18)

        # ---- 左侧步骤导航 ----
        nav = QFrame()
        nav.setObjectName("nav")
        nav.setFixedWidth(210)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(16, 24, 16, 24)
        nav_layout.setSpacing(6)
        logo = QLabel("🛟")
        logo.setObjectName("bigEmoji")
        nav_layout.addWidget(logo)
        name = QLabel(APP_NAME)
        name.setStyleSheet("font-size: 16px; font-weight: 700; color: #2563EB;")
        name.setWordWrap(True)
        nav_layout.addWidget(name)
        nav_layout.addSpacing(12)
        self.step_labels = []
        for i, t in enumerate(["欢迎", "选择目录", "附加任务", "正在安装", "完成"]):
            lb = QLabel(f"{i + 1}. {t}")
            self.step_labels.append(lb)
            nav_layout.addWidget(lb)
        nav_layout.addStretch(1)
        tip = QLabel("🚚 绿色 · 无损 · 管搬家")
        tip.setObjectName("hint")
        nav_layout.addWidget(tip)
        root.addWidget(nav)

        # ---- 右侧内容区 ----
        right = QVBoxLayout()
        right.setSpacing(14)
        self.stack = QStackedWidget()
        self._build_pages()
        right.addWidget(self.stack, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_back = QPushButton("← 上一步")
        self.btn_back.setObjectName("ghost")
        self.btn_back.clicked.connect(self._go_back)
        self.btn_next = QPushButton("下一步 →")
        self.btn_next.clicked.connect(self._go_next)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("ghost")
        self.btn_cancel.clicked.connect(self.close)
        self.btn_run = QPushButton("🚀 立即启动")
        self.btn_run.clicked.connect(self._launch_app)
        btns.addWidget(self.btn_back)
        btns.addWidget(self.btn_next)
        btns.addWidget(self.btn_run)
        btns.addWidget(self.btn_cancel)
        right.addLayout(btns)
        root.addLayout(right, 1)

        self._refresh_steps()
        self._sync_buttons()

    # ---- 页面构建 ----
    def _build_pages(self):
        # 页1：欢迎
        p1 = QWidget()
        l1 = QVBoxLayout(p1)
        l1.setContentsMargins(8, 12, 8, 12)
        emoji = QLabel("🫠")
        emoji.setObjectName("bigEmoji")
        l1.addWidget(emoji)
        t1 = QLabel("听说你的 C 盘又红了？")
        t1.setObjectName("title")
        l1.addWidget(t1)
        h1 = QLabel(
            "💡 别担心，这不是你的问题 — 是 Windows 的问题（确信）。\n\n"
            "🏠 本工具将把你的应用从 C 盘连根拔起，\n"
            "搬到它们该去的广袤天地。\n\n"
            "🛸 准备好了吗？让我们开始这场搬家大冒险！"
        )
        h1.setObjectName("hint")
        h1.setWordWrap(True)
        l1.addWidget(h1)
        l1.addSpacing(10)
        # 功能简介卡片（保持一贯的轻松风格，介绍本工具能做什么）
        feat = QFrame()
        feat.setStyleSheet(
            "QFrame { background: white; border: 1px solid #E2E8F0; border-radius: 12px; }"
            "QLabel { color: #1E293B; font-size: 13px; padding: 2px 0; }"
        )
        fl = QVBoxLayout(feat)
        fl.setContentsMargins(16, 12, 16, 12)
        fl.setSpacing(4)
        ftitle = QLabel("🛠️ 它能帮你做这些：")
        ftitle.setStyleSheet("font-size: 14px; font-weight: 700; color: #2563EB;")
        fl.addWidget(ftitle)
        for line in [
            "📦 应用搬家：把 C 盘的应用一键搬到别的盘，绿色无损",
            "🧹 应用卸载：连根拔起，绝不留下一点垃圾",
            "⚡ 一键优化内存：卡顿？给你的内存做个大扫除",
            "🛡️ 静默防护：恶意进程/启动项自动拦截，超凶",
            "🤖 zhuzhu Copilot：AI 帮你干活，说句话就行",
            "🚀 高速下载：多线程并发，下载快到飞起",
        ]:
            fl.addWidget(QLabel(line))
        l1.addWidget(feat)
        l1.addStretch(1)
        self.stack.addWidget(p1)

        # 页2：选择目录
        p2 = QWidget()
        l2 = QVBoxLayout(p2)
        l2.setContentsMargins(8, 12, 8, 12)
        t2 = QLabel("📁 选个新家给应用们")
        t2.setObjectName("title")
        l2.addWidget(t2)
        h2 = QLabel("应用们：C 盘太挤了，我们要搬去大房子！🏠\n（卸载后文件不会搬回去，选之前想清楚哦）")
        h2.setObjectName("hint")
        h2.setWordWrap(True)
        l2.addWidget(h2)
        l2.addSpacing(16)
        row = QHBoxLayout()
        self.dir_edit = QLineEdit(self.install_dir)
        self.dir_edit.textChanged.connect(self._on_dir_changed)
        btn_browse = QPushButton("浏览…")
        btn_browse.setObjectName("ghost")
        btn_browse.clicked.connect(self._browse_dir)
        row.addWidget(self.dir_edit, 1)
        row.addWidget(btn_browse)
        l2.addLayout(row)
        self.disk_hint = QLabel("")
        self.disk_hint.setObjectName("hint")
        l2.addWidget(self.disk_hint)
        l2.addStretch(1)
        self.stack.addWidget(p2)

        # 页3：附加任务
        p3 = QWidget()
        l3 = QVBoxLayout(p3)
        l3.setContentsMargins(8, 12, 8, 12)
        t3 = QLabel("✅ 附加任务")
        t3.setObjectName("title")
        l3.addWidget(t3)
        h3 = QLabel("选择安装程序需要执行的附加任务。")
        h3.setObjectName("hint")
        l3.addWidget(h3)
        l3.addSpacing(16)
        self.chk_desktop = QCheckBox("🗺️ 在桌面创建快捷方式（强烈建议，不然你找不到它！）")
        self.chk_desktop.setChecked(True)
        l3.addWidget(self.chk_desktop)
        l3.addStretch(1)
        self.stack.addWidget(p3)

        # 页4：安装进度
        p4 = QWidget()
        l4 = QVBoxLayout(p4)
        l4.setContentsMargins(8, 12, 8, 12)
        t4 = QLabel("📦 正在施展搬家魔法…")
        t4.setObjectName("title")
        l4.addWidget(t4)
        h4 = QLabel("⏳ 稍安勿躁，好工具值得等待。")
        h4.setObjectName("hint")
        l4.addWidget(h4)
        l4.addSpacing(20)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        l4.addWidget(self.progress_bar)
        self.install_status = QLabel("准备就绪…")
        self.install_status.setObjectName("hint")
        l4.addWidget(self.install_status)
        l4.addStretch(1)
        self.stack.addWidget(p4)

        # 页5：完成
        p5 = QWidget()
        l5 = QVBoxLayout(p5)
        l5.setContentsMargins(8, 12, 8, 12)
        emoji5 = QLabel("🎉")
        emoji5.setObjectName("bigEmoji")
        l5.addWidget(emoji5)
        t5 = QLabel("安装完成 — C 盘救星已上线！")
        t5.setObjectName("doneTitle")
        l5.addWidget(t5)
        h5 = QLabel(
            "⚔️ zhuzhu Copilot 已就位，随时待命。\n\n"
            "📌 记住：\n  🔴 红色的 C 盘 = 病，得治。\n  💊 本工具 = 你的处方药。\n\n"
            "      C 盘：谢谢你… 🥹"
        )
        h5.setObjectName("hint")
        h5.setWordWrap(True)
        l5.addWidget(h5)
        l5.addStretch(1)
        self.stack.addWidget(p5)

    # ---- 步骤控制 ----
    def _refresh_steps(self):
        cur = self.stack.currentIndex()
        for i, lb in enumerate(self.step_labels):
            if i == cur:
                lb.setStyleSheet(
                    "background: #DBEAFE; color: #2563EB; font-weight: 700; "
                    "padding: 8px 12px; border-radius: 8px; "
                    "border-left: 4px solid #2563EB;"
                )
            else:
                lb.setStyleSheet("color: #64748B; padding: 8px 12px;")

    def _sync_buttons(self):
        cur = self.stack.currentIndex()
        self.btn_back.setVisible(cur in (1, 2, 3))
        self.btn_run.setVisible(cur == 4)
        if cur == 0:
            self.btn_next.setText("下一步 →")
        elif cur == 3:
            self.btn_next.setText("安装")
        elif cur == 4:
            self.btn_next.setText("完成")
            self.btn_next.setEnabled(True)
        else:
            self.btn_next.setText("下一步 →")

    def _go_back(self):
        cur = self.stack.currentIndex()
        if 0 < cur < 4:
            self.stack.setCurrentIndex(cur - 1)
            self._refresh_steps()
            self._sync_buttons()

    def _go_next(self):
        cur = self.stack.currentIndex()
        if cur == 0:
            self.stack.setCurrentIndex(1)
            self._refresh_steps()
            self._sync_buttons()
            self._update_disk_hint()
        elif cur == 1:
            self.stack.setCurrentIndex(2)
            self._refresh_steps()
            self._sync_buttons()
        elif cur == 2:
            self.stack.setCurrentIndex(3)
            self._refresh_steps()
            self._sync_buttons()
        elif cur == 3:
            self._start_install()
        elif cur == 4:
            self.close()

    def _launch_app(self):
        exe = Path(self.install_dir) / f"{APP_NAME}.exe"
        if exe.is_file():
            try:
                subprocess.Popen([str(exe)], cwd=str(exe.parent))
            except OSError as e:
                QMessageBox.warning(self, "启动失败", f"无法启动应用：{e}")
        self.close()

    def _on_dir_changed(self, text: str):
        self.install_dir = text.strip()
        self._update_disk_hint()

    def _update_disk_hint(self):
        try:
            p = Path(self.install_dir)
            root = Path(p.anchor or "C:\\")
            usage = shutil.disk_usage(root)
            free_gb = usage.free / (1024 ** 3)
            self.disk_hint.setText(f"目标盘剩余空间：{free_gb:.1f} GB")
        except Exception:
            self.disk_hint.setText("")

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择安装目录", self.install_dir or str(Path.home()))
        if d:
            self.dir_edit.setText(d)

    # ---- 安装执行 ----
    def _start_install(self):
        src = app_source()
        if not src.is_dir() or not (src / f"{APP_NAME}.exe").exists():
            QMessageBox.critical(
                self, "缺少应用文件",
                "找不到主应用文件。\n\n请先运行 build_setup.bat 生成 dist\\zhuzhu Copilot，"
                "再重新打包本安装器。",
            )
            self.stack.setCurrentIndex(1)
            self._refresh_steps()
            self._sync_buttons()
            return

        dst = Path(self.install_dir)
        if not dst.is_absolute():
            QMessageBox.warning(self, "目录无效", "请选择有效的安装目录。")
            return

        # 磁盘空间预检
        try:
            src_size = sum(p.stat().st_size for p in walk_files(src))
            usage = shutil.disk_usage(dst.anchor + "\\")
            if src_size > usage.free:
                QMessageBox.warning(
                    self, "空间不足",
                    f"目标盘剩余空间不足：\n需要 {src_size / 1e6:.0f} MB，剩余 {usage.free / 1e6:.0f} MB。",
                )
                return
        except OSError as e:
            QMessageBox.warning(self, "目录无效", f"目标目录不可用：{e}")
            return

        # 目标目录已存在 → 覆盖/改名/取消
        if dst.exists() and any(dst.iterdir()):
            ret = QMessageBox.question(
                self, "目录已存在",
                f"目录 {dst} 已存在且非空。\n\n是否覆盖安装？（会清空原目录内容）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return
            try:
                shutil.rmtree(dst)
            except OSError as e:
                QMessageBox.critical(self, "清理失败", f"无法清理原目录：{e}")
                return

        self.btn_back.setEnabled(False)
        self.btn_next.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.installing = True
        self.install_worker = InstallWorker(src, dst, self.chk_desktop.isChecked(), self)
        self.install_worker.progress.connect(self._on_install_progress)
        self.install_worker.done.connect(self._on_install_done)
        self.install_worker.start()

    def _on_install_progress(self, done: int, total: int, msg: str):
        pct = int(done / total * 100) if total else 0
        self.progress_bar.setValue(pct)
        self.install_status.setText(f"{msg}（{done}/{total}）")

    def _on_install_done(self, ok: bool, err: str):
        self.installing = False
        self.btn_back.setEnabled(True)
        self.btn_next.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        if ok:
            self.stack.setCurrentIndex(4)
            self._refresh_steps()
            self._sync_buttons()
        else:
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "安装失败", f"安装过程中发生错误：\n{err}")
            self.stack.setCurrentIndex(3)
            self._refresh_steps()
            self._sync_buttons()

    def closeEvent(self, event):
        if getattr(self, "installing", False):
            event.ignore()
            QMessageBox.information(self, "安装进行中", "正在安装，请稍候…")
            return
        super().closeEvent(event)


# ------------------------------------------------------------
# 卸载 UI
# ------------------------------------------------------------
class UninstallWizard(QMainWindow):
    def __init__(self, install_dir: Path):
        super().__init__()
        self.install_dir = install_dir
        self.setWindowTitle(f"卸载 {APP_NAME}")
        self.setMinimumSize(560, 380)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(14)

        emoji = QLabel("🥺")
        emoji.setObjectName("bigEmoji")
        layout.addWidget(emoji)
        title = QLabel("真的要卸载吗？")
        title.setObjectName("title")
        layout.addWidget(title)
        hint = QLabel(
            "你的 C 盘可能会想念这个救星的…\n"
            "（当然，卸载后应用们不会搬回去，它们已经在新家安居乐业了 🏡）"
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addSpacing(8)
        info = QLabel(f"📦 将删除：{install_dir}")
        info.setObjectName("hint")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        layout.addWidget(self.status)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("算了，留着")
        self.btn_cancel.setObjectName("ghost")
        self.btn_cancel.clicked.connect(self.close)
        self.btn_confirm = QPushButton("忍痛卸载 😭")
        self.btn_confirm.clicked.connect(self._start_uninstall)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_confirm)
        layout.addLayout(btns)

    def _start_uninstall(self):
        self.btn_cancel.setEnabled(False)
        self.btn_confirm.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.working = True
        self.worker = UninstallWorker(self.install_dir, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.start()

    def _on_progress(self, pct: int, msg: str):
        self.progress.setValue(pct)
        self.status.setText(f"{msg} ({pct}%)")

    def _on_done(self, ok: bool, msg: str):
        self.working = False
        if ok:
            QMessageBox.information(
                self, "卸载完成",
                "🧹 已彻底删除应用、用户技能、对话记录与全部配置，安装目录也已清除。\n\n"
                "感谢你曾经让它存在过。",
            )
            self.close()
        else:
            self.progress.setVisible(False)
            self.btn_cancel.setEnabled(True)
            self.btn_confirm.setEnabled(True)
            QMessageBox.critical(self, "卸载失败", f"发生错误：\n{msg}")

    def closeEvent(self, event):
        if getattr(self, "working", False):
            event.ignore()
            QMessageBox.information(self, "正在卸载", "正在卸载，请稍候…")
            return
        super().closeEvent(event)


# ------------------------------------------------------------
# 卸载器 temp 副本：静默删除目录并自毁
# ------------------------------------------------------------
def resume_uninstall(target_dir: Path):
    """静默删除安装目录 + 自毁（resume 进程）。
    
    分三轮确保 zhuzhu Copilot 文件夹彻底删除：
    1. 等待主进程退出 (1.5s) → 直接 rmtree (12 次重试/1s)
    2. 仍存在 → cmd rd /s /q 延迟执行 (4s 后)
    3. 最终兜底 → 再等 10s 轮询，若仍存在则标记为「下次重启删除」
    """
    time.sleep(1.5)  # 等待原卸载器进程退出
    _kill_main_app()
    # 第一轮：直接 rmtree
    for _ in range(12):
        try:
            if target_dir.exists():
                shutil.rmtree(target_dir)
            break
        except OSError:
            time.sleep(1)
    # 第二轮：cmd 延迟强制删除
    if target_dir.exists():
        try:
            subprocess.Popen(
                f'ping -n 4 127.0.0.1 > nul & rd /s /q "{target_dir}"',
                shell=True, creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True,
            )
        except OSError:
            pass
        # 等待 cmd 执行
        for _ in range(10):
            time.sleep(1)
            if not target_dir.exists():
                break
    # 第三轮：Win32 MoveFileEx 标记「重启后删除」（终极兜底）
    if target_dir.exists():
        try:
            import ctypes
            MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
            ctypes.windll.kernel32.MoveFileExW(
                str(target_dir), None, MOVEFILE_DELAY_UNTIL_REBOOT,
            )
        except OSError:
            pass
    # 延迟删除自身（cmd 原生 del）
    try:
        subprocess.Popen(
            f'ping -n 3 127.0.0.1 > nul & del /f /q "{sys.executable}"',
            shell=True, creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True,
        )
    except OSError:
        pass


# ------------------------------------------------------------
# 入口
# ------------------------------------------------------------
def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setStyleSheet(GLOBAL_QSS)

    families = QFontDatabase.families()
    family = next((f for f in ["Microsoft YaHei UI", "Segoe UI"] if f in families), "Arial")
    app.setFont(QFont(family, 10))

    if IS_RESUME:
        # 静默：删除安装目录 + 自毁
        target = Path(sys.argv[-1])
        resume_uninstall(target)
        return 0

    if IS_UNINSTALL:
        install_dir = read_install_location()
        if install_dir is None:
            QMessageBox.information(
                None, "未安装",
                "😅 未检测到 zhuzhu Copilot 的安装记录，无需卸载。",
            )
            return 0
        win = UninstallWizard(install_dir)
    else:
        win = InstallWizard()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
