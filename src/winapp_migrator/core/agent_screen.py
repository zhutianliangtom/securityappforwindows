"""屏幕截取与鼠标键盘操控（Windows，ctypes 零依赖）

- 截屏：PyQt6 QScreen.grabWindow（程序已有依赖），输出 PNG base64 data URL 供视觉模型分析
- 鼠标：移动/左中右键点击/拖动/滚轮（user32 mouse_event / SetCursorPos）
- 键盘：虚拟键按键 + Unicode 文本输入（SendInput KEYEVENTF_UNICODE，支持中文）
"""

import ctypes
import struct
import time
from ctypes import wintypes

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtWidgets import QApplication

user32 = ctypes.windll.user32

# 鼠标事件标志
_MOUSE_LEFTDOWN, _MOUSE_LEFTUP = 0x02, 0x04
_MOUSE_RIGHTDOWN, _MOUSE_RIGHTUP = 0x08, 0x10
_MOUSE_MIDDLEDOWN, _MOUSE_MIDDLEUP = 0x20, 0x40
_MOUSE_WHEEL = 0x0800

# 键盘虚拟键（常用）
VK = {"enter": 0x0D, "return": 0x0D, "tab": 0x09, "escape": 0x1B, "esc": 0x1B,
      "backspace": 0x08, "space": 0x20, "delete": 0x2E, "home": 0x24,
      "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28,
      "left": 0x25, "right": 0x27, "capslock": 0x14, "tab_": 0x09}


# ---- 截屏 ----
def capture_screen_png() -> bytes:
    """全屏截图，返回 PNG 字节"""
    screen = QApplication.primaryScreen()
    pix = screen.grabWindow(0)
    img = pix.toImage()
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


def capture_screen_data_url() -> str:
    """全屏截图 → data URL（OpenAI 兼容 image_url 输入）"""
    import base64
    return "data:image/png;base64," + base64.b64encode(capture_screen_png()).decode()


def screen_size() -> tuple:
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


# ---- 虚拟桌面（多桌面） ----
def virtual_desktop(action: str = "new"):
    """Windows 虚拟桌面：模拟 Win+Ctrl 组合键，创建/切换独立工作桌面。
    new: 新建桌面并切换过去（不影响其他桌面内容）；back: 返回上一个桌面（任务完成后回用户桌面）；
    next/prev: 切换到下一个/上一个桌面。
    """
    seq = {"new": (0x5B, 0x11, 0x44),     # Win + Ctrl + D
           "back": (0x5B, 0x11, 0x25),    # Win + Ctrl + Left（回到上一个桌面）
           "next": (0x5B, 0x11, 0x27),    # Win + Ctrl + Right
           "prev": (0x5B, 0x11, 0x25)}    # Win + Ctrl + Left
    keys = seq.get(action, seq["new"])
    for vk in keys:                        # 依次按下
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.02)
    for vk in reversed(keys):              # 逆序释放
        user32.keybd_event(vk, 0, 0x0002, 0)
        time.sleep(0.02)
    time.sleep(0.5)                        # 等待桌面切换动画完成


# ---- 鼠标 ----
def move_mouse(x: int, y: int):
    user32.SetCursorPos(int(x), int(y))


def click(x: int, y: int, button: str = "left", clicks: int = 1, interval: float = 0.1):
    move_mouse(x, y)
    down = {"left": _MOUSE_LEFTDOWN, "right": _MOUSE_RIGHTDOWN,
            "middle": _MOUSE_MIDDLEDOWN}[button]
    up = {"left": _MOUSE_LEFTUP, "right": _MOUSE_RIGHTUP,
          "middle": _MOUSE_MIDDLEUP}[button]
    for _ in range(clicks):
        user32.mouse_event(down, 0, 0, 0, 0)
        time.sleep(interval)
        user32.mouse_event(up, 0, 0, 0, 0)
        time.sleep(interval)


def drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.4):
    move_mouse(x1, y1)
    user32.mouse_event(_MOUSE_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    steps = max(int(duration / 0.02), 5)
    for i in range(1, steps + 1):
        move_mouse(x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps)
        time.sleep(duration / steps)
    user32.mouse_event(_MOUSE_LEFTUP, 0, 0, 0, 0)


def scroll(delta: int):
    """滚轮：正值向上，负值向下（120 为 1 格）"""
    user32.mouse_event(_MOUSE_WHEEL, 0, 0, int(delta), 0)


# ---- 键盘 ----
def _vk_for_char(ch: str) -> int:
    """单字符 → 虚拟键码（ASCII/常见符号）；失败返回 0"""
    if ch in VK:
        return VK[ch]
    if len(ch) == 1:
        vk = user32.VkKeyScanW(ord(ch)) & 0xFF
        return vk if vk != 0xFF else 0
    return 0


def key_press(key_name: str):
    """按虚拟键（如 enter / tab / up / down / f5 等）"""
    name = key_name.strip().lower().replace(" ", "")
    code = VK.get(name)
    if code is None and name.startswith("f") and name[1:].isdigit():
        code = 0x70 + int(name[1:]) - 1  # F1=0x70
    if not code:
        raise ValueError(f"未知按键: {key_name}")
    user32.keybd_event(code, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(code, 0, 0x0002, 0)  # KEYEVENTF_KEYUP


def type_text(text: str, interval: float = 0.01):
    """SendInput Unicode 输入文本（支持中文）；特殊名（enter/tab/...）转虚拟键"""
    for ch in text:
        if ch in ("\n", "\r"):
            key_press("enter")
            continue
        vk = _vk_for_char(ch)
        if vk and ch.isascii():
            user32.keybd_event(vk, 0, 0, 0)
            time.sleep(interval)
            user32.keybd_event(vk, 0, 0x0002, 0)
            time.sleep(interval)
        else:
            _send_unicode(ch)
            time.sleep(interval)


def _send_unicode(ch: str):
    """SendInput 单个 Unicode 字符（KEYEVENTF_UNICODE）"""
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    for down in (True, False):
        ki = KEYBDINPUT(0, ord(ch), 0x0004 if down else 0x0004 | 0x0002,
                        0, ctypes.pointer(ctypes.c_ulong(0)))
        inp = INPUT(1, ki)  # INPUT_KEYBOARD=1
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
