"""内存优化模块：激进压缩工作集，强制换出到虚拟内存（硬盘）"""

import base64
import os
import subprocess
import logging

logger = logging.getLogger(__name__)

# 仅保护系统最核心进程，其余全部强制换出
_PROTECTED_NAMES = {
    "system", "idle", "csrss", "wininit",
    "services", "lsass", "winlogon", "smss",
    "dwm", "explorer", "audiodg",
    "winappmigrator",
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
    """激进压缩：EmptyWorkingSet + SetProcessWorkingSetSize(-1,-1) 多轮"""

    def notify(pct: int, msg: str):
        logger.info("[%d%%] %s", pct, msg)
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    protected_b64 = _encode_json([os.getpid()])
    protected_names_b64 = _encode_json(list(_PROTECTED_NAMES))

    script = rf'''
$ErrorActionPreference = "SilentlyContinue"

# --- P/Invoke ---
$sig = @"
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool EmptyWorkingSet(IntPtr hProcess);
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool SetProcessWorkingSetSize(IntPtr hProcess, IntPtr dwMinimumWorkingSetSize, IntPtr dwMaximumWorkingSetSize);
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool SetSystemFileCacheSize(IntPtr MinimumFileCacheSize, IntPtr MaximumFileCacheSize, uint Flags);
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

# 前台进程及其子进程
$hwnd = [WAM.FG]::GetForegroundWindow()
$fgPid = 0
[WAM.FG]::GetWindowThreadProcessId($hwnd, [ref]$fgPid)
if ($fgPid -gt 0) {{
    $protected += $fgPid
    Get-CimInstance Win32_Process | Where-Object {{ $_.ParentProcessId -eq $fgPid }} | ForEach-Object {{
        $protected += $_.ProcessId
    }}
}}

# --- 基线：统计所有进程总 WorkingSet ---
$totalMB = (Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize / 1024
$wsBefore = 0
$procCount = 0
$allProcs = Get-Process | Sort-Object WorkingSet64 -Descending
foreach ($p in $allProcs) {{
    try {{ $wsBefore += $p.WorkingSet64 }} catch {{ }}
    $procCount++
}}
$wsBeforeMB = $wsBefore / 1MB

$negOne = [IntPtr]::new(-1)
$emptyOk = 0
$fail = 0

# ============================================================
# 阶段 1: EmptyWorkingSet + SetProcessWorkingSetSize(-1,-1)
# ============================================================
foreach ($p in $allProcs) {{
    if ($protected -contains $p.Id) {{ continue }}
    if ($protectedNames -contains $p.ProcessName.ToLower()) {{ continue }}
    try {{
        [WAM.MemOpt]::EmptyWorkingSet($p.Handle) | Out-Null
        [WAM.MemOpt]::SetProcessWorkingSetSize($p.Handle, $negOne, $negOne) | Out-Null
        $emptyOk++
    }} catch {{ $fail++ }}
}}

# ============================================================
# 阶段 2: 清空系统文件缓存
# ============================================================
try {{
    [WAM.MemOpt]::SetSystemFileCacheSize($negOne, $negOne, 0x2) | Out-Null
    [WAM.MemOpt]::SetSystemFileCacheSize($negOne, $negOne, 0) | Out-Null
}} catch {{ }}
try {{
    $sysProc = Get-Process -Id 4 -ErrorAction Stop
    [WAM.MemOpt]::EmptyWorkingSet($sysProc.Handle) | Out-Null
    [WAM.MemOpt]::SetProcessWorkingSetSize($sysProc.Handle, $negOne, $negOne) | Out-Null
}} catch {{ }}

# ============================================================
# 阶段 3: 第二轮 EmptyWorkingSet
# ============================================================
foreach ($p in $allProcs) {{
    if ($protected -contains $p.Id) {{ continue }}
    if ($protectedNames -contains $p.ProcessName.ToLower()) {{ continue }}
    try {{ [WAM.MemOpt]::EmptyWorkingSet($p.Handle) | Out-Null }} catch {{ }}
}}

# ============================================================
# 阶段 4: 第三轮（200ms 间隔让系统完成写入）
# ============================================================
Start-Sleep -Milliseconds 200
foreach ($p in $allProcs) {{
    if ($protected -contains $p.Id) {{ continue }}
    if ($protectedNames -contains $p.ProcessName.ToLower()) {{ continue }}
    try {{ [WAM.MemOpt]::EmptyWorkingSet($p.Handle) | Out-Null }} catch {{ }}
}}

# ============================================================
# 结果：统计压缩后的总 WorkingSet
# ============================================================
$wsAfter = 0
$allProcs2 = Get-Process
foreach ($p in $allProcs2) {{
    try {{ $wsAfter += $p.WorkingSet64 }} catch {{ }}
}}
$wsAfterMB = $wsAfter / 1MB
$freedMB = $wsBeforeMB - $wsAfterMB

# 同时获取 Available MBytes 作为辅助指标
$availAfter = 0
try {{
    $perfMem = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory -ErrorAction Stop
    $availAfter = $perfMem.AvailableMBytes
}} catch {{ }}
if ($availAfter -le 0) {{
    try {{
        $availAfter = (Get-Counter "\Memory\Available MBytes" -ErrorAction Stop).CounterSamples.CookedValue
    }} catch {{ }}
}}
if ($availAfter -le 0) {{
    $availAfter = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024
}}

Write-Output "TOTAL=$totalMB"
Write-Output "WS_BEFORE=$wsBeforeMB"
Write-Output "WS_AFTER=$wsAfterMB"
Write-Output "FREED=$freedMB"
Write-Output "AVAIL_AFTER=$availAfter"
Write-Output "EMPTY_OK=$emptyOk"
Write-Output "FAIL=$fail"
Write-Output "PROC_COUNT=$procCount"
'''
    notify(10, "正在激进压缩所有后台进程到虚拟内存...")
    out, err, rc = _run_ps(script, timeout=90)

    total_mb = 0.0
    ws_before = 0.0
    ws_after = 0.0
    freed_mb = 0.0
    avail_after = 0.0
    empty_ok = 0
    fail = 0
    proc_count = 0

    for line in out.splitlines():
        line = line.strip()
        try:
            if line.startswith("TOTAL="):
                total_mb = float(line.split("=", 1)[1])
            elif line.startswith("WS_BEFORE="):
                ws_before = float(line.split("=", 1)[1])
            elif line.startswith("WS_AFTER="):
                ws_after = float(line.split("=", 1)[1])
            elif line.startswith("FREED="):
                freed_mb = float(line.split("=", 1)[1])
            elif line.startswith("AVAIL_AFTER="):
                avail_after = float(line.split("=", 1)[1])
            elif line.startswith("EMPTY_OK="):
                empty_ok = int(line.split("=", 1)[1])
            elif line.startswith("FAIL="):
                fail = int(line.split("=", 1)[1])
            elif line.startswith("PROC_COUNT="):
                proc_count = int(line.split("=", 1)[1])
        except Exception:
            pass

    if err and "timeout" not in err.lower():
        logger.warning("PowerShell stderr: %s", err[:500])

    notify(100, "优化完成")

    pct = freed_mb / max(ws_before, 1) * 100 if ws_before > 0 else 0

    details = [
        f"总内存: {total_mb:.0f} MB",
        f"优化前工作集: {ws_before:.0f} MB",
        f"优化后工作集: {ws_after:.0f} MB",
        f"释放: {freed_mb:.0f} MB ({pct:.0f}%)",
        f"压缩了 {empty_ok} / {proc_count} 个进程",
    ]

    msg = f"释放 {freed_mb:.0f} MB ({pct:.0f}%)，当前可用 {avail_after:.0f} MB"

    return {
        "success": True,
        "message": msg,
        "freed_mb": round(freed_mb, 1),
        "inuse_before_mb": round(ws_before, 0),
        "inuse_after_mb": round(ws_after, 0),
        "processes_trimmed": empty_ok,
        "processes_killed": 0,
        "services_stopped": 0,
        "services_disabled": 0,
        "details": details,
    }