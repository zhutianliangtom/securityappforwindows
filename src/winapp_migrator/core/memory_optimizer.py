"""内存优化模块：强制后台进程/服务页面换出到虚拟内存（硬盘）"""

import base64
import os
import subprocess
import logging

logger = logging.getLogger(__name__)

# 系统关键进程，绝不压缩（保持系统响应）
_PROTECTED_NAMES = {
    "system", "idle", "csrss", "wininit", "services",
    "lsass", "winlogon", "smss",
    "spoolsv", "audiodg", "dwm", "explorer",
    "taskhostw", "sihost", "runtimebroker",
    "fontdrvhost", "wlms", "logonui",
    "applicationframehost", "winappmigrator",
    "registry", "memcompression",
    "searchindexer", "securityhealthservice",
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
    """强制后台进程页面换出到虚拟内存（硬盘），释放物理 RAM"""

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
public static extern bool SetProcessWorkingSetSizeEx(IntPtr hProcess, IntPtr dwMinimumWorkingSetSize, IntPtr dwMaximumWorkingSetSize, uint Flags);
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

# --- 基线 ---
$os = Get-CimInstance Win32_OperatingSystem
$totalMB = $os.TotalVisibleMemorySize / 1024
$availBefore = (Get-Counter "\Memory\Available MBytes" -ErrorAction SilentlyContinue).CounterSamples.CookedValue
if (-not $availBefore) {{ $availBefore = $os.FreePhysicalMemory / 1024 }}
$inUseBefore = $totalMB - $availBefore

# 工作集硬限制大小：1 页 (4096 字节)，强制 Windows 把其他页面写到 pagefile
$pageSize = [IntPtr]::new(4096)
$negOne = [IntPtr]::new(-1)

$emptySuccess = 0
$limitSuccess = 0
$fail = 0

# 获取所有进程，按 WorkingSet 从大到小排序（先处理内存大户）
$allProcs = Get-Process | Sort-Object WorkingSet64 -Descending

# ============================================================
# 阶段 1: EmptyWorkingSet + 硬限制工作集（强制换出到硬盘）
# ============================================================
foreach ($p in $allProcs) {{
    # 跳过保护列表
    if ($protected -contains $p.Id) {{ continue }}
    if ($protectedNames -contains $p.ProcessName.ToLower()) {{ continue }}

    try {{
        # 第一步：EmptyWorkingSet 把所有页面踢出工作集
        [WAM.MemOpt]::EmptyWorkingSet($p.Handle) | Out-Null
        $emptySuccess++
    }} catch {{ }}

    try {{
        # 第二步：设置硬工作集限制为 1 页，阻止 Windows 把页面拉回 RAM
        # 进程访问已被换出的页面时，会从 pagefile 按需换入
        [WAM.MemOpt]::SetProcessWorkingSetSize($p.Handle, $pageSize, $pageSize) | Out-Null
        $limitSuccess++
    }} catch {{ $fail++ }}
}}

# ============================================================
# 阶段 2: 清理系统文件缓存
# ============================================================
# 先禁用再恢复文件缓存以清空
try {{
    [WAM.MemOpt]::SetSystemFileCacheSize($negOne, $negOne, 0x2) | Out-Null
    [WAM.MemOpt]::SetSystemFileCacheSize($negOne, $negOne, 0) | Out-Null
}} catch {{ }}

# 压缩 System 进程 (PID 4)
try {{
    $sysProc = Get-Process -Id 4 -ErrorAction Stop
    [WAM.MemOpt]::EmptyWorkingSet($sysProc.Handle) | Out-Null
    [WAM.MemOpt]::SetProcessWorkingSetSize($sysProc.Handle, $negOne, $negOne) | Out-Null
}} catch {{ }}

# ============================================================
# 阶段 3: 第二轮 EmptyWorkingSet 收尾
# ============================================================
foreach ($p in $allProcs) {{
    if ($protected -contains $p.Id) {{ continue }}
    if ($protectedNames -contains $p.ProcessName.ToLower()) {{ continue }}
    try {{
        [WAM.MemOpt]::EmptyWorkingSet($p.Handle) | Out-Null
    }} catch {{ }}
}}

# ============================================================
# 结果统计
# ============================================================
$availAfter = (Get-Counter "\Memory\Available MBytes" -ErrorAction SilentlyContinue).CounterSamples.CookedValue
if (-not $availAfter) {{ $availAfter = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024 }}
$inUseAfter = $totalMB - $availAfter
$freedMB = $availAfter - $availBefore

Write-Output "TOTAL=$totalMB"
Write-Output "INUSE_BEFORE=$inUseBefore"
Write-Output "INUSE_AFTER=$inUseAfter"
Write-Output "FREED=$freedMB"
Write-Output "EMPTY=$emptySuccess"
Write-Output "LIMIT=$limitSuccess"
Write-Output "FAIL=$fail"
'''
    notify(10, "正在强制换出后台进程到虚拟内存...")
    out, err, rc = _run_ps(script, timeout=90)

    total_mb = 0.0
    inuse_before = 0.0
    inuse_after = 0.0
    freed_mb = 0.0
    empty_success = 0
    limit_success = 0
    fail = 0

    for line in out.splitlines():
        line = line.strip()
        try:
            if line.startswith("TOTAL="):
                total_mb = float(line.split("=", 1)[1])
            elif line.startswith("INUSE_BEFORE="):
                inuse_before = float(line.split("=", 1)[1])
            elif line.startswith("INUSE_AFTER="):
                inuse_after = float(line.split("=", 1)[1])
            elif line.startswith("FREED="):
                freed_mb = float(line.split("=", 1)[1])
            elif line.startswith("EMPTY="):
                empty_success = int(line.split("=", 1)[1])
            elif line.startswith("LIMIT="):
                limit_success = int(line.split("=", 1)[1])
            elif line.startswith("FAIL="):
                fail = int(line.split("=", 1)[1])
        except Exception:
            pass

    if err and "timeout" not in err.lower():
        logger.warning("PowerShell stderr: %s", err[:500])

    notify(100, "优化完成")

    pct = freed_mb / max(inuse_before, 1) * 100 if inuse_before > 0 else 0

    details = [
        f"总内存: {total_mb:.0f} MB",
        f"优化前使用: {inuse_before:.0f} MB",
        f"优化后使用: {inuse_after:.0f} MB",
        f"释放: {freed_mb:.0f} MB ({pct:.0f}%)",
        f"EmptyWorkingSet: {empty_success} 个进程",
        f"硬限制工作集: {limit_success} 个进程",
    ]

    msg = f"释放 {freed_mb:.0f} MB ({pct:.0f}%)，当前使用 {inuse_after:.0f} MB"

    return {
        "success": True,
        "message": msg,
        "freed_mb": round(freed_mb, 1),
        "inuse_before_mb": round(inuse_before, 0),
        "inuse_after_mb": round(inuse_after, 0),
        "processes_trimmed": empty_success,
        "processes_killed": 0,
        "services_stopped": 0,
        "services_disabled": 0,
        "details": details,
    }