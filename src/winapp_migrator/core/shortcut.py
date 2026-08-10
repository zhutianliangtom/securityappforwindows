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
