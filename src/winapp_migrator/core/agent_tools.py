"""Agent 内置工具：注册表（LLM function calling schema）+ 执行（接入沙盒评估）

执行结果统一为 {"text": str, "images": [data_url]}：
- text 作为 tool 消息文本返回给模型
- images 中的截图 data URL 由引擎并入下一轮视觉输入（截图验证闭环）
"""

import json
import os
import subprocess

from winapp_migrator.core import agent_sandbox
from winapp_migrator.core import agent_screen

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
            "description": "在指定坐标点击鼠标（可指定左右中键与次数）。",
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
]

# 沙盒拒绝返回（无截图）
def _blocked(text: str) -> dict:
    return {"text": text, "images": []}


def execute_tool(name: str, args: dict) -> dict:
    """执行工具，返回 {"text", "images"}。危险操作硬拒绝（沙盒兜底）"""
    args = args or {}
    level, reason = agent_sandbox.assess_tool(name, args)
    if level == "dangerous":
        return _blocked(f"[沙盒拒绝] {reason}")

    try:
        if name == "screenshot":
            return {"text": "已截取屏幕", "images": [agent_screen.capture_screen_data_url()]}
        if name == "get_screen_size":
            w, h = agent_screen.screen_size()
            return {"text": f"屏幕分辨率 {w}x{h}"}
        if name == "move_mouse":
            agent_screen.move_mouse(agent_sandbox.to_int(args.get("x")),
                                    agent_sandbox.to_int(args.get("y")))
            return {"text": f"鼠标已移动到 ({args.get('x')}, {args.get('y')})", "images": []}
        if name == "click":
            agent_screen.click(agent_sandbox.to_int(args.get("x")),
                               agent_sandbox.to_int(args.get("y")),
                               str(args.get("button", "left")),
                               agent_sandbox.to_int(args.get("clicks", 1)))
            return {"text": f"已点击 ({args.get('x')}, {args.get('y')}) "
                            f"{args.get('button', 'left')} 键 x{args.get('clicks', 1)}",
                    "images": []}
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
        text = out[:4000]
        if err:
            text += f"\n[stderr] {err[:1000]}"
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
            return {"text": f.read()[:4000], "images": []}
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


def tool_schemas() -> list:
    """供 LLM tools 参数的完整 schema 列表"""
    return json.loads(json.dumps(TOOLS))
