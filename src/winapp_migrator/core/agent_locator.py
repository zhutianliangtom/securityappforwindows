"""三层混合精确定位器：UIA → OCR → 视觉兜底

L1 UIA（Windows UI Automation）：枚举原生控件，取名称+边界框中心，100% 精确。
L2 OCR（Windows 自带 OCR，Windows.Media.Ocr）：识别屏幕文字与像素坐标，
    像素级精度，覆盖所有含文字的 UI（按钮/菜单/输入框），无外部引擎依赖。
L3 视觉：由 agent_screen 的网格刻度+zoom 兜底（图标/纯图形元素）。

AI 定位目标时按此优先级取坐标，彻底绕开视觉模型"读刻度"的精度上限。
"""

import asyncio
import re

# ---------- L1：UIA 控件枚举 ----------
def uia_elements() -> list:
    """枚举当前桌面各窗口的带文本控件，返回 [{text,x,y,w,h}]（屏幕物理像素）。"""
    out = []
    try:
        import uiautomation as auto
        root = auto.GetRootControl()
        for ctrl in auto.WalkControl(root, maxDepth=6):
            try:
                name = ctrl.Name
                rect = ctrl.BoundingRectangle
                if name and rect and rect.width() > 0 and rect.height() > 0:
                    out.append({"text": name.strip(),
                                "x": rect.left + rect.width() // 2,
                                "y": rect.top + rect.height() // 2,
                                "w": rect.width(), "h": rect.height(),
                                "src": "uia"})
            except Exception:
                continue
    except Exception:
        pass
    return out


# ---------- L2：Windows 自带 OCR ----------
def ocr_elements(png_bytes: bytes, img_w: int, img_h: int) -> list:
    """OCR 识别截图文字，返回 [{text,x,y,w,h}]（图内像素坐标）。

    img_w/img_h 为原始截图尺寸；OCR 结果按比例换算回原始坐标。
    无可用 OCR 引擎时返回 []。
    """
    try:
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 2)   # COINIT_APARTMENTTHREADED，失败忽略
    except Exception:
        pass
    try:
        return asyncio.run(_ocr_async(png_bytes, img_w, img_h))
    except Exception:
        return []


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
            if not text:
                continue
            items.append({"text": text,
                          "x": int(r.x * sx + r.width * sx / 2),
                          "y": int(r.y * sy + r.height * sy / 2),
                          "w": int(r.width * sx), "h": int(r.height * sy),
                          "src": "ocr"})
    return items


# ---------- 统一入口：合并 UIA + OCR ----------
def locate_elements(png_bytes: bytes, img_w: int, img_h: int) -> list:
    """三层合并定位：UIA 优先，OCR 补充（按中心坐标去重）。"""
    elements = []
    seen = set()
    for e in uia_elements() + ocr_elements(png_bytes, img_w, img_h):
        key = (e["x"] // 4, e["y"] // 4)   # 4px 粒度去重（UIA 与 OCR 同目标会重叠）
        if key in seen:
            continue
        seen.add(key)
        elements.append(e)
    return elements


def find_element(target: str, elements: list) -> tuple:
    """模糊匹配目标文本，返回其中心坐标 (x, y)；未命中返回 None。

    匹配优先级：完全相等 > 目标含于元素名 > 元素名含于目标。
    """
    if not target:
        return None
    t = _norm(target)
    best, best_score = None, -1
    for e in elements:
        n = _norm(e.get("text", ""))
        if not n:
            continue
        if n == t:
            score = 3
        elif t in n:
            score = 2
        elif n in t:
            score = 1
        else:
            continue
        if score > best_score:
            best, best_score = e, score
    return (best["x"], best["y"]) if best else None


def summarize(elements: list, limit: int = 40) -> str:
    """把定位到的元素压缩成模型可读的文本清单（避免超长）。"""
    rows = []
    for e in elements[:limit]:
        rows.append(f"「{e['text']}」@({e['x']},{e['y']})")
    return "、".join(rows) if rows else "（未识别到文字元素）"


def _norm(s: str) -> str:
    return re.sub(r"[\s\u3000]+", "", s).lower()
