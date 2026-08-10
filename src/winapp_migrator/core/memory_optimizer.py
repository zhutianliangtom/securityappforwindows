"""内存优化模块：一键释放后台进程内存、清理缓存、禁用不必要的 Windows 服务"""

import base64
import os
import subprocess
import logging

logger = logging.getLogger(__name__)

# 不必要的后台服务（可安全禁用/停止）
_UNNECESSARY_SERVICES = [
    "EdgeUpdate",
    "MicrosoftEdgeElevationService",
    "edgeupdate",
    "edgeupdatem",
    "wuauserv",             # Windows Update
    "UsoSvc",               # Update Orchestrator
    "WaaSMedicSvc",         # Windows Update Medic
    "DoSvc",                # Delivery Optimization
    "DiagTrack",            # Connected User Experiences and Telemetry
    "dmwappushservice",     # Device Management WAP Push
    "MapsBroker",           # Downloaded Maps Manager
    "lfsvc",                # Geolocation Service
    "XblAuthManager",       # Xbox Live Auth Manager
    "XblGameSave",          # Xbox Live Game Save
    "XboxNetApiSvc",        # Xbox Live Networking
    "BcastDVRUserService",  # GameDVR and Broadcast
    "WSearch",              # Windows Search
    "SysMain",              # SysMain (Superfetch)
    "FontCache",            # Windows Font Cache
    "OneSyncSvc",           # Sync Host
    "PimIndexMaintenanceSvc",
    "MessagingService",
    "wlidsvc",              # Microsoft Account Sign-in Assistant
    "WpcMonSvc",            # Parental Controls
    "WerSvc",               # Windows Error Reporting
    "WMPNetworkSvc",
    "LicenseManager",
    "TabletInputService",
    "PrintNotify",
    "Fax",
    "seclogon",
    "RemoteRegistry",
    "shpamsvc",
    "RetailDemo",
    "wisvc",
    "SDRSVC",
    "WbioSrvc",
    "WpnService",
]

# 可安全清理内存的后台进程名模式（不杀进程，只清理 working set）
_TRIM_PATTERNS = [
    "msedge", "chrome", "firefox", "brave", "opera",
    "explorer", "shellexperiencehost",
    "onedrive", "teams", "slack", "discord", "spotify",
    "searchhost", "startmenuexperiencehost",
    "textinputhost", "systemsettings",
    "phoneexperiencehost", "yourphone",
    "widgets", "gamebar", "gamebarftbroker",
    "snippingtool", "notepad", "calculator",
    "taskmgr", "resmon", "perfmon",
    "office", "winword", "excel", "powerpnt", "outlook",
    "acrobat", "foxit", "reader",
    "vscode", "code", "notepad++",
    "steam", "epicgameslauncher", "battle.net",
    "java", "javaw", "python",
    "conhost", "cmd",
    "svchost", "dllhost", "rundll32",
    "ctfmon", "spoolsv", "audiodg",
    "msmpeng", "securityhealthsystray", "securityhealthservice",
    "smartscreen",
]

# 可安全终止的常驻后台进程（非关键，终止后用户需要时手动启动）
_KILLABLE_PATTERNS = [
    "msedge", "chrome", "firefox", "brave", "opera",
    "onedrive", "teams", "slack", "discord", "spotify",
    "yourphone", "gamebarftbroker",
    "officeclicktorun", "groove",
    "skype", "skypehost",
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


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


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


def _encode_json(obj) -> str:
    """将 Python 对象编码为 base64 UTF-16LE JSON，供 PowerShell 解码"""
    import json
    raw = json.dumps(obj, ensure_ascii=False)
    return base64.b64encode(raw.encode("utf-16-le")).decode("ascii")


def optimize_memory(progress_callback=None) -> dict:
    """一键优化内存"""

    def notify(pct: int, msg: str):
        logger.info("[%d%%] %s", pct, msg)
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    details = []
    total_freed_mb = 0.0
    processes_trimmed = 0
    processes_killed = 0
    services_stopped = 0
    services_disabled = 0

    # ---- 阶段 1：获取前台进程 PID ----
    notify(5, "获取前台进程...")
    script_fg = r'''
Add-Type -Name Foreground -Namespace WAM -MemberDefinition @"
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
"@
$hwnd = [WAM.Foreground]::GetForegroundWindow()
$pid = 0
[WAM.Foreground]::GetWindowThreadProcessId($hwnd, [ref]$pid)
Write-Output $pid
'''
    out, _, _ = _run_ps(script_fg, timeout=10)
    try:
        foreground_pid = int(out.strip())
    except Exception:
        foreground_pid = 0
    notify(8, f"前台 PID: {foreground_pid}")

    # 保护列表：前台进程 + 当前进程 + 系统关键进程
    protected_pids = {foreground_pid} if foreground_pid else set()
    protected_pids.add(os.getpid())

    # ---- 阶段 2：释放后台进程 Working Set ----
    notify(10, "释放后台进程内存...")
    patterns_b64 = _encode_json(_TRIM_PATTERNS)
    protected_b64 = _encode_json(list(protected_pids))
    protected_names_b64 = _encode_json(list(_PROTECTED_NAMES))

    script_trim = rf'''
$patterns = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String({_ps_quote(patterns_b64)})) | ConvertFrom-Json
$protected = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String({_ps_quote(protected_b64)})) | ConvertFrom-Json
$protectedNames = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String({_ps_quote(protected_names_b64)})) | ConvertFrom-Json

$sig = @"
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool EmptyWorkingSet(IntPtr hProcess);
"@
Add-Type -Name EmptyWS -Namespace WAM -MemberDefinition $sig

$count = 0
$freed = 0

Get-Process | ForEach-Object {{
    $p = $_
    if ($protected -contains $p.Id) {{ return }}
    $name = $p.ProcessName.ToLower()
    if ($protectedNames -contains $name) {{ return }}
    $match = $false
    foreach ($pat in $patterns) {{
        if ($name -like "*$pat*") {{ $match = $true; break }}
    }}
    if (-not $match) {{ return }}
    try {{
        $ws_before = $p.WorkingSet64
        $result = [WAM.EmptyWS]::EmptyWorkingSet($p.Handle)
        if ($result) {{
            $p.Refresh()
            $ws_after = $p.WorkingSet64
            if ($ws_before -gt $ws_after) {{
                $freed += ($ws_before - $ws_after)
                $count++
            }}
        }}
    }} catch {{ }}
}}

Write-Output "COUNT=$count"
Write-Output "FREED=$freed"
'''
    out, _, _ = _run_ps(script_trim, timeout=60)
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("COUNT="):
            try:
                processes_trimmed = int(line.split("=", 1)[1])
            except Exception:
                pass
        elif line.startswith("FREED="):
            try:
                total_freed_mb = int(line.split("=", 1)[1]) / (1024 * 1024)
            except Exception:
                pass

    details.append(f"释放了 {processes_trimmed} 个后台进程的工作集 ({total_freed_mb:.0f} MB)")
    notify(40, f"释放 {processes_trimmed} 个进程内存 ({total_freed_mb:.0f} MB)")

    # ---- 阶段 3：清理 .NET GC 和系统缓存 ----
    notify(50, "清理系统缓存...")
    script_cache = r'''
# 触发 .NET GC 回收（释放 CLR 堆内存）
[System.GC]::Collect()
[System.GC]::WaitForPendingFinalizers()
[System.GC]::Collect()

# 获取当前空闲内存
$ram = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory
Write-Output "FREE=$ram"
'''
    out, _, _ = _run_ps(script_cache, timeout=20)
    details.append("清理了 .NET 运行时缓存")
    notify(60, "系统缓存清理完成")

    # ---- 阶段 4：终止不必要的后台进程 ----
    notify(65, "终止不必要的后台进程...")
    kill_b64 = _encode_json(_KILLABLE_PATTERNS)

    script_kill = rf'''
$patterns = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String({_ps_quote(kill_b64)})) | ConvertFrom-Json
$protected = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String({_ps_quote(protected_b64)})) | ConvertFrom-Json
$protectedNames = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String({_ps_quote(protected_names_b64)})) | ConvertFrom-Json
$killed = 0

Get-Process | ForEach-Object {{
    $p = $_
    if ($protected -contains $p.Id) {{ return }}
    $name = $p.ProcessName.ToLower()
    if ($protectedNames -contains $name) {{ return }}
    $match = $false
    foreach ($pat in $patterns) {{
        if ($name -like "*$pat*") {{ $match = $true; break }}
    }}
    if (-not $match) {{ return }}
    # 额外检查：只杀没有窗口的后台进程
    try {{
        if ($p.MainWindowHandle -ne [IntPtr]::Zero) {{ return }}
    }} catch {{ }}
    try {{
        Stop-Process -Id $p.Id -Force -ErrorAction Stop
        $killed++
    }} catch {{ }}
}}
Write-Output "KILLED=$killed"
'''
    out, _, _ = _run_ps(script_kill, timeout=30)
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("KILLED="):
            try:
                processes_killed = int(line.split("=", 1)[1])
            except Exception:
                pass

    if processes_killed > 0:
        details.append(f"终止了 {processes_killed} 个不必要的后台进程")
    notify(75, f"终止 {processes_killed} 个后台进程")

    # ---- 阶段 5：停止并禁用不必要的 Windows 服务 ----
    notify(80, "优化 Windows 服务...")
    svc_b64 = _encode_json(_UNNECESSARY_SERVICES)

    script_svc = rf'''
$svcNames = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String({_ps_quote(svc_b64)})) | ConvertFrom-Json
$stopped = 0
$disabled = 0

foreach ($name in $svcNames) {{
    $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
    if (-not $svc) {{ continue }}
    if ($svc.Status -eq "Running") {{
        try {{
            Stop-Service -Name $name -Force -ErrorAction Stop
            $stopped++
        }} catch {{ }}
    }}
    if ($svc.StartType -ne "Disabled") {{
        try {{
            Set-Service -Name $name -StartupType Disabled -ErrorAction Stop
            $disabled++
        }} catch {{ }}
    }}
}}
Write-Output "STOPPED=$stopped"
Write-Output "DISABLED=$disabled"
'''
    out, _, _ = _run_ps(script_svc, timeout=30)
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("STOPPED="):
            try:
                services_stopped = int(line.split("=", 1)[1])
            except Exception:
                pass
        elif line.startswith("DISABLED="):
            try:
                services_disabled = int(line.split("=", 1)[1])
            except Exception:
                pass

    if services_stopped > 0:
        details.append(f"停止了 {services_stopped} 个不必要的服务")
    if services_disabled > 0:
        details.append(f"禁用了 {services_disabled} 个不必要的服务")
    notify(90, f"服务: 停止 {services_stopped}, 禁用 {services_disabled}")

    # ---- 阶段 6：获取最终可用内存 ----
    notify(95, "计算优化效果...")
    script_ram = r'$ram = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory; Write-Output $ram'
    out, _, _ = _run_ps(script_ram, timeout=10)
    try:
        free_ram_mb = int(out.strip()) * 4 / 1024
    except Exception:
        free_ram_mb = 0

    notify(100, "内存优化完成")

    # 汇总消息
    msg_parts = ["优化完成"]
    if total_freed_mb > 1:
        msg_parts.append(f"释放内存约 {total_freed_mb:.0f} MB")
    if processes_killed > 0:
        msg_parts.append(f"终止 {processes_killed} 个后台进程")
    if services_stopped + services_disabled > 0:
        msg_parts.append(f"优化 {services_stopped + services_disabled} 个服务")
    msg_parts.append(f"当前可用 {free_ram_mb:.0f} MB")

    return {
        "success": True,
        "message": "；".join(msg_parts),
        "freed_mb": round(total_freed_mb, 1),
        "processes_trimmed": processes_trimmed,
        "processes_killed": processes_killed,
        "services_stopped": services_stopped,
        "services_disabled": services_disabled,
        "free_ram_mb": round(free_ram_mb, 0),
        "details": details,
    }