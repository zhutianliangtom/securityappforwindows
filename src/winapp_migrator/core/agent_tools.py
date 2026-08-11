"""Agent 内置工具：注册表（LLM function calling schema）+ 执行（接入沙盒评估）

执行结果统一为 {"text": str, "images": [data_url]}：
- text 作为 tool 消息文本返回给模型
- images 中的截图 data URL 由引擎并入下一轮视觉输入（截图验证闭环）
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from winapp_migrator.core import agent_sandbox
from winapp_migrator.core import agent_screen
from winapp_migrator.core import agent_find

# 本地记忆文件（AI 长期记忆，markdown 格式）
MEMORY_FILE = Path.home() / ".winapp_migrator" / "agent" / "memory.md"

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
            "name": "move_mouse",
            "description": "移动鼠标到指定像素坐标（不点击）。",
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
                           "坐标从最近截图（全屏或 zoom_in 放大图）的网格刻度内插读取，"
                           "系统会自动换算为真实屏幕坐标。目标较小或坐标不确定时，"
                           "先调用 zoom_in 放大目标区域再精确读数。",
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
                           "再 zoom_in 放大后按细刻度精确读数，接着用该坐标调用 click。"
                           "注意：放大图内的刻度读数同样可直接作为 click 的 x/y，系统自动换算。",
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
            "description": "在系统终端执行命令（受沙盒白名单约束）。只读诊断命令放行，"
                           "危险命令（删除/格式化/关机等）会被拒绝。",
            "parameters": {"type": "object",
                           "properties": {"command": {"type": "string"}},
                           "required": ["command"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文本文件内容（仅允许用户目录，最大 200KB）。",
            "parameters": {"type": "object",
                           "properties": {"path": {"type": "string"}},
                           "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "创建或覆盖写入文本文件（仅允许用户目录，目录不存在自动创建，最大 500KB）。",
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
            "description": "编辑文件：把文件中的 old_text 精确替换为 new_text（仅替换第一处，仅允许用户目录，最大 200KB）。",
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
]

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
    level, reason = agent_sandbox.assess_tool(name, args)
    if level == "dangerous" and not allow_dangerous:
        return _blocked(f"[沙盒拒绝] {reason}")

    try:
        if name == "screenshot":
            return {"text": "已截取屏幕", "images": [agent_screen.capture_screen_data_url()]}
        if name == "get_screen_size":
            w, h = agent_screen.screen_size()
            return {"text": f"屏幕分辨率 {w}x{h}",
                    "images": [agent_screen.capture_screen_data_url()]}
        if name == "find_app":
            return {"text": agent_find.find_app(
                str(args.get("query", "")),
                agent_sandbox.to_int(args.get("limit", 10))), "images": []}
        if name == "search_files":
            return {"text": agent_find.search_files(
                str(args.get("query", "")),
                str(args.get("folder", "")),
                agent_sandbox.to_int(args.get("limit", 30))), "images": []}
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
            return _run_command(str(args.get("command", "")))
        if name == "read_file":
            return _read_file(str(args.get("path", "")))
        if name == "write_file":
            return _write_file(str(args.get("path", "")), str(args.get("content", "")))
        if name == "edit_file":
            return _edit_file(str(args.get("path", "")),
                              str(args.get("old_text", "")),
                              str(args.get("new_text", "")))
        if name == "list_directory":
            return _list_directory(str(args.get("path", "")))
        if name == "save_memory":
            return _save_memory(str(args.get("content", "")))
        if name == "load_memory":
            return _load_memory()
    except Exception as e:
        return _blocked(f"[工具执行错误] {name}: {e}")
    return _blocked(f"[未知工具] {name}")


def _run_command(command: str) -> dict:
    try:
        proc = subprocess.run(command, shell=True, capture_output=True,
                              text=True, timeout=30,
                              creationflags=0x08000000)  # CREATE_NO_WINDOW
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        text = out[:30000]
        if err:
            text += f"\n[stderr] {err[:8000]}"
        if not text:
            text = f"（命令完成，退出码 {proc.returncode}）"
        return {"text": text, "images": []}
    except subprocess.TimeoutExpired:
        return _blocked("[沙盒] 命令执行超时（30 秒）")
    except Exception as e:
        return _blocked(f"[沙盒] 命令执行失败: {e}")


def _read_file(path: str) -> dict:
    level, reason = agent_sandbox.assess_path(path)
    if level != "safe":
        return _blocked(f"[沙盒拒绝] {reason}")
    try:
        size = os.path.getsize(path)
        if size > 200 * 1024:
            return _blocked(f"[沙盒] 文件过大（{size} 字节 > 200KB）")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return {"text": f.read()[:30000], "images": []}
    except Exception as e:
        return _blocked(f"[沙盒] 读取失败: {e}")


def _write_file(path: str, content: str) -> dict:
    """创建/覆盖写入文件（仅允许用户目录，目录不存在自动创建）"""
    level, reason = agent_sandbox.assess_path(path)
    if level != "safe":
        return _blocked(f"[沙盒拒绝] {reason}")
    if len(content) > 500 * 1024:
        return _blocked("[沙盒] 内容过大（>500KB）")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"text": f"已写入 {len(content)} 字符到 {path}", "images": []}
    except Exception as e:
        return _blocked(f"[沙盒] 写入失败: {e}")


def _edit_file(path: str, old_text: str, new_text: str) -> dict:
    """编辑文件：精确替换第一处 old_text（仅允许用户目录）"""
    level, reason = agent_sandbox.assess_path(path)
    if level != "safe":
        return _blocked(f"[沙盒拒绝] {reason}")
    try:
        if os.path.getsize(path) > 200 * 1024:
            return _blocked("[沙盒] 文件过大（>200KB）")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read()
        if old_text not in data:
            return _blocked("[沙盒] 未找到要替换的内容")
        data = data.replace(old_text, new_text, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
        return {"text": f"已替换 1 处内容到 {path}", "images": []}
    except Exception as e:
        return _blocked(f"[沙盒] 编辑失败: {e}")


def _list_directory(path: str) -> dict:
    """列出目录内容（仅允许用户目录，最多 200 项）"""
    level, reason = agent_sandbox.assess_path(path)
    if level != "safe":
        return _blocked(f"[沙盒拒绝] {reason}")
    try:
        entries = sorted(os.listdir(path))
        lines = []
        for e in entries[:200]:
            full = os.path.join(path, e)
            mark = "DIR " if os.path.isdir(full) else "FILE"
            lines.append(f"{mark}\t{e}")
        text = f"{path} 共 {len(entries)} 项" + (f"（仅显示前 200）" if len(entries) > 200 else "") + "：\n"
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


def tool_schemas() -> list:
    """供 LLM tools 参数的完整 schema 列表"""
    return json.loads(json.dumps(TOOLS))
