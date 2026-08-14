"""Agent 内置工具：注册表（LLM function calling schema）+ 执行（接入沙盒评估）

执行结果统一为 {"text": str, "images": [data_url]}：
- text 作为 tool 消息文本返回给模型
- images 中的截图 data URL 由引擎并入下一轮视觉输入（AI 主动截图时作为视觉输入）
"""

import html as _html
import itertools
import json
import locale
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from winapp_migrator.core import agent_sandbox
from winapp_migrator.core import agent_find
from winapp_migrator.core import agent_browser
from winapp_migrator.core import agent_tts

# 本地记忆文件（AI 长期记忆，markdown 格式）
MEMORY_FILE = Path.home() / ".winapp_migrator" / "agent" / "memory.md"

# ------------------------------------------------------------
# 工作目录（面板"选择工作目录"设置，QSettings 持久化）：
# 查找/创建/修改/删除/读取文件与运行命令优先在此目录执行
# ------------------------------------------------------------
WORKDIR: str = ""


def set_workdir(path: str):
    global WORKDIR
    WORKDIR = (path or "").strip()


def get_workdir() -> str:
    return WORKDIR


def _resolve(path: str) -> Path:
    """路径解析：空 → 工作目录；相对 → 工作目录/相对路径；绝对 → 原样"""
    raw = os.path.expandvars(os.path.expanduser((path or "").strip()))
    if not raw:
        return Path(WORKDIR) if WORKDIR else Path.cwd()
    p = Path(raw)
    if p.is_absolute():
        return p
    return (Path(WORKDIR) / p) if WORKDIR else p

# ------------------------------------------------------------
# 后台命令注册表：run_command 超时未结束（未开强制退出）的命令转入后台，
# AI 可用 check_command 轮询进度。reader 线程持续排空管道，防止缓冲填满阻塞进程。
# ------------------------------------------------------------
_running_cmds: dict = {}          # cmd_id -> 记录
_cmd_seq = itertools.count(1)     # 自增命令编号
_CREATE_NO_WINDOW = 0x08000000


def _console_encoding() -> str:
    """控制台程序输出编码：GetOEMCP 获取 cmd 实际代码页（中文系统 cp936），
    避免 Python UTF-8 模式下按 utf-8 解码 GBK 输出导致乱码/解码异常"""
    try:
        import ctypes
        cp = ctypes.windll.kernel32.GetOEMCP()
        if cp:
            return f"cp{cp}"
    except Exception:
        pass
    return locale.getpreferredencoding(False)


def _kill_process_tree(pid: int) -> bool:
    """taskkill /T 结束整个进程树（shell 启动的进程常有子进程）"""
    try:
        subprocess.run(f"taskkill /PID {pid} /T /F", shell=True,
                       capture_output=True, text=True, timeout=15)
        return True
    except Exception:
        return False


def _decode_robust(raw: bytes) -> str:
    """子进程/文件字节 → 文本：UTF-8 优先（现代工具主流），失败回退控制台 OEM 代码页
    （中文系统 GBK），避免 UTF-8 输出被按 GBK 解码成乱码、或 GBK 输出解码崩溃"""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(_console_encoding(), errors="replace")


def _drain_pipe(pipe, lines: list, lock: threading.Lock):
    """后台线程逐行读取管道（二进制）并存入共享缓冲（防管道填满导致进程阻塞）"""
    try:
        for line in iter(pipe.readline, b""):
            with lock:
                lines.append(line)
    except Exception:
        pass
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def _collect(rec: dict) -> str:
    """汇总后台命令的已收集输出（stdout + stderr，完整返回）"""
    with rec["lock"]:
        out = _decode_robust(b"".join(rec["out"])).strip()
        err = _decode_robust(b"".join(rec["err"])).strip()
    text = out
    if err:
        text += f"\n[stderr] {err}" if text else f"[stderr] {err}"
    return text

# ---------- 工具定义（LLM 可见） ----------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_app",
            "description": "快速查找已安装应用（扫描开始菜单/桌面快捷方式/注册表，秒查带缓存），"
                           "返回可启动的完整路径候选。当用户要打开某个应用而你不确定其确切名称/"
                           "路径时使用，无需逐层截图找图标。",
            "parameters": {"type": "object",
                           "properties": {
                               "query": {"type": "string", "description": "应用名称，如 微信/记事本/chrome"},
                               "limit": {"type": "integer", "description": "最多返回候选数，默认 10"}},
                           "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "在用户目录快速模糊查找文件（并行遍历，找到即返回），"
                           "返回匹配的文件完整路径列表。当需要定位某个文件而不知道确切路径时使用。",
            "parameters": {"type": "object",
                           "properties": {
                               "query": {"type": "string", "description": "文件名关键字，如 报告/photo/setup"},
                               "folder": {"type": "string", "description": "限定搜索目录（可选，默认用户常用目录）"},
                               "limit": {"type": "integer", "description": "最多返回条数，默认 30"}},
                           "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "当用户需求不明确、缺少关键信息（如目标文件路径、目标对象、期望结果）时，"
                           "用此工具向用户提问并等待回答。禁止在信息不足时猜测执行，必须先提问。",
            "parameters": {"type": "object",
                           "properties": {
                               "question": {"type": "string", "description": "要问用户的问题（简洁明确）"},
                               "options": {"type": "array", "items": {"type": "string"},
                                           "description": "建议选项，用户可直接选择（可为空数组表示自由回答）"},
                               "multi_select": {"type": "boolean",
                                                "description": "是否允许多选，默认 false"}},
                           "required": ["question"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "在系统终端执行命令（受沙盒约束）。危险命令（删除/格式化/关机等）会被拒绝。"
                           "默认等待 wait 秒（默认 5）：期间持续收集输出；若 wait 秒内未完成，"
                           "force_quit=true 则强制结束进程树，false 则转入后台运行，返回命令 ID，"
                           "之后用 check_command 轮询进度。启动 GUI 应用建议 wait=1。",
            "parameters": {"type": "object",
                           "properties": {
                               "command": {"type": "string", "description": "要执行的命令"},
                               "wait": {"type": "integer",
                                        "description": "等待秒数，默认 5。长任务可调大以等待更多输出"},
                               "force_quit": {"type": "boolean",
                                              "description": "是否开启超时强制退出：wait 秒内未完成则强制结束进程树。"
                                                             "默认 false（转入后台运行，可轮询）。预计会长时间挂起/无输出的命令建议开启"}},
                           "required": ["command"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_command",
            "description": "查询后台运行命令的进度与最新输出（run_command 超时未结束且未开强制退出时转入后台的命令）。"
                           "返回是否仍在运行、已产生的输出；若已结束则返回最终输出与退出码。"
                           "不传 cmd_id 时列出全部后台命令。",
            "parameters": {"type": "object",
                           "properties": {
                               "cmd_id": {"type": "integer",
                                          "description": "后台命令 ID（run_command 返回的 id），不传则列出全部"}},
                           "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文本文件内容（最大 200KB）。",
            "parameters": {"type": "object",
                           "properties": {"path": {"type": "string"}},
                           "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "创建或覆盖写入文本文件（目录不存在自动创建，最大 500KB）。",
            "parameters": {"type": "object",
                           "properties": {"path": {"type": "string"},
                                          "content": {"type": "string"}},
                           "required": ["path", "content"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "编辑文件：把文件中的 old_text 精确替换为 new_text（仅替换第一处，最大 200KB）。",
            "parameters": {"type": "object",
                           "properties": {"path": {"type": "string"},
                                          "old_text": {"type": "string"},
                                          "new_text": {"type": "string"}},
                           "required": ["path", "old_text", "new_text"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "删除文件或空目录（工作目录优先）。删除系统关键目录内的内容仍被沙盒拒绝；"
                           "非空目录请用 run_command 精确处理。",
            "parameters": {"type": "object",
                           "properties": {"path": {"type": "string",
                                                   "description": "要删除的文件或空目录路径（相对路径基于工作目录）"}},
                           "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出目录内容（仅允许用户目录，最多 200 项，带 DIR/FILE 标记），用于探索文件结构。",
            "parameters": {"type": "object",
                           "properties": {"path": {"type": "string"}},
                           "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "把任务中的关键信息（用户偏好、重要结论、文件路径、约定等）追加保存到本地记忆文件 "
                           "memory.md（自动带时间戳，单条 ≤8000 字符）。值得长期记住的内容请主动保存。",
            "parameters": {"type": "object",
                           "properties": {"content": {"type": "string"}},
                           "required": ["content"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_memory",
            "description": "读取本地记忆文件 memory.md 的完整内容。开始新任务或需要回忆过往信息时，"
                           "由你自行决定是否调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ---------- 系统信息（原 MCP server 工具内置化） ----------
    {
        "type": "function",
        "function": {
            "name": "system_info",
            "description": "获取本机系统信息：主机名、系统版本（可区分 Win10/Win11）、CPU 核心数、物理内存、Python 版本。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "获取当前系统时间（YYYY-MM-DD HH:MM:SS）。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "env_var",
            "description": "读取指定环境变量的值（如 PATH、SystemRoot）。",
            "parameters": {"type": "object",
                           "properties": {"name": {"type": "string", "description": "环境变量名"}},
                           "required": ["name"]},
        },
    },
    # ---------- WinAppMigrator 能力内置化 ----------
    {
        "type": "function",
        "function": {
            "name": "optimize_memory",
            "description": "一键清理系统内存：终止可安全退出的后台进程、压缩工作集并清理内存。"
                           "ask/edit 模式执行前会请用户确认；YOLO 模式直接执行。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "uninstall_app",
            "description": "卸载已安装应用（优先调用应用自带卸载器，再清理数据目录/注册表/快捷方式）。"
                           "需要先扫描已安装应用并匹配名称；ask/edit 模式执行前会请用户确认，"
                           "YOLO 模式直接执行（仅系统关键目录/进程仍受保护）。",
            "parameters": {"type": "object",
                           "properties": {"name": {"type": "string", "description": "应用名称（支持模糊匹配）"}},
                           "required": ["name"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "migrate_app",
            "description": "把已安装应用迁移到其他盘符（移动主目录/数据目录并更新注册表、快捷方式）。"
                           "需要先扫描应用匹配名称；ask/edit 模式执行前会请用户确认，"
                           "YOLO 模式直接执行（仅系统关键目录仍受保护）。",
            "parameters": {"type": "object",
                           "properties": {
                               "name": {"type": "string", "description": "应用名称（支持模糊匹配）"},
                               "target": {"type": "string", "description": "目标路径，如 D:\\Apps\\微信"}},
                           "required": ["name", "target"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fast_download",
            "description": "多段并发高速下载文件到指定目录（自动探测文件名，支持断点续传）。",
            "parameters": {"type": "object",
                           "properties": {
                               "url": {"type": "string", "description": "下载地址"},
                               "dest_dir": {"type": "string",
                                            "description": "保存目录，留空用工作目录"}},
                           "required": ["url"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "联网请求指定 URL（网页 HTML / JSON 接口 / raw 文件 / REST API），返回响应文本。"
                           "默认 GET；可指定 method/headers/body 发起 POST/PUT/DELETE 等调用 API。"
                           "需要访问网络上的页面、接口或调用 API 时使用。",
            "parameters": {"type": "object",
                           "properties": {
                               "url": {"type": "string", "description": "http/https 地址"},
                               "method": {"type": "string",
                                          "description": "请求方法：GET/POST/PUT/DELETE/PATCH，默认 GET"},
                               "headers": {"type": "object",
                                           "description": "请求头字典，如 {\"Authorization\": \"Bearer xxx\"}"},
                               "body": {"type": "string",
                                        "description": "请求体（POST/PUT/PATCH 时使用），JSON 字符串或原始文本"},
                               "max_chars": {"type": "integer",
                                             "description": "返回内容最大字符数，默认 8000"}},
                           "required": ["url"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_open",
            "description": "启动独立浏览器实例（Edge/Chrome，独立持久用户目录+调试端口，与用户正在用的浏览器完全隔离，"
                           "不碰鼠标键盘、不影响用户其他操作）。登录态/cookie/token 会持久保存，"
                           "下次打开浏览器自动恢复、无需重复登录。浏览器任务（打开网页/登录/填表/抓取/自动操作网页）"
                           "第一步先 browser_open 启动，之后用 browser_navigate/browser_snapshot/browser_click/"
                           "browser_type/browser_eval/browser_html 完成操作，最后 browser_close 关闭。",
            "parameters": {"type": "object",
                           "properties": {
                               "engine": {"type": "string",
                                          "description": "（可选）优先使用 edge 或 chrome，留空自动找可用浏览器"},
                               "headless": {"type": "boolean",
                                            "description": "（可选）无头模式（不显示窗口），默认 false"}},
                           "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "在独立浏览器中打开网页（自动补全 http/https）。用 browser_open 启动后使用。",
            "parameters": {"type": "object",
                           "properties": {"url": {"type": "string",
                                                  "description": "要打开的网址，如 https://www.baidu.com"}},
                           "required": ["url"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_snapshot",
            "description": "截取独立浏览器当前页面并返回可交互元素语义清单 [id] (标签) 文字。"
                           "每步操作前/操作后先 browser_snapshot 看页面状态与元素，"
                           "点击/输入用 browser_click(id) / browser_type(text, id) 按编号精确操作，"
                           "系统解析 DOM 坐标派发输入，无需估算像素。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "在独立浏览器中点击元素。支持三种定位（任选其一）："
                           "① id=browser_snapshot 清单里的元素编号；② text=元素文字（按钮/链接/输入框/选项）；"
                           "③ selector=CSS 选择器精确定位（如 #submit / .btn-primary / form button）。"
                           "系统解析 DOM 坐标派发点击（含原生 click+合成事件兜底，兼容 React/Vue）。"
                           "点击后返回最新页面截图。",
            "parameters": {"type": "object",
                           "properties": {
                               "id": {"type": "integer",
                                      "description": "（推荐）browser_snapshot 清单里的元素编号 [id]"},
                               "text": {"type": "string",
                                        "description": "（推荐）目标元素文字，与 id/selector 三选一"},
                               "selector": {"type": "string",
                                            "description": "（推荐）CSS 选择器精确定位元素，与 id/text 三选一"},
                               "button": {"type": "string",
                                          "description": "鼠标键：left/right/middle，默认 left"}},
                           "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "在独立浏览器的输入框中输入文本。支持三种定位（任选其一）："
                           "① id=browser_snapshot 清单编号；② target=输入框文字（占位符/标签）；"
                           "③ selector=CSS 选择器精确定位输入框。先点击聚焦再输入。中文/英文/数字均可。",
            "parameters": {"type": "object",
                           "properties": {
                               "text": {"type": "string", "description": "要输入的文本"},
                               "id": {"type": "integer",
                                      "description": "（推荐）browser_snapshot 清单里的输入框编号 [id]"},
                               "target": {"type": "string",
                                          "description": "（推荐）输入框文字（占位符/标签），与 id/selector 三选一"},
                               "selector": {"type": "string",
                                            "description": "（推荐）CSS 选择器定位输入框，与 id/target 三选一"}},
                           "required": ["text"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "滚动独立浏览器页面或指定容器。direction=up/down/left/right/top/bottom"
                           "（top 滚到顶部、bottom 滚到底部，默认 down）；amount 指定像素步长"
                           "（默认滚动一屏的 80%）；eid/selector 可指定滚动容器（留空滚动整个页面）。"
                           "页面内容超出屏幕（列表/长文/评论区）需查看更多时使用。",
            "parameters": {"type": "object",
                           "properties": {
                               "direction": {"type": "string",
                                             "description": "滚动方向：up/down/left/right/top/bottom，默认 down"},
                               "amount": {"type": "integer",
                                          "description": "（可选）滚动像素步长，默认一屏 80% 高度"},
                               "id": {"type": "integer",
                                      "description": "（可选）要滚动的容器编号 [id]"},
                               "selector": {"type": "string",
                                            "description": "（可选）要滚动的容器 CSS 选择器"}},
                           "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_eval",
            "description": "在独立浏览器页面执行 JavaScript 并返回结果。可直接读取/修改 DOM（解析 HTML/CSS）、"
                           "调用页面函数、抓取数据、模拟操作。返回结果文本。",
            "parameters": {"type": "object",
                           "properties": {"js": {"type": "string",
                                                 "description": "要执行的 JavaScript 代码，return 值会作为结果返回"}},
                           "required": ["js"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_html",
            "description": "读取独立浏览器当前页面的 HTML/文本内容。传 selector（CSS 选择器）可只读取指定区域，"
                           "留空返回整页文本摘要。用于分析网页内容、确认操作结果、抓取数据。",
            "parameters": {"type": "object",
                           "properties": {"selector": {"type": "string",
                                                       "description": "（可选）CSS 选择器，如 #content / .price / form"}},
                           "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close",
            "description": "关闭独立浏览器实例（仅关闭 AI 启动的专用实例，不影响用户正在使用的浏览器）。"
                           "登录态/cookie/token 会保留在持久目录，下次 browser_open 自动恢复、无需重复登录。"
                           "浏览器任务完成后调用清理资源。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_tabs",
            "description": "列出独立浏览器内所有页面标签（含 window.open 弹出的新窗口/新标签）。"
                           "当页面弹窗/新窗口里的元素（如关闭按钮）在 browser_snapshot 中找不到时，"
                           "先 browser_tabs 查看弹窗标签，再用 browser_switch_tab 切过去操作。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_switch_tab",
            "description": "切换到指定编号的页面标签（弹窗/新窗口）。切换后 browser_snapshot/browser_click 等"
                           "操作都针对该标签。弹窗里的关闭按钮：切到弹窗标签后 browser_snapshot 找到关闭按钮再点击。",
            "parameters": {"type": "object",
                           "properties": {
                               "id": {"type": "integer",
                                      "description": "browser_tabs 返回的标签页编号（从 1 开始）"}},
                           "required": ["id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard",
            "description": "读写系统剪贴板：read 读取当前剪贴板文本，write 把指定文本写入剪贴板"
                           "（复制/粘贴场景，或读取用户已复制的内容）。",
            "parameters": {"type": "object",
                           "properties": {
                               "action": {"type": "string", "description": "read 读取 / write 写入"},
                               "text": {"type": "string", "description": "action=write 时要写入的文本"}},
                           "required": ["action"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_text",
            "description": "提取文档纯文本：支持 txt/md/log/json/csv/docx/pptx/xlsx"
                           "（docx/pptx/xlsx 直接解析 zip+XML，无需第三方库），PDF 需先 pip install pypdf。"
                           "读取文档内容、分析表格数据时使用。",
            "parameters": {"type": "object",
                           "properties": {
                               "path": {"type": "string", "description": "文档文件路径（相对路径基于工作目录）"}},
                           "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_docx",
            "description": "生成 Word 文档（.docx）：可选大标题 + 段落文本列表 + 图片（可选）+ 艺术字（可选）。"
                           "适合报告、说明文档、合同文本、简历等文字型文档。"
                           "支持 style 参数自定义配色/排版/背景，不传则用默认商务风。",
            "parameters": {"type": "object",
                           "properties": {
                               "path": {"type": "string", "description": "保存路径（.docx，相对路径基于工作目录）"},
                               "title": {"type": "string", "description": "文档大标题（可选）"},
                               "paragraphs": {"type": "array",
                                              "description": "段落文本列表，每项一个字符串，支持轻量标记："
                                                              "'# '一级标题 / '## '二级标题 / '### '三级标题 / '- '项目符号",
                                              "items": {"type": "string"}},
                               "images": {"type": "array",
                                          "description": "图片列表（可选，相对路径基于工作目录）。每项为路径字符串，"
                                                          "或 {path: 图片路径, align: left/center/right 水平对齐, width: 宽(英寸)}；"
                                                          "默认居中、宽6英寸，自动等比缩放防溢出页面",
                                          "items": {"type": "object",
                                                    "properties": {
                                                        "path": {"type": "string", "description": "图片路径"},
                                                        "align": {"type": "string", "description": "水平对齐：left/center/right，默认center"},
                                                        "width": {"type": "number", "description": "图片宽度（英寸），默认6"}},
                                                    "required": ["path"]}},
                               "wordart": {"type": "array",
                                          "description": "艺术字（样式化大字）列表（可选）：每项 {text: 文字, "
                                                          "size: 字号(默认36), color: 颜色HEX, font: 字体名, "
                                                          "align: left/center/right}，大幅加粗彩色文字，用于标题/强调",
                                          "items": {"type": "object",
                                                    "properties": {
                                                        "text": {"type": "string", "description": "艺术字文字"},
                                                        "size": {"type": "integer", "description": "字号，默认36"},
                                                        "color": {"type": "string", "description": "颜色HEX，默认主题主色"},
                                                        "font": {"type": "string", "description": "字体名，默认正文用字体"},
                                                        "align": {"type": "string", "description": "水平对齐：left/center/right，默认center"}},
                                                    "required": ["text"]}},
                               "style": {"type": "object",
                                         "description": "样式配置（可选）。不传则用默认商务风；传了可大胆自定义："
                                                         "theme=配色主题(business深蓝/green墨绿/warm橙棕/purple紫/"
                                                         "tech科技蓝/dark暗色/pastel浅蓝/red朱红/black-gold黑金)，"
                                                         "base_color=主色HEX，heading_color=标题色HEX，"
                                                         "text_color=正文色HEX，font_name=字体名(如'宋体'/'仿宋'/'楷体')，"
                                                         "align=正文对齐(left/center/right/justify)，"
                                                         "line_spacing=行距倍数(1.0-2.0)，title_size=大标题字号，"
                                                         "body_size=正文字号，page=纸张方向(portrait/landscape)，"
                                                         "bg_color=页面背景色HEX"}},
                           "required": ["path", "paragraphs"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "AI 文生图：生成与主题匹配的图片素材，下载到本地并返回本地路径。"
                           "生成 Word/PPT/Excel 文档需要配图（汇报/产品介绍/感言/总结/宣传等）时，"
                           "**必须**先用本工具生成素材图，再把返回的本地路径作为 image 参数"
                           "传入 create_docx/create_pptx/create_xlsx。",
            "parameters": {"type": "object",
                           "properties": {
                               "prompt": {"type": "string",
                                          "description": "要生成的画面描述（英文/中文均可，写清主体、场景、风格、配色、构图）"},
                               "ratio": {"type": "string",
                                         "enum": ["1:1", "3:4", "4:3", "16:9", "9:16"],
                                         "description": "画面比例，默认 1:1"},
                               "dest_dir": {"type": "string",
                                            "description": "保存目录（可选，相对路径基于工作目录，默认工作目录/images）"}},
                           "required": ["prompt"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_pptx",
            "description": "生成 PowerPoint 演示文稿（.pptx）：首页标题 + 多页内容页。"
                           "**页数要够、内容要详**：主题类 PPT 建议 8-15 页，每页要点要展开成完整句子/段落，"
                           "不要只写短语。"
                           "每页支持要点列表、彩色卡片、表格、图表、思维导图/流程图/对比图、插图、艺术字。"
                           "**配色要多元、页面要有图形排版**：不要每页都白底黑字，用 bg_color 换页底色、"
                           "用卡片(array)分区、用 table/chart/diagram 呈现结构化内容，"
                           "需要配图时先用 generate_image 生成素材图再传 image。"
                           "支持 style 参数自定义主题配色/封面布局/切换动画，不传则用默认商务风。",
            "parameters": {"type": "object",
                           "properties": {
                               "path": {"type": "string", "description": "保存路径（.pptx）"},
                               "title": {"type": "string", "description": "演示文稿标题（可选，用作首页）"},
                               "slides": {"type": "array",
                                          "description": "幻灯片列表，每项 {title, bullets(要点列表), "
                                                          "cards(彩色卡片数组), table(表格), chart(图表), "
                                                          "diagram(思维导图/流程图/对比图), image(插图), "
                                                          "wordart(艺术字), bg_color, title_color, "
                                                          "layout(left_image/right_image/two_col/center_highlight)}",
                                          "items": {"type": "object",
                                                    "properties": {
                                                        "title": {"type": "string", "description": "页标题"},
                                                        "bullets": {"type": "array",
                                                                    "description": "本页要点列表（每项为完整句子/段落，"
                                                                                    "可含'## '子标题、'- '子要点）",
                                                                    "items": {"type": "string"}},
                                                        "cards": {"type": "array",
                                                                  "description": "本页彩色卡片数组（关键词/数据并排展示），"
                                                                                  "每项 {title, desc, color}",
                                                                  "items": {"type": "object",
                                                                            "properties": {
                                                                                "title": {"type": "string", "description": "卡片标题"},
                                                                                "desc": {"type": "string", "description": "卡片说明文字"},
                                                                                "color": {"type": "string", "description": "卡片底色HEX（可选，默认主题浅色）"}},
                                                                            "required": ["title"]}},
                                                        "table": {"type": "object",
                                                                  "description": "本页表格（结构化数据）：{header: [列名], "
                                                                                  "rows: [[值,...],...], title: 表标题(可选)}",
                                                                  "properties": {
                                                                      "header": {"type": "array", "items": {"type": "string"},
                                                                                 "description": "表头列名"},
                                                                      "rows": {"type": "array",
                                                                               "description": "数据行二维数组",
                                                                               "items": {"type": "array", "items": {}}},
                                                                      "title": {"type": "string", "description": "表标题（可选）"}},
                                                                  "required": ["header", "rows"]},
                                                        "chart": {"type": "object",
                                                                  "description": "本页图表：{type: bar/column/line/pie/doughnut, "
                                                                                  "labels: [分类], values: [数值], "
                                                                                  "title: 图标题(可选)}，用原生图形绘制",
                                                                  "properties": {
                                                                      "type": {"type": "string", "description": "bar/column/line/pie/doughnut"},
                                                                      "labels": {"type": "array", "items": {"type": "string"}},
                                                                      "values": {"type": "array", "items": {"type": "number"}},
                                                                      "title": {"type": "string", "description": "图标题（可选）"}},
                                                                  "required": ["type", "labels", "values"]},
                                                        "diagram": {"type": "object",
                                                                    "description": "本页图形排版：{type: mindmap/flow/compare/cycle, "
                                                                                    "center: 中心主题(可选), items: [节点/步骤/对比项], "
                                                                                    "title: 附加标题(可选)}",
                                                                    "properties": {
                                                                        "type": {"type": "string", "description": "mindmap/flow/compare/cycle"},
                                                                        "center": {"type": "string", "description": "中心主题（mindmap 用）"},
                                                                        "items": {"type": "array",
                                                                                  "description": "节点/步骤；compare 为对比项数组，每项 {title, left, right}",
                                                                                  "items": {}},
                                                                        "title": {"type": "string", "description": "附加标题（可选）"}},
                                                                    "required": ["type", "items"]},
                                                        "image": {"type": "object",
                                                                  "description": "本页插图（可选）：路径字符串或 {path, "
                                                                                  "align: left/center/right, width: 宽(英寸)}",
                                                                  "properties": {
                                                                      "path": {"type": "string", "description": "图片路径"},
                                                                      "align": {"type": "string", "description": "水平对齐：left/center/right，默认center"},
                                                                      "width": {"type": "number", "description": "图片宽度（英寸），默认8"}},
                                                                  "required": ["path"]},
                                                        "wordart": {"type": "object",
                                                                    "description": "本页艺术字（可选）：{text, size, color}，"
                                                                                    "大幅加粗彩色装饰文字",
                                                                    "properties": {
                                                                        "text": {"type": "string", "description": "艺术字文字"},
                                                                        "size": {"type": "integer", "description": "字号，默认44"},
                                                                        "color": {"type": "string", "description": "颜色HEX，默认主题主色"}},
                                                                    "required": ["text"]},
                                                        "bg_color": {"type": "string",
                                                                     "description": "本页背景色 HEX（可选，覆盖全局背景）"},
                                                        "title_color": {"type": "string",
                                                                        "description": "本页标题色 HEX（可选，覆盖全局标题色）"},
                                                        "layout": {"type": "string",
                                                                   "description": "本页布局：left_image/right_image（图文左右分栏）"
                                                                                   "、two_col（左右两栏）、center_highlight（居中大字强调）"}},
                                                    "required": ["title"]}},
                               "style": {"type": "object",
                                         "description": "样式配置（可选）。不传则用默认商务风；传了可大胆自定义："
                                                         "theme=配色方案(business深蓝/black-gold黑金/green墨绿/warm暖橙/"
                                                         "tech科技蓝/vivid明快/dark暗色/pastel浅色/red朱红/purple紫)，"
                                                         "cover_style=封面布局(solid纯色底/split左右分屏/centered居中)，"
                                                         "title_color=标题色HEX，bg_color=内容页背景色HEX，"
                                                         "accent=强调色HEX，font_name=字体名，"
                                                         "bullet_style=要点符号(dot/number/arrow/check)，"
                                                         "transition=页面切换动画(fade推入/push推出/wipe擦除/zoom缩放/random随机)，"
                                                         "title_size=页标题字号，body_size=要点字号"}},
                           "required": ["path", "slides"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_xlsx",
            "description": "生成 Excel 工作簿（.xlsx）：多个工作表，每表 {name, rows, image(可选), wordart(可选)}，"
                           "rows 为二维数组（首行可作为表头）。适合数据表、统计报表、清单等。"
                           "支持 style 参数自定义表头配色/隔行/边框/背景，不传则用默认商务风。",
            "parameters": {"type": "object",
                           "properties": {
                               "path": {"type": "string", "description": "保存路径（.xlsx）"},
                               "sheets": {"type": "array",
                                          "description": "工作表列表，每项 {name: 表名, rows: [[单元格,...],...], "
                                                          "image: 表插图(可选，路径字符串或 {path, width}), "
                                                          "wordart: 表标题艺术字(可选，{text,size,color})}",
                                          "items": {"type": "object",
                                                    "properties": {
                                                        "name": {"type": "string", "description": "工作表名"},
                                                        "rows": {"type": "array",
                                                                 "description": "数据行二维数组",
                                                                 "items": {"type": "array",
                                                                           "items": {}}},
                                                        "image": {"type": "object",
                                                                  "description": "表插图（可选）：路径字符串或 "
                                                                                  "{path, width: 宽(像素,默认800)}",
                                                                  "properties": {
                                                                      "path": {"type": "string", "description": "图片路径"},
                                                                      "width": {"type": "number", "description": "图片宽度(像素)，默认800"}},
                                                                  "required": ["path"]},
                                                        "wordart": {"type": "object",
                                                                    "description": "表标题艺术字（可选）：{text, size, "
                                                                                    "color}，顶部大号加粗彩色标题行",
                                                                    "properties": {
                                                                        "text": {"type": "string", "description": "标题文字"},
                                                                        "size": {"type": "integer", "description": "字号，默认16"},
                                                                        "color": {"type": "string", "description": "颜色HEX，默认主题主色"}},
                                                                    "required": ["text"]}},
                                                    "required": ["name", "rows"]}},
                               "style": {"type": "object",
                                         "description": "样式配置（可选）。不传则用默认商务风；传了可大胆自定义："
                                                         "theme_color=主题色HEX，header_fill=表头填充色HEX，"
                                                         "header_color=表头字色HEX，font_name=字体名，"
                                                         "banded=隔行变色(true/false，默认true)，band_fill=隔行填充色HEX，"
                                                         "freeze_header=冻结首行(true/false，默认true)，"
                                                         "auto_filter=自动筛选(true/false，默认true)，"
                                                         "border_color=边框色HEX，header_size=表头字号，"
                                                         "body_size=数据字号，header_bold=表头加粗(true/false，默认true)，"
                                                         "bg_color=工作表背景色HEX(填充数据区域)"}},
                           "required": ["path", "sheets"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索：在 Bing 上搜索关键词，返回结果列表（标题/URL/摘要）。"
                           "需要查询实时信息、新闻、文档或知识范围外内容时使用。",
            "parameters": {"type": "object",
                           "properties": {
                               "query": {"type": "string", "description": "搜索关键词"},
                               "max_results": {"type": "integer",
                                               "description": "返回结果条数，默认 8，最大 10"}},
                           "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_skill",
            "description": "以用户自然语言描述为基础，自动生成市场标准 SKILL.md 技能文件并加载（写入 "
                           "skills/<name>/SKILL.md，创建后立即生效，AI 与用户均可通过 /技能名 调用）。",
            "parameters": {"type": "object",
                           "properties": {
                               "name": {"type": "string",
                                        "description": "技能名（仅字母/数字/下划线/连字符，≤50 字符）"},
                               "description": {"type": "string", "description": "技能用途一句话简介"},
                               "instruction": {"type": "string",
                                               "description": "技能执行流程/规则正文（markdown，写清触发条件与步骤）"}},
                           "required": ["name", "description", "instruction"]},
        },
    },
    # ---------- 子 Agent 工具（主 Agent 派发只读子任务，执行由引擎调度） ----------
    {
        "type": "function",
        "function": {
            "name": "dispatch_sub_agents",
            "description": "把多个互不依赖的子任务分发给并行运行的子 Agent，各自独立执行后汇总返回。"
                           "适合大规模读取/搜索/探索、以及多文件并行迭代（子 Agent 可创建/编辑/删除项目文件，"
                           "但不能执行命令）。子任务建议 1-8 个；任务越多总体耗时越长。",
            "parameters": {"type": "object",
                           "properties": {
                               "tasks": {"type": "array",
                                         "description": "子任务列表（每项含 title 标题与 goal 目标）",
                                         "items": {"type": "object",
                                                   "properties": {
                                                       "title": {"type": "string",
                                                                 "description": "子任务标题"},
                                                       "goal": {"type": "string",
                                                                "description": "子任务目标与要求（写清要做什么、输出什么）"}},
                                                   "required": ["title", "goal"]}}},
                           "required": ["tasks"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explore_project",
            "description": "探索并理解一个项目/目录（Explorer 子 Agent）：生成目录结构、读取 README 与关键入口文件，"
                           "输出项目概览（用途、技术栈、模块结构、入口、构建/运行方式）。接手新项目时先用它快速了解。",
            "parameters": {"type": "object",
                           "properties": {
                               "directory": {"type": "string",
                                             "description": "要探索的项目目录（绝对路径）"}},
                           "required": ["directory"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_large",
            "description": "大规模搜索（Search 子 Agent）：在多个目录范围内搜索关键词并汇总命中（跨目录、多轮搜索、"
                           "重要命中读取上下文确认）。比 search_files 更适合范围大、文件多的搜索。",
            "parameters": {"type": "object",
                           "properties": {
                               "query": {"type": "string", "description": "搜索关键词"},
                               "directories": {"type": "array", "items": {"type": "string"},
                                               "description": "可选：搜索目录列表；留空用工作目录/用户常用目录"},
                               "max_results": {"type": "integer",
                                               "description": "可选：最多保留命中条数，默认 20"}},
                           "required": ["query"]},
        },
    },
    # ---------- TTS 语音合成（Qwen-TTS 声音复刻，DashScope 真实 API） ----------
    {
        "type": "function",
        "function": {
            "name": "tts_create_voice",
            "description": "上传参考音频创建自定义音色（声音复刻）：支持 wav 等音频（推荐 10~20s、"
                           "≥24kHz 单声道、≤10MB），返回 voice_id 供 tts_speak 使用。"
                           "创建后音色长期有效，同一 target_model 可反复创建。",
            "parameters": {"type": "object",
                           "properties": {
                               "audio_path": {"type": "string",
                                              "description": "参考音频文件路径（绝对路径或基于工作目录的相对路径）"},
                               "preferred_name": {"type": "string",
                                                  "description": "音色名称（字母/数字/下划线，默认 diede）"},
                               "target_model": {"type": "string",
                                                "description": "绑定模型（默认 qwen3-tts-vc-2026-01-22）"}},
                           "required": ["audio_path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tts_query_voice",
            "description": "查询音色详情（创建时间/语言/绑定模型）。需传入已有 voice_id。",
            "parameters": {"type": "object",
                           "properties": {
                               "voice_id": {"type": "string", "description": "音色 ID"},
                               "target_model": {"type": "string",
                                                "description": "绑定模型（默认 qwen3-tts-vc-2026-01-22）"}},
                           "required": ["voice_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tts_delete_voice",
            "description": "删除指定音色（不可恢复）。需传入已有 voice_id。",
            "parameters": {"type": "object",
                           "properties": {
                               "voice_id": {"type": "string", "description": "要删除的音色 ID"}},
                           "required": ["voice_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tts_speak",
            "description": "用指定音色把文本合成为语音，流式边生成边自动播放，并下载保存到本地，返回音频文件路径。"
                           "适合朗读回复、生成语音文件；voice_id 留空使用设置面板选中的音色；"
                           "output_path 留空自动保存到工作目录 tts_output/；play=false 可关闭自动播放。",
            "parameters": {"type": "object",
                           "properties": {
                               "text": {"type": "string", "description": "要合成的文本"},
                               "voice_id": {"type": "string",
                                            "description": "音色 ID（留空使用设置面板选中音色）"},
                               "model": {"type": "string",
                                         "description": "合成模型（默认 qwen3-tts-vc-2026-01-22）"},
                               "output_path": {"type": "string",
                                               "description": "输出音频文件路径（可选，留空自动生成）"},
                               "play": {"type": "boolean",
                                        "description": "是否边生成边自动播放（默认 true）"}},
                           "required": ["text"]},
        },
    },
]

# 子 Agent 工具名（由 agent_engine 拦截调度，携带 LLM 客户端执行；不在此直接实现）
SUB_AGENT_TOOLS = ("dispatch_sub_agents", "explore_project", "search_large")


# ------------------------------------------------------------
# TTS 流式播放器（pygame.mixer 逐片排队，边生成边播放）
# ------------------------------------------------------------
_TTS_PLAYER_LOCK = threading.Lock()
_TTS_MIXER_OK = False
_TTS_CHANNEL = None
_TTS_QUEUED = 0


def _tts_play_start() -> bool:
    """开始一段流式播放：初始化 mixer（幂等）并清空上一段未播完的队列。
    返回是否可播放（True=播放可用；False=pygame 不可用/初始化失败）。"""
    global _TTS_MIXER_OK, _TTS_CHANNEL, _TTS_QUEUED
    with _TTS_PLAYER_LOCK:
        if not _TTS_MIXER_OK:
            try:
                import pygame
                # 统一请求双声道：SDL 常把单声道请求强制回退为 stereo，
                # 主动用 stereo 可保证 mixer.get_init() 声道数稳定，播放端按该声道扩展 PCM
                pygame.mixer.pre_init(24000, -16, 2, 4096)
                pygame.mixer.init()
                _TTS_MIXER_OK = True
            except Exception:
                _TTS_MIXER_OK = False
                return False
        try:
            import pygame
            if _TTS_CHANNEL is None:
                _TTS_CHANNEL = pygame.mixer.Channel(0)
            _TTS_CHANNEL.stop()
            _TTS_QUEUED = 0
        except Exception:
            return False
        return True


def _tts_play_chunk(pcm: bytes):
    """把一个 PCM 分片构造为内存 WAV 并排队播放（每片 0.3s，天然帧对齐）

    注意：SDL 可能把请求的单声道强制开成双声道（mixer.get_init() 返回 2 声道），
    此时必须把 mono PCM 扩展为 mixer 实际声道数，否则 Sound 会把 mono 数据按
    stereo 解析 → 时长减半 → 播放倍速 + 音调翻倍（听起来"夹/发尖"）。
    """
    global _TTS_QUEUED
    if not pcm or not _TTS_MIXER_OK:
        return
    try:
        import pygame, struct, array
        # 读取 mixer 实际声道数（pre_init 请求 mono，但 SDL 可能回退为 stereo）
        init = pygame.mixer.get_init()
        out_ch = init[2] if init and len(init) >= 3 else 1
        if out_ch > 1:
            a = array.array("h", pcm)
            out = array.array("h")
            for x in a:
                for _ in range(out_ch):
                    out.append(x)
            pcm = out.tobytes()
        wav = struct.pack("<4sI4s4sIHHIIHH4sI",
                          b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16,
                          1, out_ch, 24000, 24000 * out_ch * 2, out_ch * 2, 16,
                          b"data", len(pcm)) + pcm
        snd = pygame.mixer.Sound(buffer=wav)
        with _TTS_PLAYER_LOCK:
            if _TTS_CHANNEL is None:
                return
            if _TTS_QUEUED == 0:
                _TTS_CHANNEL.play(snd)
            else:
                _TTS_CHANNEL.queue(snd)
            _TTS_QUEUED += 1
    except Exception:
        pass


def _tts_play_stop():
    """停止并清理播放（合成失败时调用）"""
    global _TTS_QUEUED
    with _TTS_PLAYER_LOCK:
        try:
            if _TTS_CHANNEL is not None:
                _TTS_CHANNEL.stop()
        except Exception:
            pass
        _TTS_QUEUED = 0


# 沙盒拒绝返回（无截图）
def _blocked(text: str) -> dict:
    return {"text": text, "images": []}


def _image_scale(path: str, max_w: float, max_h: float) -> tuple:
    """读取图片像素尺寸，返回 (scale, w, h)：scale 为按 max_w×max_h 等比缩放的比例(≤1)。
    用于文档/幻灯片插图自适应，防止大图/竖图溢出页面。读取失败返回 None。"""
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
        if not w or not h:
            return None
        return (min(max_w / w, max_h / h, 1.0), w, h)
    except Exception:
        return None


def _ask_user(args: dict, ask_user_cb) -> dict:
    """向用户提问（需求不明确时强制提问，禁止猜测执行）"""
    question = str(args.get("question", "")).strip()
    if not question:
        return _blocked("[ask_user] 缺少问题")
    if not ask_user_cb:
        return _blocked("[ask_user] 未接入提问面板，请基于已有信息继续")
    try:
        answer = ask_user_cb({
            "question": question,
            "options": args.get("options") or [],
            "multi_select": bool(args.get("multi_select", False)),
        })
        return {"text": f"用户回答：{answer}", "images": []}
    except Exception as e:
        return _blocked(f"[ask_user] 提问失败: {e}")


def execute_tool(name: str, args: dict, allow_dangerous: bool = False,
                 ask_user_cb=None) -> dict:
    """执行工具，返回 {"text", "images"}。

    allow_dangerous=True 时放行危险操作（AskBeforeEdit 模式下用户显式确认后的授权）；
    False 时危险操作硬拒绝（YOLO 自动放行场景的安全底线）。
    ask_user_cb: Callable[[dict], str] 提问回调（阻塞式，返回用户回答文本）。
    """
    args = args or {}
    if name == "ask_user":
        return _ask_user(args, ask_user_cb)
    if name in SUB_AGENT_TOOLS:
        return _blocked(f"[{name}] 子 Agent 工具由主引擎调度执行")
    level, reason = agent_sandbox.assess_tool(name, args)
    if level == "dangerous" and not allow_dangerous:
        return _blocked(f"[沙盒拒绝] {reason}")

    try:
        if name == "find_app":
            return {"text": agent_find.find_app(
                str(args.get("query", "")),
                agent_sandbox.to_int(args.get("limit", 10))), "images": []}
        if name == "search_files":
            folder = str(args.get("folder", "")).strip()
            if not folder and WORKDIR:
                folder = WORKDIR   # 未指定目录时默认在工作目录内查找
            return {"text": agent_find.search_files(
                str(args.get("query", "")), folder,
                agent_sandbox.to_int(args.get("limit", 30))), "images": []}
        if name == "run_command":
            return _run_command(str(args.get("command", "")),
                                agent_sandbox.to_int(args.get("wait", 5)),
                                bool(args.get("force_quit", False)))
        if name == "check_command":
            return _check_command(agent_sandbox.to_int(args.get("cmd_id", 0)) or None)
        if name == "read_file":
            return _read_file(str(args.get("path", "")))
        if name == "write_file":
            return _write_file(str(args.get("path", "")), str(args.get("content", "")))
        if name == "edit_file":
            return _edit_file(str(args.get("path", "")),
                              str(args.get("old_text", "")),
                              str(args.get("new_text", "")))
        if name == "delete_file":
            return _delete_file(str(args.get("path", "")))
        if name == "list_directory":
            return _list_directory(str(args.get("path", "")))
        if name == "save_memory":
            return _save_memory(str(args.get("content", "")))
        if name == "load_memory":
            return _load_memory()
        # 系统信息（原 MCP server 工具内置化）
        if name == "system_info":
            return _system_info()
        if name == "get_time":
            return _get_time()
        if name == "env_var":
            return _env_var(str(args.get("name", "")))
        # WinAppMigrator 能力
        if name == "optimize_memory":
            return _optimize_memory()
        if name == "uninstall_app":
            return _uninstall_app(str(args.get("name", "")))
        if name == "migrate_app":
            return _migrate_app(str(args.get("name", "")), str(args.get("target", "")))
        if name == "fast_download":
            return _fast_download(str(args.get("url", "")), str(args.get("dest_dir", "")))
        if name == "web_fetch":
            return _web_fetch(str(args.get("url", "")),
                              str(args.get("method", "GET")),
                              args.get("headers") if isinstance(args.get("headers"), dict) else None,
                              str(args.get("body", "")),
                              agent_sandbox.to_int(args.get("max_chars", 8000)))
        # ---- 浏览器操控（独立浏览器实例，CDP） ----
        if name == "browser_open":
            ok, msg = agent_browser.controller().start(
                str(args.get("engine", "")), bool(args.get("headless", False)))
            return {"text": msg, "images": []}
        if name == "browser_navigate":
            ok, msg = agent_browser.controller().navigate(str(args.get("url", "")))
            if not ok:
                return {"text": f"[browser_navigate] {msg}", "images": []}
            try:
                shot = agent_browser.controller().screenshot()
                return {"text": msg, "images": [shot]}
            except Exception:
                return {"text": msg, "images": []}
        if name == "browser_snapshot":
            ctl = agent_browser.controller()
            try:
                shot = ctl.screenshot()
                elems = ctl.summarize()
            except Exception as e:
                return {"text": f"[browser_snapshot] {e}", "images": []}
            return {"text": "页面元素清单（按 [编号] 或文字引用操作）：\n" + elems,
                    "images": [shot]}
        if name == "browser_click":
            ctl = agent_browser.controller()
            eid = args.get("id")
            text = str(args.get("text", "")).strip()
            ok, msg, shot = ctl.click(
                eid=agent_sandbox.to_int(eid) if eid is not None else None,
                text=text or None,
                button=str(args.get("button", "left")))
            if not ok:
                return {"text": f"[browser_click] {msg}", "images": []}
            return {"text": msg, "images": [shot] if shot else []}
        if name == "browser_type":
            ctl = agent_browser.controller()
            eid = args.get("id")
            ok, msg, shot = ctl.type_text(
                str(args.get("text", "")),
                eid=agent_sandbox.to_int(eid) if eid is not None else None,
                target=str(args.get("target", "")).strip() or None)
            if not ok:
                return {"text": f"[browser_type] {msg}", "images": []}
            return {"text": msg, "images": [shot] if shot else []}
        if name == "browser_eval":
            try:
                res = agent_browser.controller().eval(str(args.get("js", "")))
            except Exception as e:
                return {"text": f"[browser_eval] {e}", "images": []}
            return {"text": res.get("text", ""), "images": []}
        if name == "browser_html":
            try:
                res = agent_browser.controller().html(str(args.get("selector", "")))
            except Exception as e:
                return {"text": f"[browser_html] {e}", "images": []}
            return {"text": res.get("text", ""), "images": []}
        if name == "browser_scroll":
            ctl = agent_browser.controller()
            eid = args.get("id")
            ok, msg, shot = ctl.scroll(
                str(args.get("direction", "down")),
                agent_sandbox.to_int(args.get("amount", 0)) or None,
                eid=agent_sandbox.to_int(eid) if eid is not None else None,
                selector=str(args.get("selector", "")).strip() or None)
            if not ok:
                return {"text": f"[browser_scroll] {msg}", "images": []}
            return {"text": msg, "images": [shot] if shot else []}
        if name == "browser_close":
            ok, msg = agent_browser.controller().stop()
            return {"text": msg, "images": []}
        if name == "browser_tabs":
            pages = agent_browser.controller().list_pages()
            if not pages:
                return {"text": "[browser_tabs] 当前无可用页面标签（浏览器未启动？）", "images": []}
            rows = [f"[{p['id']}] {p['title']} | {p['url']}" for p in pages]
            return {"text": "页面标签清单（用 browser_switch_tab(id) 切换）：\n" + "\n".join(rows),
                    "images": []}
        if name == "browser_switch_tab":
            ok, msg = agent_browser.controller().switch_tab(
                agent_sandbox.to_int(args.get("id", 0)))
            return {"text": f"[browser_switch_tab] {msg}", "images": []}
        if name == "web_search":
            return _web_search(str(args.get("query", "")),
                               agent_sandbox.to_int(args.get("max_results", 8)))
        if name == "clipboard":
            return _clipboard(str(args.get("action", "read")), str(args.get("text", "")))
        if name == "extract_text":
            return _extract_text(str(args.get("path", "")))
        if name == "generate_image":
            return _generate_image(str(args.get("prompt", "")),
                                   str(args.get("ratio", "1:1")),
                                   str(args.get("dest_dir", "")))
        if name == "create_docx":
            return _create_docx(str(args.get("path", "")), str(args.get("title", "")),
                                args.get("paragraphs") if isinstance(args.get("paragraphs"), list) else [],
                                args.get("images") if isinstance(args.get("images"), list) else [],
                                args.get("style") if isinstance(args.get("style"), dict) else {},
                                args.get("wordart") if isinstance(args.get("wordart"), list) else [])
        if name == "create_pptx":
            return _create_pptx(str(args.get("path", "")), str(args.get("title", "")),
                                args.get("slides") if isinstance(args.get("slides"), list) else [],
                                args.get("style") if isinstance(args.get("style"), dict) else {})
        if name == "create_xlsx":
            return _create_xlsx(str(args.get("path", "")),
                                args.get("sheets") if isinstance(args.get("sheets"), list) else [],
                                args.get("style") if isinstance(args.get("style"), dict) else {})
        if name == "create_skill":
            return _create_skill(str(args.get("name", "")),
                                 str(args.get("description", "")),
                                 str(args.get("instruction", "")))
        # ---- TTS 语音合成（Qwen-TTS 声音复刻，DashScope 真实 API） ----
        if name == "tts_create_voice":
            try:
                vid = agent_tts.create_voice(
                    str(args.get("audio_path", "")),
                    str(args.get("target_model", agent_tts.DEFAULT_TARGET_MODEL)),
                    str(args.get("preferred_name", "diede")))
                return {"text": f"音色创建成功：{vid}", "images": []}
            except Exception as e:
                return _blocked(f"[tts_create_voice] {e}")
        if name == "tts_query_voice":
            try:
                d = agent_tts.query_voice(
                    str(args.get("voice_id", "")),
                    str(args.get("target_model", agent_tts.DEFAULT_TARGET_MODEL)))
                return {"text": json.dumps(d, ensure_ascii=False, indent=2), "images": []}
            except Exception as e:
                return _blocked(f"[tts_query_voice] {e}")
        if name == "tts_delete_voice":
            try:
                agent_tts.delete_voice(str(args.get("voice_id", "")))
                return {"text": f"音色已删除：{args.get('voice_id', '')}", "images": []}
            except Exception as e:
                return _blocked(f"[tts_delete_voice] {e}")
        if name == "tts_speak":
            try:
                play = bool(args.get("play", True))
                play_ok = True
                if play:
                    play_ok = _tts_play_start()   # 播放器不可用时不再静默：明确反馈给 AI/用户
                def _on_chunk(pcm):
                    if play and play_ok:
                        _tts_play_chunk(pcm)
                out = agent_tts.synthesize_stream(
                    str(args.get("text", "")),
                    str(args.get("voice_id", "")),
                    str(args.get("model", agent_tts.DEFAULT_TARGET_MODEL)),
                    on_chunk=_on_chunk,
                    output_path=str(args.get("output_path", "")))
                note = "（已自动播放）" if (play and play_ok) else \
                       ("（合成成功，但自动播放不可用：pygame 未安装或音频初始化失败，"
                        "已保存音频文件，可用其他播放器打开）" if play else "")
                return {"text": f"语音合成完成，已保存：{out}" + note, "images": []}
            except Exception as e:
                _tts_play_stop()
                return _blocked(f"[tts_speak] {e}")
    except Exception as e:
        return _blocked(f"[工具执行错误] {name}: {e}")
    return _blocked(f"[未知工具] {name}")


def _run_command(command: str, wait: int = 5, force_quit: bool = False) -> dict:
    """执行命令，AI 自主选择等待/强制退出策略。

    - wait 秒内完成：返回完整输出与退出码
    - wait 秒内未完成：
      · force_quit=True  → taskkill /T 强制结束进程树，返回已收集输出
      · force_quit=False → 转入后台注册表（可 check_command 轮询进度），返回命令 ID
    reader 线程持续排空 stdout/stderr，轮询期间可拿到增量进度。
    """
    try:
        wait = max(0, int(wait))   # 不做上限：长命令可无限等待，由 stop/转后台机制兜底
        # 二进制模式读取管道，统一由 _decode_robust 智能解码（UTF-8 优先，回退 OEM 代码页），
        # 兼容现代工具 UTF-8 输出与传统控制台 GBK 输出
        proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                cwd=WORKDIR or None,     # 命令默认在工作目录执行
                                creationflags=_CREATE_NO_WINDOW)
    except Exception as e:
        return _blocked(f"[沙盒] 命令执行失败: {e}")

    out_lines, err_lines = [], []
    lock = threading.Lock()
    threads = [
        threading.Thread(target=_drain_pipe, args=(proc.stdout, out_lines, lock), daemon=True),
        threading.Thread(target=_drain_pipe, args=(proc.stderr, err_lines, lock), daemon=True),
    ]
    for t in threads:
        t.start()

    # 轮询等待：wait 秒内每 1s 检查一次进程是否退出（期间输出持续被 reader 线程收集）
    deadline = time.time() + wait
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        time.sleep(1.0)

    with lock:
        out = _decode_robust(b"".join(out_lines)).strip()
        err = _decode_robust(b"".join(err_lines)).strip()
    code = proc.poll()

    def _compose() -> str:
        text = out
        if err:
            text += f"\n[stderr] {err}" if text else f"[stderr] {err}"
        if not text:
            text = f"（命令完成，退出码 {code}）"
        return text

    if code is not None:
        for t in threads:
            t.join(1.0)   # 等 reader 线程排空剩余输出
        return {"text": _compose(), "images": []}

    if force_quit:
        _kill_process_tree(proc.pid)
        # 留出清理时间后再读一次输出
        time.sleep(0.8)
        for t in threads:
            t.join(1.0)
        with lock:
            out = _decode_robust(b"".join(out_lines)).strip()
            err = _decode_robust(b"".join(err_lines)).strip()
        code = proc.poll()
        return {"text": f"命令在 {wait}s 内未完成，已按 force_quit 强制结束（退出码 {code}）。\n" + _compose(),
                "images": []}

    # 转入后台运行：注册并返回 ID，AI 用 check_command 轮询进度
    cmd_id = next(_cmd_seq)
    _running_cmds[cmd_id] = {
        "proc": proc, "command": command, "out": out_lines, "err": err_lines,
        "lock": lock, "threads": threads, "start": time.strftime("%H:%M:%S"),
    }
    text = (f"命令已转入后台运行（ID {cmd_id}，{wait}s 内未完成）。可用 "
            f"check_command(cmd_id={cmd_id}) 轮询进度。当前输出：\n" + _compose())
    return {"text": text, "images": []}


def _check_command(cmd_id: int = None) -> dict:
    """轮询后台命令进度：cmd_id 为空时列出全部；指定 ID 时返回最新输出，
    已结束则返回最终输出与退出码并从注册表移除。"""
    if cmd_id is None:
        # 顺手清理已结束的命令，避免注册表堆积僵尸条目
        for i in [i for i, r in _running_cmds.items() if r["proc"].poll() is not None]:
            del _running_cmds[i]
        if not _running_cmds:
            return {"text": "当前没有后台运行中的命令", "images": []}
        lines = [f"ID {i}: {rec['command'][:80]}（{rec['start']} 启动）"
                 for i, rec in _running_cmds.items()]
        return {"text": "后台运行中的命令：\n" + "\n".join(lines), "images": []}

    rec = _running_cmds.get(cmd_id)
    if rec is None:
        return {"text": f"未找到后台命令 ID {cmd_id}（可能已结束或被清理）", "images": []}
    code = rec["proc"].poll()
    if code is None:
        return {"text": f"命令 ID {cmd_id} 仍在运行（{time.strftime('%H:%M:%S')}）。当前输出：\n"
                        + _collect(rec), "images": []}
    for t in rec.get("threads", []):
        t.join(1.0)   # 等 reader 线程排空剩余输出
    del _running_cmds[cmd_id]
    return {"text": f"命令 ID {cmd_id} 已结束，退出码 {code}。最终输出：\n" + _collect(rec), "images": []}


def _read_file(path: str) -> dict:
    p = _resolve(path)
    level, reason = agent_sandbox.assess_path(str(p), "read")
    if level != "safe":
        return _blocked(f"[沙盒拒绝] {reason}")
    try:
        size = os.path.getsize(p)
        if size > 200 * 1024:
            return _blocked(f"[沙盒] 文件过大（{size} 字节 > 200KB）")
        with open(p, "rb") as f:
            raw = f.read()
        return {"text": _decode_robust(raw)[:30000], "images": []}
    except Exception as e:
        return _blocked(f"[沙盒] 读取失败: {e}")


def _write_file(path: str, content: str) -> dict:
    """创建/覆盖写入文件（工作目录优先；系统目录也可写，删除系统目录仍被拒）"""
    p = _resolve(path)
    level, reason = agent_sandbox.assess_path(str(p), "write")
    if level != "safe":
        return _blocked(f"[沙盒拒绝] {reason}")
    if len(content) > 500 * 1024:
        return _blocked("[沙盒] 内容过大（>500KB）")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return {"text": f"已写入 {len(content)} 字符到 {p}", "images": []}
    except Exception as e:
        return _blocked(f"[沙盒] 写入失败: {e}")


def _edit_file(path: str, old_text: str, new_text: str) -> dict:
    """编辑文件：精确替换第一处 old_text"""
    p = _resolve(path)
    level, reason = agent_sandbox.assess_path(str(p), "write")
    if level != "safe":
        return _blocked(f"[沙盒拒绝] {reason}")
    try:
        if os.path.getsize(p) > 200 * 1024:
            return _blocked("[沙盒] 文件过大（>200KB）")
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            data = f.read()
        if old_text not in data:
            return _blocked("[沙盒] 未找到要替换的内容")
        data = data.replace(old_text, new_text, 1)
        with open(p, "w", encoding="utf-8") as f:
            f.write(data)
        return {"text": f"已替换 1 处内容到 {p}", "images": []}
    except Exception as e:
        return _blocked(f"[沙盒] 编辑失败: {e}")


def _delete_file(path: str) -> dict:
    """删除文件或空目录（工作目录优先；删除系统关键目录内容被沙盒拒绝）"""
    p = _resolve(path)
    level, reason = agent_sandbox.assess_path(str(p), "delete")
    if level != "safe":
        return _blocked(f"[沙盒拒绝] {reason}")
    try:
        if not p.exists():
            return _blocked(f"[沙盒] 路径不存在: {p}")
        if p.is_dir():
            if any(p.iterdir()):
                return _blocked(f"[沙盒] 目录非空，禁止递归删除: {p}（可用 run_command 精确处理）")
            p.rmdir()
        else:
            p.unlink()
        return {"text": f"已删除: {p}", "images": []}
    except Exception as e:
        return _blocked(f"[沙盒] 删除失败: {e}")


def _list_directory(path: str) -> dict:
    """列出目录内容（工作目录优先，最多 200 项）"""
    p = _resolve(path)
    level, reason = agent_sandbox.assess_path(str(p), "read")
    if level != "safe":
        return _blocked(f"[沙盒拒绝] {reason}")
    try:
        entries = sorted(os.listdir(p))
        lines = []
        for e in entries[:200]:
            full = os.path.join(p, e)
            mark = "DIR " if os.path.isdir(full) else "FILE"
            lines.append(f"{mark}\t{e}")
        text = f"{p} 共 {len(entries)} 项" + (f"（仅显示前 200）" if len(entries) > 200 else "") + "：\n"
        text += "\n".join(lines)
        return {"text": text, "images": []}
    except Exception as e:
        return _blocked(f"[沙盒] 读取失败: {e}")


_MEMORY_MAX_TOTAL = 50 * 1024   # 记忆文件总上限 50KB（超出后截断旧部分）
_MEMORY_MAX_ENTRY = 8000       # 单条记忆上限 8000 字符


def _save_memory(content: str) -> dict:
    """把关键信息追加写入本地记忆文件（markdown，自动带时间戳）"""
    content = (content or "").strip()
    if not content:
        return _blocked("[记忆] 内容为空，未保存")
    if len(content) > _MEMORY_MAX_ENTRY:
        return _blocked(f"[记忆] 单条内容过长（{len(content)} 字符 > {_MEMORY_MAX_ENTRY}）")
    try:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        # 超限时截断：保留尾部内容
        if MEMORY_FILE.exists() and MEMORY_FILE.stat().st_size > _MEMORY_MAX_TOTAL:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                old = f.read()
            old = old[-(_MEMORY_MAX_TOTAL // 2):]   # 保留最近 ~25KB
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                f.write("<!-- 记忆已达上限，旧内容已截断 -->\n" + old)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n## {stamp}\n{content}\n")
        return {"text": f"已保存到记忆文件 memory.md（{len(content)} 字符）", "images": []}
    except Exception as e:
        return _blocked(f"[记忆] 保存失败: {e}")


def _load_memory() -> dict:
    """读取本地记忆文件完整内容"""
    try:
        if not MEMORY_FILE.exists():
            return {"text": "（记忆文件为空，暂无历史记忆。可在遇到值得记住的关键信息时调用 save_memory 保存。）",
                    "images": []}
        size = MEMORY_FILE.stat().st_size
        if size > _MEMORY_MAX_TOTAL:
            return _blocked(f"[记忆] 记忆文件过大（{size // 1024}KB > {_MEMORY_MAX_TOTAL // 1024}KB），请人工清理")
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            text = f.read().strip() or "（记忆为空）"
        return {"text": text, "images": []}
    except Exception as e:
        return _blocked(f"[记忆] 读取失败: {e}")


# ---------- 系统信息（原 MCP server 工具内置化，真实 API） ----------

def _os_name() -> str:
    """注册表读取真实系统产品名（Win10/Win11 内核同为 10.0，按 build>=22000 修正为 Win11）"""
    try:
        import platform
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
            name = winreg.QueryValueEx(k, "ProductName")[0]
            display = winreg.QueryValueEx(k, "DisplayVersion")[0]
            build = int(winreg.QueryValueEx(k, "CurrentBuildNumber")[0])
        if build >= 22000 and name.startswith("Windows 10"):
            name = name.replace("Windows 10", "Windows 11")
        return f"{name}（{display}，内部版本 {build}）"
    except (OSError, ValueError):
        import platform
        return f"{platform.system()} {platform.release()}"


def _total_memory_mb() -> int:
    """读取物理内存总量（MB）"""
    try:
        import ctypes
        class _MS(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        ms = _MS()
        ms.dwLength = ctypes.sizeof(_MS)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
            return ms.ullTotalPhys // (1024 * 1024)
    except Exception:
        pass
    return 0


def _system_info() -> dict:
    import platform
    import socket
    import sys
    text = (f"主机名: {socket.gethostname()}\n"
            f"系统: {_os_name()}\n"
            f"架构: {platform.machine()}\n"
            f"CPU 核心数: {os.cpu_count()}\n"
            f"物理内存: {_total_memory_mb()} MB\n"
            f"Python: {sys.version.split()[0]}")
    return {"text": text, "images": []}


def _get_time() -> dict:
    return {"text": time.strftime("%Y-%m-%d %H:%M:%S"), "images": []}


def _env_var(name: str) -> dict:
    name = (name or "").strip()
    if not name:
        return _blocked("[env_var] 缺少环境变量名（name）")
    v = os.environ.get(name)
    return {"text": f"{name} = {v}" if v is not None else f"环境变量 {name} 不存在",
            "images": []}


# ---------- WinAppMigrator 能力内置化 ----------

def _fmt_size(n: int) -> str:
    n = int(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _find_app(name: str):
    """按名称模糊匹配已安装应用；返回 AppInfo 或 None"""
    from winapp_migrator.core.app_scanner import AppScanner
    key = (name or "").strip().lower()
    apps = AppScanner().scan_all()
    for a in apps:
        if key in a.name.lower():
            return a
    return None


def _optimize_memory() -> dict:
    from winapp_migrator.core.memory_optimizer import optimize_memory
    result = optimize_memory()
    details = result.get("details") or []
    text = f"内存优化完成：{result.get('message', '')}"
    if details:
        text += "\n" + "\n".join(f"  - {d}" for d in details[:20])
    return {"text": text, "images": []}


def _uninstall_app(name: str) -> dict:
    from winapp_migrator.core.uninstaller import Uninstaller
    if not (name or "").strip():
        return _blocked("[uninstall_app] 缺少应用名称（name）")
    app = _find_app(name)
    if not app:
        return _blocked(f"未找到应用「{name}」。可先用 find_app 或 /screenshot 查看已装应用")
    plan = Uninstaller().build_plan(app)
    result = Uninstaller().uninstall(plan)
    return {"text": f"应用「{app.name}」卸载：{result.get('message', '')}", "images": []}


def _migrate_app(name: str, target: str) -> dict:
    from winapp_migrator.core.orchestrator import MigrationOrchestrator
    if not (name or "").strip() or not (target or "").strip():
        return _blocked("[migrate_app] 需要 name 与 target 参数")
    app = _find_app(name)
    if not app:
        return _blocked(f"未找到应用「{name}」。可先用 find_app 查询")
    result = MigrationOrchestrator().migrate(app, Path(target))
    state = "成功" if result.get("success") else "失败"
    return {"text": f"应用「{app.name}」迁移{state}：{result.get('message', '')}", "images": []}


# 当前活跃下载任务（供 UI 轮询快照渲染进度条）
_active_download = None


def get_active_download():
    return _active_download


def set_active_download(task):
    global _active_download
    _active_download = task


def clear_active_download():
    global _active_download
    _active_download = None


def cancel_active_download():
    """停止按钮触发时取消后台下载任务"""
    global _active_download
    t, _active_download = _active_download, None
    if t is not None:
        try:
            t.cancel()
        except Exception:
            pass


def _http_request(url: str, timeout: int = 15, max_bytes: int = 512 * 1024,
                  method: str = "GET", headers: dict = None, body: str = None) -> str:
    """真实 HTTP 请求：urllib 标准库，支持 GET/POST/PUT/DELETE/PATCH + 请求头/请求体。
    自动探测响应编码（响应头 charset → HTML meta → utf-8），保证中文页（含 GBK）解码准确。"""
    import gzip
    import re as _re
    import urllib.request
    method = (method or "GET").upper()
    hdrs = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/126.0 Safari/537.36"),
        "Accept": "text/html,application/json,text/plain,*/*",
        "Accept-Encoding": "identity",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if headers:
        hdrs.update({str(k): str(v) for k, v in headers.items()
                     if k and v is not None})
    data = None
    if body:
        data = body.encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(max_bytes + 1)
        # 编码探测 1：响应头 Content-Type charset
        charset = None
        try:
            m = _re.search(r"charset=([\w-]+)",
                           resp.headers.get("Content-Type", ""), _re.I)
            if m:
                charset = m.group(1)
        except Exception:
            pass
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
    # 少数服务器无视 Accept-Encoding 仍返回 gzip：按魔数判断解压
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    # 编码探测 2：HTML <meta charset>（GBK 等老站点常见，硬编码 utf-8 会乱码）
    if not charset:
        m = _re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', raw[:2048], _re.I)
        if m:
            charset = m.group(1).decode("ascii", "ignore")
    try:
        return raw.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _html_to_text(html: str, max_chars: int = 8000) -> str:
    """HTML → 可读文本：提取标题 + 剥离 script/style/nav 等噪音 + 去标签压缩空白，
    让截断窗口内尽量是有效正文信息。"""
    import re as _re
    m = _re.search(r"<title[^>]*>(.*?)</title>", html, _re.S | _re.I)
    title = _re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
    body = _re.sub(r"(?is)<(script|style|nav|footer|header|aside|iframe|svg|noscript)[^>]*>.*?</\1>",
                   " ", html)
    body = _re.sub(r"(?s)<!--.*?-->", " ", body)
    body = _re.sub(r"(?i)</(p|div|h[1-6]|li|tr|br|section|article)>", "\n", body)
    body = _re.sub(r"<[^>]+>", "", body)
    body = _html.unescape(body)
    body = _re.sub(r"[ \t\r\f\v]+", " ", body)
    body = _re.sub(r"\n\s*\n+", "\n", body).strip()
    out = title if title else ""
    if body:
        out = (out + "\n" if out else "") + body
    return out[:max_chars]


def _web_fetch(url: str, method: str = "GET", headers: dict = None,
               body: str = "", max_chars: int = 8000) -> dict:
    """联网请求 URL 文本内容（网页/JSON/raw/REST API）。
    HTML 页面自动提取标题+正文文本（去脚本/标签噪音），JSON/纯文本按原样返回。"""
    url = (url or "").strip()
    if not url:
        return _blocked("[web_fetch] 缺少 URL")
    if not url.lower().startswith(("http://", "https://")):
        return _blocked("[web_fetch] 仅支持 http/https 地址")
    try:
        text = _http_request(url, method=method, headers=headers, body=body or None)
    except Exception as e:
        return _blocked(f"[web_fetch] 请求失败: {e}")
    text = text.strip()
    if not text:
        return _blocked("[web_fetch] 返回内容为空")
    # HTML 页面：提取正文文本，确保截断窗口内是有效信息
    if text.lstrip().startswith(("<",)):
        text = _html_to_text(text, max_chars=max_chars)
    else:
        text = _html.unescape(text)
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n…（内容过长，已截断至 {max_chars} 字符）"
    return {"text": f"[web_fetch] {method} {url}\n{text}", "images": []}


def _clipboard(action: str = "read", text: str = "") -> dict:
    """读写系统剪贴板（真实 Win32 API，Unicode 文本）"""
    import ctypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    # 64 位句柄必须显式声明类型，否则默认 c_int 会截断 HGLOBAL 导致访问无效内存
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_int
    user32.EmptyClipboard.argtypes = []
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.argtypes = []
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

    CF_UNICODETEXT = 13
    if not user32.OpenClipboard(None):
        return _blocked("[clipboard] 打开剪贴板失败（可能被其他程序占用）")
    try:
        if action == "write":
            data = (text or "").encode("utf-16-le") + b"\x00\x00"
            user32.EmptyClipboard()
            h = kernel32.GlobalAlloc(0x0042, len(data))
            if not h:
                return _blocked("[clipboard] 内存分配失败")
            ptr = kernel32.GlobalLock(h)
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(h)
            user32.SetClipboardData(CF_UNICODETEXT, h)
            return {"text": f"已写入剪贴板（{len(text)} 字符）", "images": []}
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return {"text": "（剪贴板为空或非文本内容）", "images": []}
        ptr = kernel32.GlobalLock(h)
        value = ctypes.wstring_at(ptr)
        kernel32.GlobalUnlock(h)
        return {"text": f"[clipboard] 当前剪贴板内容：\n{value[:4000]}", "images": []}
    finally:
        user32.CloseClipboard()


def _extract_text(path: str) -> dict:
    """提取文档纯文本：txt/md/log/json/csv 直接读，docx/xlsx 解析 zip+XML（标准库），
    pdf 提示先 pip install pypdf"""
    import csv as _csv
    import html as _html
    import re as _re
    import zipfile
    p = _resolve(path)
    if not p.is_file():
        return _blocked(f"[extract_text] 文件不存在: {p}")
    suffix = p.suffix.lower()
    try:
        if suffix in (".txt", ".md", ".log", ".json"):
            return {"text": p.read_text(encoding="utf-8", errors="replace")[:8000], "images": []}
        if suffix == ".csv":
            with p.open(encoding="utf-8-sig", errors="replace", newline="") as f:
                rows = list(_csv.reader(f))
            return {"text": "\n".join(" | ".join(r) for r in rows)[:8000], "images": []}
        if suffix == ".docx":
            # docx = zip + word/document.xml，段落 <w:p> 内 <w:t> 为文本
            with zipfile.ZipFile(p) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
            paras = ["".join(_re.findall(r"<w:t[^>]*>(.*?)</w:t>", seg, _re.S))
                     for seg in xml.split("</w:p>")]
            return {"text": "\n".join(_html.unescape(x) for x in paras if x.strip())[:8000], "images": []}
        if suffix == ".xlsx":
            # xlsx = zip + xl/sharedStrings.xml（共享字符串）+ xl/worksheets/sheetN.xml（单元格）
            with zipfile.ZipFile(p) as z:
                names = z.namelist()
                shared = []
                if "xl/sharedStrings.xml" in names:
                    sx = z.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
                    shared = ["".join(_re.findall(r"<t[^>]*>(.*?)</t>", seg, _re.S))
                              for seg in sx.split("</si>")]
                out = []
                for sh in sorted(n for n in names
                                 if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")):
                    wx = z.read(sh).decode("utf-8", errors="replace")
                    out.append(f"[{sh}]")
                    for row in wx.split("</row>"):
                        cells = []
                        for cm in _re.finditer(r'<c r="([A-Z]+\d+)"([^>]*)>(.*?)</c>', row, _re.S):
                            ref, attrs, inner = cm.group(1), cm.group(2), cm.group(3)
                            vm = _re.search(r"<v>(.*?)</v>", inner, _re.S)
                            val = vm.group(1) if vm else ""
                            if 't="s"' in attrs and val:
                                try:
                                    val = shared[int(val)]
                                except (ValueError, IndexError):
                                    pass
                            elif 't="inlineStr"' in attrs:
                                ism = _re.search(r"<t[^>]*>(.*?)</t>", inner, _re.S)
                                val = ism.group(1) if ism else ""
                            cells.append(f"{ref}:{_html.unescape(val)}")
                        if cells:
                            out.append(" ".join(cells))
                return {"text": "\n".join(out)[:8000], "images": []}
        if suffix == ".pptx":
            # pptx = zip + ppt/slides/slideN.xml，文本在 <a:t>，标题文字带 txBody
            with zipfile.ZipFile(p) as z:
                names = z.namelist()
                out = []
                for sn in sorted(n for n in names
                                 if n.startswith("ppt/slides/slide") and n.endswith(".xml")):
                    sx = z.read(sn).decode("utf-8", errors="replace")
                    texts = _re.findall(r"<a:t>(.*?)</a:t>", sx, _re.S)
                    out.append(f"[{sn}]")
                    out.append(" | ".join(_html.unescape(t) for t in texts))
                return {"text": "\n".join(out)[:8000], "images": []}
        if suffix == ".pdf":
            return _blocked("[extract_text] PDF 文本提取需 pypdf：先 run_command 执行 "
                            "pip install pypdf 后重试（pip 已在命令白名单）")
        return _blocked(f"[extract_text] 不支持格式 {suffix}（支持 txt/csv/docx/pptx/xlsx，pdf 需装 pypdf）")
    except Exception as e:
        return _blocked(f"[extract_text] 解析失败: {e}")


# 默认商务专业风主题色（深蓝 + 深灰）
_DOC_NAVY = "1F3864"          # 主色：深蓝
_DOC_NAVY_SOFT = "8EAADB"     # 浅蓝（副标题/辅助）
_DOC_DARK = "404040"          # 正文深灰
_DOC_FONT = "微软雅黑"
# 预置配色主题（AI 传 style.theme 即可整体换肤；base=主色 soft=浅辅助色 dark=深色正文/文字）
_DOC_THEMES = {
    "business":   {"base": "1F3864", "soft": "8EAADB", "dark": "404040"},
    "black-gold": {"base": "1A1A1A", "soft": "C9A227", "dark": "3B3B3B"},
    "green":      {"base": "2E5E4E", "soft": "A8C6B8", "dark": "333F3B"},
    "warm":       {"base": "B0561A", "soft": "E8C39E", "dark": "5A4636"},
    "tech":       {"base": "0E5A8A", "soft": "7FB8DE", "dark": "2B3A4A"},
    "vivid":      {"base": "E4572E", "soft": "F5B99B", "dark": "4A403C"},
    "purple":     {"base": "5B2D8F", "soft": "BDA8D8", "dark": "3D3352"},
    "pastel":     {"base": "7A9CC6", "soft": "D8E2F0", "dark": "4A5A6A"},
    "dark":       {"base": "23272E", "soft": "8E98A6", "dark": "E8EAED"},
    "red":        {"base": "8C2F39", "soft": "E0B4B9", "dark": "4A3035"},
}


def _doc_style(style: dict) -> dict:
    """解析 style 参数：返回合并后的样式字典（theme 预置色板 + 字段覆盖 + 默认兜底）。
    键：base/soft/dark(颜色)，font，align，line_spacing，title_size，body_size 等。"""
    s = dict(style or {})
    theme = str(s.get("theme") or "business").lower()
    pal = _DOC_THEMES.get(theme) or _DOC_THEMES["business"]
    merged = {
        "base": str(s.get("base_color") or pal["base"]),
        "soft": pal["soft"],
        "dark": str(s.get("text_color") or pal["dark"]),
        "heading": str(s.get("heading_color") or ""),
        "font": str(s.get("font_name") or _DOC_FONT),
        "align": str(s.get("align") or "left"),
        "line_spacing": float(s.get("line_spacing") or 1.5),
        "title_size": int(s.get("title_size") or 22),
        "body_size": int(s.get("body_size") or 11),
    }
    if merged["heading"]:
        merged["base"] = merged["heading"]
    return merged


def _docx_set_font(run, size=None, bold=None, color=None, font=None):
    """设置 run 字体（含东亚字体，默认微软雅黑）"""
    from docx.shared import Pt, RGBColor
    f = font or _DOC_FONT
    run.font.name = f
    from docx.oxml.ns import qn
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = rPr.makeelement(qn("w:rFonts"), {})
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:eastAsia"), f)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _docx_set_bg(doc, hex_color: str):
    """设置 Word 整页背景色（w:background 颜色）"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    bg = OxmlElement("w:background")
    bg.set(qn("w:color"), hex_color.strip().lstrip("#"))
    doc.element.insert(0, bg)


# 内置文生图：调用 agnes images/generations（真实 API，非 mock）
_GEN_IMAGE_URL = "https://api.agnes-ai.cn/v1/images/generations"
_GEN_IMAGE_MODEL = "agnes-image-2.1-flash"
_GEN_RATIOS = ("1:1", "3:4", "4:3", "16:9", "9:16")


def _generate_image(prompt: str, ratio: str = "1:1", dest_dir: str = "") -> dict:
    """AI 文生图：调用内置 agnes 图片生成 API，下载到本地并返回本地路径。

    返回文本含本地路径，供 create_docx/create_pptx/create_xlsx 的 image 参数直接引用。
    """
    import base64
    import urllib.error
    import urllib.request
    prompt = (prompt or "").strip()
    if not prompt:
        return _blocked("[generate_image] 缺少 prompt（要生成的画面描述）")
    ratio = (ratio or "1:1").strip().lower()
    if ratio not in _GEN_RATIOS:
        ratio = "1:1"
    from winapp_migrator.core import agent_llm
    payload = {"model": _GEN_IMAGE_MODEL, "prompt": prompt,
               "size": "1K", "ratio": ratio,
               "extra_body": {"response_format": "url"}}
    req = urllib.request.Request(
        _GEN_IMAGE_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": "WinAppMigrator/1.0 AgentClient",
                 "Authorization": f"Bearer {agent_llm.DEFAULT_API_KEY}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return _blocked(f"[generate_image] 生成失败 HTTP {e.code}: "
                        f"{e.read().decode('utf-8', 'replace')[:300]}")
    except Exception as e:
        return _blocked(f"[generate_image] 生成失败: {e}")
    items = [d for d in (data.get("data") or []) if isinstance(d, dict)]
    if not items:
        return _blocked(f"[generate_image] API 未返回图片: {str(data)[:200]}")
    # 保存目录：显式指定 → 工作目录相对解析；否则 工作目录/images（无则桌面/images）
    if (dest_dir or "").strip():
        base = _resolve(dest_dir)
    elif WORKDIR:
        base = Path(WORKDIR) / "images"
    else:
        base = Path.home() / "Desktop" / "images"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        base = Path.home() / "Desktop" / "images"
        base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved = []
    for i, d in enumerate(items[:4], 1):
        url = d.get("url") or ""
        b64 = d.get("b64_json") or ""
        try:
            if b64:
                raw = base64.b64decode(b64)
            else:
                with urllib.request.urlopen(url, timeout=60) as rr:
                    raw = rr.read()
            path = base / f"img_{stamp}_{i}.png"
            path.write_bytes(raw)
            saved.append(str(path))
        except Exception as e:
            saved.append(f"(下载失败 {url}: {e})")
    if not any(not s.startswith("(下载失败") for s in saved):
        return _blocked("[generate_image] 图片下载失败：" + "；".join(saved))
    return {"text": "已生成图片素材（本地路径，供 image 参数引用）：\n"
                    + "\n".join(saved)
                    + "\n把这些路径作为 create_docx/create_pptx/create_xlsx 的 image 参数传入。",
            "images": []}


def _create_docx(path: str, title: str, paragraphs: list, images: list = None,
                 style: dict = None, wordart: list = None) -> dict:
    """生成 Word 文档（python-docx）：默认商务专业风，支持 style 自定义配色/字体/排版/背景。
    段落支持轻量标记：'# '/'## '/'### ' 为标题层级，'- '/'* ' 为项目符号，其余为正文。
    images：图片列表，每项为路径字符串或 {path, align, width}（默认居中、宽6英寸，等比缩放防溢出）。
    wordart：艺术字（样式化大字）列表 [{text, size, color, font, align}]。
    style：可选 dict，字段见 schema（theme/base_color/heading_color/text_color/font_name/
           align/line_spacing/title_size/body_size/page/bg_color）。"""
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
    except ImportError:
        return _blocked("[create_docx] 缺少 python-docx：run_command 执行 pip install python-docx")
    p = _resolve(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        st = _doc_style(style)
        f, base, soft, dark = st["font"], st["base"], st["soft"], st["dark"]
        body_size, title_size = st["body_size"], st["title_size"]
        ls = st["line_spacing"]
        align_map = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
                     "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}
        body_align = align_map.get(st["align"], WD_ALIGN_PARAGRAPH.LEFT)
        doc = Document()
        if str(style.get("page") if isinstance(style, dict) else "").lower() == "landscape":
            from docx.enum.section import WD_ORIENT
            sec = doc.sections[0]
            sec.orientation = WD_ORIENT.LANDSCAPE
            sec.page_width, sec.page_height = sec.page_height, sec.page_width
        # 页面背景色（整页背景）
        bgc = str(style.get("bg_color") if isinstance(style, dict) else "").strip() or ""
        if bgc:
            _docx_set_bg(doc, bgc)
        if (title or "").strip():
            h = doc.add_paragraph()
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = h.add_run(str(title))
            _docx_set_font(r, size=title_size, bold=True, color=base, font=f)
            h.paragraph_format.space_after = Pt(14)
        # 艺术字（样式化大字）：大幅加粗彩色文字，用于标题/强调
        for wa in (wordart or []):
            wp = doc.add_paragraph()
            wp.alignment = align_map.get(str(wa.get("align") or "center").lower(),
                                         WD_ALIGN_PARAGRAPH.CENTER)
            wr = wp.add_run(str(wa.get("text") or ""))
            _docx_set_font(wr, size=int(wa.get("size") or 36), bold=True,
                           color=str(wa.get("color") or base).strip() or base,
                           font=str(wa.get("font") or f).strip() or f)
            wp.paragraph_format.space_after = Pt(6)
        for para in (paragraphs or []):
            para = str(para).strip()
            if not para:
                doc.add_paragraph()
                continue
            # 轻量标记：标题层级 / 项目符号 / 正文
            if para.startswith("### "):
                h = doc.add_paragraph()
                r = h.add_run(para[4:])
                _docx_set_font(r, size=max(11, body_size - 1), bold=True, color=dark, font=f)
                h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(8), Pt(4)
            elif para.startswith("## "):
                h = doc.add_paragraph()
                r = h.add_run(para[3:])
                _docx_set_font(r, size=body_size + 2, bold=True, color=soft, font=f)
                h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(10), Pt(4)
            elif para.startswith("# "):
                h = doc.add_paragraph()
                r = h.add_run(para[2:])
                _docx_set_font(r, size=body_size + 5, bold=True, color=base, font=f)
                h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(12), Pt(6)
            elif para.startswith(("- ", "* ")):
                li = doc.add_paragraph()
                r = li.add_run(para[2:])
                _docx_set_font(r, size=body_size, color=dark, font=f)
                li.paragraph_format.left_indent = Pt(18)
                li.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
                # 手工项目符号圆点（避免依赖样式模板缺失）
                li.style = doc.styles["List Bullet"] if "List Bullet" in doc.styles else li.style
            else:
                body = doc.add_paragraph()
                r = body.add_run(para)
                _docx_set_font(r, size=body_size, color=dark, font=f)
                pf = body.paragraph_format
                pf.space_after = Pt(6)
                pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
                pf.line_spacing = ls
                if body_align != WD_ALIGN_PARAGRAPH.LEFT:
                    body.alignment = body_align
        # 图片：每张作为独立段落插入文档末尾（支持水平对齐 + 宽度，等比缩放防溢出页面）
        missing = []
        for img in (images or []):
            if isinstance(img, str):
                img_src, ialign, iwidth = img, "center", 6.0
            else:
                img_src = str(img.get("path") or "")
                ialign = str(img.get("align") or "center").lower()
                try:
                    iwidth = float(img.get("width") or 6.0)
                except (TypeError, ValueError):
                    iwidth = 6.0
            img_p = _resolve(img_src)
            if not img_p.is_file():
                missing.append(str(img_src))
                continue
            para = doc.add_paragraph()
            para.alignment = align_map.get(ialign, WD_ALIGN_PARAGRAPH.CENTER)
            pic = para.add_run()
            fit = _image_scale(str(img_p), iwidth * 96, 8.5 * 96)
            if fit:
                sc, w, h = fit
                pic.add_picture(str(img_p),
                                width=Inches(w * sc / 96), height=Inches(h * sc / 96))
            else:
                pic.add_picture(str(img_p), width=Inches(min(iwidth, 6.0)))
        doc.save(str(p))
    except Exception as e:
        return _blocked(f"[create_docx] 生成失败: {e}")
    msg = f"已生成 Word 文档：{p}"
    if missing:
        msg += f"（{len(missing)} 张图片不存在已跳过）"
    return {"text": msg, "images": []}


def _pptx_font(run, size, bold=False, color="404040", font=None):
    """设置 pptx run 字体（拉丁 + 东亚，默认微软雅黑）"""
    from pptx.util import Pt
    from pptx.dml.color import RGBColor
    f = font or _DOC_FONT
    run.font.name = f
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    from pptx.oxml.ns import qn
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = rPr.makeelement(qn("a:ea"), {})
        rPr.append(ea)
    ea.set("typeface", f)


# 供 PPT 卡片/图表/图形排版使用的多色板（在主题色基础上增加变化，避免每页单调）
_PPTX_MULTI = ["1F3864", "2E5E4E", "B0561A", "0E5A8A", "5B2D8F", "8C2F39", "E4572E", "3D6B35"]
_PPTX_ARR = "→"


def _pptx_set_transition(slide, transition: str):
    """给幻灯片注入页面切换过渡动画（fade/push/wipe/zoom/random；none 或空则无）。
    python-pptx 不直接支持过渡，需向 <p:sld> 注入 <p:transition> 元素。"""
    name = (str(transition or "").strip().lower())
    if not name or name in ("none", "无"):
        return
    inner = {"fade": "<p:fade/>", "push": '<p:push dir="l"/>',
             "wipe": '<p:wipe dir="l"/>', "zoom": '<p:zoom/><p:zoomOptions dir="in"/>',
             "random": "<p:random/>"}.get(
        name, "<p:fade/>")
    ns = ('xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
          'xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main"')
    xml = f'<p:transition {ns} p14:dur="600">{inner}</p:transition>'
    try:
        from pptx.oxml import parse_xml
        from pptx.oxml.ns import qn
        trans = parse_xml(xml)
        sld = slide._element
        clr = sld.find(qn("p:clrMapOvr"))
        if clr is not None:
            clr.addnext(trans)
        else:
            sld.append(trans)
    except Exception:
        pass


def _pptx_add_cards(slide, cards, f, base):
    """并排彩色卡片：每项 {title, desc, color}，圆角矩形 + 标题 + 说明。"""
    from pptx.util import Inches
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.enum.shapes import MSO_SHAPE
    cards = [c for c in (cards or []) if isinstance(c, dict)]
    if not cards:
        return
    n = len(cards)
    gap = 0.15
    x = 0.6
    y, h = 2.0, 3.6
    w = (13.333 - 1.2 - gap * (n - 1)) / n
    for idx, c in enumerate(cards):
        color = str(c.get("color") or "").strip() or _PPTX_MULTI[idx % len(_PPTX_MULTI)]
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                      Inches(x), Inches(y), Inches(w), Inches(h))
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor.from_string(color)
        card.line.color.rgb = RGBColor.from_string(color)
        card.shadow.inherit = False
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.15)
        tf.margin_top = tf.margin_bottom = Inches(0.15)
        p1 = tf.paragraphs[0]
        p1.alignment = PP_ALIGN.CENTER
        r1 = p1.add_run()
        r1.text = str(c.get("title") or "")
        _pptx_font(r1, 22, bold=True, color="FFFFFF", font=f)
        desc = str(c.get("desc") or "").strip()
        if desc:
            p2 = tf.add_paragraph()
            p2.alignment = PP_ALIGN.CENTER
            r2 = p2.add_run()
            r2.text = desc
            _pptx_font(r2, 14, color="FFFFFF", font=f)
        x += w + gap


def _pptx_add_table(slide, spec, f, base):
    """添加结构化表格：{header: [..], rows: [[..]], title}，表头主色底白字。"""
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    spec = spec or {}
    header = [str(h) for h in (spec.get("header") or [])]
    rows = spec.get("rows") or []
    ncols = max(len(header), max((len(r) for r in rows if isinstance(r, (list, tuple))), default=0))
    if not ncols:
        return
    nrows = 1 + len(rows)
    y = 1.7
    if str(spec.get("title") or "").strip():
        tb = slide.shapes.add_textbox(Inches(0.6), Inches(1.35), Inches(12.1), Inches(0.5))
        r = tb.text_frame.paragraphs[0].add_run()
        r.text = str(spec["title"])
        _pptx_font(r, 18, bold=True, color=base, font=f)
        y = 1.95
    tbl = slide.shapes.add_table(nrows, ncols, Inches(0.6), Inches(y),
                                 Inches(12.1), Inches(min(5.0, 0.4 * nrows))).table
    tbl.columns[0].width = Inches(3.0)
    for ci in range(1, ncols):
        tbl.columns[ci].width = Inches(9.1 / max(ncols - 1, 1))
    for rn in range(nrows):
        for cn in range(ncols):
            cell = tbl.cell(rn, cn)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            if rn == 0:
                val = header[cn] if cn < len(header) else ""
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor.from_string(base)
            else:
                src = rows[rn - 1]
                val = str(src[cn]) if isinstance(src, (list, tuple)) and cn < len(src) else ""
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor.from_string(
                    "FFFFFF" if rn % 2 == 0 else "EEF2F8")
            para = cell.text_frame.paragraphs[0]
            rr = para.add_run()
            rr.text = val
            _pptx_font(rr, 12, bold=(rn == 0),
                       color="FFFFFF" if rn == 0 else "404040", font=f)
            para.alignment = PP_ALIGN.CENTER if rn == 0 else PP_ALIGN.LEFT


def _pptx_draw_chart(slide, chart, f, base):
    """用原生图形绘制图表：column/bar/line/pie/doughnut。"""
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.enum.shapes import MSO_SHAPE
    ctype = str(chart.get("type") or "column").lower()
    labels = [str(x) for x in (chart.get("labels") or [])]
    raw = [float(v) for v in (chart.get("values") or []) if isinstance(v, (int, float))]
    n = min(len(labels), len(raw))
    if n == 0:
        return
    labels, values = labels[:n], raw[:n]
    title = str(chart.get("title") or "").strip()
    if title:
        tb = slide.shapes.add_textbox(Inches(0.6), Inches(1.35), Inches(12.1), Inches(0.5))
        r = tb.text_frame.paragraphs[0].add_run()
        r.text = title
        _pptx_font(r, 18, bold=True, color=base, font=f)
    if ctype in ("pie", "doughnut"):
        total = sum(values) or 1
        dia = 3.6
        cx, cy = 3.4, 2.0 + 2.2
        start = 0.0
        for i, v in enumerate(values):
            color = _PPTX_MULTI[i % len(_PPTX_MULTI)]
            sweep = v / total * 360.0
            sh = slide.shapes.add_shape(MSO_SHAPE.PIE,
                                        Inches(cx - dia / 2), Inches(cy - dia / 2),
                                        Inches(dia), Inches(dia))
            try:
                sh.adjustments[0] = int(start * 60000)
                sh.adjustments[1] = int((start + sweep) * 60000)
            except Exception:
                pass
            sh.fill.solid()
            sh.fill.fore_color.rgb = RGBColor.from_string(color)
            sh.line.color.rgb = RGBColor.from_string("FFFFFF")
            sh.line.width = Pt(1.5)
            start += sweep
        # 图例（右侧）
        ly = 2.0
        for i, lb in enumerate(labels):
            dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(8.6), Inches(ly), Inches(0.22), Inches(0.22))
            dot.fill.solid()
            dot.fill.fore_color.rgb = RGBColor.from_string(_PPTX_MULTI[i % len(_PPTX_MULTI)])
            dot.line.fill.background()
            tb = slide.shapes.add_textbox(Inches(8.95), Inches(ly - 0.04), Inches(3.9), Inches(0.4))
            rr = tb.text_frame.paragraphs[0].add_run()
            rr.text = f"{lb}  {values[i]:g}"
            _pptx_font(rr, 12, color="404040", font=f)
            ly += 0.42
        return
    x0_in, y0_in, plot_w_in, plot_h_in = 0.8, 2.0, 10.6, 3.8
    vmax = max(values) or 1
    base_y_in = y0_in + plot_h_in
    if ctype == "bar":
        # 横向条形
        bw_in = plot_h_in / n
        for i, v in enumerate(values):
            w_in = plot_w_in * (v / vmax)
            bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                         Inches(x0_in), Inches(base_y_in - (i + 1) * bw_in),
                                         Inches(w_in), Inches(bw_in * 0.7))
            bar.fill.solid()
            bar.fill.fore_color.rgb = RGBColor.from_string(_PPTX_MULTI[i % len(_PPTX_MULTI)])
            bar.line.fill.background()
            tb = slide.shapes.add_textbox(Inches(x0_in + 0.05), Inches(base_y_in - (i + 1) * bw_in - 0.02),
                                          Inches(3.5), Inches(bw_in * 0.7))
            rr = tb.text_frame.paragraphs[0].add_run()
            rr.text = f"{labels[i]}  {v:g}"
            _pptx_font(rr, 11, color="404040", font=f)
    else:
        # 柱状
        bw_in = plot_w_in / n
        for i, v in enumerate(values):
            bh_in = plot_h_in * (v / vmax)
            bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                         Inches(x0_in + i * bw_in + 0.12),
                                         Inches(base_y_in - bh_in),
                                         Inches(min(0.5, bw_in * 0.6)), Inches(bh_in))
            bar.fill.solid()
            bar.fill.fore_color.rgb = RGBColor.from_string(_PPTX_MULTI[i % len(_PPTX_MULTI)])
            bar.line.fill.background()
            tb = slide.shapes.add_textbox(Inches(x0_in + i * bw_in), Inches(base_y_in + 0.05),
                                          Inches(0.9), Inches(0.4))
            rr = tb.text_frame.paragraphs[0].add_run()
            rr.text = labels[i]
            _pptx_font(rr, 10, color="404040", font=f)
            vt = slide.shapes.add_textbox(Inches(x0_in + i * bw_in + 0.1), Inches(base_y_in - bh_in - 0.3),
                                          Inches(0.9), Inches(0.3))
            vr = vt.text_frame.paragraphs[0].add_run()
            vr.text = f"{v:g}"
            _pptx_font(vr, 10, bold=True, color="404040", font=f)


def _pptx_draw_diagram(slide, diagram, f, base):
    """图形排版：mindmap(思维导图)/flow(流程图)/compare(对比)/cycle(循环)。"""
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.enum.shapes import MSO_SHAPE
    dtype = str(diagram.get("type") or "mindmap").lower()
    items = [it for it in (diagram.get("items") or [])]
    title = str(diagram.get("title") or "").strip()
    if title:
        tb = slide.shapes.add_textbox(Inches(0.6), Inches(1.35), Inches(12.1), Inches(0.5))
        r = tb.text_frame.paragraphs[0].add_run()
        r.text = title
        _pptx_font(r, 18, bold=True, color=base, font=f)
    if dtype == "flow":
        # 横向流程框 + 箭头
        n = len(items)
        if n == 0:
            return
        gap = 0.5
        bw = min(2.6, (12.1 - gap * (n - 1)) / n)
        total_w = n * bw + (n - 1) * gap
        x = (13.333 - total_w) / 2
        y = 3.0
        for i, it in enumerate(items):
            box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                         Inches(x), Inches(y), Inches(bw), Inches(1.4))
            color = _PPTX_MULTI[i % len(_PPTX_MULTI)]
            box.fill.solid()
            box.fill.fore_color.rgb = RGBColor.from_string(color)
            box.line.fill.background()
            tf = box.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            r = p.add_run()
            r.text = str(it)
            _pptx_font(r, 14, bold=True, color="FFFFFF", font=f)
            if i < n - 1:
                ar = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW,
                                            Inches(x + bw + 0.05), Inches(y + 0.45),
                                            Inches(gap - 0.1), Inches(0.5))
                ar.fill.solid()
                ar.fill.fore_color.rgb = RGBColor.from_string(base)
                ar.line.fill.background()
            x += bw + gap
    elif dtype == "compare":
        # 左右对比 + 中间 VS
        n = len(items)
        if n == 0:
            return
        col_w = 5.6
        gap = 0.6
        x_l = 0.6
        x_r = 13.333 - 0.6 - col_w
        y = 2.0
        color_l = _PPTX_MULTI[0]
        color_r = _PPTX_MULTI[1]
        for cf in (x_l, x_r):
            color = color_l if cf == x_l else color_r
            box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                         Inches(cf), Inches(y), Inches(col_w), Inches(4.4))
            box.fill.solid()
            box.fill.fore_color.rgb = RGBColor.from_string(color)
            box.line.fill.background()
            tf = box.text_frame
            tf.word_wrap = True
            tf.margin_left = tf.margin_right = Inches(0.2)
            first = True
            for it in items:
                if isinstance(it, dict):
                    lines = [str(it.get("title") or ""), str(it.get("left") or ""), str(it.get("right") or "")]
                else:
                    lines = [str(it)]
                for ln in lines:
                    if not ln:
                        continue
                    p = tf.paragraphs[0] if first else tf.add_paragraph()
                    first = False
                    r = p.add_run()
                    r.text = ln
                    _pptx_font(r, 14, bold=("title" in (str(it) if not isinstance(it, dict) else ""))
                               or (isinstance(it, dict) and ln == str(it.get("title") or "")),
                               color="FFFFFF", font=f)
        vs = slide.shapes.add_textbox(Inches(x_l + col_w + 0.1), Inches(y + 1.8), Inches(gap - 0.2), Inches(0.8))
        vr = vs.text_frame.paragraphs[0].add_run()
        vr.text = "VS"
        _pptx_font(vr, 24, bold=True, color=base, font=f)
        vs.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    elif dtype == "cycle":
        # 环形：中心圆 + 四周节点
        n = len(items)
        if n == 0:
            return
        cx, cy, radius = 6.67, 3.9, 2.2
        for i, it in enumerate(items):
            ang = -90 + i * (360.0 / n)
            import math
            bx = cx + radius * math.cos(math.radians(ang)) - 1.0
            by = cy + radius * math.sin(math.radians(ang)) - 0.6
            node = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(bx), Inches(by), Inches(2.0), Inches(1.2))
            color = _PPTX_MULTI[i % len(_PPTX_MULTI)]
            node.fill.solid()
            node.fill.fore_color.rgb = RGBColor.from_string(color)
            node.line.fill.background()
            tf = node.text_frame
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            r = p.add_run()
            r.text = str(it)
            _pptx_font(r, 12, bold=True, color="FFFFFF", font=f)
        center = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - 1.0), Inches(cy - 0.8), Inches(2.0), Inches(1.6))
        center.fill.solid()
        center.fill.fore_color.rgb = RGBColor.from_string(base)
        center.line.fill.background()
        tf = center.text_frame
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = str(diagram.get("center") or "")
        _pptx_font(r, 14, bold=True, color="FFFFFF", font=f)
    else:
        # mindmap：中心主题 + 四周分支
        center = str(diagram.get("center") or "").strip()
        n = len(items)
        if n == 0:
            return
        cx, cy = 6.67, 3.9
        cnode = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                       Inches(cx - 1.5), Inches(cy - 0.6), Inches(3.0), Inches(1.2))
        cnode.fill.solid()
        cnode.fill.fore_color.rgb = RGBColor.from_string(base)
        cnode.line.fill.background()
        tf = cnode.text_frame
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = center or "主题"
        _pptx_font(r, 16, bold=True, color="FFFFFF", font=f)
        positions = [(6.67, 1.2), (6.67, 6.4), (1.2, 3.9), (12.13, 3.9),
                     (1.2, 1.4), (12.13, 1.4), (1.2, 6.4), (12.13, 6.4)]
        for i, it in enumerate(items):
            if i >= len(positions):
                break
            bx, by = positions[i]
            node = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                          Inches(bx), Inches(by), Inches(2.6), Inches(1.0))
            color = _PPTX_MULTI[i % len(_PPTX_MULTI)]
            node.fill.solid()
            node.fill.fore_color.rgb = RGBColor.from_string(color)
            node.line.fill.background()
            tf = node.text_frame
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            r = p.add_run()
            r.text = str(it)
            _pptx_font(r, 12, bold=True, color="FFFFFF", font=f)


def _create_pptx(path: str, title: str, slides: list, style: dict = None) -> dict:
    """生成 PowerPoint（python-pptx）：16:9 宽屏，支持多色卡片/表格/图表/图形排版/切换动画。
    style 可选：theme(配色)/accent(强调色)/cover_style(封面)/transition(切换动画)/
    title_color/bg_color/font_name/bullet_style/title_size/body_size；
    每页 slides 项可带 title/bullets/cards/table/chart/diagram/image/wordart/
    bg_color/title_color/layout。"""
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN
        from pptx.enum.shapes import MSO_SHAPE
    except ImportError:
        return _blocked("[create_pptx] 缺少 python-pptx：run_command 执行 pip install python-pptx")
    p = _resolve(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        st = _doc_style(style)
        f, base, soft, dark = st["font"], st["base"], st["soft"], st["dark"]
        _s = style or {}
        title_size = int(_s.get("title_size") or 26)
        body_size = int(_s.get("body_size") or 18)
        accent = str(_s.get("accent") or "").strip() or base
        bg_color = str((style or {}).get("bg_color") or "FFFFFF")
        title_color = str((style or {}).get("title_color") or base)
        cover_style = str((style or {}).get("cover_style") or "solid").lower()
        transition = str((style or {}).get("transition") or "fade").lower()
        bullet_map = {"dot": "•  ", "number": "{}.  ", "arrow": "→  ", "check": "✓  "}
        bullet_fmt = bullet_map.get(str((style or {}).get("bullet_style") or "dot").lower(), "•  ")
        prs = Presentation()
        prs.slide_width = Inches(13.333)   # 16:9
        prs.slide_height = Inches(7.5)
        blank = prs.slide_layouts[6]
        # 标题页
        if (title or "").strip():
            s = prs.slides.add_slide(blank)
            _pptx_set_transition(s, transition)
            cover = str(title)
            if cover_style == "split":
                left = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(5.2), prs.slide_height)
                left.fill.solid()
                left.fill.fore_color.rgb = RGBColor.from_string(base)
                left.line.fill.background()
                tb = s.shapes.add_textbox(Inches(6.0), Inches(2.8), Inches(6.8), Inches(2.0))
                tf = tb.text_frame
                tf.word_wrap = True
                r = tf.paragraphs[0].add_run()
                r.text = cover
                _pptx_font(r, 36, bold=True, color=base, font=f)
                tf.paragraphs[0].alignment = PP_ALIGN.LEFT
            elif cover_style == "centered":
                tb = s.shapes.add_textbox(Inches(1), Inches(2.4), Inches(11.333), Inches(1.8))
                tf = tb.text_frame
                tf.word_wrap = True
                r = tf.paragraphs[0].add_run()
                r.text = cover
                _pptx_font(r, 40, bold=True, color=base, font=f)
                tf.paragraphs[0].alignment = PP_ALIGN.CENTER
                ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6.0), Inches(4.3), Inches(1.3), Pt(4))
                ln.fill.solid()
                ln.fill.fore_color.rgb = RGBColor.from_string(soft)
                ln.line.fill.background()
            else:
                bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
                bg.fill.solid()
                bg.fill.fore_color.rgb = RGBColor.from_string(base)
                bg.line.fill.background()
                tb = s.shapes.add_textbox(Inches(1), Inches(2.6), Inches(11.333), Inches(1.6))
                tf = tb.text_frame
                tf.word_wrap = True
                r = tf.paragraphs[0].add_run()
                r.text = cover
                _pptx_font(r, 40, bold=True, color="FFFFFF", font=f)
                tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        # 内容页
        missing = []
        for i, item in enumerate(slides or [], 1):
            if not isinstance(item, dict):
                continue
            slide = prs.slides.add_slide(blank)
            _pptx_set_transition(slide, transition)
            pg_bg = str(item.get("bg_color") or bg_color)
            pg_title = str(item.get("title_color") or title_color)
            layout = str(item.get("layout") or "").lower()
            if pg_bg.lower() != "ffffff":
                bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
                bg.fill.solid()
                bg.fill.fore_color.rgb = RGBColor.from_string(pg_bg)
                bg.line.fill.background()
            # 标题 + 底部主色分隔线
            tb = slide.shapes.add_textbox(Inches(0.6), Inches(0.35), Inches(12.1), Inches(0.8))
            r = tb.text_frame.paragraphs[0].add_run()
            r.text = str(item.get("title") or "")
            _pptx_font(r, title_size, bold=True, color=pg_title, font=f)
            line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(1.18),
                                          Inches(12.1), Pt(2.5))
            line.fill.solid()
            line.fill.fore_color.rgb = RGBColor.from_string(accent)
            line.line.fill.background()
            # 彩色卡片（并排展示关键词/数据）
            _pptx_add_cards(slide, item.get("cards"), f, base)
            # 表格
            if item.get("table"):
                _pptx_add_table(slide, item.get("table"), f, base)
            # 图表
            if item.get("chart"):
                _pptx_draw_chart(slide, item.get("chart"), f, base)
            # 图形排版（思维导图/流程图/对比/循环）
            if item.get("diagram"):
                _pptx_draw_diagram(slide, item.get("diagram"), f, base)
            # 要点正文（无 cards/table/chart/diagram 时占满；有则放右侧或下方）
            bullets = item.get("bullets") or []
            has_block = bool(item.get("cards") or item.get("table")
                             or item.get("chart") or item.get("diagram"))
            bx, bw = 0.6, 12.1
            if layout in ("left_image", "right_image"):
                img = item.get("image") or ""
                if isinstance(img, dict) and str(img.get("path") or "").strip():
                    img_p = _resolve(str(img["path"]))
                    if img_p.is_file():
                        fit = _image_scale(str(img_p), 5.6 * 96, 5.2 * 96)
                        if fit:
                            sc, w, h = fit
                            w_in, h_in = w * sc / 96, h * sc / 96
                            iy = 4.6 - h_in / 2
                            ix = 0.7 if layout == "left_image" else 13.333 - w_in - 0.7
                            slide.shapes.add_picture(str(img_p), Inches(ix), Inches(iy),
                                                     width=Inches(w_in), height=Inches(h_in))
                            bx = w_in + 1.4 if layout == "left_image" else 0.7
                            bw = 13.333 - bx - 0.7
            body = slide.shapes.add_textbox(Inches(bx), Inches(1.5), Inches(bw), Inches(5.4))
            tf = body.text_frame
            tf.word_wrap = True
            for j, b in enumerate(bullets):
                para = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
                para.space_after = Pt(10)
                txt = str(b).strip()
                is_sub = txt.startswith("## ")
                is_bullet = txt.startswith("- ")
                if is_sub:
                    txt = txt[3:].strip()
                elif is_bullet:
                    txt = txt[2:].strip()
                r = para.add_run()
                prefix = ""
                if not is_sub and not is_bullet and txt:
                    prefix = bullet_fmt.format(j + 1) if "{}" in bullet_fmt else bullet_fmt
                r.text = (prefix + (("• " if is_bullet else "") + txt)) if txt else ""
                _pptx_font(r, (body_size + 2) if is_sub else body_size,
                           bold=(is_sub or j == 0), color=dark, font=f)
            # 本页插图（非图文分栏时）：要点下方区域
            img = item.get("image") or ""
            if img and layout not in ("left_image", "right_image"):
                if isinstance(img, str):
                    img_src, ialign, iwidth = img, "center", 8.0
                else:
                    img_src = str(img.get("path") or "")
                    ialign = str(img.get("align") or "center").lower()
                    try:
                        iwidth = float(img.get("width") or 8.0)
                    except (TypeError, ValueError):
                        iwidth = 8.0
                img_p = _resolve(img_src)
                if not img_p.is_file():
                    missing.append(str(img_src))
                else:
                    fit = _image_scale(str(img_p), max(iwidth, 1.0) * 96, 1.95 * 96)
                    if fit:
                        sc, w, h = fit
                        w_in, h_in = w * sc / 96, h * sc / 96
                        if ialign == "left":
                            ix = 0.6
                        elif ialign == "right":
                            ix = 13.333 - w_in - 0.6
                        else:
                            ix = (13.333 - w_in) / 2
                        slide.shapes.add_picture(str(img_p), Inches(ix), Inches(5.55),
                                                 width=Inches(w_in), height=Inches(h_in))
                    else:
                        slide.shapes.add_picture(str(img_p), Inches(2.67), Inches(5.55),
                                                 width=Inches(min(iwidth, 8.0)))
            # 本页艺术字（样式化大字）：居中大幅加粗彩色文字
            wa = item.get("wordart") or {}
            if wa and str(wa.get("text") or "").strip():
                wb = slide.shapes.add_textbox(Inches(0.6), Inches(2.8), Inches(12.13), Inches(1.6))
                wtf = wb.text_frame
                wtf.word_wrap = True
                wr = wtf.paragraphs[0].add_run()
                wr.text = str(wa["text"])
                _pptx_font(wr, int(wa.get("size") or 44), bold=True,
                           color=str(wa.get("color") or accent).strip() or accent, font=f)
                wtf.paragraphs[0].alignment = PP_ALIGN.CENTER
            # 页脚页码
            foot = slide.shapes.add_textbox(Inches(11.9), Inches(7.0), Inches(1.0), Inches(0.4))
            fr = foot.text_frame.paragraphs[0].add_run()
            fr.text = str(i)
            _pptx_font(fr, 10, color=soft, font=f)
            foot.text_frame.paragraphs[0].alignment = PP_ALIGN.RIGHT
        prs.save(str(p))
    except Exception as e:
        return _blocked(f"[create_pptx] 生成失败: {e}")
    msg = f"已生成 PPT：{p}"
    if missing:
        msg += f"（{len(missing)} 张图片不存在已跳过）"
    return {"text": msg, "images": []}


def _xlsx_cell(v):
    """单元格值：数字字符串自动转数值，其余保留"""
    if isinstance(v, (int, float)):
        return v
    s = str(v)
    try:
        return int(s) if s.lstrip("+-").isdigit() else \
            float(s) if any(c in s for c in ".eE") and s.strip() else s
    except ValueError:
        return s


def _xlsx_col_width(texts) -> float:
    """估算列宽：中文按 2 字符宽计，带最小/最大限制"""
    w = max((sum(2 if ord(ch) > 127 else 1 for ch in str(t)) for t in texts), default=4)
    return max(8, min(w + 2, 40))


def _create_xlsx(path: str, sheets: list, style: dict = None) -> dict:
    """生成 Excel 工作簿（openpyxl）：默认商务专业风，支持 style 自定义表头/隔行/边框。
    style 可选字段：theme_color/header_fill/header_color/font_name/banded/band_fill/
    freeze_header/auto_filter/border_color/header_size/body_size/header_bold。"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return _blocked("[create_xlsx] 缺少 openpyxl：run_command 执行 pip install openpyxl")
    p = _resolve(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        s = style or {}
        theme = str(s.get("theme") or "business").lower()
        pal = _DOC_THEMES.get(theme) or _DOC_THEMES["business"]
        base = str(s.get("theme_color") or s.get("base_color") or pal["base"])
        header_fill = str(s.get("header_fill") or base)
        header_color = str(s.get("header_color") or "FFFFFF")
        font_name = str(s.get("font_name") or _DOC_FONT)
        banded = bool(s.get("banded", True))
        band_fill = str(s.get("band_fill") or "F2F6FC")
        freeze_header = bool(s.get("freeze_header", True))
        auto_filter = bool(s.get("auto_filter", True))
        border_color = str(s.get("border_color") or "D9D9D9")
        header_size = int(s.get("header_size") or 11)
        body_size = int(s.get("body_size") or 10)
        header_bold = bool(s.get("header_bold", True))
        wb = Workbook()
        wb.remove(wb.active)
        thin = Side(style="thin", color=border_color)
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        missing = []
        for sheet in (sheets or []):
            if not isinstance(sheet, dict):
                continue
            ws = wb.create_sheet(title=str(sheet.get("name") or "Sheet")[:31])
            ws.sheet_properties.tabColor = header_fill
            wa = sheet.get("wordart") or {}
            title_row = str(wa.get("text") or "").strip() if isinstance(wa, dict) else ""
            bg_fill = str(s.get("bg_color") or "").strip()
            rows = [r for r in (sheet.get("rows") or []) if isinstance(r, (list, tuple))]
            for row in rows:
                ws.append([_xlsx_cell(v) for v in row])
            if not rows and not title_row:
                continue
            offset = 1 if title_row else 0
            # 艺术字标题行：顶部大号加粗彩色标题（跨列合并居中）
            if title_row:
                ncols = max((len(r) for r in rows), default=1) or 1
                ws.insert_rows(1)
                a1 = ws.cell(row=1, column=1, value=title_row)
                if ncols > 1:
                    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
                a1.font = Font(name=font_name, size=int(wa.get("size") or 16), bold=True,
                               color=str(wa.get("color") or base).strip() or base)
                a1.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                ws.row_dimensions[1].height = max(24, int(wa.get("size") or 16) + 10)
            hdr = offset + 1
            # 工作表背景色：填充数据区域空单元格（表头/隔行样式覆盖其上）
            if bg_fill and rows:
                for row in ws.iter_rows(min_row=1, max_row=offset + len(rows),
                                        max_col=max((len(r) for r in rows), default=1)):
                    for c in row:
                        if c.value is None:
                            c.fill = PatternFill("solid", fgColor=bg_fill)
            # 表头：主题色底 + 白字加粗居中
            for c in ws[hdr]:
                c.font = Font(name=font_name, size=header_size, bold=header_bold, color=header_color)
                c.fill = PatternFill("solid", fgColor=header_fill)
                c.alignment = Alignment(horizontal="center", vertical="center")
                c.border = border
            ws.row_dimensions[hdr].height = 22
            # 数据行：字体 + 边框 + 隔行变色 + 数字右对齐
            for r_idx, row in enumerate(ws.iter_rows(min_row=hdr + 1), hdr + 1):
                for c in row:
                    c.font = Font(name=font_name, size=body_size, color="404040")
                    c.border = border
                    c.alignment = Alignment(horizontal=("right" if isinstance(c.value, (int, float))
                                                        else "left"), vertical="center")
                    if banded and (r_idx - offset) % 2 == 0:
                        c.fill = PatternFill("solid", fgColor=band_fill)
            # 自动列宽（按数据行估算）+ 冻结首行 + 自动筛选
            for ci in range(max((len(r) for r in rows), default=1)):
                texts = [str(r[ci]) for r in rows if ci < len(r)]
                ws.column_dimensions[get_column_letter(ci + 1)].width = _xlsx_col_width(texts)
            if freeze_header and rows:
                ws.freeze_panes = f"A{hdr + 1}"
            if auto_filter and rows:
                ws.auto_filter.ref = ws.dimensions
            # 表插图：数据下方（支持宽度，等比缩放）
            img = sheet.get("image") or ""
            if img:
                if isinstance(img, str):
                    img_src, iwidth = img, 800.0
                else:
                    img_src = str(img.get("path") or "")
                    try:
                        iwidth = float(img.get("width") or 800.0)
                    except (TypeError, ValueError):
                        iwidth = 800.0
                img_p = _resolve(img_src)
                if not img_p.is_file():
                    missing.append(str(img_src))
                else:
                    from openpyxl.drawing.image import Image as _XlImg
                    xl = _XlImg(str(img_p))
                    fit = _image_scale(str(img_p), max(iwidth, 1.0), 500)
                    if fit:
                        sc, w, h = fit
                        xl.width = int(w * sc)
                        xl.height = int(h * sc)
                    ws.add_image(xl, f"A{offset + len(rows) + 2}")
        wb.save(str(p))
    except Exception as e:
        return _blocked(f"[create_xlsx] 生成失败: {e}")
    msg = f"已生成 Excel 工作簿：{p}"
    if missing:
        msg += f"（{len(missing)} 张图片不存在已跳过）"
    return {"text": msg, "images": []}


def _web_search(query: str, max_results: int = 8) -> dict:
    """联网搜索：Bing（cn.bing.com）关键词搜索，解析结果列表（标题/URL/摘要）"""
    import re as _re
    import urllib.parse
    query = (query or "").strip()
    if not query:
        return _blocked("[web_search] 缺少搜索关键词 query")
    max_results = max(1, min(int(max_results or 8), 10))
    url = f"https://cn.bing.com/search?q={urllib.parse.quote(query)}&mkt=zh-CN"
    try:
        html = _http_request(url)
    except Exception as e:
        return _blocked(f"[web_search] 搜索请求失败: {e}")
    # Bing 结果条目 <li class="b_algo"> 内 <h2><a href> 标题 + <p> 摘要
    items = []
    for m in _re.finditer(r'<li class="b_algo"[^>]*>(.*?)</li>', html, _re.S):
        block = m.group(1)
        am = _re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, _re.S)
        if not am:
            continue
        href = am.group(1).strip()
        title = _re.sub(r"<[^>]+>", "", am.group(2)).strip()
        if not title:
            continue
        pm = _re.search(r"<p[^>]*>(.*?)</p>", block, _re.S)
        snippet = _re.sub(r"<[^>]+>", "", pm.group(1)).strip() if pm else ""
        items.append((title, href, snippet))
        if len(items) >= max_results:
            break
    if not items:
        return {"text": f"[web_search] 未解析到结果（关键词：{query}）。"
                        "可改用 web_fetch 直接抓取搜索页分析。", "images": []}
    import html as _html_mod
    lines = [f"搜索结果（{len(items)} 条，来源 Bing）："]
    for i, (t, h, s) in enumerate(items, 1):
        lines.append(f"{i}. {_html_mod.unescape(t)}")
        lines.append(f"   {h}")
        if s:
            lines.append(f"   摘要：{_html_mod.unescape(s)[:200]}")
    return {"text": "\n".join(lines), "images": []}


def _fast_download(url: str, dest_dir: str) -> dict:
    from winapp_migrator.core.fast_download import DownloadTask
    url = (url or "").strip()
    if not url:
        return _blocked("[fast_download] 缺少下载地址（url）")
    dest = (dest_dir or "").strip() or WORKDIR or os.getcwd()
    try:
        os.makedirs(dest, exist_ok=True)
        task = DownloadTask(url, dest)
        set_active_download(task)   # 注册为活跃下载，UI 轮询快照渲染进度条
        task.start()
        task.join()                 # 等待完成/失败/取消，不做提前放弃
        snap = task.snapshot()
        if snap.get("status") == "done":
            return {"text": f"下载完成：{snap.get('path')}（{_fmt_size(snap.get('total'))}）",
                    "images": []}
        err = snap.get("error") or "进行中（可稍后重试）"
        return {"text": f"下载未完成：状态 {snap.get('status')}，{err}", "images": []}
    except Exception as e:
        clear_active_download()
        return _blocked(f"[fast_download] 下载失败: {e}")


def _create_skill(name: str, description: str, instruction: str) -> dict:
    """生成市场标准 SKILL.md 技能并注册（创建后立即生效）"""
    from winapp_migrator.core import agent_skills
    ok, msg = agent_skills.create_md_skill(name, description, instruction)
    return ({"text": msg, "images": []} if ok else _blocked(msg))


def tool_schemas() -> list:
    """供 LLM tools 参数的完整 schema 列表"""
    return json.loads(json.dumps(TOOLS))
