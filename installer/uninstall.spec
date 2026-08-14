# -*- mode: python ; coding: utf-8 -*-
# WinAppMigrator 卸载器打包配置（onefile，无数据负载，随安装复制到安装目录）
from PyInstaller.building.build_main import Analysis, PYZ, EXE
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ['setup_app.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'win32com.client',
        'pythoncom',
        'pywintypes',
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='uninstall',
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
