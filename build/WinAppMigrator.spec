# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['../src/main.py'],
    pathex=['../src'],
    binaries=[],
    datas=[('../assets', 'assets'), ('../src/winapp_migrator/skills', 'skills')],
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
        'winapp_migrator.core.security',
        'winapp_migrator.core.network_defense',
        'winapp_migrator.core.execution_guard',
        'winapp_migrator.ui.main_window',
        'winapp_migrator.ui.styles',
        'winapp_migrator.ui.widgets',
        'winapp_migrator.ui.agent_panel',
        'winapp_migrator.core.agent_llm',
        'winapp_migrator.core.agent_screen',
        'winapp_migrator.core.agent_sandbox',
        'winapp_migrator.core.agent_tools',
        'winapp_migrator.core.agent_browser',
        'winapp_migrator.core.agent_mcp',
        'winapp_migrator.core.agent_skills',
        'winapp_migrator.core.agent_engine',
        'winapp_migrator.core.agent_tts',
        'winapp_migrator.core.agent_plugins',
        'winapp_migrator.utils.helpers',
        # TTS 自动朗读播放器（函数内动态 import pygame，显式声明防打包遗漏）
        'pygame',
        'pywintypes',
        'win32api',
        'win32gui',
        'win32security',
        'win32con',
        # agent_panel 的 _svg_icon 渲染 Lucide SVG 矢量图标依赖 QtSvg
        'PyQt6.QtSvg',
        # win32com 为动态包，需完整收集子模块（快捷方式 TargetPath 读取依赖）
        *collect_submodules('win32com'),
        # 三件套图片依赖：docx/pptx/openpyxl 的 add_picture/add_image 运行时 import PIL，显式声明确保随包
        'PIL',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 运行环境性能优化：排除确定未使用的重型 Qt 模块与内置库，
    # 减小体积、加快启动加载、降低驻留内存（QtWebEngine 等体积数百 MB）
    excludes=[
        'tkinter', 'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtQuick', 'PyQt6.QtQml', 'PyQt6.Qt3DCore', 'PyQt6.Qt3DRender',
        'PyQt6.QtCharts', 'PyQt6.QtDataVisualization', 'PyQt6.QtPdf',
        'PyQt6.QtBluetooth', 'PyQt6.QtNfc', 'PyQt6.QtSerialPort',
        'PyQt6.QtWebSockets', 'PyQt6.QtDesigner', 'PyQt6.QtHelp',
        'PyQt6.QtSql', 'PyQt6.QtXml', 'PyQt6.QtTest', 'PyQt6.QtDBus',
        'numpy', 'pandas', 'scipy', 'matplotlib', 'sklearn', 'torch',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 性能优化：应用未使用 QTranslator，剔除全部 Qt 翻译文件(.qm)，
# 减小体积、加快安装解压与目录扫描
a.datas = [d for d in a.datas if not d[0].endswith('.qm')]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='zhuzhu Copilot',
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
    version='version_info.txt',
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
    name='zhuzhu Copilot',
)
