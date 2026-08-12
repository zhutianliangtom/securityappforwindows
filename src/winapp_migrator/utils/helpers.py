import os
import sys
import logging
import tempfile
from pathlib import Path
from datetime import datetime

def setup_logging() -> logging.Logger:
    log_dir = Path(tempfile.gettempdir()) / "WinAppMigrator"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"migrator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logger = logging.getLogger("WinAppMigrator")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        # windowed 模式下 stdout 可能为 None，仅作兜底，不阻塞
        if sys.stdout is not None:
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(fmt)
            logger.addHandler(sh)
    return logger

def install_excepthook():
    """将未捕获异常写入日志，便于排查运行时错误"""
    import traceback
    logger = setup_logging()

    def hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical("未捕获异常:\n%s", msg)
        try:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    sys.excepthook = hook

def is_admin() -> bool:
    try:
        return os.getuid() == 0
    except AttributeError:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0

def ensure_admin():
    if not is_admin():
        raise PermissionError("本工具需要管理员权限才能迁移应用。请右键以管理员身份运行。")

def format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def get_directory_size(path: Path, max_depth: int = 3) -> int:
    """统计目录大小，限制递归深度以加快扫描速度；跳过目录联接防循环"""
    total = 0

    def walk(p: Path, depth: int):
        nonlocal total
        if depth > max_depth:
            return
        try:
            for entry in os.scandir(p):
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if _is_junction(Path(entry.path)):
                            continue
                        walk(Path(entry.path), depth + 1)
                    else:
                        total += entry.stat(follow_symlinks=False).st_size
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            pass

    walk(path, 0)
    return total

def safe_remove(path: Path) -> bool:
    """安全删除文件/目录：处理只读属性与瞬时占用，失败自动重试"""
    import shutil
    import stat as stat_mod
    import time

    def _force(func, p, exc_info):
        # 删除失败（常见：文件/目录只读）时清除只读属性后重试一次
        try:
            os.chmod(p, stat_mod.S_IWRITE | stat_mod.S_IREAD)
            func(p)
        except Exception:
            pass

    for _ in range(4):
        try:
            if path.is_symlink() or _is_junction(path):
                path.unlink()
                return True
            if path.is_dir():
                shutil.rmtree(path, onerror=_force)
                if not path.exists():
                    return True
            elif path.exists():
                path.unlink()
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

def _is_junction(path: Path) -> bool:
    if not path.exists():
        return False
    import ctypes
    FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    return attrs != -1 and (attrs & FILE_ATTRIBUTE_REPARSE_POINT) != 0
