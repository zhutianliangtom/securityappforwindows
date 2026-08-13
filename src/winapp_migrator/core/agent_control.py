"""电脑操控专属 Agent（Windows 环境优化）：最优操控逻辑集中管理。

定位策略（语义树优先，准确率优先）：
  目标窗口 UIA 语义树（原生控件,精确）→ OCR 兜底，带同屏缓存；按文字或
  清单编号 [id] 精确定位，未命中返回可点元素清单供模型换方案，杜绝盲目坐标估算。

移动策略（人性化，避免激进）：
  真人式两条线段：快速接近 + 慢速精确落点，ease-out 快起慢落、温和弧度，
  时长随距离自适应，末段精确落点保证。

执行策略（可靠+反馈）：
  点击/输入/滑动统一入口，文本优先（click_text / click_id），坐标仅用于纯图标；
  结果文本返回给模型自查，不强制每次整屏截图（多模态模型仅在需要时主动截图）。
"""

from winapp_migrator.core import agent_screen, agent_locator, agent_feedback


class ComputerController:
    """电脑操控最优逻辑控制器（Windows 环境）。"""

    # ---------- 定位：窗口语义树 + 缓存 + 智能重试 ----------
    def find(self, text: str, retry: bool = True):
        """按文字定位物理坐标 (x,y)。UIA 语义树→OCR 兜底，带缓存；未命中强制刷新重试一次。"""
        text = (text or "").strip()
        if not text:
            return None
        for force in (False, True) if retry else (False,):
            elems = agent_locator.get_elements(force=force)
            hit = agent_locator.find_element(text, elems)
            if hit:
                return hit
        return None

    def find_id(self, uid: int, retry: bool = True):
        """按清单编号 [id] 定位物理坐标 (x,y)。"""
        if not uid:
            return None
        elems = agent_locator.get_elements(force=True)
        return agent_locator.find_by_id(int(uid), elems)

    def summarize(self) -> str:
        """当前目标窗口的可点/可输入语义元素编号清单（模型按 id/文字引用，勿读坐标）"""
        return agent_locator.summarize(agent_locator.get_elements())

    # ---------- 移动：真人式最优轨迹 ----------
    def move(self, x, y):
        agent_screen.move_mouse(int(x), int(y))

    # ---------- 点击：文字/编号精确定位，坐标仅图标兜底 ----------
    def _snap(self, x: int, y: int, elems, radius: int = 6):
        """若坐标落在某语义元素矩形内(含容差)，吸附到该元素中心，否则返回原坐标。
        用于图标坐标自动纠偏：若恰好落在文字控件上，吸附到控件中心更精准。"""
        for e in elems:
            w, h = e.get("w", 0), e.get("h", 0)
            if w <= 0 or h <= 0:
                continue
            ex, ey = e["x"], e["y"]
            if abs(x - ex) <= w // 2 + radius and abs(y - ey) <= h // 2 + radius:
                return ex, ey
        return x, y

    def _element_at(self, x: int, y: int, elems, radius: int = 6) -> str:
        """返回包含坐标 (x,y) 的语义元素文本；无则返回空串（用于点击后校验落点）"""
        for e in elems:
            w, h = e.get("w", 0), e.get("h", 0)
            if w <= 0 or h <= 0:
                continue
            ex, ey = e["x"], e["y"]
            if abs(x - ex) <= w // 2 + radius and abs(y - ey) <= h // 2 + radius:
                return f"[{e.get('id')}] ({e.get('type', '元素')}) {e.get('text', '')}"
        return ""

    def click_text(self, text: str, button: str = "left"):
        """按文字精准点击；返回 (坐标, 结果文本)。未命中返回 (None, 提示)。"""
        hit = self.find(text)
        if not hit:
            return None, f"[未找到文字「{text}」] 可用元素：\n{self.summarize()}"
        x, y = hit
        agent_screen.click_physical(x, y, button, 1)
        return (x, y), f"已按文字「{text}」精确定位并点击 ({x},{y})"

    def click_id(self, uid: int, button: str = "left"):
        """按清单编号 [id] 精准点击；返回 (坐标, 结果文本)。未命中返回 (None, 提示)。"""
        hit = self.find_id(uid)
        if not hit:
            return None, f"[未找到编号 {uid}] 当前可用元素：\n{self.summarize()}"
        x, y = hit
        agent_screen.click_physical(x, y, button, 1)
        return (x, y), f"已按清单编号 [{uid}] 精确定位并点击 ({x},{y})"

    def click(self, x=None, y=None, text=None, uid=None, button: str = "left", clicks: int = 1):
        """统一入口：优先 text/uid 语义定位，其次坐标（仅图标）自动纠偏+校验，最后当前光标。

        语义路径（推荐）：text/uid 命中语义树 → click_physical 物理坐标直接点，像素级精确。
        坐标路径（仅纯图标/无文字目标）：模型读数 → map_to_screen 换算物理像素一次，
        吸附/落点校验均在物理空间，再 click_physical，杜绝二次换算乱点。
        """
        if text:
            return self.click_text(text, button)
        if uid is not None:
            return self.click_id(uid, button)
        if x is None or y is None:
            agent_screen.click(None, None, button, clicks)
            return None, f"已点击当前鼠标位置 {button} 键 x{clicks}"
        px, py = agent_screen.map_to_screen(int(x), int(y))
        elems = agent_locator.get_elements()
        sx, sy = self._snap(px, py, elems)
        agent_screen.click_physical(sx, sy, button, clicks)
        msg = f"已按坐标点击 ({sx}, {sy}) {button} 键 x{clicks}"
        if (sx, sy) != (px, py):
            msg += "（已吸附到最近元素中心自动纠偏）"
        hit_name = self._element_at(sx, sy, elems)
        if hit_name:
            msg += f"（落点校验：在「{hit_name}」内）"
        return (sx, sy), msg

    # ---------- 输入 / 滑动 / 拖拽 / 缩放 ----------
    def type_text(self, text: str):
        agent_screen.type_text(text)

    def press(self, key: str):
        agent_screen.key_press(key)

    def scroll(self, delta: int):
        agent_screen.scroll(delta)

    def drag(self, x1, y1, x2, y2):
        agent_screen.drag(int(x1), int(y1), int(x2), int(y2))

    def zoom(self, x, y):
        """放大指定坐标附近区域，返回 (物理坐标, 放大图 data URL)。"""
        px, py = agent_screen.map_to_screen(int(x), int(y))
        url = agent_screen.capture_zoom_data_url(px, py)
        return (px, py), url


# 模块级单例：供 agent_tools 等复用同一控制器
_instance = None


def controller() -> ComputerController:
    global _instance
    if _instance is None:
        _instance = ComputerController()
    return _instance