"""静默安全核心：纯 ctypes 直接调用 Win32 API，不依赖系统自带安全工具
（无 PowerShell / WMI / MpCmdRun / netstat / taskkill，全部底层 API 实现）

- 进程枚举与路径：CreateToolhelp32Snapshot + QueryFullProcessImageNameW
- 进程终止：OpenProcess + TerminateProcess，NtOpenProcess 兜底，SeDebugPrivilege 提权
- 启动项：winreg（RegOpenKeyEx / RegEnumValue / RegDeleteValue 底层注册表 API）
- 网络监听：GetExtendedTcpTable 枚举监听端口（iphlpapi）
- 防火墙状态：注册表 EnableFirewall

特征库采用保守白名单式规则，排除系统目录，避免误杀正常软件。
"""

import ctypes
import ctypes.wintypes as wintypes
import os
import socket
import winreg
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

from winapp_migrator.utils.helpers import setup_logging

logger = setup_logging()

# ------------------------------------------------------------
# Win32 常量
# ------------------------------------------------------------
TH32CS_SNAPPROCESS = 0x2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
PROCESS_ALL_ACCESS = 0x001FFFFF
TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_QUERY = 0x0008
SE_PRIVILEGE_ENABLED = 0x2
AF_INET = 2
TCP_TABLE_OWNER_PID_LISTENER = 5
MIB_TCP_STATE_LISTEN = 2

# ------------------------------------------------------------
# 恶意特征库（保守规则：仅收录知名恶意软件名，避免误杀）
# ------------------------------------------------------------
# 恶意进程名（小写，不含扩展名）
_MALICIOUS_PROCESS_NAMES = frozenset({
    # 挖矿木马
    "xmrig", "minerd", "minerd64", "cryptominer", "cpuminer",
    "lolminer", "nbminer", "phoenixminer", "claymore", "wildrig",
    "t-rex", "trex", "teamredminer", "ethminer", "gminer", "kawpow",
    # 远控木马 / 蠕虫
    "njrat", "njw0rm", "darkcomet", "poisonivy", "gh0st", "ghostrat",
    "shellex", "winrar_setup", "srvany", "tcpviewer",
    "asyncrat", "quasar", "quasarrat", "remcos", "comrat",
    # 键盘记录 / 盗号 / 窃密
    "keylogger", "qakbot", "emotet", "trickbot", "botnet",
    "infostealer", "azorult", "redline", "vidar", "formbook",
    # 勒索软件
    "wannacry", "locky", "cerber", "teslacrypt", "gandcrab",
    "ryuk", "conti", "blackcat", "revil", "phobos",
})

# 恶意进程名 + 必须出现在非系统目录（防止误杀同名正常组件）
_SYSTEM_DIRS = frozenset({
    "windows", "system32", "syswow64", "program files", "program files (x86)",
})

# 启动项命令中的恶意特征（下载器/临时目录随机名 exe 等）
_MALICIOUS_STARTUP_MARKERS = (
    "xmrig", "minerd", "njrat", "darkcomet", "poisonivy",
    "wannacry", "locky", "asyncrat", "quasar",
    "\\temp\\", "\\tmp\\", "\\appdata\\local\\temp",
)

# 高危端口：暴露且防火墙关闭时提示风险
_HIGH_RISK_PORTS = frozenset({445, 139, 135, 3389, 23, 21, 1433, 3306, 5900, 6379})

# 注册表启动项位置
_STARTUP_REG_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
]

# 防火墙策略注册表位置
_FW_POLICY_KEYS = {
    "标准": r"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy\StandardProfile",
    "公用": r"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy\PublicProfile",
    "域": r"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy\DomainProfile",
}

# ------------------------------------------------------------
# Win32 API 绑定
# ------------------------------------------------------------
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll", use_last_error=True)

kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel32.TerminateProcess.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t)]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
ntdll.NtQueryInformationProcess.argtypes = [
    wintypes.HANDLE, wintypes.ULONG, wintypes.LPVOID, wintypes.ULONG, wintypes.PULONG]
ntdll.NtQueryInformationProcess.restype = ctypes.c_long


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


class PROCESS_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("ExitStatus", ctypes.c_ulong),
        ("PebBaseAddress", ctypes.c_void_p),
        ("AffinityMask", ctypes.c_void_p),
        ("BasePriority", ctypes.c_long),
        ("UniqueProcessId", ctypes.c_void_p),
        ("InheritedFromUniqueProcessId", ctypes.c_void_p),
    ]


class MIB_TCPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwRemoteAddr", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


# ------------------------------------------------------------
# 底层工具函数
# ------------------------------------------------------------
def _enable_debug_privilege() -> None:
    """启用 SeDebugPrivilege，允许打开更多进程句柄（真实安全软件标准做法）"""
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    h_token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(),
                                     TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
                                     ctypes.byref(h_token)):
        return

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", ctypes.c_long)]

    class LUID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

    class TOKEN_PRIVILEGES(ctypes.Structure):
        _fields_ = [("PrivilegeCount", wintypes.DWORD),
                    ("Privileges", LUID_AND_ATTRIBUTES * 1)]

    luid = LUID()
    try:
        if not advapi32.LookupPrivilegeValueW(None, "SeDebugPrivilege", ctypes.byref(luid)):
            return
        tp = TOKEN_PRIVILEGES(1, (LUID_AND_ATTRIBUTES(luid, SE_PRIVILEGE_ENABLED),))
        advapi32.AdjustTokenPrivileges(h_token, False, ctypes.byref(tp), 0, None, None)
    finally:
        kernel32.CloseHandle(h_token)


def _enum_processes() -> List[dict]:
    """CreateToolhelp32Snapshot 枚举全部进程，返回 [{'pid','name'}]"""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == wintypes.HANDLE(-1).value:
        return []
    procs = []
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            procs.append({"pid": int(pe.th32ProcessID), "name": pe.szExeFile})
            ok = kernel32.Process32NextW(snap, ctypes.byref(pe))
    finally:
        kernel32.CloseHandle(snap)
    return procs


def _read_mem(h, addr: int, size: int) -> bytes:
    """ReadProcessMemory 读取目标进程内存"""
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    if kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(read)):
        return buf.raw[:read.value]
    return b""


def _real_process_path(pid: int) -> str:
    """QueryFullProcessImageNameW 获取进程真实可执行路径"""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
    finally:
        kernel32.CloseHandle(h)
    return ""


def _process_path(pid: int) -> str:
    """获取进程显示路径：优先读目标进程 PEB.ImagePathName（含伪装值，
    恶意软件常篡改 PEB 使显示路径/命令行暴露特征名），失败回退真实路径"""
    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010
    h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if h:
        try:
            pbi = PROCESS_BASIC_INFORMATION()
            if ntdll.NtQueryInformationProcess(h, 0, ctypes.byref(pbi),
                                               ctypes.sizeof(pbi), None) == 0 and pbi.PebBaseAddress:
                pp_raw = _read_mem(h, pbi.PebBaseAddress + 0x20, 8)  # x64: ProcessParameters
                if len(pp_raw) == 8:
                    pp = int.from_bytes(pp_raw, "little")
                    if pp:
                        us_raw = _read_mem(h, pp + 0x60, 16)  # x64: ImagePathName UNICODE_STRING
                        if len(us_raw) == 16:
                            length = int.from_bytes(us_raw[:2], "little")
                            buf_addr = int.from_bytes(us_raw[8:16], "little")
                            if buf_addr and 0 < length <= 2048:
                                data = _read_mem(h, buf_addr, length)
                                if data:
                                    return data.decode("utf-16-le", "replace")
        finally:
            kernel32.CloseHandle(h)
    return _real_process_path(pid)


def _terminate_process(pid: int) -> bool:
    """OpenProcess + TerminateProcess，失败时 NtOpenProcess 兜底"""
    h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if h:
        try:
            if kernel32.TerminateProcess(h, 1):
                return True
        finally:
            kernel32.CloseHandle(h)

    # NtOpenProcess + NtTerminateProcess 兜底
    class CLIENT_ID(ctypes.Structure):
        _fields_ = [("UniqueProcess", wintypes.HANDLE),
                    ("UniqueThread", wintypes.HANDLE)]

    class OBJECT_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Length", wintypes.ULONG),
                    ("RootDirectory", wintypes.HANDLE),
                    ("ObjectName", ctypes.c_void_p),
                    ("Attributes", wintypes.ULONG),
                    ("SecurityDescriptor", ctypes.c_void_p),
                    ("SecurityQualityOfService", ctypes.c_void_p)]

    ntdll.NtOpenProcess.argtypes = [
        ctypes.POINTER(wintypes.HANDLE), wintypes.ULONG,
        ctypes.POINTER(OBJECT_ATTRIBUTES), ctypes.POINTER(CLIENT_ID)]
    ntdll.NtOpenProcess.restype = ctypes.c_long
    ntdll.NtTerminateProcess.argtypes = [wintypes.HANDLE, ctypes.c_long]
    ntdll.NtTerminateProcess.restype = ctypes.c_long
    ntdll.NtClose.argtypes = [wintypes.HANDLE]

    cid = CLIENT_ID(pid, None)
    oa = OBJECT_ATTRIBUTES(ctypes.sizeof(OBJECT_ATTRIBUTES), None, None, 0, None, None)
    h = wintypes.HANDLE()
    if ntdll.NtOpenProcess(ctypes.byref(h), PROCESS_ALL_ACCESS,
                           ctypes.byref(oa), ctypes.byref(cid)) == 0:
        try:
            return ntdll.NtTerminateProcess(h, 1) == 0
        finally:
            ntdll.NtClose(h)
    return False


def _listening_ports() -> set:
    """GetExtendedTcpTable 枚举监听端口（iphlpapi）"""
    try:
        iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
        iphlpapi.GetExtendedTcpTable.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
            wintypes.BOOL, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG]
        iphlpapi.GetExtendedTcpTable.restype = wintypes.ULONG

        size = wintypes.DWORD(0)
        iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), False, AF_INET,
                                     TCP_TABLE_OWNER_PID_LISTENER, 0)
        if not size.value:
            return set()
        buf = ctypes.create_string_buffer(size.value)
        if iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), False, AF_INET,
                                        TCP_TABLE_OWNER_PID_LISTENER, 0) != 0:
            return set()
        n = ctypes.c_ulong.from_buffer(buf).value
        ports = set()
        offset = 4  # 表头 dwNumEntries 之后是行数组
        row_size = ctypes.sizeof(MIB_TCPROW_OWNER_PID)
        for i in range(n):
            row = MIB_TCPROW_OWNER_PID.from_buffer(buf, offset + i * row_size)
            if row.dwState == MIB_TCP_STATE_LISTEN:
                ports.add(socket.ntohs(row.dwLocalPort))
        return ports
    except Exception:
        return set()


def _firewall_off_profiles() -> List[str]:
    """读取防火墙策略注册表，返回已关闭防火墙的配置文件名"""
    off = []
    for label, key_path in _FW_POLICY_KEYS.items():
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as k:
                v, _ = winreg.QueryValueEx(k, "EnableFirewall")
                if v == 0:
                    off.append(label)
        except OSError:
            continue
    return off


# ------------------------------------------------------------
# 安全扫描器
# ------------------------------------------------------------
class SecurityScanner:
    """自研安全检测与清理（纯 Win32 API）"""

    # ---------- 恶意进程 ----------
    def scan_processes(self) -> List[dict]:
        """枚举进程并按特征库匹配，返回 [{'pid','name','path'}]。

        进程名（Name）与可执行路径文件名（ExecutablePath）任一命中特征库即告警：
        恶意软件常伪装进程名（PEB 篡改），但可执行路径往往暴露矿机/木马文件名。
        """
        all_procs = _enum_processes()
        if not all_procs:
            return []

        out = []
        pending = []
        for p in all_procs:
            name = (p["name"] or "").lower()
            if self._is_malicious_name(name):
                out.append({"pid": p["pid"], "name": p["name"], "path": ""})
            else:
                pending.append(p)

        # 其余进程取路径匹配（并行加速，进程伪装后路径暴露特征）
        if pending:
            with ThreadPoolExecutor(max_workers=8) as pool:
                for p, path in zip(pending, pool.map(_process_path, [q["pid"] for q in pending])):
                    if self._malicious_path(path):
                        out.append({"pid": p["pid"], "name": p["name"], "path": path})

        return [e for e in out if self._not_system(e["path"] or e["name"])]

    @staticmethod
    def _is_malicious_name(name: str) -> bool:
        return name.replace(".exe", "").strip() in _MALICIOUS_PROCESS_NAMES

    @staticmethod
    def _malicious_path(path: str) -> bool:
        """匹配可执行路径文件名（进程名伪装后路径暴露特征）"""
        if not path:
            return False
        base = os.path.basename(path).lower().replace(".exe", "").strip()
        return base in _MALICIOUS_PROCESS_NAMES

    @staticmethod
    def _not_system(path: str) -> bool:
        if not path:
            return True
        try:
            parts = Path(path).parts
        except Exception:
            return True
        return not any(p in _SYSTEM_DIRS for p in (x.lower() for x in parts))

    # ---------- 恶意启动项 ----------
    def scan_startup(self) -> List[dict]:
        """扫描注册表 Run/RunOnce 与启动文件夹，返回 [{'where','name','command'}]"""
        found: List[dict] = []

        def _check_command(where: str, name: str, command: str):
            if not command:
                return
            cmd_lower = command.lower()
            if any(m in cmd_lower for m in _MALICIOUS_STARTUP_MARKERS):
                found.append({"where": where, "name": name, "command": command})

        for hive, key_path in _STARTUP_REG_KEYS:
            try:
                with winreg.OpenKey(hive, key_path) as k:
                    i = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(k, i)
                        except OSError:
                            break
                        i += 1
                        _check_command(key_path, name, value)
            except OSError:
                continue

        for base in (Path.home(), Path(r"C:\Users\Public")):
            startup = base / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
            if startup.is_dir():
                for lnk in startup.glob("*.lnk"):
                    _check_command(str(startup), lnk.stem, lnk.stem)
        return found

    def _remove_startup(self, entry: dict) -> bool:
        """删除恶意启动项（注册表值 / 快捷方式）"""
        for hive, key_path in _STARTUP_REG_KEYS:
            try:
                with winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE) as k:
                    try:
                        winreg.DeleteValue(k, entry["name"])
                        return True
                    except OSError:
                        continue
            except OSError:
                continue
        for base in (Path.home(), Path(r"C:\Users\Public")):
            p = base / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{entry['name']}.lnk"
            if p.exists():
                try:
                    p.unlink()
                    return True
                except OSError:
                    continue
        return False

    # ---------- 网络防护检查 ----------
    def check_network(self) -> dict:
        """检查监听端口暴露与防火墙启用状态"""
        exposed = sorted(p for p in _listening_ports() if p in _HIGH_RISK_PORTS)
        fw_off = _firewall_off_profiles()
        return {
            "firewall_off": fw_off,
            "high_risk_listening": exposed,
            "risk": bool(fw_off) or bool(exposed),
        }

    # ---------- 组合扫描 ----------
    def sweep(self, include_network: bool = False) -> dict:
        """一次完整巡检：检测恶意进程/启动项并自动清理；可选网络检查"""
        summary = {
            "killed": [],      # 已结束的恶意进程
            "removed": [],     # 已删除的恶意启动项
            "failed": [],      # 检测到但清理失败（仍需通知用户）
            "network": None,
            "risk": False,
        }
        _enable_debug_privilege()

        for p in self.scan_processes():
            if _terminate_process(p["pid"]):
                summary["killed"].append(f"{p['name']} (PID {p['pid']})")
            else:
                summary["failed"].append(f"进程 {p['name']} (PID {p['pid']}) 清理失败")

        for s in self.scan_startup():
            if self._remove_startup(s):
                summary["removed"].append(f"{s['where']} → {s['name']}")
            else:
                summary["failed"].append(f"启动项 {s['name']} 清理失败")

        if include_network:
            net = self.check_network()
            summary["network"] = net
            summary["risk"] = summary["risk"] or net["risk"]

        return summary
