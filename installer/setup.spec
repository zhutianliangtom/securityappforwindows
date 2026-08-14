# -*- mode: python ; coding: utf-8 -*-
# WinAppMigrator 安装器打包配置（onefile，内嵌主应用全部文件）
from pathlib import Path
from PyInstaller.building.build_main import Analysis, PYZ, EXE, Tree
from PyInstaller.utils.hooks import collect_submodules

_SPEC_DIR = Path(SPECPATH)
_PROJECT_DIR = _SPEC_DIR.parent

a = Analysis(
    ['setup_app.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'win32com.client',
        'pythoncom',
        'pywintypes',
        # win32com 为动态包，需完整收集子模块（WScript.Shell 快捷方式依赖）
        *collect_submodules('win32com'),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# 性能优化：剔除全部 Qt 翻译文件(.qm)，减小 onefile 体积
a.datas = [d for d in a.datas if not d[0].endswith('.qm')]

pyz = PYZ(a.pure)

# 把已构建好的主应用 dist\zhuzhu Copilot 整体嵌入（_MEIPASS/app）
app_tree = Tree(str(_PROJECT_DIR / 'dist' / 'zhuzhu Copilot'), prefix='app')
a.datas += app_tree

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='zhuzhu Copilot Setup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../assets/icon.ico',
    manifest='../assets/admin.manifest',
    version='../build/version_info.txt',
    uac_admin=True,
)
