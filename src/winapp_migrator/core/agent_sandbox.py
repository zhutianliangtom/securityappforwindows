"""Agent 沙盒与白名单：工具调用/命令执行前的安全评估

- 命令白名单：只读/诊断类命令与普通文件操作（新建/复制/移动/删除）默认放行
- 危险黑名单：递归/强制删除、格式化/关机/注册表/服务/权限等高风险操作直接拒绝
- 路径限制：读/写放行系统目录（允许安装/更新到 Program Files），仅禁止删除系统关键目录内的内容
- 评估结果分级：safe（放行）/ risky（需用户确认）/ dangerous（拒绝）
"""

import os
import re as _re
from pathlib import Path

# 白名单：只读/诊断类命令 + 普通文件操作（默认放行）
SAFE_COMMANDS = {
    "ping", "ipconfig", "tasklist", "netstat", "systeminfo", "whoami", "ver",
    "dir", "type", "echo", "hostname", "tree", "where", "findstr", "path",
    "set", "route", "arp", "nslookup", "tracert", "getmac",
    # 普通文件操作：新建/复制/移动/重命名/删除单文件或空目录
    "mkdir", "md", "copy", "move", "ren", "rename", "del", "erase", "rd", "rmdir",
    # curl：HTTP 请求/下载（管道/重定向等组合仍会降级为 risky 需确认）
    "curl",
    # git：常规提交/推送/拉取/查看（危险子命令由 DANGEROUS_KW 先行拒绝）
    "git",
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
    # git 危险操作：丢弃改动 / 强制覆盖 / 强制删除 / 重写历史
    "git reset --hard", "git clean", "git push --force", "git push -f",
    "git push --delete", "git branch -d", "git checkout --", "git restore .",
    "git filter-branch",
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


# 系统关键进程：禁止 taskkill（防止杀系统进程导致系统崩溃/锁屏/桌面重启）
_SYSTEM_PROCS = frozenset({
    "system", "system idle process", "registry", "smss", "csrss", "wininit",
    "winlogon", "services", "lsass", "lsm", "svchost", "dwm", "explorer",
    "conhost", "spoolsv", "taskhost", "taskhostw", "fontdrvhost",
    "searchindexer", "wmiprvse", "runtimebroker", "sihost",
    "shellexperiencehost", "textinputhost", "startmenuexperiencehost",
    "ctfmon", "audiodg", "securityhealthservice", "msmpeng",
})

# 卸载/清理流程可豁免的危险词：目标安全（非系统进程/非系统目录）时降级为 risky
# （ask/edit 弹确认、YOLO 放行），目标为系统对象时仍按 dangerous 硬拒绝。
# 注册表/服务删除（reg delete / sc delete）等高风险操作不豁免，引导走 uninstall_app 工具。
_EXEMPT_KW = frozenset({
    "taskkill /f", "rd /s", "rmdir /s", "del /s", "del /f", "del /q",
    "rd /q", "rmdir /q", "move /y",
})


def _exempt_uninstall_op(low: str, kw: str) -> bool:
    """豁免判断：taskkill /f 目标必须是非系统进程；
    强制/递归删除与覆盖移动（rd /s、del /f、move /y 等）目标必须不含系统关键目录。"""
    if kw == "taskkill /f":
        m = _re.search(r"/im\s+([\w\-.]+)", low)
        proc = m.group(1).lower().rstrip(".exe") if m else ""
        return bool(proc and proc not in _SYSTEM_PROCS)
    flat = low.replace("\\", "/").replace('"', "").replace("'", "")
    for d in _system_dirs():
        if str(d).lower().replace("\\", "/") in flat:
            return False
    return True


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


def _custom_safe() -> set:
    """用户自定义 bash 白名单命令（settings.json custom_safe_commands，追加放行）"""
    try:
        from winapp_migrator.core import agent_skills
        s = agent_skills.load_settings()
        return {str(c).strip().lower() for c in (s.get("custom_safe_commands") or [])
                if str(c).strip()}
    except Exception:
        return set()


def assess_command(cmd: str) -> tuple:
    """评估命令。返回 (level, reason)，level ∈ safe/risky/dangerous"""
    cmd = (cmd or "").strip()
    low = cmd.lower()
    if not low:
        return "risky", "空命令"
    first_tok = low.split()[0]
    del_base = os.path.basename(first_tok.replace("\\", "/"))
    is_curl = del_base == "curl"
    # 剥离 URL token：URL 只是访问目标，避免 format/shutdown 等词及 & 查询参数误伤
    # （如 curl https://x/api/format-report、curl "…?a=1&b=2" 均属正常请求）
    low_nourl = _re.sub(r'https?://[^\s"\'<>]+', "URL", low)
    if is_curl:
        # curl 的 URL/请求头/表单数据（-d/-H/--data-urlencode 等）里的任意字符串
        # 不构成当地危险操作（curl 无删除/格式化能力），跳过危险词子串匹配；
        # 危险面仅在：管道执行、写入系统目录
        if _re.search(r"\|\s*(sh|bash|cmd(\.exe)?|powershell|pwsh|python(3)?|perl|ruby)\b",
                      low_nourl):
            return "dangerous", "禁止 curl 管道执行（下载即执行高危模式）"
    else:
        # 危险优先；卸载/清理类命令（杀应用进程、删非系统目录）在目标安全时
        # 降级为 risky（ask/edit 弹确认、YOLO 放行），其余危险词硬拒绝
        for kw in DANGEROUS_KW:
            if kw in low_nourl:
                if kw in _EXEMPT_KW and _exempt_uninstall_op(low, kw):
                    return "risky", f"卸载/清理类命令: {kw}（目标非系统，需确认）"
                return "dangerous", f"命令含危险操作: {kw}"
    # 删除命令 + 目标位于系统关键目录 → 拒绝（如 del C:\Program Files\xxx）
    if del_base in ("del", "erase", "rd", "rmdir", "rm", "deltree"):
        flat = low.replace("\\", "/").replace('"', "")
        for d in _system_dirs():
            if str(d).lower().replace("\\", "/") in flat:
                return "dangerous", f"禁止删除系统关键目录: {d}"
    # curl 下载到系统关键目录 → 拒绝（防止覆盖系统文件）
    if is_curl:
        flat = low.replace("\\", "/").replace('"', "")
        for d in _system_dirs():
            if str(d).lower().replace("\\", "/") in flat:
                return "dangerous", f"禁止写入系统关键目录: {d}"
    # 含管道/重定向/多命令串联 → risky：即使首命令在白名单
    # （如 `git add .; git commit`、`echo hi > file`），避免绕过单命令白名单
    if any(s in low_nourl for s in ("|", ">", "&", "&&", ";")):
        return "risky", "命令含管道/重定向/多命令，非单条白名单命令"
    base = del_base
    if base in SAFE_COMMANDS or base in _custom_safe():
        return "safe", ""
    return "risky", "非白名单命令"


def assess_path(path: str, operation: str = "write") -> tuple:
    """评估文件路径（operation ∈ read/write/delete）。

    读/写放行系统目录：安装/更新到 Program Files、读取系统配置等属正常需求，
    不再一刀切拒绝（YOLO/确认模式均可执行）。
    删除（delete）系统关键目录内的内容仍一律拒绝，守住安全底线。
    返回 (level, reason)
    """
    try:
        p = Path(os.path.abspath(os.path.expandvars(os.path.expanduser(path))))
    except Exception:
        return "dangerous", "路径解析失败"
    if operation == "delete":
        for d in _system_dirs():
            try:
                p.relative_to(d)
                return "dangerous", f"系统关键目录禁止删除: {d}"
            except ValueError:
                continue
    return "safe", ""


def assess_tool(name: str, args: dict) -> tuple:
    """工具级评估：命令/路径分级。返回 (level, reason)"""
    if name == "run_command":
        return assess_command(str(args.get("command", "")))
    # 重量级操作：卸载/迁移/内存优化涉及删改系统与应用，需用户确认
    if name in ("uninstall_app", "migrate_app", "optimize_memory"):
        return "risky", f"{name} 为重量级操作，需用户确认"
    return "safe", ""
