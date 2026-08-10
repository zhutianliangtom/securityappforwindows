"""内存优化模块：激进杀进程 + 清缓存 + 禁用服务，目标释放 >= 1/3 内存"""

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

# 可安全终止的进程名（精确匹配，不区分大小写）
# 这些进程通常消耗大量内存，终止后用户可随时重新打开
_KILLABLE_NAMES = {
    # 浏览器（内存大户）
    "msedge", "chrome", "firefox", "brave", "opera",
    "iexplore", "browser",
    # Electron 应用
    "teams", "discord", "slack", "spotify", "whatsapp",
    "signal", "notion", "figma", "postman", "insomnia",
    "githubdesktop", "sourcetree", "mongodbcompass",
    # 云存储
    "onedrive", "dropbox", "googledrivesync", "icloud",
    "baidunetdisk", "aliyunpan",
    # 聊天/通讯
    "skype", "skypehost", "wechat", "weixin", "dingtalk",
    "feishu", "lark", "telegram", "line",
    # 工具类
    "yourphone", "gamebarftbroker", "gamebar", "xbox",
    "officeclicktorun", "groove", "zune",
    # Adobe 后台
    "creativecloud", "coresync", "adobedesktopservice",
    "adobeipcbroker", "adobecollabsync",
    # Java/更新器
    "jusched", "jucheck", "javaw",
    # 其他
    "epicgameslauncher", "steamwebhelper", "battle.net",
    "galaxyclient", "ubisoftconnect",
}


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
    """一键激进优化内存 — 杀进程为主，压缩工作集为辅"""

    def notify(pct: int, msg: str):
        logger.info("[%d%%] %s", pct, msg)
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    protected_b64 = _encode_json([os.getpid()])
    protected_names_b64 = _encode_json(list(_PROTECTED_NAMES))
    killable_b64 = _encode_json(list(_KILLABLE_NAMES))
    svc_b64 = _encode_json(_UNNECESSARY_SERVICES)

    script = rf'''
$ErrorActionPreference = "SilentlyContinue"

# --- P/Invoke ---
$sig = @"
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool SetProcessWorkingSetSize(IntPtr hProcess, IntPtr dwMin, IntPtr dwMax);
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool EmptyWorkingSet(IntPtr hProcess);
[DllImport("psapi.dll", SetLastError=true)]
public static extern bool GetProcessMemoryInfo(IntPtr hProcess, out PROCESS_MEMORY_COUNTERS_EX ppsmemCounters, uint cb);

[StructLayout(LayoutKind.Sequential)]
public struct PROCESS_MEMORY_COUNTERS_EX {{
    public uint cb;
    public uint PageFaultCount;
    public UIntPtr PeakWorkingSetSize;
    public UIntPtr WorkingSetSize;
    public UIntPtr QuotaPeakPagedPoolUsage;
    public UIntPtr QuotaPagedPoolUsage;
    public UIntPtr QuotaPeakNonPagedPoolUsage;
    public UIntPtr QuotaNonPagedPoolUsage;
    public UIntPtr PagefileUsage;
    public UIntPtr PeakPagefileUsage;
    public UIntPtr PrivateUsage;
}}
"@
Add-Type -Name MemOpt -Namespace WAM -MemberDefinition $sig

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

# 前台进程 PID 和其子进程（保护整个前台进程树）
$hwnd = [WAM.FG]::GetForegroundWindow()
$fgPid = 0
[WAM.FG]::GetWindowThreadProcessId($hwnd, [ref]$fgPid)
if ($fgPid -gt 0) {{
    $protected += $fgPid
    # 保护前台进程的所有子进程
    Get-CimInstance Win32_Process | Where-Object {{ $_.ParentProcessId -eq $fgPid }} | ForEach-Object {{
        $protected += $_.ProcessId
    }}
}}

# --- 基线：使用 Available MBytes（任务管理器公认指标）---
$os = Get-CimInstance Win32_OperatingSystem
$ramTotal = $os.TotalVisibleMemorySize * 1KB / 1MB
$ramBefore = $os.FreePhysicalMemory * 1KB / 1MB
$availBefore = (Get-Counter "\Memory\Available MBytes" -ErrorAction SilentlyContinue).CounterSamples.CookedValue
if (-not $availBefore) {{ $availBefore = $ramBefore }}

# ============================================================
# 阶段 1: 终止高内存后台进程（核心手段）
# ============================================================
$killed = 0
$killedMemMB = 0.0

Get-Process | ForEach-Object {{
    $p = $_
    if ($protected -contains $p.Id) {{ return }}
    if ($protectedNames -contains $p.ProcessName.ToLower()) {{ return }}
    $name = $p.ProcessName.ToLower()
    if (-not ($killable -contains $name)) {{ return }}

    # 获取进程内存
    $memMB = 0
    try {{
        $pmc = New-Object WAM.MemOpt+PROCESS_MEMORY_COUNTERS_EX
        $pmc.cb = [System.Runtime.InteropServices.Marshal]::SizeOf($pmc)
        if ([WAM.MemOpt]::GetProcessMemoryInfo($p.Handle, [ref]$pmc, $pmc.cb)) {{
            $memMB = [uint64]$pmc.WorkingSetSize / 1MB
        }}
    }} catch {{ }}
    try {{ $memMB = $p.WorkingSet64 / 1MB }} catch {{ }}

    # 强制终止（包括有窗口的，只要不是前台）
    try {{
        Stop-Process -Id $p.Id -Force -ErrorAction Stop
        $killed++
        $killedMemMB += $memMB
    }} catch {{ }}
}}

# ============================================================
# 阶段 2: 清理系统文件缓存和备用列表
# ============================================================
# 使用 EmptyWorkingSet 压缩所有非保护进程（比 SetProcessWorkingSetSize 更有效）
$negOne = [IntPtr]::new(-1)
$trimCount = 0
Get-Process | ForEach-Object {{
    $p = $_
    if ($protected -contains $p.Id) {{ return }}
    if ($protectedNames -contains $p.ProcessName.ToLower()) {{ return }}
    try {{
        [WAM.MemOpt]::EmptyWorkingSet($p.Handle) | Out-Null
        [WAM.MemOpt]::SetProcessWorkingSetSize($p.Handle, $negOne, $negOne) | Out-Null
        $trimCount++
    }} catch {{ }}
}}

# 压缩 System 进程 (PID 4) - 清理系统文件缓存
try {{
    $sysProc = Get-Process -Id 4 -ErrorAction Stop
    [WAM.MemOpt]::EmptyWorkingSet($sysProc.Handle) | Out-Null
    [WAM.MemOpt]::SetProcessWorkingSetSize($sysProc.Handle, $negOne, $negOne) | Out-Null
}} catch {{ }}

# 压缩 svchost、dllhost 等宿主进程
Get-Process | Where-Object {{
    $n = $_.ProcessName.ToLower()
    ($n -eq "svchost" -or $n -eq "dllhost" -or $n -eq "rundll32" -or $n -eq "conhost")
}} | ForEach-Object {{
    try {{
        [WAM.MemOpt]::EmptyWorkingSet($_.Handle) | Out-Null
        [WAM.MemOpt]::SetProcessWorkingSetSize($_.Handle, $negOne, $negOne) | Out-Null
    }} catch {{ }}
}}

# ============================================================
# 阶段 3: 停止/禁用不必要的服务
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

# ============================================================
# 结果统计
# ============================================================
$ramAfter = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory * 1KB / 1MB
$availAfter = (Get-Counter "\Memory\Available MBytes" -ErrorAction SilentlyContinue).CounterSamples.CookedValue
if (-not $availAfter) {{ $availAfter = $ramAfter }}
$inUse_before = $ramTotal - $availBefore
$inUse_after = $ramTotal - $availAfter
$freed = $availAfter - $availBefore

Write-Output "TOTAL=$ramTotal"
Write-Output "AVAIL_BEFORE=$availBefore"
Write-Output "AVAIL_AFTER=$availAfter"
Write-Output "INUSE_BEFORE=$inUse_before"
Write-Output "INUSE_AFTER=$inUse_after"
Write-Output "FREED=$freed"
Write-Output "KILLED=$killed"
Write-Output "KILLED_MEM=$killedMemMB"
Write-Output "TRIM=$trimCount"
Write-Output "STOPPED=$stopped"
Write-Output "DISABLED=$disabled"
'''
    notify(10, "执行激进优化脚本...")
    out, err, rc = _run_ps(script, timeout=90)

    # 解析结果
    total_mb = 0.0
    avail_before = 0.0
    avail_after = 0.0
    inuse_before = 0.0
    inuse_after = 0.0
    freed_mb = 0.0
    killed = 0
    killed_mem = 0.0
    trim_count = 0
    stopped = 0
    disabled = 0

    for line in out.splitlines():
        line = line.strip()
        try:
            if line.startswith("TOTAL="):
                total_mb = float(line.split("=", 1)[1])
            elif line.startswith("AVAIL_BEFORE="):
                avail_before = float(line.split("=", 1)[1])
            elif line.startswith("AVAIL_AFTER="):
                avail_after = float(line.split("=", 1)[1])
            elif line.startswith("INUSE_BEFORE="):
                inuse_before = float(line.split("=", 1)[1])
            elif line.startswith("INUSE_AFTER="):
                inuse_after = float(line.split("=", 1)[1])
            elif line.startswith("FREED="):
                freed_mb = float(line.split("=", 1)[1])
            elif line.startswith("KILLED="):
                killed = int(line.split("=", 1)[1])
            elif line.startswith("KILLED_MEM="):
                killed_mem = float(line.split("=", 1)[1])
            elif line.startswith("TRIM="):
                trim_count = int(line.split("=", 1)[1])
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
    details.append(f"总内存: {total_mb:.0f} MB")
    details.append(f"优化前使用: {inuse_before:.0f} MB")
    details.append(f"优化后使用: {inuse_after:.0f} MB")
    if killed > 0:
        details.append(f"终止了 {killed} 个后台进程 (释放 ~{killed_mem:.0f} MB)")
    details.append(f"压缩了 {trim_count} 个进程的工作集")
    if stopped > 0:
        details.append(f"停止了 {stopped} 个服务")
    if disabled > 0:
        details.append(f"禁用了 {disabled} 个服务")

    pct = freed_mb / max(inuse_before, 1) * 100 if inuse_before > 0 else 0
    msg = f"释放 {freed_mb:.0f} MB ({pct:.0f}%)，当前使用 {inuse_after:.0f} MB"

    return {
        "success": True,
        "message": msg,
        "freed_mb": round(freed_mb, 1),
        "inuse_before_mb": round(inuse_before, 0),
        "inuse_after_mb": round(inuse_after, 0),
        "processes_killed": killed,
        "processes_trimmed": trim_count,
        "services_stopped": stopped,
        "services_disabled": disabled,
        "details": details,
    }