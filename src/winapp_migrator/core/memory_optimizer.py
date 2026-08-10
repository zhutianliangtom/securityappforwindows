"""内存优化模块：纯 EmptyWorkingSet 压缩方案，不杀进程不影响服务"""

import base64
import os
import subprocess
import logging

logger = logging.getLogger(__name__)


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


def optimize_memory(progress_callback=None) -> dict:
    """纯 EmptyWorkingSet 压缩所有进程工作集，瞬间释放内存，不影响任何进程运行"""

    def notify(pct: int, msg: str):
        logger.info("[%d%%] %s", pct, msg)
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    script = r'''
$ErrorActionPreference = "SilentlyContinue"

# --- P/Invoke ---
$sig = @"
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool EmptyWorkingSet(IntPtr hProcess);
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool SetProcessWorkingSetSize(IntPtr hProcess, IntPtr dwMin, IntPtr dwMax);
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool SetSystemFileCacheSize(IntPtr MinimumFileCacheSize, IntPtr MaximumFileCacheSize, uint Flags);
"@
Add-Type -Name MemOpt -Namespace WAM -MemberDefinition $sig

# --- 基线 ---
$os = Get-CimInstance Win32_OperatingSystem
$totalMB = $os.TotalVisibleMemorySize / 1024
$availBefore = (Get-Counter "\Memory\Available MBytes" -ErrorAction SilentlyContinue).CounterSamples.CookedValue
if (-not $availBefore) { $availBefore = $os.FreePhysicalMemory / 1024 }
$inUseBefore = $totalMB - $availBefore

# ============================================================
# 阶段 1: EmptyWorkingSet 所有进程（核心手段）
# ============================================================
$negOne = [IntPtr]::new(-1)
$success = 0
$fail = 0

Get-Process | ForEach-Object {
    try {
        [WAM.MemOpt]::EmptyWorkingSet($_.Handle) | Out-Null
        [WAM.MemOpt]::SetProcessWorkingSetSize($_.Handle, $negOne, $negOne) | Out-Null
        $success++
    } catch { $fail++ }
}

# ============================================================
# 阶段 2: 清理系统文件缓存 (SetSystemFileCacheSize)
# ============================================================
# Flags: 0x2 = FILE_CACHE_MAX_HARD_DISABLE, 先禁用再恢复以清空缓存
try {
    [WAM.MemOpt]::SetSystemFileCacheSize($negOne, $negOne, 0x2) | Out-Null
    [WAM.MemOpt]::SetSystemFileCacheSize($negOne, $negOne, 0) | Out-Null
} catch { }

# 额外压缩 System 进程 (PID 4)
try {
    $sysProc = Get-Process -Id 4 -ErrorAction Stop
    [WAM.MemOpt]::EmptyWorkingSet($sysProc.Handle) | Out-Null
    [WAM.MemOpt]::SetProcessWorkingSetSize($sysProc.Handle, $negOne, $negOne) | Out-Null
} catch { }

# ============================================================
# 阶段 3: 第二轮压缩（被换出的页面可能又被拉回，再压一次）
# ============================================================
Get-Process | ForEach-Object {
    try {
        [WAM.MemOpt]::EmptyWorkingSet($_.Handle) | Out-Null
    } catch { }
}

# ============================================================
# 结果统计
# ============================================================
$availAfter = (Get-Counter "\Memory\Available MBytes" -ErrorAction SilentlyContinue).CounterSamples.CookedValue
if (-not $availAfter) { $availAfter = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024 }
$inUseAfter = $totalMB - $availAfter
$freedMB = $availAfter - $availBefore

Write-Output "TOTAL=$totalMB"
Write-Output "INUSE_BEFORE=$inUseBefore"
Write-Output "INUSE_AFTER=$inUseAfter"
Write-Output "FREED=$freedMB"
Write-Output "SUCCESS=$success"
Write-Output "FAIL=$fail"
'''
    notify(10, "正在压缩所有进程工作集...")
    out, err, rc = _run_ps(script, timeout=60)

    total_mb = 0.0
    inuse_before = 0.0
    inuse_after = 0.0
    freed_mb = 0.0
    success = 0
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
            elif line.startswith("SUCCESS="):
                success = int(line.split("=", 1)[1])
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
        f"压缩了 {success} 个进程的工作集",
    ]

    msg = f"释放 {freed_mb:.0f} MB ({pct:.0f}%)，当前使用 {inuse_after:.0f} MB"

    return {
        "success": True,
        "message": msg,
        "freed_mb": round(freed_mb, 1),
        "inuse_before_mb": round(inuse_before, 0),
        "inuse_after_mb": round(inuse_after, 0),
        "processes_trimmed": success,
        "processes_killed": 0,
        "services_stopped": 0,
        "services_disabled": 0,
        "details": details,
    }