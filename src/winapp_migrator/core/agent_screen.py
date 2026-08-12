"""屏幕截取与鼠标键盘操控（Windows，ctypes 零依赖）

- 截屏：PyQt6 QScreen.grabWindow（程序已有依赖），输出 PNG base64 data URL 供视觉模型分析
- 鼠标：移动/左中右键点击/拖动/滚轮（user32 mouse_event / SetCursorPos）
- 键盘：虚拟键按键 + Unicode 文本输入（SendInput KEYEVENTF_UNICODE，支持中文）
"""

import ctypes
import struct
import time
from ctypes import wintypes

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
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
_shot_size = None    # 原始截图尺寸 (w, h)，物理屏幕采样基准
_model_size = None   # 发给视觉模型的截图尺寸（统一缩放到 _MODEL_W 宽），模型刻度读数基准
_MODEL_W = 1280      # 视觉模型统一输入宽度：截图先缩放再叠刻度，刻度与所见图像同基准，杜绝 API 二次缩放导致的读数偏差
_view = None         # 当前视觉基准：None=全屏；否则 {"cx","cy","region","img_w","img_h","x0","y0"}（zoom 放大态）


def capture_screen_png() -> bytes:
    """全屏截图，返回 PNG 字节；同时记录原始截图尺寸供坐标换算"""
    global _shot_size
    screen = QApplication.primaryScreen()
    pix = screen.grabWindow(0)
    img = pix.toImage()
    _shot_size = (img.width(), img.height())
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


def screen_scale() -> tuple:
    """原始截图像素 → 屏幕物理像素 的换算比例 (sx, sy)。

    截图分辨率与屏幕物理分辨率不一致（如系统 DPI 缩放 125%/150%）时，
    点击必须按比例换算，否则系统性偏移。
    """
    w, h = screen_size()
    sw, sh = _shot_size or (w, h)
    return (w / sw if sw else 1.0), (h / sh if sh else 1.0)


def map_to_screen(x: int, y: int) -> tuple:
    """模型读数（基于当前视觉基准 _view）→ 屏幕物理像素。

    全屏基准：缩放系（模型刻度读数）→ 原始截图系 → 屏幕物理像素（DPI）。
    zoom 基准：放大图内坐标 → 对应原始截图区域 → 屏幕物理像素。
    模型看到的刻度数字与所见图像同基准，读数直接可信；此处换算到真实
    屏幕坐标，杜绝模型自行心算导致的双重误差。
    """
    sx, sy = screen_scale()
    if _view is not None and _view.get("img_w", 0) > 0:
        # zoom 放大态：图内坐标 → 原始截图系 → 物理像素
        ox = _view["x0"] + x * _view["region"] / _view["img_w"]
        oy = _view["y0"] + y * _view["region"] / _view["img_h"]
        return int(ox * sx), int(oy * sy)
    # 全屏态：缩放系 → 原始截图系 → 物理像素
    w_orig, h_orig = _shot_size or screen_size()
    mw, mh = _model_size or (w_orig, h_orig)
    if mw > 0 and mh > 0:
        x = x * w_orig / mw
        y = y * h_orig / mh
    return int(x * sx), int(y * sy)


def capture_screen_data_url(grid: bool = True, mark_cursor: bool = True) -> str:
    """全屏截图 → data URL（OpenAI 兼容 image_url 输入）。

    grid=True 时先等比缩放到统一宽度 _MODEL_W，再叠加坐标网格与像素刻度。
    mark_cursor=True 时叠加红色准星标记当前鼠标位置（物理坐标标注），
    模型凭"准星是否套住目标"对齐，比读刻度猜坐标更可靠。
    全屏截图会重置视觉基准回全屏态。
    """
    import base64
    global _model_size, _view
    _view = None   # 回到全屏视觉基准
    png = capture_screen_png()
    img = QImage.fromData(png)
    if grid:
        if img.width() > _MODEL_W:
            img = img.scaledToWidth(_MODEL_W, Qt.TransformationMode.SmoothTransformation)
        _model_size = (img.width(), img.height())
        _draw_coord_grid(img)
    else:
        _model_size = _shot_size
    if mark_cursor:
        _draw_cursor_marker(img)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(bytes(ba)).decode()


def capture_zoom_data_url(cx: int, cy: int, region: int = 400, zoom: int = 3,
                          mark_cursor: bool = True) -> str:
    """以屏幕物理坐标 (cx,cy) 为中心截取 region×region 区域 → 放大 zoom 倍 →
    叠细网格刻度后返回，并切换视觉基准为 zoom 态。

    用于两步精确定位：模型先看全屏图给粗坐标 → zoom_in 放大目标区域 →
    基于放大图细刻度/准星对齐给精确坐标。
    """
    import base64
    global _view
    png = capture_screen_png()   # 记录原始尺寸
    img = QImage.fromData(png)
    sx, sy = screen_scale()
    # 屏幕物理坐标 → 原始截图系中心，取 region 区域（带边界裁剪）
    cx0 = max(0, min(img.width() - 1, int(cx / sx if sx else cx)))
    cy0 = max(0, min(img.height() - 1, int(cy / sy if sy else cy)))
    x0 = max(0, cx0 - region // 2)
    y0 = max(0, cy0 - region // 2)
    x0 = min(x0, max(0, img.width() - region))
    y0 = min(y0, max(0, img.height() - region))
    crop = img.copy(x0, y0, region, region)
    crop = crop.scaled(region * zoom, region * zoom,
                       Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    _draw_coord_grid(crop, cells=16)
    _view = {"cx": cx, "cy": cy, "region": region,
             "img_w": crop.width(), "img_h": crop.height(), "x0": x0, "y0": y0}
    if mark_cursor:
        _draw_cursor_marker(crop)   # 鼠标在区域内则画准星
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    crop.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(bytes(ba)).decode()


def _print_window_bitmap(hwnd: int) -> QImage:
    """PrintWindow 抓取指定窗口内容位图（含被其他窗口遮挡的部分），
    实现"只截目标窗口、避免其他窗口干扰"。返回窗口位图 QImage（32bpp）。"""
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("无法获取窗口区域")
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0 or w > 8192 or h > 8192:
        raise RuntimeError("窗口尺寸无效")
    gdi32 = ctypes.WinDLL("gdi32")

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    hwnd_dc = user32.GetWindowDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bmp = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
    old = gdi32.SelectObject(mem_dc, bmp)
    try:
        user32.PrintWindow(hwnd, mem_dc, 2)   # PW_RENDERFULLCONTENT（Win8.1+，抓完整内容）
        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h            # 自顶向下
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0        # BI_RGB
        buf = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(mem_dc, bmp, 0, h, buf, ctypes.byref(bmi), 0):
            raise RuntimeError("GetDIBits 失败")
        img = QImage(bytes(buf), w, h, w * 4, QImage.Format.Format_RGB32).copy()
        if img.isNull():
            raise RuntimeError("窗口位图转换失败")
        return img
    finally:
        gdi32.SelectObject(mem_dc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)


def capture_window_png(hwnd: int) -> bytes:
    """截取指定窗口 → PNG 字节（供 OCR 识别窗口内文字）"""
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    _print_window_bitmap(hwnd).save(buf, "PNG")
    return bytes(ba)


def capture_window_data_url(hwnd: int, grid: bool = True, mark_cursor: bool = True) -> str:
    """截取指定窗口 → 网格刻度 data URL，并把视觉基准切为窗口态。

    窗口态复用 zoom 态的坐标换算语义：模型在窗口图内读数（刻度与图像同基准），
    click 时自动换算回屏幕物理坐标；只截目标窗口，不受其他窗口遮挡/干扰。
    """
    import base64
    global _view
    img = _print_window_bitmap(hwnd)
    orig_w, orig_h = img.width(), img.height()
    if grid:
        if img.width() > _MODEL_W:
            img = img.scaledToWidth(_MODEL_W, Qt.TransformationMode.SmoothTransformation)
        _draw_coord_grid(img)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    sx, sy = screen_scale()
    # 与 zoom 态一致：x0/y0 = 窗口左上角（原始截图系），region = 窗口位图原始宽
    _view = {"cx": 0, "cy": 0, "region": orig_w,
             "img_w": img.width(), "img_h": img.height(),
             "x0": rect.left / sx if sx else rect.left,
             "y0": rect.top / sy if sy else rect.top}
    if mark_cursor:
        _draw_cursor_marker(img)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(bytes(ba)).decode()


def list_windows() -> list:
    """EnumWindows 枚举可见顶层窗口，返回 [{'hwnd','title','x','y','w','h'}]。

    过滤无标题、尺寸过小（<60×40）的窗口；坐标为屏幕物理像素。
    """
    out = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value.strip()
        if not title:
            return True
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w < 60 or h < 40:
            return True
        out.append({"hwnd": int(hwnd), "title": title,
                    "x": rect.left, "y": rect.top, "w": w, "h": h})
        return True

    user32.EnumWindows(proc(cb), 0)
    return out


def _draw_coord_grid(img: QImage, cells: int = 16):
    """在缩放后的截图上叠加坐标网格、像素刻度与中心十字线，帮助视觉模型精确定位。

    - 网格线：每格 1/cells 屏宽，红色细线（加密到 16 格，缩小内插误差）
    - 中心十字：半透明白色十字，辅助模型判断图像中心
    - 刻度：网格线两端标注该处的图像像素值，黑色描边 + 亮色填充保证 API
      缩放后仍清晰可读；X 轴顶部黄色、Y 轴左侧青色，每 2 格标一个数字防拥挤
    - 刻度与 _model_size 同基准：模型读出的数字可直接作为 click 坐标
    """
    w, h = img.width(), img.height()
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    # 网格线
    p.setPen(QPen(QColor(255, 80, 80, 120), 1))
    for i in range(1, cells):
        x, y = w * i // cells, h * i // cells
        p.drawLine(x, 0, x, h)
        p.drawLine(0, y, w, y)
    # 中心十字线
    p.setPen(QPen(QColor(255, 255, 255, 150), 1))
    p.drawLine(w // 2, 0, w // 2, h)
    p.drawLine(0, h // 2, w, h // 2)
    # 刻度文字（黑色描边 + 亮色填充）
    font = QFont("Consolas", 13)
    font.setBold(True)
    step = max(1, cells // 2)   # 每 2 格标注一个数字，避免顶部/左侧数字拥挤
    for i in range(0, cells + 1, step):
        x, y = w * i // cells, h * i // cells
        for txt, px, py, color in ((f"{x}", x + 3, 18, QColor(255, 230, 0, 255)),
                                   (f"{y}", 4, y + 18, QColor(0, 255, 170, 255))):
            path = QPainterPath()
            path.addText(px, py, font, txt)
            p.setPen(QPen(QColor(0, 0, 0, 220), 3))   # 黑色描边，保证缩放后仍可读
            p.drawPath(path)
            p.fillPath(path, color)
    p.end()


def screen_size() -> tuple:
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def _cursor_pos() -> tuple:
    """当前鼠标屏幕物理坐标 (x, y)"""
    pt = wintypes.POINT()
    if user32.GetCursorPos(ctypes.byref(pt)):
        return int(pt.x), int(pt.y)
    return 0, 0


def _draw_cursor_marker(img: QImage):
    """在截图上绘制红色准星标记当前鼠标位置（物理坐标标注），辅助模型精确对齐。

    鼠标物理坐标 → 当前视觉基准（全屏缩放系或 zoom 放大系）；鼠标不在
    zoom 区域内时跳过（目标区域与光标无关）。
    """
    cx, cy = _cursor_pos()
    if cx <= 0 and cy <= 0:
        return
    sx, sy = screen_scale()
    ox = cx / sx if sx else cx      # 物理 → 原始截图系
    oy = cy / sy if sy else cy
    if _view is not None and _view.get("img_w", 0) > 0:
        # zoom 态：鼠标必须在放大区域内才画
        x0, y0, reg = _view["x0"], _view["y0"], _view["region"]
        if not (x0 <= ox < x0 + reg and y0 <= oy < y0 + reg):
            return
        mx = (ox - x0) * _view["img_w"] / reg
        my = (oy - y0) * _view["img_h"] / reg
    else:
        # 全屏缩放系
        w_orig, h_orig = _shot_size or screen_size()
        mw, mh = _model_size or (w_orig, h_orig)
        mx = ox * mw / w_orig if w_orig else ox
        my = oy * mh / h_orig if h_orig else oy
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    x, y = int(mx), int(my)
    # 外圈（红）
    p.setPen(QPen(QColor(255, 51, 85, 230), 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(x - 15, y - 15, 30, 30)
    # 十字（白描边红芯，醒目）
    p.setPen(QPen(QColor(255, 255, 255, 230), 1))
    p.drawLine(x - 9, y, x + 9, y)
    p.drawLine(x, y - 9, x, y + 9)
    p.setPen(QPen(QColor(255, 51, 85, 255), 1))
    p.drawLine(x - 9, y, x + 9, y)
    p.drawLine(x, y - 9, x, y + 9)
    # 中心实心点
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 51, 85, 255))
    p.drawEllipse(x - 2, y - 2, 4, 4)
    # 物理坐标标注（黑描边黄字，靠近准星右上方）
    font = QFont("Consolas", 12)
    font.setBold(True)
    label = f"cursor ({cx},{cy})"
    path = QPainterPath()
    path.addText(x + 20, y - 20, font, label)
    p.setPen(QPen(QColor(0, 0, 0, 220), 3))
    p.drawPath(path)
    p.fillPath(path, QColor(255, 230, 0, 255))
    p.end()


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
    x, y = map_to_screen(x, y)   # 截图像素 → 屏幕物理像素（防 DPI 缩放偏移）
    user32.SetCursorPos(int(x), int(y))


def move_mouse_physical(x: int, y: int):
    """物理像素直接移动（不经过模型坐标换算），供 UIA/OCR 等非视觉定位结果使用"""
    user32.SetCursorPos(int(x), int(y))


def click(x: int, y: int, button: str = "left", clicks: int = 1, interval: float = 0.1):
    x, y = map_to_screen(x, y)
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


def click_physical(x: int, y: int, button: str = "left", clicks: int = 1, interval: float = 0.06):
    """物理像素直接点击（不经过模型坐标换算），供 UIA/OCR 定位结果使用（像素级精确）"""
    move_mouse_physical(x, y)
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
    x1, y1 = map_to_screen(x1, y1)
    x2, y2 = map_to_screen(x2, y2)
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
