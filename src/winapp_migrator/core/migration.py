import os
import shutil
from pathlib import Path
from typing import Callable, Optional

from winapp_migrator.utils.helpers import setup_logging, format_size
from winapp_migrator.core.permissions import take_ownership

logger = setup_logging()

class MigrationResult:
    def __init__(self, success: bool, message: str, details: list[str] = None, backup_path: Path = None):
        self.success = success
        self.message = message
        self.details = details or []
        self.backup_path = backup_path

def migrate_folder(
    source: Path,
    target: Path,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    mode: str = "junction",
) -> MigrationResult:
    """迁移目录。mode="junction" 时旧路径保留目录联接；mode="move" 完全移动，备份由调用方清理"""
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

    report(80, "处理旧目录...")
    if mode == "junction":
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

        report(90, "清理备份...")
        try:
            shutil.rmtree(backup, ignore_errors=True)
            details.append("已清理备份")
        except Exception as e:
            logger.warning("清理备份失败: %s", e)
            details.append(f"备份保留在: {backup}")

        report(100, "迁移完成")
        return MigrationResult(True, f"成功迁移到 {target}", details)

    # 完全移动模式：旧目录已重命名为备份，等待调用方更新引用后清理
    report(80, "旧目录已重命名为备份，更新引用后将删除")
    details.append("旧目录已移除，待引用更新后清理备份")
    return MigrationResult(True, f"成功迁移到 {target}", details, backup_path=backup)

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
    """在 link 处创建指向 target 的目录联接（junction），链接目录由标准库内部创建"""
    import _winapi
    try:
        # 参数顺序: (目标路径, 链接路径)；link 必须不存在
        _winapi.CreateJunction(str(target.resolve()), str(link))
    except Exception:
        # 清理标准库失败时可能残留的空链接目录，避免影响后续回滚
        try:
            os.rmdir(link)
        except OSError:
            pass
        raise
