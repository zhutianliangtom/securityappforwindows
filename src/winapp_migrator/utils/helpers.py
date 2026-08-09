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
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger

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

def get_directory_size(path: Path) -> int:
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_dir(follow_symlinks=False):
                    total += get_directory_size(Path(entry.path))
                else:
                    total += entry.stat(follow_symlinks=False).st_size
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        pass
    return total

def safe_remove(path: Path) -> bool:
    try:
        if path.is_symlink() or _is_junction(path):
            path.unlink()
            return True
        if path.is_dir():
            import shutil
            shutil.rmtree(path)
            return True
        if path.exists():
            path.unlink()
            return True
    except Exception:
        return False
    return False

def _is_junction(path: Path) -> bool:
    if not path.exists():
        return False
    import ctypes
    FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    return attrs != -1 and (attrs & FILE_ATTRIBUTE_REPARSE_POINT) != 0
