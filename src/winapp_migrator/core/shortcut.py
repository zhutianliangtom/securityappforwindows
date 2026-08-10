"""更新桌面/开始菜单快捷方式指向新路径（完全移动后旧路径失效）"""
import base64
import subprocess
from pathlib import Path

NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

_SCRIPT = r"""
$w = New-Object -ComObject WScript.Shell
$oldDir = __OLD__
$newDir = __NEW__
$count = 0
$folders = @(
    [Environment]::GetFolderPath('Desktop'),
    [Environment]::GetFolderPath('CommonDesktopDirectory'),
    [Environment]::GetFolderPath('StartMenu') + '\Programs',
    [Environment]::GetFolderPath('CommonStartMenu') + '\Programs'
)
foreach ($folder in $folders) {
    if (-not (Test-Path -LiteralPath $folder)) { continue }
    Get-ChildItem -LiteralPath $folder -Filter *.lnk -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $lnk = $w.CreateShortcut($_.FullName)
            $changed = $false
            if ($lnk.TargetPath -and $lnk.TargetPath.StartsWith($oldDir, [System.StringComparison]::OrdinalIgnoreCase)) {
                $lnk.TargetPath = $newDir + $lnk.TargetPath.Substring($oldDir.Length)
                $changed = $true
            }
            if ($lnk.WorkingDirectory -and $lnk.WorkingDirectory.StartsWith($oldDir, [System.StringComparison]::OrdinalIgnoreCase)) {
                $lnk.WorkingDirectory = $newDir + $lnk.WorkingDirectory.Substring($oldDir.Length)
                $changed = $true
            }
            if ($changed) { $lnk.Save(); $count++ }
        } catch {}
    }
}
$host.UI.Write($count)
"""

def _ps_quote(s) -> str:
    """转成 PowerShell 单引号字面量（反斜杠/中文/空格均安全）"""
    return "'" + str(s).replace("'", "''") + "'"

def update_shortcuts(old_dir: Path, new_dir: Path) -> int:
    """把桌面/开始菜单中指向旧目录的快捷方式更新到新目录，返回更新数量"""
    try:
        script = _SCRIPT.replace("__OLD__", _ps_quote(old_dir)).replace("__NEW__", _ps_quote(new_dir))
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-EncodedCommand", encoded],
            capture_output=True, creationflags=NO_WINDOW, timeout=120,
        )
        text = (result.stdout or b"").decode("utf-8", "replace").strip()
        return int(text) if text.isdigit() else 0
    except Exception:
        return 0


# ---- 强力卸载：扫描/删除指向目录的快捷方式 ----

_SCAN_SCRIPT = r"""
$dir = __DIR__
$folders = @(
    [Environment]::GetFolderPath('Desktop'),
    [Environment]::GetFolderPath('CommonDesktopDirectory'),
    [Environment]::GetFolderPath('StartMenu') + '\Programs',
    [Environment]::GetFolderPath('CommonStartMenu') + '\Programs'
)
$w = New-Object -ComObject WScript.Shell
foreach ($folder in $folders) {
    if (-not (Test-Path -LiteralPath $folder)) { continue }
    Get-ChildItem -LiteralPath $folder -Filter *.lnk -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $lnk = $w.CreateShortcut($_.FullName)
            if ($lnk.TargetPath -and $lnk.TargetPath.StartsWith($dir, [System.StringComparison]::OrdinalIgnoreCase)) {
                Write-Output $_.FullName
            }
        } catch {}
    }
}
"""

_REMOVE_SCRIPT = r"""
$dir = __DIR__
$count = 0
$folders = @(
    [Environment]::GetFolderPath('Desktop'),
    [Environment]::GetFolderPath('CommonDesktopDirectory'),
    [Environment]::GetFolderPath('StartMenu') + '\Programs',
    [Environment]::GetFolderPath('CommonStartMenu') + '\Programs'
)
$w = New-Object -ComObject WScript.Shell
foreach ($folder in $folders) {
    if (-not (Test-Path -LiteralPath $folder)) { continue }
    Get-ChildItem -LiteralPath $folder -Filter *.lnk -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $lnk = $w.CreateShortcut($_.FullName)
            if ($lnk.TargetPath -and $lnk.TargetPath.StartsWith($dir, [System.StringComparison]::OrdinalIgnoreCase)) {
                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
                $count++
            }
        } catch {}
    }
}
$host.UI.Write($count)
"""


def _run_ps(script: str) -> str:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-EncodedCommand", encoded],
        capture_output=True, creationflags=NO_WINDOW, timeout=120,
    )
    return (result.stdout or b"").decode("utf-8", "replace")


def scan_shortcuts(directory: Path) -> list:
    """返回桌面/开始菜单中 TargetPath 指向该目录的 .lnk 路径列表"""
    try:
        script = _SCAN_SCRIPT.replace("__DIR__", _ps_quote(directory))
        return [ln.strip() for ln in _run_ps(script).splitlines() if ln.strip()]
    except Exception:
        return []


def remove_shortcuts(directory: Path) -> int:
    """删除桌面/开始菜单中指向该目录的快捷方式，返回删除数量"""
    try:
        script = _REMOVE_SCRIPT.replace("__DIR__", _ps_quote(directory))
        text = _run_ps(script).strip()
        return int(text) if text.isdigit() else 0
    except Exception:
        return 0
