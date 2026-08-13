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
from winapp_migrator.core import agent_screen
from winapp_migrator.core import agent_find
from winapp_migrator.core import agent_locator

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
_COMMAND_OUTPUT_MAX = 60000       # 单次返回的输出上限（字符）
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
    """汇总后台命令的已收集输出（stdout + stderr，带截断）"""
    with rec["lock"]:
        out = _decode_robust(b"".join(rec["out"])).strip()
        err = _decode_robust(b"".join(rec["err"])).strip()
    text = out
    if err:
        text += f"\n[stderr] {err[:8000]}" if text else f"[stderr] {err[:8000]}"
    if len(text) > _COMMAND_OUTPUT_MAX:
        text = "（输出过长，已截断）\n" + text[-_COMMAND_OUTPUT_MAX:]
    return text

# ---------- 工具定义（LLM 可见） ----------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "截取当前整个屏幕，返回截图图像。观察屏幕/验证操作结果时使用，"
                           "AI 视觉模型会直接看到截图内容。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_screen_size",
            "description": "获取屏幕分辨率（宽、高像素），用于计算点击/移动坐标。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_windows",
            "description": "枚举当前可见窗口（标题+编号），供 AI 选择目标窗口聚焦操作，"
                           "避免全屏截图中其他窗口干扰。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "capture_window",
            "description": "截取指定窗口（只截该窗口，避开其他窗口遮挡/干扰），返回截图与窗口内文字元素清单。"
                           "窗口图带坐标刻度，后续 click 的窗口内读数会自动换算回屏幕坐标。"
                           "先调用 list_windows 确认目标窗口，window 传标题（模糊）或编号。",
            "parameters": {"type": "object",
                           "properties": {
                               "window": {"type": "string",
                                          "description": "目标窗口：标题（支持模糊匹配）或 list_windows 返回的编号"}},
                           "required": ["window"]},
        },
    },
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
            "name": "click_text",
            "description": "按文字精确定位点击：输入目标文字（如按钮文字、菜单项、输入框标签），"
                           "系统通过 Windows 原生控件(UIA)与屏幕OCR找到该文字的确切像素位置并点击，"
                           "像素级精确，无需自己估算坐标。文字类目标（按钮/菜单/对话框按钮）优先用它，"
                           "找不到时才用 click 视觉定位。",
            "parameters": {"type": "object",
                           "properties": {"text": {"type": "string",
                                                   "description": "要点击的文字内容，如 确定/取消/开始/新建 等"},
                                          "button": {"type": "string", "enum": ["left", "right", "middle"],
                                                     "description": "鼠标键，默认 left"}},
                           "required": ["text"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_mouse",
            "description": "移动鼠标到指定像素坐标（不点击）。移动后截图会显示红色准星标记鼠标位置，"
                           "用于图标目标的对齐：看准星是否套住目标，未对准按偏移修正坐标再移动，对准后再 click。",
            "parameters": {"type": "object",
                           "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                           "required": ["x", "y"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "在指定坐标点击鼠标（可指定左右中键与次数）。"
                           "文字类目标优先用 click_text；图标/图形目标用准星对齐法："
                           "先用 move_mouse 移到目标附近，截图看红色准星是否套住目标，"
                           "未对准则修正坐标再移动，对准后 click（坐标=鼠标当前位置）一次点准。"
                           "系统会自动把坐标换算为真实屏幕坐标。目标太小可先 zoom_in 放大。",
            "parameters": {"type": "object",
                           "properties": {"x": {"type": "integer"}, "y": {"type": "integer"},
                                          "button": {"type": "string", "enum": ["left", "right", "middle"]},
                                          "clicks": {"type": "integer"}},
                           "required": ["x", "y"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "zoom_in",
            "description": "以指定屏幕坐标为中心放大 400×400 区域（放大 3 倍并叠加细网格刻度），"
                           "返回放大后的局部截图。用于两步精确定位：先在全屏图上估出目标附近坐标，"
                           "再 zoom_in 放大后按放大图里的红色准星对齐目标（若鼠标在区域内），"
                           "或按细刻度读数，随后用该坐标调用 click。"
                           "注意：放大图内的坐标读数同样可直接作为 click 的 x/y，系统自动换算。",
            "parameters": {"type": "object",
                           "properties": {"x": {"type": "integer",
                                                "description": "目标附近的屏幕坐标 X（全屏刻度读数）"},
                                          "y": {"type": "integer",
                                                "description": "目标附近的屏幕坐标 Y（全屏刻度读数）"}},
                           "required": ["x", "y"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drag",
            "description": "从 (x1,y1) 拖动鼠标到 (x2,y2)（按住左键拖拽）。",
            "parameters": {"type": "object",
                           "properties": {"x1": {"type": "integer"}, "y1": {"type": "integer"},
                                          "x2": {"type": "integer"}, "y2": {"type": "integer"}},
                           "required": ["x1", "y1", "x2", "y2"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "滚动鼠标滚轮，正值向上、负值向下（120 为 1 格）。",
            "parameters": {"type": "object",
                           "properties": {"delta": {"type": "integer"}},
                           "required": ["delta"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "按键盘虚拟键：enter/tab/escape/backspace/space/delete/home/end/"
                           "pageup/pagedown/up/down/left/right/f1-f12 等。",
            "parameters": {"type": "object",
                           "properties": {"key": {"type": "string"}},
                           "required": ["key"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "输入文本（支持中文），可含特殊键名 enter/tab。",
            "parameters": {"type": "object",
                           "properties": {"text": {"type": "string"}},
                           "required": ["text"]},
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
                           "属于重量级操作，执行前会请用户确认。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "uninstall_app",
            "description": "卸载已安装应用（优先调用应用自带卸载器，再清理数据目录/注册表/快捷方式）。"
                           "需要先扫描已安装应用并匹配名称；属于重量级操作，执行前会请用户确认。",
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
                           "需要先扫描应用匹配名称；属于重量级操作，执行前会请用户确认。",
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
            "description": "生成 Word 文档（.docx）：可选大标题 + 段落文本列表。"
                           "适合报告、说明文档、合同文本、简历等文字型文档。",
            "parameters": {"type": "object",
                           "properties": {
                               "path": {"type": "string", "description": "保存路径（.docx，相对路径基于工作目录）"},
                               "title": {"type": "string", "description": "文档大标题（可选）"},
                               "paragraphs": {"type": "array",
                                              "description": "段落文本列表，每项一个字符串",
                                              "items": {"type": "string"}}},
                           "required": ["path", "paragraphs"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_pptx",
            "description": "生成 PowerPoint 演示文稿（.pptx）：可选首页标题 + 多页幻灯片，"
                           "每页包含页标题与要点列表。适合汇报、产品介绍、培训课件等演示文档。",
            "parameters": {"type": "object",
                           "properties": {
                               "path": {"type": "string", "description": "保存路径（.pptx）"},
                               "title": {"type": "string", "description": "演示文稿标题（可选，用作首页）"},
                               "slides": {"type": "array",
                                          "description": "幻灯片列表，每项 {title: 页标题, bullets: [要点, ...]}",
                                          "items": {"type": "object",
                                                    "properties": {
                                                        "title": {"type": "string", "description": "页标题"},
                                                        "bullets": {"type": "array",
                                                                    "description": "本页要点列表",
                                                                    "items": {"type": "string"}}},
                                                    "required": ["title"]}}},
                           "required": ["path", "slides"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_xlsx",
            "description": "生成 Excel 工作簿（.xlsx）：多个工作表，每表 {name, rows}，"
                           "rows 为二维数组（首行可作为表头）。适合数据表、统计报表、清单等。",
            "parameters": {"type": "object",
                           "properties": {
                               "path": {"type": "string", "description": "保存路径（.xlsx）"},
                               "sheets": {"type": "array",
                                          "description": "工作表列表，每项 {name: 表名, rows: [[单元格,...],...]}",
                                          "items": {"type": "object",
                                                    "properties": {
                                                        "name": {"type": "string", "description": "工作表名"},
                                                        "rows": {"type": "array",
                                                                 "description": "数据行二维数组",
                                                                 "items": {"type": "array",
                                                                           "items": {}}}},
                                                    "required": ["name", "rows"]}}},
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
]

# 子 Agent 工具名（由 agent_engine 拦截调度，携带 LLM 客户端执行；不在此直接实现）
SUB_AGENT_TOOLS = ("dispatch_sub_agents", "explore_project", "search_large")

# 沙盒拒绝返回（无截图）
def _blocked(text: str) -> dict:
    return {"text": text, "images": []}


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
        if name == "screenshot":
            url = agent_screen.capture_screen_data_url()
            # 同时用 OCR 提取文字元素坐标，随截图返回给模型（像素级点击依据）
            png = agent_screen.capture_screen_png()
            w, h = agent_screen.screen_size()
            elems = agent_locator.locate_elements(png, w, h)
            return {"text": "已截取屏幕。" + agent_locator.summarize(elems),
                    "images": [url]}
        if name == "get_screen_size":
            w, h = agent_screen.screen_size()
            return {"text": f"屏幕分辨率 {w}x{h}",
                    "images": [agent_screen.capture_screen_data_url()]}
        if name == "click_text":
            # 按文字精确定位：UIA + OCR 找到文字中心坐标，直接点击（像素级，无需视觉读数）
            target = str(args.get("text", "")).strip()
            button = str(args.get("button", "left"))
            if not target:
                return {"text": "[click_text] 缺少要点击的文字参数 text", "images": []}
            w, h = agent_screen.screen_size()
            png = agent_screen.capture_screen_png()
            elems = agent_locator.locate_elements(png, w, h)
            hit = agent_locator.find_element(target, elems)
            if hit is None:
                # 兜底：重新截图 OCR 一次（UIA 有时缓存延迟），仍未命中则报错让模型换方案
                elems = agent_locator.locate_elements(
                    agent_screen.capture_screen_png(), w, h)
                hit = agent_locator.find_element(target, elems)
            if hit is None:
                return {"text": f"[click_text] 未找到文字「{target}」。屏幕上的文字元素："
                                f"{agent_locator.summarize(elems)}。请改用 click 视觉定位或确认目标存在。",
                        "images": []}
            x, y = hit
            agent_screen.click_physical(x, y, button, 1)   # 物理像素直点，UIA/OCR 坐标无需换算
            return {"text": f"已按文字「{target}」精确定位并点击屏幕坐标 ({x},{y})",
                    "images": []}
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
        if name == "list_windows":
            return _list_windows()
        if name == "capture_window":
            return _capture_window(str(args.get("window", "")))
        if name == "move_mouse":
            agent_screen.move_mouse(agent_sandbox.to_int(args.get("x")),
                                    agent_sandbox.to_int(args.get("y")))
            return {"text": f"鼠标已移动到 ({args.get('x')}, {args.get('y')})", "images": []}
        if name == "click":
            x, y = agent_sandbox.to_int(args.get("x")), agent_sandbox.to_int(args.get("y"))
            px, py = agent_screen.map_to_screen(x, y)   # 换算后的真实屏幕坐标（供模型核对）
            agent_screen.click(x, y,
                               str(args.get("button", "left")),
                               agent_sandbox.to_int(args.get("clicks", 1)))
            return {"text": f"已点击 ({x}, {y}) {args.get('button', 'left')} 键 x{args.get('clicks', 1)}"
                            f"（换算屏幕坐标 {px},{py}）", "images": []}
        if name == "zoom_in":
            # 模型给的全屏读数 → 物理坐标 → 放大局部截图（切换视觉基准为 zoom 态）
            x, y = agent_sandbox.to_int(args.get("x")), agent_sandbox.to_int(args.get("y"))
            px, py = agent_screen.map_to_screen(x, y)
            url = agent_screen.capture_zoom_data_url(px, py)
            return {"text": f"已放大屏幕坐标 ({px},{py}) 附近 400×400 区域（3 倍）。"
                            "请基于放大图内的细网格刻度精确读取目标坐标，再调用 click。",
                    "images": [url]}
        if name == "drag":
            agent_screen.drag(agent_sandbox.to_int(args.get("x1")),
                              agent_sandbox.to_int(args.get("y1")),
                              agent_sandbox.to_int(args.get("x2")),
                              agent_sandbox.to_int(args.get("y2")))
            return {"text": f"已从 ({args.get('x1')},{args.get('y1')}) 拖到 ({args.get('x2')},{args.get('y2')})",
                    "images": []}
        if name == "scroll":
            agent_screen.scroll(agent_sandbox.to_int(args.get("delta")))
            return {"text": f"已滚动 {args.get('delta')}", "images": []}
        if name == "press_key":
            agent_screen.key_press(str(args["key"]))
            return {"text": f"已按键 {args['key']}", "images": []}
        if name == "type_text":
            agent_screen.type_text(str(args["text"]))
            return {"text": f"已输入文本（{len(str(args['text']))} 字符）", "images": []}
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
        if name == "web_search":
            return _web_search(str(args.get("query", "")),
                               agent_sandbox.to_int(args.get("max_results", 8)))
        if name == "clipboard":
            return _clipboard(str(args.get("action", "read")), str(args.get("text", "")))
        if name == "extract_text":
            return _extract_text(str(args.get("path", "")))
        if name == "create_docx":
            return _create_docx(str(args.get("path", "")), str(args.get("title", "")),
                                args.get("paragraphs") if isinstance(args.get("paragraphs"), list) else [])
        if name == "create_pptx":
            return _create_pptx(str(args.get("path", "")), str(args.get("title", "")),
                                args.get("slides") if isinstance(args.get("slides"), list) else [])
        if name == "create_xlsx":
            return _create_xlsx(str(args.get("path", "")),
                                args.get("sheets") if isinstance(args.get("sheets"), list) else [])
        if name == "create_skill":
            return _create_skill(str(args.get("name", "")),
                                 str(args.get("description", "")),
                                 str(args.get("instruction", "")))
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
            text += f"\n[stderr] {err[:8000]}" if text else f"[stderr] {err[:8000]}"
        if not text:
            text = f"（命令完成，退出码 {code}）"
        return text[:_COMMAND_OUTPUT_MAX]

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


def _list_windows() -> dict:
    """枚举可见窗口（标题+编号），供 AI 选择目标窗口"""
    try:
        wins = agent_screen.list_windows()
    except Exception as e:
        return {"text": f"[list_windows] 枚举失败: {e}", "images": []}
    if not wins:
        return {"text": "未发现可见窗口（请先打开目标窗口）", "images": []}
    lines = [f"{i + 1}. {w['title']}（{w['w']}x{w['h']} @{w['x']},{w['y']}）"
             for i, w in enumerate(wins[:40])]
    more = f"\n…共 {len(wins)} 个窗口" if len(wins) > 40 else ""
    return {"text": "可见窗口：\n" + "\n".join(lines) + more, "images": []}


def _capture_window(window: str) -> dict:
    """截取指定窗口（标题模糊/编号），返回截图与窗口内文字元素清单"""
    try:
        wins = agent_screen.list_windows()
    except Exception as e:
        return {"text": f"[capture_window] 窗口枚举失败: {e}", "images": []}
    if not wins:
        return {"text": "[capture_window] 未发现可见窗口，请先打开目标窗口", "images": []}
    q = str(window or "").strip().lower()
    if not q:
        return {"text": "[capture_window] 缺少 window 参数（窗口标题或 list_windows 编号）", "images": []}
    target = None
    try:   # 编号定位
        idx = int(q) - 1
        if 0 <= idx < len(wins):
            target = wins[idx]
    except ValueError:
        pass
    if target is None:   # 标题模糊匹配：全等 → 包含 → 任一分词
        for w in wins:
            t = w["title"].lower()
            if t == q or q in t or any(tok and tok in t for tok in q.split()):
                target = w
                break
    if target is None:
        cand = "\n".join(f"{i + 1}. {w['title']}" for i, w in enumerate(wins[:30]))
        return {"text": f"[capture_window] 未找到窗口「{window}」。可见窗口：\n{cand}", "images": []}
    try:
        url = agent_screen.capture_window_data_url(target["hwnd"])
        summary = ""
        try:   # 窗口内 OCR 元素（窗口内像素坐标，供视觉定位参考）
            png = agent_screen.capture_window_png(target["hwnd"])
            elems = agent_locator.ocr_elements(png, target["w"], target["h"])
            summary = agent_locator.summarize(elems, 40)
        except Exception:
            pass
        return {"text": f"已截取窗口「{target['title']}」（{target['w']}x{target['h']}）"
                        + (f"。窗口内文字元素：{summary}" if summary else ""),
                "images": [url]}
    except Exception as e:
        return {"text": f"[capture_window] 截取失败: {e}", "images": []}


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


# 商务专业风主题色（深蓝 + 深灰）
_DOC_NAVY = "1F3864"          # 主色：深蓝
_DOC_NAVY_SOFT = "8EAADB"     # 浅蓝（副标题/辅助）
_DOC_DARK = "404040"          # 正文深灰
_DOC_FONT = "微软雅黑"


def _docx_set_font(run, size=None, bold=None, color=None):
    """设置 run 字体（含东亚字体微软雅黑）"""
    from docx.shared import Pt, RGBColor
    run.font.name = _DOC_FONT
    from docx.oxml.ns import qn
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = rPr.makeelement(qn("w:rFonts"), {})
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:eastAsia"), _DOC_FONT)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _create_docx(path: str, title: str, paragraphs: list) -> dict:
    """生成 Word 文档（python-docx）：商务专业风（微软雅黑 + 深蓝主题）。
    段落支持轻量标记：'# '/'## ' 为标题层级，'- '/'* ' 为项目符号，其余为正文。"""
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
    except ImportError:
        return _blocked("[create_docx] 缺少 python-docx：run_command 执行 pip install python-docx")
    p = _resolve(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        doc = Document()
        if (title or "").strip():
            h = doc.add_paragraph()
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = h.add_run(str(title))
            _docx_set_font(r, size=22, bold=True, color=_DOC_NAVY)
            h.paragraph_format.space_after = Pt(14)
        for para in (paragraphs or []):
            para = str(para).strip()
            if not para:
                doc.add_paragraph()
                continue
            # 轻量标记：标题层级 / 项目符号 / 正文
            if para.startswith("### "):
                h = doc.add_paragraph()
                r = h.add_run(para[4:])
                _docx_set_font(r, size=12, bold=True, color=_DOC_DARK)
                h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(8), Pt(4)
            elif para.startswith("## "):
                h = doc.add_paragraph()
                r = h.add_run(para[3:])
                _docx_set_font(r, size=13, bold=True, color=_DOC_NAVY_SOFT)
                h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(10), Pt(4)
            elif para.startswith("# "):
                h = doc.add_paragraph()
                r = h.add_run(para[2:])
                _docx_set_font(r, size=16, bold=True, color=_DOC_NAVY)
                h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(12), Pt(6)
            elif para.startswith(("- ", "* ")):
                li = doc.add_paragraph()
                r = li.add_run(para[2:])
                _docx_set_font(r, size=11, color=_DOC_DARK)
                li.paragraph_format.left_indent = Pt(18)
                li.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
                # 手工项目符号圆点（避免依赖样式模板缺失）
                li.style = doc.styles["List Bullet"] if "List Bullet" in doc.styles else li.style
            else:
                body = doc.add_paragraph()
                r = body.add_run(para)
                _docx_set_font(r, size=11, color=_DOC_DARK)
                pf = body.paragraph_format
                pf.space_after = Pt(6)
                pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
        doc.save(str(p))
    except Exception as e:
        return _blocked(f"[create_docx] 生成失败: {e}")
    return {"text": f"已生成 Word 文档：{p}", "images": []}


def _pptx_font(run, size, bold=False, color="404040"):
    """设置 pptx run 字体（拉丁 + 东亚均为微软雅黑）"""
    from pptx.util import Pt
    from pptx.dml.color import RGBColor
    run.font.name = _DOC_FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    from pptx.oxml.ns import qn
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = rPr.makeelement(qn("a:ea"), {})
        rPr.append(ea)
    ea.set("typeface", _DOC_FONT)


def _create_pptx(path: str, title: str, slides: list) -> dict:
    """生成 PowerPoint（python-pptx）：16:9 商务专业风。
    标题页深蓝底白字；内容页白底深蓝标题条 + 深灰要点。"""
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
        prs = Presentation()
        prs.slide_width = Inches(13.333)   # 16:9
        prs.slide_height = Inches(7.5)
        blank = prs.slide_layouts[6]
        # 标题页：深蓝全屏 + 居中白字
        if (title or "").strip():
            s = prs.slides.add_slide(blank)
            bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
            bg.fill.solid()
            bg.fill.fore_color.rgb = RGBColor.from_string(_DOC_NAVY)
            bg.line.fill.background()
            tb = s.shapes.add_textbox(Inches(1), Inches(2.6), Inches(11.333), Inches(1.6))
            tf = tb.text_frame
            tf.word_wrap = True
            r = tf.paragraphs[0].add_run()
            r.text = str(title)
            _pptx_font(r, 40, bold=True, color="FFFFFF")
            tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        # 内容页
        for i, item in enumerate(slides or [], 1):
            if not isinstance(item, dict):
                continue
            slide = prs.slides.add_slide(blank)
            # 标题 + 底部深蓝分隔线
            tb = slide.shapes.add_textbox(Inches(0.6), Inches(0.35), Inches(12.1), Inches(0.8))
            r = tb.text_frame.paragraphs[0].add_run()
            r.text = str(item.get("title") or "")
            _pptx_font(r, 26, bold=True, color=_DOC_NAVY)
            line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(1.18),
                                          Inches(12.1), Pt(2.5))
            line.fill.solid()
            line.fill.fore_color.rgb = RGBColor.from_string(_DOC_NAVY)
            line.line.fill.background()
            # 要点正文
            body = slide.shapes.add_textbox(Inches(0.6), Inches(1.45), Inches(12.1), Inches(5.4))
            tf = body.text_frame
            tf.word_wrap = True
            bullets = item.get("bullets") or []
            for j, b in enumerate(bullets):
                para = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
                para.space_after = Pt(10)
                r = para.add_run()
                r.text = ("•  " if str(b).strip() else "") + str(b).strip()
                _pptx_font(r, 18, bold=(j == 0), color=_DOC_DARK)
            # 页脚页码
            foot = slide.shapes.add_textbox(Inches(11.9), Inches(7.0), Inches(1.0), Inches(0.4))
            fr = foot.text_frame.paragraphs[0].add_run()
            fr.text = str(i)
            _pptx_font(fr, 10, color=_DOC_NAVY_SOFT)
            foot.text_frame.paragraphs[0].alignment = PP_ALIGN.RIGHT
        prs.save(str(p))
    except Exception as e:
        return _blocked(f"[create_pptx] 生成失败: {e}")
    return {"text": f"已生成 PPT：{p}", "images": []}


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


def _create_xlsx(path: str, sheets: list) -> dict:
    """生成 Excel 工作簿（openpyxl）：商务专业风。
    首行深蓝表头白字 + 细边框 + 隔行浅蓝 + 自动列宽 + 冻结首行 + 自动筛选。"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        return _blocked("[create_xlsx] 缺少 openpyxl：run_command 执行 pip install openpyxl")
    p = _resolve(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        wb = Workbook()
        wb.remove(wb.active)
        thin = Side(style="thin", color="D9D9D9")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        for sheet in (sheets or []):
            if not isinstance(sheet, dict):
                continue
            ws = wb.create_sheet(title=str(sheet.get("name") or "Sheet")[:31])
            ws.sheet_properties.tabColor = _DOC_NAVY
            rows = [r for r in (sheet.get("rows") or []) if isinstance(r, (list, tuple))]
            for row in rows:
                ws.append([_xlsx_cell(v) for v in row])
            if not rows:
                continue
            # 表头：深蓝底白字加粗居中
            for c in ws[1]:
                c.font = Font(name=_DOC_FONT, size=11, bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor=_DOC_NAVY)
                c.alignment = Alignment(horizontal="center", vertical="center")
                c.border = border
            ws.row_dimensions[1].height = 22
            # 数据行：微软雅黑 + 边框 + 隔行浅蓝 + 数字右对齐
            for r_idx, row in enumerate(ws.iter_rows(min_row=2), 2):
                for c in row:
                    c.font = Font(name=_DOC_FONT, size=10, color=_DOC_DARK)
                    c.border = border
                    c.alignment = Alignment(horizontal=("right" if isinstance(c.value, (int, float))
                                                        else "left"), vertical="center")
                    if r_idx % 2 == 0:
                        c.fill = PatternFill("solid", fgColor="F2F6FC")
            # 自动列宽 + 冻结首行 + 自动筛选
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = \
                    _xlsx_col_width([c.value for c in col])
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
        wb.save(str(p))
    except Exception as e:
        return _blocked(f"[create_xlsx] 生成失败: {e}")
    return {"text": f"已生成 Excel 工作簿：{p}", "images": []}


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
