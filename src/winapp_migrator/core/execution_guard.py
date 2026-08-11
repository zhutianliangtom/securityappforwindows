"""执行防护：监控新启动的进程，检测申请管理员权限的安装/脚本，拦截格机与无文件攻击

纯 Win32 API（复用 security 核心工具）：
- 新进程发现：CreateToolhelp32Snapshot 快照对比基线
- 提权检测：LoadLibraryEx(LOAD_LIBRARY_AS_DATAFILE) 读取 PE manifest requestedExecutionLevel
- 命令行：ReadProcessMemory 读取目标进程 PEB CommandLine
- 拦截：OpenProcess + TerminateProcess

策略分级：
  block 格机/破坏性命令（format/diskpart clean/sysprep/systemreset/rm -rf 等）→ 自动终止
  block 无文件攻击（PowerShell -EncodedCommand / IEX 远程加载）→ 自动终止
  warn  申请管理员权限的程序 → 仅提示（避免误杀正常安装程序）
"""

import ctypes
import ctypes.wintypes as wintypes
import re
from pathlib import Path
from typing import Dict, List, Optional

import winapp_migrator.core.security as _sec

kernel32 = _sec.kernel32
ntdll = _sec.ntdll

RT_MANIFEST = 24
LOAD_LIBRARY_AS_DATAFILE = 0x2

# ------------------------------------------------------------
# 恶意特征（保守，避免误杀正常操作）
# ------------------------------------------------------------
# 格机/破坏性命令特征（命令行小写子串匹配）
_DESTRUCT_CMDS = (
    "format ", "format.com", "diskpart", " clean", "sysprep", "systemreset",
    "reagentc", "cipher /w", "rm -rf", "del /f /s /q c:", "del c:\\",
    "bcdedit /set", "dism /remove",
)
# 破坏性程序名（即使无命令行参数也拦截）
_DESTRUCT_EXES = {
    "format.exe", "format.com", "diskpart.exe", "sysprep.exe",
    "systemreset.exe", "reagentc.exe", "bootsect.exe",
}
# 无文件攻击：编码执行 / 远程加载下载执行
_LIVELESS_MARKERS = (
    "encodedcommand", "-enc ", "downloadstring", "invoke-expression",
)


def _manifest_level(exe_path: str) -> str:
    """读取 PE 可执行文件的 manifest requestedExecutionLevel（空串表示未提权）"""
    kernel32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    kernel32.LoadLibraryExW.restype = wintypes.HMODULE
    kernel32.FindResourceW.argtypes = [wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p]
    kernel32.FindResourceW.restype = wintypes.HRSRC
    kernel32.SizeofResource.argtypes = [wintypes.HMODULE, wintypes.HRSRC]
    kernel32.SizeofResource.restype = wintypes.DWORD
    kernel32.LoadResource.argtypes = [wintypes.HMODULE, wintypes.HRSRC]
    kernel32.LoadResource.restype = wintypes.HGLOBAL
    kernel32.LockResource.argtypes = [wintypes.HGLOBAL]
    kernel32.LockResource.restype = ctypes.c_void_p
    kernel32.FreeLibrary.argtypes = [wintypes.HMODULE]

    try:
        hmod = kernel32.LoadLibraryExW(exe_path, None, LOAD_LIBRARY_AS_DATAFILE)
        if not hmod:
            return ""
        try:
            hres = kernel32.FindResourceW(hmod, ctypes.c_void_p(1), ctypes.c_void_p(RT_MANIFEST))
            if not hres:
                return ""
            size = kernel32.SizeofResource(hmod, hres)
            hdata = kernel32.LoadResource(hmod, hres)
            ptr = kernel32.LockResource(hdata)
            if not ptr or size <= 0:
                return ""
            xml = ctypes.string_at(ptr, size).decode("utf-8", "ignore")
            m = re.search(r'requestedExecutionLevel[^>]*level="(\w+)"', xml)
            return m.group(1) if m else ""
        finally:
            kernel32.FreeLibrary(hmod)
    except Exception:
        return ""


def _process_cmdline(pid: int) -> str:
    """ReadProcessMemory 读取目标进程 PEB.CommandLine（x64 偏移 0x70）"""
    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010
    h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        return ""
    try:
        pbi = _sec.PROCESS_BASIC_INFORMATION()
        if ntdll.NtQueryInformationProcess(h, 0, ctypes.byref(pbi),
                                           ctypes.sizeof(pbi), None) == 0 and pbi.PebBaseAddress:
            pp_raw = _sec._read_mem(h, pbi.PebBaseAddress + 0x20, 8)
            if len(pp_raw) == 8:
                pp = int.from_bytes(pp_raw, "little")
                if pp:
                    us_raw = _sec._read_mem(h, pp + 0x70, 16)  # CommandLine UNICODE_STRING
                    if len(us_raw) == 16:
                        length = int.from_bytes(us_raw[:2], "little")
                        buf_addr = int.from_bytes(us_raw[8:16], "little")
                        if buf_addr and 0 < length <= 4096:
                            data = _sec._read_mem(h, buf_addr, length)
                            if data:
                                return data.decode("utf-16-le", "replace")
    finally:
        kernel32.CloseHandle(h)
    return ""


class ExecutionGuard:
    """执行防护：监控新进程并检测提权/格机/无文件攻击"""

    def __init__(self):
        self._baseline: set = set()

    def start(self):
        """记录当前进程基线（防护开启时已运行的进程视为可信）"""
        self._baseline = {p["pid"] for p in _sec._enum_processes()}

    def check(self) -> dict:
        """对比快照发现新进程并分析，返回 {'blocked': [...], 'warned': [...]}"""
        result = {"blocked": [], "warned": []}
        now_pids = {p["pid"] for p in _sec._enum_processes()}
        for pid in sorted(now_pids - self._baseline):
            entry = self._analyze(pid)
            if not entry:
                continue
            if entry["level"] == "block":
                entry["killed"] = _sec._terminate_process(pid)
                result["blocked"].append(entry)
            else:
                result["warned"].append(entry)
        self._baseline = now_pids
        return result

    def _analyze(self, pid: int) -> Optional[dict]:
        path = _sec._process_path(pid)
        name = Path(path).name if path else ""
        cmdline = _process_cmdline(pid)
        low = cmdline.lower()

        # 1) 格机/破坏性命令 → 拦截
        if any(m in low for m in _DESTRUCT_CMDS) or (name and name.lower() in _DESTRUCT_EXES):
            return {"pid": pid, "name": name or f"PID {pid}", "cmdline": cmdline,
                    "level": "block", "reason": "检测到格机/破坏性命令"}
        # 2) 无文件攻击（编码执行/远程加载）→ 拦截
        if any(m in low for m in _LIVELESS_MARKERS):
            return {"pid": pid, "name": name or f"PID {pid}", "cmdline": cmdline,
                    "level": "block", "reason": "检测到无文件攻击（编码/远程加载执行）"}
        # 3) 申请管理员权限 → 提示（不拦截，避免误杀正常安装程序）
        if path and _manifest_level(path) == "requireAdministrator" \
                and _sec.SecurityScanner._not_system(path):
            return {"pid": pid, "name": name or f"PID {pid}", "cmdline": cmdline,
                    "level": "warn", "reason": "该程序申请管理员权限"}
        return None
