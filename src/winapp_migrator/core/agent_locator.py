"""窗口级语义元素定位器（Windows）：UIA 语义树为主 + OCR 兜底

核心思路（让多模态模型"稳定·快速·流畅"操控计算机）：
- 只扫描"目标窗口"（前台应用窗口或 capture_window 指定的窗口），不扫全屏
  → 快、干净。
- UIA 语义树（原生控件，100% 精确坐标）为主；OCR 仅兜底 UIA 识别不到的
  自绘/画布文字。
- 输出紧凑的**编号语义清单** [id] (类型) 文字，模型按 id/文字引用，坐标由
  系统确定性地解析 → 模型无需读像素刻度猜坐标。
- 语义树带缓存：同屏多次操作复用同一份清单，界面变化才强制刷新
  → 少一次全量扫描就多一分流畅。

所有元素坐标统一为**屏幕物理像素**（UIA 与 OCR 均已换算一致），
click 直接 click_physical 执行，杜绝多套坐标换算错乱。
"""

import asyncio
import re
import time

# 无意义词（UIA/OCR 噪声，过滤避免干扰匹配）
_NOISE = {"|", "-", "_", ".", "·", "…", "→", "√", "×", "✓", "✕"}

# 当前目标窗口 + 语义树缓存（按窗口缓存，界面不变则复用）
_TARGET = {"hwnd": 0, "title": ""}
_CACHE = {"elems": None, "t": 0.0, "hwnd": 0}
_TTL = 2.0   # 同屏语义树复用窗口（秒）

# UIA ControlType → 给模型的语义类型提示
_UIA_TYPE = {
    50000: "按钮", 50001: "日历", 50002: "勾选框", 50003: "下拉框",
    50004: "输入框", 50005: "链接", 50006: "图片", 50007: "列表项",
    50008: "菜单", 50009: "菜单栏", 50010: "菜单项", 50011: "面板",
    50012: "单选", 50013: "滚动条", 50014: "滑块", 50015: "分体按钮",
    50016: "状态栏", 50017: "标签页", 50018: "标签项", 50019: "文本",
    50020: "工具栏", 50021: "提示", 50022: "树", 50023: "树节点",
    50024: "控件", 50025: "分组", 50026: "滑块柄", 50028: "数据网格",
    50029: "数据项", 50030: "文档", 50032: "进度条", 50033: "数值框",
    50034: "标题", 50040: "表格", 50041: "表格项", 50042: "选项卡",
    50043: "工具提示", 50044: "拆分按钮",
}


def _meaningful(text: str) -> bool:
    """文本是否值得作为定位元素：含中文或至少 2 个字母数字"""
    return bool(re.search(r"[\u4e00-\u9fff]", text)) or \
        bool(re.search(r"[A-Za-z0-9]{2,}", text))


# ---------- 目标窗口管理 ----------
def set_target_window(hwnd: int, title: str = ""):
    """设定当前操作的目标窗口（capture_window / screenshot 调用）。换窗口即失效缓存。"""
    hwnd = int(hwnd or 0)
    if hwnd != _TARGET["hwnd"]:
        _CACHE["elems"] = None
    _TARGET["hwnd"] = hwnd
    _TARGET["title"] = title or ""


def target_window_hwnd() -> int:
    """当前目标窗口句柄；未显式指定则取前台应用窗口（0=无法确定/本程序前台）。"""
    if _TARGET["hwnd"]:
        return _TARGET["hwnd"]
    from winapp_migrator.core import agent_screen
    return agent_screen.foreground_window_hwnd()


def target_window_title() -> str:
    return _TARGET["title"]


# ---------- 语义树获取（带缓存） ----------
def get_elements(force: bool = False) -> list:
    """获取当前目标窗口的语义元素列表（屏幕物理像素），带同屏缓存。

    force=True 强制重扫（界面变化后需要重新定位）。
    """
    hwnd = target_window_hwnd()
    if not hwnd:
        return []
    now = time.time()
    if not force and _CACHE["elems"] and _CACHE["hwnd"] == hwnd \
            and now - _CACHE["t"] < _TTL:
        return _CACHE["elems"]
    elems = _locate_window_elements(hwnd)
    _CACHE.update(elems=elems, t=now, hwnd=hwnd)
    return elems


def invalidate_cache():
    """手动失效语义树缓存（如界面明显变化后）"""
    _CACHE["elems"] = None


def _locate_window_elements(hwnd: int) -> list:
    """合并 UIA 语义树 + 窗口 OCR，去重、按位置排序、分配稳定 id。坐标为屏幕物理像素。"""
    from winapp_migrator.core import agent_screen
    elems, seen = [], set()

    def _add(e):
        key = (e["x"] // 4, e["y"] // 4)   # 4px 粒度去重（UIA 与 OCR 同目标会重叠）
        if key in seen:
            return
        seen.add(key)
        elems.append(e)

    for e in _window_uia_elements(hwnd):
        _add(e)
    try:
        rect = agent_screen.window_rect(hwnd)
        png = agent_screen.capture_window_png(hwnd)
        for e in _window_ocr_elements(png, rect):
            _add(e)
    except Exception:
        pass
    # 按位置排序（自上而下、再从左到右），分配稳定 id
    elems.sort(key=lambda e: (e["y"] // 8, e["x"]))
    for i, e in enumerate(elems, 1):
        e["id"] = i
    return elems


# ---------- L1：窗口 UIA 语义树（精确坐标） ----------
def _window_uia_elements(hwnd: int) -> list:
    """枚举指定窗口的 UIA 控件子树，返回 [{id,text,type,x,y,w,h}]（屏幕物理像素）。

    只遍历该窗口子树（maxDepth=10），远快于全桌面遍历，且不含其他窗口干扰。
    """
    out = []
    try:
        import uiautomation as auto
        win = auto.ControlFromHandle(hwnd)
        if win is None:
            return []
        for ctrl in auto.WalkControl(win, maxDepth=10):
            try:
                name = ctrl.Name
                rect = ctrl.BoundingRectangle
                if name and rect and rect.width() > 0 and rect.height() > 0 \
                        and _meaningful(name.strip()):
                    out.append({"text": name.strip(),
                                "type": _UIA_TYPE.get(int(ctrl.ControlType), "元素"),
                                "x": rect.left + rect.width() // 2,
                                "y": rect.top + rect.height() // 2,
                                "w": rect.width(), "h": rect.height(),
                                "src": "uia"})
            except Exception:
                continue
    except Exception:
        pass
    return out


# ---------- L2：窗口 OCR 兜底（自绘/画布文字） ----------
def _window_ocr_elements(png_bytes: bytes, rect) -> list:
    """OCR 识别窗口位图文字，换算为屏幕物理像素。
    rect 为窗口屏幕物理矩形；位图尺寸即 rect 尺寸，OCR 坐标 + rect 原点即屏幕坐标。"""
    items = []
    try:
        items = asyncio.run(_ocr_async(png_bytes, rect.width(), rect.height()))
    except Exception:
        return []
    for e in items:
        e["type"] = "文字"
        e["src"] = "ocr"
        e["x"] += rect.left
        e["y"] += rect.top
    return items


async def _ocr_async(png_bytes: bytes, img_w: int, img_h: int) -> list:
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.storage.streams import InMemoryRandomAccessStream, DataWriter

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream.get_output_stream_at(0))
    writer.write_bytes(png_bytes)
    await writer.store_async()

    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        langs = OcrEngine.available_recognizer_languages
        if not langs:
            return []
        engine = OcrEngine.try_create_from_language(langs[0])
    if engine is None:
        return []

    result = await engine.recognize_async(bitmap)
    sx = img_w / bitmap.pixel_width
    sy = img_h / bitmap.pixel_height
    items = []
    for line in result.lines:
        for w in line.words:
            r = w.bounding_rect
            text = w.text.strip()
            if not text or not _meaningful(text):
                continue
            items.append({"text": text,
                          "x": int(r.x * sx + r.width * sx / 2),
                          "y": int(r.y * sy + r.height * sy / 2),
                          "w": int(r.width * sx), "h": int(r.height * sy)})
    return items


# ---------- 匹配 ----------
def find_element(target: str, elements: list) -> tuple:
    """模糊匹配目标文本，返回其中心坐标 (x, y)；未命中返回 None。

    匹配优先级：完全相等 > 目标含于元素名 > 元素名含于目标 > 任一分词命中。
    """
    if not target:
        return None
    t = _norm(target)
    tokens = [w for w in re.split(r"[^\w\u4e00-\u9fff]+", t) if w]
    best, best_score = None, -1
    for e in elements:
        n = _norm(e.get("text", ""))
        if not n:
            continue
        if n == t:
            score = 100
        elif t in n:
            score = 60
        elif n in t:
            score = 50
        elif tokens and any(tok and tok in n for tok in tokens):
            score = 30
        else:
            continue
        if score > best_score:
            best, best_score = e, score
    return (best["x"], best["y"]) if best else None


def find_by_id(uid: int, elements: list) -> tuple:
    """按清单编号 id 定位，返回中心坐标 (x, y)；未命中返回 None。"""
    for e in elements:
        if e.get("id") == uid:
            return e.get("x"), e.get("y")
    return None


def summarize(elements: list, limit: int = 80) -> str:
    """把语义元素做成编号清单 [id] (类型) 文字。模型按 id/文字引用，坐标由系统解析。"""
    if not elements:
        return "（未识别到文字元素）"
    rows = []
    for e in elements[:limit]:
        rows.append(f"[{e.get('id')}] ({e.get('type', '元素')}) {e['text']}")
    if len(elements) > limit:
        rows.append(f"… 还有 {len(elements) - limit} 项")
    return "\n".join(rows)


def _norm(s: str) -> str:
    return re.sub(r"[\s\u3000]+", "", s).lower()