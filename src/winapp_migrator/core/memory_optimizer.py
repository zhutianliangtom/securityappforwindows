"""内存优化模块：纯 Python ctypes 直调 Win32 API，无 PowerShell 开销"""

import ctypes
import ctypes.wintypes as w
import logging
import os
from ctypes import byref, sizeof, c_size_t, c_void_p, POINTER, Structure

logger = logging.getLogger(__name__)

# ============================================================
# Win32 API 绑定
# ============================================================
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

# --- 常量 ---
TH32CS_SNAPPROCESS = 0x02
PROCESS_SET_QUOTA = 0x0100
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_QUERY = 0x0008
SE_PRIVILEGE_ENABLED = 0x2

# --- 结构体 ---
class PROCESSENTRY32W(Structure):
    _fields_ = [
        ("dwSize", w.DWORD),
        ("cntUsage", w.DWORD),
        ("th32ProcessID", w.DWORD),
        ("th32DefaultHeapID", POINTER(w.ULONG)),
        ("th32ModuleID", w.DWORD),
        ("cntThreads", w.DWORD),
        ("th32ParentProcessID", w.DWORD),
        ("pcPriClassBase", w.LONG),
        ("dwFlags", w.DWORD),
        ("szExeFile", w.WCHAR * 260),
    ]

class PROCESS_MEMORY_COUNTERS_EX(Structure):
    _fields_ = [
        ("cb", w.DWORD),
        ("PageFaultCount", w.DWORD),
        ("PeakWorkingSetSize", c_size_t),
        ("WorkingSetSize", c_size_t),
        ("QuotaPeakPagedPoolUsage", c_size_t),
        ("QuotaPagedPoolUsage", c_size_t),
        ("QuotaPeakNonPagedPoolUsage", c_size_t),
        ("QuotaNonPagedPoolUsage", c_size_t),
        ("PagefileUsage", c_size_t),
        ("PeakPagefileUsage", c_size_t),
        ("PrivateUsage", c_size_t),
    ]

class LUID(Structure):
    _fields_ = [("LowPart", w.DWORD), ("HighPart", w.LONG)]

class LUID_AND_ATTRIBUTES(Structure):
    _fields_ = [("Luid", LUID), ("Attributes", w.DWORD)]

class TOKEN_PRIVILEGES(Structure):
    _fields_ = [("PrivilegeCount", w.DWORD), ("Privileges", LUID_AND_ATTRIBUTES * 1)]

# --- 函数签名 ---
CreateToolhelp32Snapshot = kernel32.CreateToolhelp32Snapshot
CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
CreateToolhelp32Snapshot.restype = w.HANDLE

Process32FirstW = kernel32.Process32FirstW
Process32FirstW.argtypes = [w.HANDLE, POINTER(PROCESSENTRY32W)]
Process32FirstW.restype = w.BOOL

Process32NextW = kernel32.Process32NextW
Process32NextW.argtypes = [w.HANDLE, POINTER(PROCESSENTRY32W)]
Process32NextW.restype = w.BOOL

OpenProcess = kernel32.OpenProcess
OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
OpenProcess.restype = w.HANDLE

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [w.HANDLE]
CloseHandle.restype = w.BOOL

EmptyWorkingSet = psapi.EmptyWorkingSet
EmptyWorkingSet.argtypes = [w.HANDLE]
EmptyWorkingSet.restype = w.BOOL

SetProcessWorkingSetSize = kernel32.SetProcessWorkingSetSize
SetProcessWorkingSetSize.argtypes = [w.HANDLE, c_size_t, c_size_t]
SetProcessWorkingSetSize.restype = w.BOOL

GetProcessMemoryInfo = psapi.GetProcessMemoryInfo
GetProcessMemoryInfo.argtypes = [w.HANDLE, POINTER(PROCESS_MEMORY_COUNTERS_EX), w.DWORD]
GetProcessMemoryInfo.restype = w.BOOL

GetCurrentProcess = kernel32.GetCurrentProcess
GetCurrentProcess.restype = w.HANDLE

OpenProcessToken = advapi32.OpenProcessToken
OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, POINTER(w.HANDLE)]
OpenProcessToken.restype = w.BOOL

LookupPrivilegeValueW = advapi32.LookupPrivilegeValueW
LookupPrivilegeValueW.argtypes = [w.LPCWSTR, w.LPCWSTR, POINTER(LUID)]
LookupPrivilegeValueW.restype = w.BOOL

AdjustTokenPrivileges = advapi32.AdjustTokenPrivileges
AdjustTokenPrivileges.argtypes = [w.HANDLE, w.BOOL, POINTER(TOKEN_PRIVILEGES), w.DWORD, c_void_p, c_void_p]
AdjustTokenPrivileges.restype = w.BOOL

SetSystemFileCacheSize = kernel32.SetSystemFileCacheSize
SetSystemFileCacheSize.argtypes = [c_size_t, c_size_t, w.DWORD]
SetSystemFileCacheSize.restype = w.BOOL

GetForegroundWindow = user32.GetForegroundWindow
GetForegroundWindow.restype = w.HANDLE

GetWindowThreadProcessId = user32.GetWindowThreadProcessId
GetWindowThreadProcessId.argtypes = [w.HANDLE, POINTER(w.DWORD)]
GetWindowThreadProcessId.restype = w.DWORD

GlobalMemoryStatusEx = kernel32.GlobalMemoryStatusEx

class MEMORYSTATUSEX(Structure):
    _fields_ = [
        ("dwLength", w.DWORD),
        ("dwMemoryLoad", w.DWORD),
        ("ullTotalPhys", w.ULARGE_INTEGER),
        ("ullAvailPhys", w.ULARGE_INTEGER),
        ("ullTotalPageFile", w.ULARGE_INTEGER),
        ("ullAvailPageFile", w.ULARGE_INTEGER),
        ("ullTotalVirtual", w.ULARGE_INTEGER),
        ("ullAvailVirtual", w.ULARGE_INTEGER),
        ("ullAvailExtendedVirtual", w.ULARGE_INTEGER),
    ]

GlobalMemoryStatusEx.argtypes = [POINTER(MEMORYSTATUSEX)]
GlobalMemoryStatusEx.restype = w.BOOL

# ============================================================
# 保护列表
# ============================================================
_PROTECTED_NAMES = {
    "system", "idle", "csrss", "wininit",
    "services", "lsass", "winlogon", "smss",
    "dwm", "explorer", "audiodg",
    "winappmigrator",
}


def _get_last_error():
    return ctypes.get_last_error()


def _enable_quota_privilege() -> bool:
    """启用 SeIncreaseQuotaPrivilege，确保 OpenProcess(PROCESS_SET_QUOTA) 成功"""
    h_token = w.HANDLE()
    if not OpenProcessToken(GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, byref(h_token)):
        return False

    luid = LUID()
    if not LookupPrivilegeValueW(None, "SeIncreaseQuotaPrivilege", byref(luid)):
        CloseHandle(h_token)
        return False

    tp = TOKEN_PRIVILEGES()
    tp.PrivilegeCount = 1
    tp.Privileges[0].Luid = luid
    tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED

    result = AdjustTokenPrivileges(h_token, False, byref(tp), sizeof(tp), None, None)
    CloseHandle(h_token)
    return result


def _get_foreground_pids() -> set:
    """获取前台窗口及其子进程 PID"""
    pids = set()
    hwnd = GetForegroundWindow()
    if hwnd:
        fg_pid = w.DWORD()
        GetWindowThreadProcessId(hwnd, byref(fg_pid))
        if fg_pid.value:
            pids.add(fg_pid.value)
    return pids


def _enum_processes() -> list[tuple[int, str, int]]:
    """枚举所有进程，返回 [(pid, name, working_set_bytes), ...] 按内存降序"""
    snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == w.HANDLE(-1):
        return []

    processes = []
    pe = PROCESSENTRY32W()
    pe.dwSize = sizeof(pe)

    if Process32FirstW(snap, byref(pe)):
        while True:
            pid = pe.th32ProcessID
            name = pe.szExeFile.lower() if pe.szExeFile else ""

            # 获取内存信息
            ws_bytes = 0
            if pid > 0 and pid != 4:  # skip idle (0) and system (4) for now
                h = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
                if h:
                    pmc = PROCESS_MEMORY_COUNTERS_EX()
                    pmc.cb = sizeof(pmc)
                    if GetProcessMemoryInfo(h, byref(pmc), sizeof(pmc)):
                        ws_bytes = pmc.WorkingSetSize
                    CloseHandle(h)

            processes.append((pid, name, ws_bytes))

            if not Process32NextW(snap, byref(pe)):
                break

    CloseHandle(snap)
    processes.sort(key=lambda x: x[2], reverse=True)
    return processes


def _get_memory_status() -> dict:
    """获取系统内存状态"""
    ms = MEMORYSTATUSEX()
    ms.dwLength = sizeof(ms)
    GlobalMemoryStatusEx(byref(ms))
    return {
        "total_mb": ms.ullTotalPhys / (1024 * 1024),
        "avail_mb": ms.ullAvailPhys / (1024 * 1024),
        "used_mb": (ms.ullTotalPhys - ms.ullAvailPhys) / (1024 * 1024),
        "load_pct": ms.dwMemoryLoad,
    }


def optimize_memory(progress_callback=None) -> dict:
    """激进压缩：纯 ctypes，零 PowerShell 开销"""

    def notify(pct: int, msg: str):
        logger.info("[%d%%] %s", pct, msg)
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    # 1. 启用特权
    notify(2, "启用 SeIncreaseQuotaPrivilege...")
    _enable_quota_privilege()

    # 2. 基线测量
    notify(5, "获取基线内存状态...")
    mem_before = _get_memory_status()

    # 3. 枚举所有进程
    notify(8, "枚举所有进程...")
    all_procs = _enum_processes()
    proc_count = len(all_procs)

    # 统计基线工作集
    ws_before = sum(p[2] for p in all_procs)
    ws_before_mb = ws_before / (1024 * 1024)

    # 保护列表
    protected_pids = {os.getpid()}
    protected_pids |= _get_foreground_pids()

    # 4. 激进压缩主循环
    notify(10, "激进压缩所有后台进程...")
    ACCESS = PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION
    NEG_ONE = c_size_t(-1)

    ok = 0
    fail_open = 0
    fail_empty = 0
    skipped = 0

    for i, (pid, name, _ws) in enumerate(all_procs):
        # 跳过保护和系统进程
        if pid in protected_pids:
            skipped += 1
            continue
        if name in _PROTECTED_NAMES:
            skipped += 1
            continue
        if pid <= 4:  # idle, system
            skipped += 1
            continue

        h = OpenProcess(ACCESS, False, pid)
        if not h:
            fail_open += 1
            continue

        r1 = EmptyWorkingSet(h)
        r2 = SetProcessWorkingSetSize(h, NEG_ONE, NEG_ONE)
        if r1 or r2:
            ok += 1
        else:
            fail_empty += 1

        CloseHandle(h)

        # 每 30 个进程报告一次进度
        if i % 30 == 0:
            pct = 10 + int(i / max(proc_count, 1) * 80)
            notify(pct, f"已压缩 {ok}/{i+1} 个进程...")

    # 5. 清空系统文件缓存
    notify(92, "清空系统文件缓存...")
    NEG_ONE_SZ = c_size_t(-1)
    try:
        SetSystemFileCacheSize(NEG_ONE_SZ, NEG_ONE_SZ, 0x2)
        SetSystemFileCacheSize(NEG_ONE_SZ, NEG_ONE_SZ, 0)
    except Exception:
        pass

    # 6. 压缩 System 进程 (PID 4)
    notify(95, "压缩系统进程...")
    h_sys = OpenProcess(ACCESS, False, 4)
    if h_sys:
        EmptyWorkingSet(h_sys)
        SetProcessWorkingSetSize(h_sys, NEG_ONE, NEG_ONE)
        CloseHandle(h_sys)

    # 7. 第二轮快速横扫
    notify(97, "第二轮收尾...")
    for pid, name, _ws in all_procs:
        if pid in protected_pids or name in _PROTECTED_NAMES or pid <= 4:
            continue
        h = OpenProcess(ACCESS, False, pid)
        if h:
            EmptyWorkingSet(h)
            CloseHandle(h)

    # 8. 结果统计
    notify(98, "计算优化结果...")
    mem_after = _get_memory_status()

    # 重新枚举获取优化后工作集
    all_procs2 = _enum_processes()
    ws_after = sum(p[2] for p in all_procs2)
    ws_after_mb = ws_after / (1024 * 1024)

    freed_mb = ws_before_mb - ws_after_mb
    avail_gained = mem_after["avail_mb"] - mem_before["avail_mb"]
    pct = freed_mb / max(ws_before_mb, 1) * 100 if ws_before_mb > 0 else 0

    notify(100, "优化完成")

    details = [
        f"总内存: {mem_after['total_mb']:.0f} MB",
        f"优化前工作集: {ws_before_mb:.0f} MB",
        f"优化后工作集: {ws_after_mb:.0f} MB",
        f"释放: {freed_mb:.0f} MB ({pct:.0f}%)",
        f"可用内存增加: {avail_gained:.0f} MB",
        f"成功压缩: {ok} / {proc_count} 个进程",
        f"OpenProcess 失败: {fail_open}，EmptyWorkingSet 失败: {fail_empty}",
    ]

    msg = f"释放 {freed_mb:.0f} MB ({pct:.0f}%)，可用内存 +{avail_gained:.0f} MB"

    return {
        "success": True,
        "message": msg,
        "freed_mb": round(freed_mb, 1),
        "inuse_before_mb": round(ws_before_mb, 0),
        "inuse_after_mb": round(ws_after_mb, 0),
        "processes_trimmed": ok,
        "processes_killed": 0,
        "services_stopped": 0,
        "services_disabled": 0,
        "details": details,
    }