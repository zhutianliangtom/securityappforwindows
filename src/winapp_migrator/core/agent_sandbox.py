"""Agent 沙盒与白名单：工具调用/命令执行前的安全评估

- 命令白名单：只读/诊断类命令与普通文件操作（新建/复制/移动/删除）默认放行
- 危险黑名单：递归/强制删除、格式化/关机/注册表/服务/权限等高风险操作直接拒绝
- 路径限制：文件类操作拒绝系统关键目录（Windows/Program Files 等），其余路径放行
- 评估结果分级：safe（放行）/ risky（需用户确认）/ dangerous（拒绝）
"""

import os
from pathlib import Path

# 白名单：只读/诊断类命令 + 普通文件操作（默认放行）
SAFE_COMMANDS = {
    "ping", "ipconfig", "tasklist", "netstat", "systeminfo", "whoami", "ver",
    "dir", "type", "echo", "hostname", "tree", "where", "findstr", "path",
    "set", "route", "arp", "nslookup", "tracert", "getmac",
    # 普通文件操作：新建/复制/移动/重命名/删除单文件或空目录
    "mkdir", "md", "copy", "move", "ren", "rename", "del", "erase", "rd", "rmdir",
}

# 危险关键词（拒绝）
DANGEROUS_KW = [
    "format", "diskpart", "bcdedit", "shutdown", "restart", "taskkill /f",
    "reg delete", "reg add", "sc delete", "net user", "net localgroup",
    "takeown", "icacls", "cacls", "attrib /s /d", "rd /s", "rmdir /s",
    "del /s", "del /f", "del /q", "rd /q", "rmdir /q",
    "move /y", "xcopy", "robocopy /e /purge",
    "powershell -enc", "powershell -e", "certutil -urlcache", "bitsadmin",
    "mshta", "wscript", "cscript", "vssadmin delete", "wmic process",
]

# 系统关键目录：禁止写入/修改，防止破坏系统
def _system_dirs() -> list:
    drive = os.environ.get("SystemDrive", "C:")
    root = Path(drive + "\\")   # 盘符根（C:\），避免 "C:xxx" 相对路径
    windir = os.environ.get("WINDIR") or str(root / "Windows")
    cands = [
        root / "Windows", root / "Program Files", root / "Program Files (x86)",
        root / "ProgramData", root / "PerfLogs", root / "System Volume Information",
        Path(windir), Path(windir) / "System32",
    ]
    return [d for d in cands if d.exists()]


def to_int(v) -> int:
    """健壮数值转换：容忍 LLM 返回的 '16, 980' 等字符串，取第一个数字"""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(",", " ").replace("，", " ").replace("px", "")
    for tok in s.split():
        try:
            return int(float(tok))
        except ValueError:
            continue
    return 0


def assess_command(cmd: str) -> tuple:
    """评估命令。返回 (level, reason)，level ∈ safe/risky/dangerous"""
    cmd = (cmd or "").strip()
    low = cmd.lower()
    if not low:
        return "risky", "空命令"
    # 危险优先
    for kw in DANGEROUS_KW:
        if kw in low:
            return "dangerous", f"命令含危险操作: {kw}"
    first = low.split()[0]
    base = os.path.basename(first.replace("\\", "/"))
    if base in SAFE_COMMANDS:
        return "safe", ""
    # 含重定向/管道/复杂脚本视为 risky
    if any(s in low for s in ("|", ">", "&", "&&", ";")):
        return "risky", "命令含管道/重定向，非白名单"
    return "risky", "非白名单命令"


def assess_path(path: str) -> tuple:
    """评估文件路径：拒绝系统关键目录，其余路径放行。返回 (level, reason)"""
    try:
        p = Path(os.path.abspath(os.path.expandvars(os.path.expanduser(path))))
    except Exception:
        return "dangerous", "路径解析失败"
    for d in _system_dirs():
        try:
            p.relative_to(d)
            return "dangerous", f"系统关键目录禁止操作: {d}"
        except ValueError:
            continue
    return "safe", ""


def assess_tool(name: str, args: dict) -> tuple:
    """工具级评估：坐标越界、命令/路径分级。返回 (level, reason)"""
    if name == "run_command":
        return assess_command(str(args.get("command", "")))
    if name in ("move_mouse", "click", "drag"):
        import ctypes
        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
        coords = [(args.get("x"), args.get("y"))]
        if name == "drag":
            coords += [(args.get("x2"), args.get("y2"))]
        for x, y in coords:
            if x is None or y is None:
                return "risky", "缺少坐标参数"
            if not (0 <= to_int(x) < w and 0 <= to_int(y) < h):
                return "risky", f"坐标越界 ({x},{y})，屏幕 {w}x{h}"
    if name == "click_text" and not str(args.get("text", "")).strip():
        return "risky", "缺少要点击的文字参数"
    return "safe", ""
