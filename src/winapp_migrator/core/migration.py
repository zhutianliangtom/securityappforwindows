import os
import shutil
import ctypes
import struct
from pathlib import Path
from typing import Callable, Optional

from winapp_migrator.utils.helpers import setup_logging, format_size
from winapp_migrator.core.permissions import take_ownership

logger = setup_logging()

FSCTL_SET_REPARSE_POINT = 0x000900A4
FSCTL_GET_REPARSE_POINT = 0x000900A8
FSCTL_DELETE_REPARSE_POINT = 0x000900AC
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003

class MigrationResult:
    def __init__(self, success: bool, message: str, details: list[str] = None):
        self.success = success
        self.message = message
        self.details = details or []

def migrate_folder(
    source: Path,
    target: Path,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    use_junction: bool = True,
) -> MigrationResult:
    if not source.exists():
        return MigrationResult(False, f"源目录不存在: {source}")
    if target.exists():
        return MigrationResult(False, f"目标目录已存在: {target}")

    details = []

    def report(percent: int, msg: str):
        logger.info("[%d%%] %s", percent, msg)
        if progress_callback:
            progress_callback(percent, msg)

    report(5, "获取目标目录权限...")
    parent = source.parent
    if not os.access(parent, os.W_OK):
        take_ownership(parent)

    report(10, "复制文件到新位置...")
    try:
        shutil.copytree(source, target, symlinks=True)
    except Exception as e:
        logger.exception("复制目录失败")
        return MigrationResult(False, f"复制目录失败: {e}")

    report(60, "校验文件完整性...")
    if not _verify_copy(source, target):
        shutil.rmtree(target, ignore_errors=True)
        return MigrationResult(False, "文件复制校验失败，已回滚")

    report(70, "重命名原目录为备份...")
    backup = Path(str(source) + ".migrator_backup")
    try:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        source.rename(backup)
    except Exception as e:
        logger.exception("重命名原目录失败")
        shutil.rmtree(target, ignore_errors=True)
        return MigrationResult(False, f"无法重命名原目录: {e}")

    if use_junction:
        report(80, "创建目录联接保证兼容性...")
        try:
            _create_junction(source, target)
            details.append("已创建目录联接")
        except Exception as e:
            logger.exception("创建junction失败，尝试恢复")
            try:
                backup.rename(source)
                shutil.rmtree(target, ignore_errors=True)
            except Exception:
                pass
            return MigrationResult(False, f"创建目录联接失败: {e}")
    else:
        report(80, "跳过目录联接（完全移动模式）")

    report(90, "清理备份...")
    try:
        shutil.rmtree(backup, ignore_errors=True)
        details.append("已清理备份")
    except Exception as e:
        logger.warning("清理备份失败: %s", e)
        details.append(f"备份保留在: {backup}")

    report(100, "迁移完成")
    return MigrationResult(True, f"成功迁移到 {target}", details)

def _verify_copy(src: Path, dst: Path) -> bool:
    try:
        for root, dirs, files in os.walk(src):
            rel_root = Path(root).relative_to(src)
            for d in dirs:
                s = Path(root) / d
                d_dst = dst / rel_root / d
                if not d_dst.exists() and not s.is_symlink():
                    return False
            for f in files:
                s = Path(root) / f
                d_dst = dst / rel_root / f
                if s.is_symlink():
                    if not d_dst.is_symlink():
                        return False
                    continue
                if not d_dst.exists():
                    return False
                if s.stat().st_size != d_dst.stat().st_size:
                    return False
        return True
    except Exception as e:
        logger.error("校验失败: %s", e)
        return False

def _create_junction(link: Path, target: Path):
    link.mkdir(parents=True, exist_ok=False)
    target_abs = str(target.resolve())
    target_nt = "\\??\\" + target_abs

    hFile = ctypes.windll.kernel32.CreateFileW(
        str(link),
        0x40000000,
        0,
        None,
        3,
        0x02200000,
        None,
    )
    if hFile == -1:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        target_bytes = target_nt.encode("utf-16-le")
        substitute_name_offset = 0
        substitute_name_length = len(target_bytes)
        print_name_offset = substitute_name_length
        print_name_length = len(target_bytes)

        reparse_data = struct.pack(
            "<LHHHHHH",
            IO_REPARSE_TAG_MOUNT_POINT,
            substitute_name_length + print_name_length + 8,
            0,
            substitute_name_offset,
            substitute_name_length,
            print_name_offset,
            print_name_length,
        ) + target_bytes + target_bytes

        bytes_returned = ctypes.c_ulong(0)
        success = ctypes.windll.kernel32.DeviceIoControl(
            hFile,
            FSCTL_SET_REPARSE_POINT,
            reparse_data,
            len(reparse_data),
            None,
            0,
            ctypes.byref(bytes_returned),
            None,
        )
        if not success:
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        ctypes.windll.kernel32.CloseHandle(hFile)
