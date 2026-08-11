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
            agent_screen.move_mouse(int(args["x"]), int(args["y"]))
            return {"text": f"鼠标已移动到 ({args['x']}, {args['y']})", "images": []}
        if name == "click":
            agent_screen.click(int(args["x"]), int(args["y"]),
                               str(args.get("button", "left")),
                               int(args.get("clicks", 1)))
            return {"text": f"已点击 ({args['x']}, {args['y']}) "
                            f"{args.get('button', 'left')} 键 x{args.get('clicks', 1)}",
                    "images": []}
        if name == "drag":
            agent_screen.drag(int(args["x1"]), int(args["y1"]),
                              int(args["x2"]), int(args["y2"]))
            return {"text": f"已从 ({args['x1']},{args['y1']}) 拖到 ({args['x2']},{args['y2']})",
                    "images": []}
        if name == "scroll":
            agent_screen.scroll(int(args["delta"]))
            return {"text": f"已滚动 {args['delta']}", "images": []}
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


def tool_schemas() -> list:
    """供 LLM tools 参数的完整 schema 列表"""
    return json.loads(json.dumps(TOOLS))
