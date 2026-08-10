"""内存优化模块：通过 OpenProcess 获取正确权限句柄，强制换出到虚拟内存"""

import base64
import os
import subprocess
import logging

logger = logging.getLogger(__name__)

# 仅保护核心进程
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
    """激进压缩：OpenProcess(PROCESS_SET_QUOTA) + EmptyWorkingSet 多轮"""

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
public static extern IntPtr OpenProcess(uint dwDesiredAccess, bool bInheritHandle, uint dwProcessId);
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool CloseHandle(IntPtr hObject);
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool EmptyWorkingSet(IntPtr hProcess);
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool SetProcessWorkingSetSize(IntPtr hProcess, IntPtr dwMinimumWorkingSetSize, IntPtr dwMaximumWorkingSetSize);
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool SetSystemFileCacheSize(IntPtr MinimumFileCacheSize, IntPtr MaximumFileCacheSize, uint Flags);
[DllImport("advapi32.dll", SetLastError=true)]
public static extern bool OpenProcessToken(IntPtr ProcessHandle, uint DesiredAccess, out IntPtr TokenHandle);
[DllImport("advapi32.dll", SetLastError=true)]
public static extern bool LookupPrivilegeValue(string lpSystemName, string lpName, out long lpLuid);
[DllImport("advapi32.dll", SetLastError=true)]
public static extern bool AdjustTokenPrivileges(IntPtr TokenHandle, bool DisableAllPrivileges, IntPtr NewState, uint BufferLength, IntPtr PreviousState, IntPtr ReturnLength);
[DllImport("kernel32.dll", SetLastError=true)]
public static extern IntPtr GetCurrentProcess();
"@
Add-Type -Name MemOpt -Namespace WAM -MemberDefinition $sig

$sigFG = @"
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
"@
Add-Type -Name FG -Namespace WAM -MemberDefinition $sigFG

# --- 启用 SeIncreaseQuotaPrivilege ---
$SE_INCREASE_QUOTA_NAME = "SeIncreaseQuotaPrivilege"
$TOKEN_ADJUST_PRIVILEGES = 0x0020
$TOKEN_QUERY = 0x0008
$SE_PRIVILEGE_ENABLED = 0x2

$hToken = [IntPtr]::Zero
$hProc = [WAM.MemOpt]::GetCurrentProcess()
if ([WAM.MemOpt]::OpenProcessToken($hProc, $TOKEN_ADJUST_PRIVILEGES -bor $TOKEN_QUERY, [ref]$hToken)) {{
    $luid = 0L
    if ([WAM.MemOpt]::LookupPrivilegeValue($null, $SE_INCREASE_QUOTA_NAME, [ref]$luid)) {{
        # 构建 TOKEN_PRIVILEGES 结构
        $tpSize = [System.Runtime.InteropServices.Marshal]::SizeOf([long]) * 2 + [System.Runtime.InteropServices.Marshal]::SizeOf([int])
        $tp = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($tpSize)
        try {{
            [System.Runtime.InteropServices.Marshal]::WriteInt32($tp, 0, 1)  # PrivilegeCount
            [System.Runtime.InteropServices.Marshal]::WriteInt64($tp, [System.Runtime.InteropServices.Marshal]::SizeOf([int]), $luid)
            [System.Runtime.InteropServices.Marshal]::WriteInt32($tp, [System.Runtime.InteropServices.Marshal]::SizeOf([int]) + [System.Runtime.InteropServices.Marshal]::SizeOf([long]), $SE_PRIVILEGE_ENABLED)
            [WAM.MemOpt]::AdjustTokenPrivileges($hToken, $false, $tp, [uint32]$tpSize, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
        }} finally {{
            [System.Runtime.InteropServices.Marshal]::FreeHGlobal($tp)
        }}
    }}
    [WAM.MemOpt]::CloseHandle($hToken) | Out-Null
}}

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

# --- 权限常量 ---
$PROCESS_SET_QUOTA = 0x0100
$PROCESS_QUERY_INFORMATION = 0x0400
$ACCESS = $PROCESS_SET_QUOTA -bor $PROCESS_QUERY_INFORMATION

$totalMB = (Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize / 1024
$negOne = [IntPtr]::new(-1)

# --- 基线测量 ---
$availBefore = 0
try {{
    $availBefore = (Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory -ErrorAction Stop).AvailableMBytes
}} catch {{ }}
if ($availBefore -le 0) {{
    $availBefore = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024
}}

$allProcs = Get-Process | Sort-Object WorkingSet64 -Descending
$wsBefore = 0
$procCount = 0
foreach ($p in $allProcs) {{
    try {{ $wsBefore += $p.WorkingSet64 }} catch {{ }}
    $procCount++
}}
$wsBeforeMB = $wsBefore / 1MB

$emptyOk = 0
$failOpen = 0
$failEmpty = 0

# ============================================================
# 主循环：OpenProcess + EmptyWorkingSet + SetProcessWorkingSetSize(-1,-1)
# 核心：EmptyWorkingSet 踢出页面，SetProcessWorkingSetSize(-1,-1) 双保险
# 不使用硬上限（会引发 thrashing，页面被立刻 fault 回来）
# ============================================================
foreach ($p in $allProcs) {{
    if ($protected -contains $p.Id) {{ continue }}
    if ($protectedNames -contains $p.ProcessName.ToLower()) {{ continue }}

    $h = [WAM.MemOpt]::OpenProcess($ACCESS, $false, [uint32]$p.Id)
    if ($h -eq [IntPtr]::Zero) {{
        $failOpen++
        continue
    }}

    try {{
        $r1 = [WAM.MemOpt]::EmptyWorkingSet($h)
        $r2 = [WAM.MemOpt]::SetProcessWorkingSetSize($h, $negOne, $negOne)
        if ($r1 -or $r2) {{
            $emptyOk++
        }} else {{
            $failEmpty++
        }}
    }} catch {{
        $failEmpty++
    }}

    [WAM.MemOpt]::CloseHandle($h) | Out-Null
}}

# ============================================================
# 清空系统文件缓存
# ============================================================
try {{
    [WAM.MemOpt]::SetSystemFileCacheSize($negOne, $negOne, 0x2) | Out-Null
    [WAM.MemOpt]::SetSystemFileCacheSize($negOne, $negOne, 0) | Out-Null
}} catch {{ }}

# 压缩 System 进程 (PID 4)
$hSys = [WAM.MemOpt]::OpenProcess($ACCESS, $false, 4)
if ($hSys -ne [IntPtr]::Zero) {{
    try {{
        [WAM.MemOpt]::EmptyWorkingSet($hSys) | Out-Null
        [WAM.MemOpt]::SetProcessWorkingSetSize($hSys, $negOne, $negOne) | Out-Null
    }} catch {{ }}
    [WAM.MemOpt]::CloseHandle($hSys) | Out-Null
}}

# ============================================================
# 结果统计（立即测量，避免页面被 fault 回来）
# ============================================================
$allProcs2 = Get-Process
$wsAfter = 0
foreach ($p in $allProcs2) {{
    try {{ $wsAfter += $p.WorkingSet64 }} catch {{ }}
}}
$wsAfterMB = $wsAfter / 1MB
$freedMB = $wsBeforeMB - $wsAfterMB

$availAfter = 0
try {{
    $availAfter = (Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory -ErrorAction Stop).AvailableMBytes
}} catch {{ }}
if ($availAfter -le 0) {{
    $availAfter = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024
}}
$availGained = $availAfter - $availBefore

Write-Output "TOTAL=$totalMB"
Write-Output "WS_BEFORE=$wsBeforeMB"
Write-Output "WS_AFTER=$wsAfterMB"
Write-Output "FREED=$freedMB"
Write-Output "AVAIL_BEFORE=$availBefore"
Write-Output "AVAIL_AFTER=$availAfter"
Write-Output "AVAIL_GAINED=$availGained"
Write-Output "EMPTY_OK=$emptyOk"
Write-Output "FAIL_OPEN=$failOpen"
Write-Output "FAIL_EMPTY=$failEmpty"
Write-Output "PROC_COUNT=$procCount"
'''
    notify(10, "正在激进压缩所有后台进程到虚拟内存...")
    out, err, rc = _run_ps(script, timeout=120)

    # 诊断日志：记录 PowerShell 原始输出
    logger.info("Memory optimize PS output:\n%s", out[:2000] if out else "(empty)")
    if err:
        logger.warning("Memory optimize PS stderr:\n%s", err[:1000])

    total_mb = 0.0
    ws_before = 0.0
    ws_after = 0.0
    freed_mb = 0.0
    avail_before = 0.0
    avail_after = 0.0
    avail_gained = 0.0
    empty_ok = 0
    fail_open = 0
    fail_empty = 0
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
            elif line.startswith("AVAIL_BEFORE="):
                avail_before = float(line.split("=", 1)[1])
            elif line.startswith("AVAIL_AFTER="):
                avail_after = float(line.split("=", 1)[1])
            elif line.startswith("AVAIL_GAINED="):
                avail_gained = float(line.split("=", 1)[1])
            elif line.startswith("EMPTY_OK="):
                empty_ok = int(line.split("=", 1)[1])
            elif line.startswith("FAIL_OPEN="):
                fail_open = int(line.split("=", 1)[1])
            elif line.startswith("FAIL_EMPTY="):
                fail_empty = int(line.split("=", 1)[1])
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
        f"可用内存增加: {avail_gained:.0f} MB",
        f"成功压缩: {empty_ok} / {proc_count} 个进程",
        f"OpenProcess 失败: {fail_open}，EmptyWorkingSet 失败: {fail_empty}",
    ]

    msg = f"释放 {freed_mb:.0f} MB ({pct:.0f}%)，可用内存 +{avail_gained:.0f} MB"

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