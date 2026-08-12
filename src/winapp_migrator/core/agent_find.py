"""快速查找 App / 文件（优化：一次扫描建立索引缓存 + 并行遍历 + 提前终止）

- find_app：扫描开始菜单快捷方式 + 注册表 App Paths，名称模糊匹配，秒查（带缓存 TTL 1 小时）
- search_files：在用户目录并行遍历文件名模糊匹配，找到足够结果立即停止
"""

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import winreg

_CACHE_TTL = 3600          # 应用索引缓存有效期（秒）
_CACHE_FILE = Path.home() / ".winapp_migrator" / "agent" / "apps_cache.json"
_cache = {"apps": [], "ts": 0.0}
_lock = threading.Lock()

# 未出现在快捷方式/注册表时的兜底常见应用（系统自带）
_COMMON_APPS = {
    "notepad": r"C:\Windows\System32\notepad.exe",
    "记事本": r"C:\Windows\System32\notepad.exe",
    "calc": r"C:\Windows\System32\calc.exe",
    "计算器": r"C:\Windows\System32\calc.exe",
    "cmd": r"C:\Windows\System32\cmd.exe",
    "命令提示符": r"C:\Windows\System32\cmd.exe",
    "powershell": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    "explorer": r"C:\Windows\explorer.exe",
    "资源管理器": r"C:\Windows\explorer.exe",
    "control": r"C:\Windows\System32\control.exe",
    "控制面板": r"C:\Windows\System32\control.exe",
}


def _norm(s: str) -> str:
    """归一化：小写 + 去掉空格/连字符/下划线/点"""
    return re.sub(r"[\s\-_\.]+", "", str(s or "").lower())


def _start_menu_dirs() -> list:
    dirs = []
    pd = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    dirs.append(Path(pd) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    ad = os.environ.get("APPDATA", "")
    if ad:
        dirs.append(Path(ad) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return [d for d in dirs if d.is_dir()]


def _desktop_dirs() -> list:
    dirs = []
    ud = os.environ.get("USERPROFILE", "")
    if ud:
        dirs += [Path(ud) / "Desktop", Path(ud) / "桌面"]
    pub = os.environ.get("PUBLIC", r"C:\Users\Public")
    dirs.append(Path(pub) / "Desktop")
    return [d for d in dirs if d.is_dir()]


def _lnk_entries() -> list:
    """扫描开始菜单与桌面快捷方式，返回 [{"name","path","kind":"lnk"}]"""
    out, seen = [], set()
    for base in _start_menu_dirs() + _desktop_dirs():
        try:
            for root, _dirs, files in os.walk(base):
                for f in files:
                    if not f.lower().endswith(".lnk"):
                        continue
                    p = os.path.join(root, f)
                    if p in seen:
                        continue
                    seen.add(p)
                    out.append({"name": Path(f).stem, "path": p, "kind": "lnk"})
        except OSError:
            continue
    return out


def _app_paths_entries() -> list:
    """注册表 App Paths：返回 [{"name","path","kind":"exe"}]"""
    out = []
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
    ]
    for hive, sub in roots:
        try:
            with winreg.OpenKey(hive, sub) as k:
                i = 0
                while True:
                    try:
                        key_name = winreg.EnumKey(k, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(k, key_name) as kk:
                            exe, _ = winreg.QueryValueEx(kk, None)
                    except OSError:
                        exe = None
                    if not exe:
                        continue
                    out.append({"name": Path(key_name).stem, "path": exe, "kind": "exe"})
        except OSError:
            continue
    return out


def _load_app_index() -> list:
    """应用索引：内存缓存 → 文件缓存 → 重建（TTL 1 小时，秒查）"""
    now = time.time()
    with _lock:
        if _cache["apps"] and now - _cache["ts"] < _CACHE_TTL:
            return _cache["apps"]
    if _CACHE_FILE.exists():
        try:
            data = json.loads(_CACHE_FILE.read_text("utf-8"))
            if data.get("apps") and data.get("ts", 0) + _CACHE_TTL > now:
                with _lock:
                    _cache["apps"], _cache["ts"] = data["apps"], data["ts"]
                return _cache["apps"]
        except Exception:
            pass
    apps = _lnk_entries() + _app_paths_entries()
    with _lock:
        _cache["apps"], _cache["ts"] = apps, now
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps({"apps": apps, "ts": now},
                                          ensure_ascii=False, indent=1), "utf-8")
    except OSError:
        pass
    return apps


def find_app(query: str, limit: int = 10) -> str:
    """模糊查找应用，返回可启动路径候选（名称 → 路径）"""
    q = _norm(query)
    if not q:
        return "（缺少应用名）"

    def score(a):
        n = _norm(a["name"])
        if n == q:
            return 0
        if q in n:
            return 1
        if n in q:
            return 2
        return 9

    hits = sorted((a for a in _load_app_index() if score(a) < 9),
                  key=score)[:max(1, int(limit))]
    if hits:
        lines = [f"{i + 1}. {a['name']} → {a['path']}（{a['kind']}）"
                 for i, a in enumerate(hits)]
        return "找到应用：\n" + "\n".join(lines)
    # 兜底：系统常见应用
    fallback = [{"name": k, "path": v} for k, v in _COMMON_APPS.items() if q in _norm(k)]
    if fallback:
        return "找到应用：\n" + "\n".join(f"{i + 1}. {a['name']} → {a['path']}"
                                           for i, a in enumerate(fallback))
    return f"未找到与「{query}」匹配的应用，可尝试用 start_menu 目录名称重试"


def search_files(query: str, folder: str = "", limit: int = 30) -> str:
    """并行遍历用户目录模糊查找文件（找到足够结果立即停止）"""
    q = _norm(query)
    if not q:
        return "（缺少文件名关键字）"
    roots = []
    if folder:
        p = Path(os.path.expandvars(os.path.expanduser(folder)))
        if p.is_dir():
            roots = [p]
    if not roots:
        home = Path.home()
        roots = [home / "Desktop", home / "桌面", home / "Downloads", home / "下载",
                 home / "Documents", home / "文档"]
        roots = [d for d in roots if d.is_dir()]
    if not roots:
        roots = [Path.home()]

    results, done = [], threading.Event()
    n_limit = max(1, int(limit))

    def walk_one(root):
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                if done.is_set():
                    return
                dirnames[:] = [d for d in dirnames
                               if not d.startswith(("$", "System Volume Information"))]
                for fn in filenames:
                    if done.is_set():
                        return
                    if q in _norm(fn):
                        results.append(os.path.join(dirpath, fn))
                        if len(results) >= n_limit:
                            done.set()
                            return
        except OSError:
            return

    with ThreadPoolExecutor(max_workers=min(len(roots), 8)) as ex:
        futs = [ex.submit(walk_one, r) for r in roots]
        for _ in as_completed(futs):
            if done.is_set():
                break
    lines = results[:n_limit]
    if not lines:
        return f"未找到包含「{query}」的文件"
    return f"找到 {len(lines)} 个文件：\n" + "\n".join(lines)
