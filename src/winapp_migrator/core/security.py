"""静默安全模块：后台监控恶意进程/启动项、网络风险，Defender 快速扫描

全部基于真实系统 API：
- 进程枚举：Get-CimInstance Win32_Process（含可执行路径）
- 启动项：注册表 Run/RunOnce（HKLM/HKCU）+ 启动文件夹
- 网络：Get-NetFirewallProfile + netstat 监听端口
- 恶意软件扫描：Windows Defender MpCmdRun.exe -Scan -ScanType 2

特征库采用保守白名单式规则，排除系统目录，避免误杀正常软件。
"""

import base64
import subprocess
import winreg
from pathlib import Path
from typing import List, Optional

from winapp_migrator.utils.helpers import setup_logging

logger = setup_logging()

# ------------------------------------------------------------
# 恶意特征库（保守规则：仅收录知名恶意软件名，避免误杀）
# ------------------------------------------------------------
# 恶意进程名（小写，不含扩展名）
_MALICIOUS_PROCESS_NAMES = frozenset({
    # 挖矿木马
    "xmrig", "minerd", "minerd64", "cryptominer", "cpuminer",
    "lolminer", "nbminer", "phoenixminer", "claymore", "wildrig",
    # 远控木马 / 蠕虫
    "njrat", "njw0rm", "darkcomet", "poisonivy", "gh0st", "ghostrat",
    "shellex", "winrar_setup", "srvany", "tcpviewer",
    # 键盘记录 / 盗号
    "keylogger", "qakbot", "emotet", "trickbot", "botnet",
})

# 恶意进程名 + 必须出现在非系统目录（防止误杀同名正常组件）
_SYSTEM_DIRS = frozenset({
    "windows", "system32", "syswow64", "program files", "program files (x86)",
})

# 启动项命令中的恶意特征（下载器/临时目录随机名 exe 等）
_MALICIOUS_STARTUP_MARKERS = (
    "xmrig", "minerd", "njrat", "darkcomet", "poisonivy",
    "\\temp\\", "\\tmp\\",
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


def _ps_run(script: str, timeout: int = 90) -> list:
    """以 UTF-16LE base64 静默执行 PowerShell 脚本，返回输出行（真实 API）"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-EncodedCommand", encoded],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=timeout,
        )
        return [(result.stdout or b"").decode("utf-8", "replace")] or []
    except Exception as e:
        logger.warning("PowerShell 执行失败: %s", e)
        return []


class SecurityScanner:
    """安全检测与清理"""

    # ---------- 恶意进程 ----------
    def scan_processes(self) -> List[dict]:
        """枚举进程并按特征库匹配，返回 [{'pid','name','path'}]（真实 CIM API）"""
        script = r'''
$procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -or $_.ExecutablePath } |
    ForEach-Object { $_.ProcessId.ToString() + "|" + $_.Name + "|" + $_.ExecutablePath })
$procs
'''
        lines = _ps_run(script)
        out = []
        for line in lines:
            for entry in line.splitlines():
                parts = entry.strip().split("|")
                if len(parts) < 2 or not parts[0].isdigit():
                    continue
                pid = int(parts[0])
                name = (parts[1] or "").lower()
                path = parts[2] if len(parts) > 2 else ""
                if self._is_malicious_name(name) and self._not_system(path or name):
                    out.append({"pid": pid, "name": parts[1], "path": path})
        return out

    @staticmethod
    def _is_malicious_name(name: str) -> bool:
        return name.replace(".exe", "").strip() in _MALICIOUS_PROCESS_NAMES

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

        # 启动文件夹（用户 + 公共）
        for base in (Path.home(), Path(r"C:\Users\Public")):
            startup = base / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
            if startup.is_dir():
                for lnk in startup.glob("*.lnk"):
                    _check_command(str(startup), lnk.stem, lnk.stem)
        return found

    def _kill_process(self, entry: dict) -> bool:
        """结束恶意进程：taskkill /F /T（真实 API）"""
        try:
            r = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(entry["pid"])],
                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30,
            )
            return r.returncode == 0
        except Exception:
            return False

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
        # 启动文件夹快捷方式
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
        """检查防火墙启用状态与高危端口暴露情况"""
        fw_lines = _ps_run(
            r"Get-NetFirewallProfile | ForEach-Object { $_.Name + '=' + $_.Enabled }", timeout=60
        )
        profiles = {}
        for line in fw_lines:
            for item in line.splitlines():
                if "=" in item:
                    k, v = item.split("=", 1)
                    profiles[k.strip()] = v.strip()

        # netstat 解析监听端口
        listening = set()
        try:
            ns = subprocess.run(
                ["netstat", "-ano"], capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=30,
            )
            out = (ns.stdout or b"").decode("utf-8", "replace")
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1].upper() == "LISTENING":
                    addr = parts[0].rsplit(":", 1)
                    if len(addr) == 2 and addr[1].isdigit():
                        listening.add(int(addr[1]))
        except Exception:
            pass

        exposed = sorted(p for p in listening if p in _HIGH_RISK_PORTS)
        fw_off = [k for k, v in profiles.items() if v.lower() == "false"]
        return {
            "firewall": profiles,
            "firewall_off": fw_off,
            "high_risk_listening": exposed,
            "risk": bool(fw_off) or bool(exposed),
        }

    # ---------- Defender 快速扫描 ----------
    def run_defender_quick_scan(self) -> dict:
        """调用 Windows Defender 快速扫描（MpCmdRun -Scan -ScanType 2），返回结果"""
        candidates = [
            Path(r"C:\Program Files\Windows Defender\MpCmdRun.exe"),
            Path(r"C:\Program Files (x86)\Windows Defender\MpCmdRun.exe"),
        ]
        mp = next((p for p in candidates if p.is_file()), None)
        if mp is None:
            return {"ok": False, "message": "未找到 Windows Defender"}
        try:
            r = subprocess.run(
                [str(mp), "-Scan", "-ScanType", "2"],
                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=600,
            )
            # 退出码：0=未发现威胁，2=发现并已处理威胁
            if r.returncode == 0:
                return {"ok": True, "threats": 0, "message": "未发现威胁"}
            if r.returncode == 2:
                return {"ok": True, "threats": 1, "message": "发现威胁，Defender 已处理"}
            return {"ok": True, "threats": -1, "message": f"扫描完成（退出码 {r.returncode}）"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "message": "扫描超时"}
        except Exception as e:
            return {"ok": False, "message": f"扫描失败: {e}"}

    # ---------- 组合扫描 ----------
    def sweep(self, include_network: bool = False, include_defender: bool = False) -> dict:
        """一次完整巡检：检测恶意进程/启动项并自动清理；可选网络与 Defender 检查"""
        summary = {
            "killed": [],      # 已结束的恶意进程
            "removed": [],     # 已删除的恶意启动项
            "failed": [],      # 检测到但清理失败（仍需通知用户）
            "network": None,
            "defender": None,
            "risk": False,
        }

        for p in self.scan_processes():
            if self._kill_process(p):
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

        if include_defender:
            summary["defender"] = self.run_defender_quick_scan()

        return summary
