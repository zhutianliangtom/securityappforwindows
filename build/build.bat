@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 安装依赖...
python -m pip install -r ../requirements.txt pyinstaller

echo 关闭可能正在运行的 WinAppMigrator...
taskkill /F /IM WinAppMigrator.exe 2>nul

echo 清理旧构建...
if exist ..\dist (
    rmdir /s /q ..\dist
    if exist ..\dist (
        echo 首次删除失败，等待 2 秒后重试...
        timeout /t 2 /nobreak >nul
        rmdir /s /q ..\dist
    )
)
if exist ..\build (
    rmdir /s /q ..\build
)

echo 开始打包...
pyinstaller --clean --noconfirm WinAppMigrator.spec

echo 打包完成，输出目录: ..\dist\WinAppMigrator
pause
