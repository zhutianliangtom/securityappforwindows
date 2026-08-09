@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 安装依赖...
python -m pip install -r ../requirements.txt pyinstaller
echo 清理旧构建...
if exist ..\dist rmdir /s /q ..\dist
if exist ..\build rmdir /s /q ..\build
echo 开始打包...
pyinstaller --clean --noconfirm WinAppMigrator.spec
echo 打包完成，输出目录: ..\dist\WinAppMigrator
pause
