@echo off
rem ============================================================
rem  WinAppMigrator - PyQt6 installer build script
rem  Steps:
rem    1. Build main app  (dist\WinAppMigrator)     [skip if exists]
rem    2. Build uninstall.exe                       (dist\uninstall)
rem    3. Copy uninstall.exe into the app payload
rem    4. Build onefile setup.exe with embedded payload
rem  Output:
rem    dist\WinAppMigrator_Setup.exe
rem ============================================================
setlocal
cd /d "%~dp0.."

echo.
echo ============================================
echo  [1/4] Build main app (dist\WinAppMigrator)
echo ============================================
if exist "dist\WinAppMigrator\WinAppMigrator.exe" (
    echo Main app already built, skip.
) else (
    pyinstaller --clean --noconfirm build\WinAppMigrator.spec
    if errorlevel 1 goto :err
)

echo.
echo ============================================
echo  [2/4] Build uninstall.exe
echo ============================================
pyinstaller --clean --noconfirm installer\uninstall.spec
if errorlevel 1 goto :err

echo.
echo ============================================
echo  [3/4] Embed uninstall.exe into app payload
echo ============================================
copy /y "dist\uninstall.exe" "dist\WinAppMigrator\uninstall.exe"
if errorlevel 1 goto :err

echo.
echo ============================================
echo  [4/4] Build setup.exe (embedded payload)
echo ============================================
pyinstaller --clean --noconfirm installer\setup.spec
if errorlevel 1 goto :err

echo.
echo ============================================
echo  DONE.  Output:
echo    dist\WinAppMigrator_Setup.exe   (single-file installer)
echo ============================================
rem Remove the intermediate uninstall.exe; it is already embedded
rem inside WinAppMigrator_Setup.exe and copied to the install dir at setup time.
del /q "dist\uninstall.exe" 2>nul
exit /b 0

:err
echo.
echo BUILD FAILED.
exit /b 1
