# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['../src/main.py'],
    pathex=['../src'],
    binaries=[],
    datas=[('../assets', 'assets')],
    hiddenimports=[
        'winapp_migrator.core.app_scanner',
        'winapp_migrator.core.migration',
        'winapp_migrator.core.registry',
        'winapp_migrator.core.uwp',
        'winapp_migrator.core.orchestrator',
        'winapp_migrator.core.permissions',
        'winapp_migrator.core.data_dirs',
        'winapp_migrator.core.shortcut',
        'winapp_migrator.core.uninstaller',
        'winapp_migrator.core.memory_optimizer',
        'winapp_migrator.ui.main_window',
        'winapp_migrator.ui.styles',
        'winapp_migrator.ui.widgets',
        'winapp_migrator.utils.helpers',
        'pywintypes',
        'win32api',
        'win32gui',
        'win32security',
        'win32con',
        # win32com 为动态包，需完整收集子模块（快捷方式 TargetPath 读取依赖）
        *collect_submodules('win32com'),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WinAppMigrator',
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
    uac_admin=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WinAppMigrator',
)
