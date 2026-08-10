"""内存优化模块：激进全量压缩工作集 + 清理系统备用缓存 + 终止进程 + 禁用服务"""

import base64
import os
import subprocess
import logging

logger = logging.getLogger(__name__)

# 不必要的后台服务
_UNNECESSARY_SERVICES = [
    "EdgeUpdate", "MicrosoftEdgeElevationService", "edgeupdate", "edgeupdatem",
    "wuauserv", "UsoSvc", "WaaSMedicSvc", "DoSvc", "DiagTrack",
    "dmwappushservice", "MapsBroker", "lfsvc",
    "XblAuthManager", "XblGameSave", "XboxNetApiSvc", "BcastDVRUserService",
    "WSearch", "SysMain", "FontCache", "OneSyncSvc",
    "PimIndexMaintenanceSvc", "MessagingService", "wlidsvc", "WpcMonSvc",
    "WerSvc", "WMPNetworkSvc", "LicenseManager", "TabletInputService",
    "PrintNotify", "Fax", "seclogon", "RemoteRegistry", "shpamsvc",
    "RetailDemo", "wisvc", "SDRSVC", "WbioSrvc", "WpnService",
]

# 系统关键进程名，绝不触碰
_PROTECTED_NAMES = {
    "system", "idle", "csrss", "wininit", "services",
    "lsass", "winlogon", "smss", "svchost",
    "spoolsv", "audiodg", "dwm", "explorer",
    "taskhostw", "sihost", "runtimebroker",
    "fontdrvhost", "wlms", "logonui",
    "applicationframehost", "winappmigrator",
    "registry", "memcompression",
}

# 可安全终止的常驻后台进程
_KILLABLE_PATTERNS = [
    "msedge", "chrome", "firefox", "brave", "opera",
    "onedrive", "teams", "slack", "discord", "spotify",
    "yourphone", "gamebarftbroker",
    "officeclicktorun", "groove", "skype", "skypehost",
]


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _encode_json(obj) -> str:
    import json
    raw = json.dumps(obj, ensure_ascii=False)
    return base64.b64encode(raw.encode("utf-16-le")).decode("ascii")


def _run_ps(script: str, timeout: int = 120) -> tuple:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-EncodedCommand", encoded],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=timeout,
        )
        out = (r.stdout or b"").decode("utf-8", "replace")
        err = (r.stderr or b"").decode("utf-8", "replace")
        return out, err, r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", 1
    except Exception as e:
        return "", str(e), 1


def optimize_memory(progress_callback=None) -> dict:
    """一键激进优化内存"""

    def notify(pct: int, msg: str):
        logger.info("[%d%%] %s", pct, msg)
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    protected_b64 = _encode_json([os.getpid()])
    protected_names_b64 = _encode_json(list(_PROTECTED_NAMES))
    killable_b64 = _encode_json(_KILLABLE_PATTERNS)
    svc_b64 = _encode_json(_UNNECESSARY_SERVICES)

    # ============================================================
    # 单一大脚本：获取基线 -> 全量压缩 -> 清理系统缓存 -> 杀进程 -> 禁服务 -> 获取结果
    # ============================================================
    notify(5, "开始激进内存优化...")

    script = rf'''
$ErrorActionPreference = "SilentlyContinue"

# --- P/Invoke 定义 ---
$sigSetWS = @"
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool SetProcessWorkingSetSize(IntPtr hProcess, IntPtr dwMin, IntPtr dwMax);
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool EmptyWorkingSet(IntPtr hProcess);
"@
Add-Type -Name MemOpt -Namespace WAM -MemberDefinition $sigSetWS

$sigFG = @"
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
"@
Add-Type -Name FG -Namespace WAM -MemberDefinition $sigFG

# --- 保护列表 ---
$protected = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String({_ps_quote(protected_b64)})) | ConvertFrom-Json
$protectedNames = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String({_ps_quote(protected_names_b64)})) | ConvertFrom-Json
$killable = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String({_ps_quote(killable_b64)})) | ConvertFrom-Json
$svcNames = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String({_ps_quote(svc_b64)})) | ConvertFrom-Json

# 前台进程 PID
$hwnd = [WAM.FG]::GetForegroundWindow()
$fgPid = 0
[WAM.FG]::GetWindowThreadProcessId($hwnd, [ref]$fgPid)
if ($fgPid -gt 0) {{ $protected += $fgPid }}

# --- 基线内存 ---
$ramBefore = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory * 4KB / 1MB

# ============================================================
# 阶段 1: 全量压缩所有非保护进程工作集 (SetProcessWorkingSetSize -1 -1)
# ============================================================
$trimCount = 0
$negativeOne = [IntPtr]::new(-1)

Get-Process | ForEach-Object {{
    $p = $_
    if ($protected -contains $p.Id) {{ return }}
    if ($protectedNames -contains $p.ProcessName.ToLower()) {{ return }}
    try {{
        [WAM.MemOpt]::SetProcessWorkingSetSize($p.Handle, $negativeOne, $negativeOne) | Out-Null
        $trimCount++
    }} catch {{ }}
}}

# ============================================================
# 阶段 2: 清理系统备用缓存（压缩 System 进程 PID 4 的工作集）
# ============================================================
try {{
    $sysProc = Get-Process -Id 4 -ErrorAction Stop
    [WAM.MemOpt]::EmptyWorkingSet($sysProc.Handle) | Out-Null
    [WAM.MemOpt]::SetProcessWorkingSetSize($sysProc.Handle, $negativeOne, $negativeOne) | Out-Null
}} catch {{ }}

# 额外：压缩 svchost / dllhost / rundll32 等系统宿主进程
Get-Process | Where-Object {{
    $n = $_.ProcessName.ToLower()
    ($n -eq "svchost" -or $n -eq "dllhost" -or $n -eq "rundll32" -or $n -eq "conhost")
}} | ForEach-Object {{
    try {{
        [WAM.MemOpt]::SetProcessWorkingSetSize($_.Handle, $negativeOne, $negativeOne) | Out-Null
    }} catch {{ }}
}}

# ============================================================
# 阶段 3: 终止不必要的后台进程（仅无窗口的）
# ============================================================
$killed = 0
Get-Process | ForEach-Object {{
    $p = $_
    if ($protected -contains $p.Id) {{ return }}
    if ($protectedNames -contains $p.ProcessName.ToLower()) {{ return }}
    $match = $false
    foreach ($pat in $killable) {{
        if ($p.ProcessName.ToLower() -like "*$pat*") {{ $match = $true; break }}
    }}
    if (-not $match) {{ return }}
    try {{ if ($p.MainWindowHandle -ne [IntPtr]::Zero) {{ return }} }} catch {{ }}
    try {{ Stop-Process -Id $p.Id -Force -ErrorAction Stop; $killed++ }} catch {{ }}
}}

# ============================================================
# 阶段 4: 停止/禁用不必要的服务
# ============================================================
$stopped = 0
$disabled = 0
foreach ($name in $svcNames) {{
    $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
    if (-not $svc) {{ continue }}
    if ($svc.Status -eq "Running") {{
        try {{ Stop-Service -Name $name -Force -ErrorAction Stop; $stopped++ }} catch {{ }}
    }}
    if ($svc.StartType -ne "Disabled") {{
        try {{ Set-Service -Name $name -StartupType Disabled -ErrorAction Stop; $disabled++ }} catch {{ }}
    }}
}}

# 额外：停止 WSearch 和 SysMain 如果正在运行
$extraSvcs = @("WSearch", "SysMain")
foreach ($name in $extraSvcs) {{
    $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -eq "Running") {{
        try {{ Stop-Service -Name $name -Force -ErrorAction Stop; $stopped++ }} catch {{ }}
    }}
    if ($svc -and $svc.StartType -ne "Disabled") {{
        try {{ Set-Service -Name $name -StartupType Disabled -ErrorAction Stop; $disabled++ }} catch {{ }}
    }}
}}

# ============================================================
# 结果统计
# ============================================================
$ramAfter = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory * 4KB / 1MB
$freed = $ramAfter - $ramBefore

Write-Output "BASELINE=$ramBefore"
Write-Output "AFTER=$ramAfter"
Write-Output "FREED=$freed"
Write-Output "TRIM=$trimCount"
Write-Output "KILLED=$killed"
Write-Output "STOPPED=$stopped"
Write-Output "DISABLED=$disabled"
'''
    notify(15, "执行优化脚本...")
    out, err, rc = _run_ps(script, timeout=90)

    # 解析结果
    baseline_mb = 0.0
    after_mb = 0.0
    freed_mb = 0.0
    trim_count = 0
    killed = 0
    stopped = 0
    disabled = 0

    for line in out.splitlines():
        line = line.strip()
        try:
            if line.startswith("BASELINE="):
                baseline_mb = float(line.split("=", 1)[1])
            elif line.startswith("AFTER="):
                after_mb = float(line.split("=", 1)[1])
            elif line.startswith("FREED="):
                freed_mb = float(line.split("=", 1)[1])
            elif line.startswith("TRIM="):
                trim_count = int(line.split("=", 1)[1])
            elif line.startswith("KILLED="):
                killed = int(line.split("=", 1)[1])
            elif line.startswith("STOPPED="):
                stopped = int(line.split("=", 1)[1])
            elif line.startswith("DISABLED="):
                disabled = int(line.split("=", 1)[1])
        except Exception:
            pass

    if err and "timeout" not in err.lower():
        logger.warning("PowerShell stderr: %s", err[:500])

    notify(100, "优化完成")

    # 汇总
    details = []
    details.append(f"优化前可用: {baseline_mb:.0f} MB")
    details.append(f"优化后可用: {after_mb:.0f} MB")
    details.append(f"释放内存: {freed_mb:.0f} MB")
    details.append(f"压缩了 {trim_count} 个进程的工作集")
    if killed > 0:
        details.append(f"终止了 {killed} 个后台进程")
    if stopped > 0:
        details.append(f"停止了 {stopped} 个服务")
    if disabled > 0:
        details.append(f"禁用了 {disabled} 个服务")

    pct = freed_mb / max(baseline_mb, 1) * 100 if baseline_mb > 0 else 0
    msg = f"释放 {freed_mb:.0f} MB ({pct:.0f}%)，当前可用 {after_mb:.0f} MB"

    return {
        "success": True,
        "message": msg,
        "freed_mb": round(freed_mb, 1),
        "baseline_mb": round(baseline_mb, 0),
        "after_mb": round(after_mb, 0),
        "processes_trimmed": trim_count,
        "processes_killed": killed,
        "services_stopped": stopped,
        "services_disabled": disabled,
        "details": details,
    }