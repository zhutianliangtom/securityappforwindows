@echo off
rem ============================================================
rem  WinAppMigrator - Inno Setup Default.isl 修复脚本
rem  作用：用官方完整中文版覆盖被旧版中文翻译污染的 Default.isl
rem  运行方式：右键本文件 → 以管理员身份运行
rem ============================================================
chcp 65001 >nul
setlocal

set "ISDIR=C:\Program Files\Inno Setup 7"
set "SRC=%~dp0ChineseSimplified.isl"
set "DST=%ISDIR%\Default.isl"

if not exist "%ISDIR%\Default.isl" (
    echo [错误] 找不到 %ISDIR%\Default.isl，请检查 Inno Setup 安装路径
    pause
    exit /b 1
)

if not exist "%SRC%" (
    echo [错误] 找不到 %SRC%，请把本脚本放在 installer 目录下运行
    pause
    exit /b 1
)

rem 备份原文件
copy /y "%DST%" "%DST%.bak" >nul 2>&1
if exist "%DST%.bak" (
    echo [备份] 原 Default.isl 已备份为 Default.isl.bak
) else (
    echo [提示] 原文件备份失败（可能无权限），继续...
)

rem 用官方完整中文版覆盖
copy /y "%SRC%" "%DST%" >nul
if errorlevel 1 (
    echo [错误] 覆盖失败，请确认已右键以管理员身份运行
    pause
    exit /b 1
)

echo.
echo [完成] Default.isl 已替换为官方完整中文版（含全部 Inno Setup 7 必需键）
echo 现在可以重新编译安装包了，祝编译顺利，告别报错！🎉
echo.
pause
