"""Agent 沙盒与白名单：工具调用/命令执行前的安全评估

- 命令白名单：只读/诊断类命令默认放行
- 危险黑名单：删除/格式化/关机/注册表/服务/权限等高风险命令直接拒绝
- 路径限制：文件类操作仅允许用户目录（桌面/下载/文档/临时）
- 评估结果分级：safe（放行）/ risky（需用户确认）/ dangerous（拒绝）
"""

import os
from pathlib import Path

# 白名单：只读/诊断类命令（默认放行）
SAFE_COMMANDS = {
    "ping", "ipconfig", "tasklist", "netstat", "systeminfo", "whoami", "ver",
    "dir", "type", "echo", "hostname", "tree", "where", "findstr", "path",
    "set", "route", "arp", "nslookup", "tracert", "getmac",
}

# 危险关键词（拒绝）
DANGEROUS_KW = [
    "format", "diskpart", "bcdedit", "shutdown", "restart", "taskkill /f",
    "reg delete", "reg add", "sc delete", "net user", "net localgroup",
    "takeown", "icacls", "cacls", "attrib /s /d", "rd /s", "rmdir /s",
    "del /s", "del /f", "move /y", "xcopy", "robocopy /e /purge",
    "powershell -enc", "powershell -e", "certutil -urlcache", "bitsadmin",
    "mshta", "wscript", "cscript", "vssadmin delete", "wmic process",
]

# 允许访问的目录（用户数据目录），其余拒绝
def _user_dirs() -> list:
    home = Path.home()
    dirs = {home, home / "Desktop", home / "Downloads", home / "Documents",
            home / "桌面", home / "下载", home / "文档"}
    tmp = os.environ.get("TEMP") or "/tmp"
    dirs.add(Path(tmp))
    return [d for d in dirs if d.exists()]


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
    """评估文件路径。返回 (level, reason)"""
    try:
        p = Path(os.path.abspath(os.path.expandvars(os.path.expanduser(path))))
    except Exception:
        return "dangerous", "路径解析失败"
    allowed = _user_dirs()
    for d in allowed:
        try:
            p.relative_to(d)
            return "safe", ""
        except ValueError:
            continue
    return "dangerous", f"路径不在允许目录内: {path}"


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
    return "safe", ""
