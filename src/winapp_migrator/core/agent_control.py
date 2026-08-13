"""电脑操控专属 Agent（Windows 环境优化）：最优操控逻辑集中管理。

定位策略（准确率优先）：
  UIA(原生控件,精确) → OCR(像素级) 多策略，带 TTL 缓存；未命中自动强制刷新重试，
  仍失败返回可点元素清单供模型换方案，杜绝盲目坐标估算。

移动策略（人性化，避免激进）：
  真人式两条线段：快速接近 + 慢速精确落点，ease-out 快起慢落、温和弧度，
  时长随距离自适应，末段精确落点保证。

执行策略（可靠+反馈）：
  点击/输入/滑动统一入口，均在操作位置触发反馈动画，结果文本返回给模型自查。
"""

from winapp_migrator.core import agent_screen, agent_locator, agent_feedback


class ComputerController:
    """电脑操控最优逻辑控制器（Windows 环境）。"""

    # ---------- 定位：多策略 + 缓存 + 智能重试 ----------
    def find(self, text: str, retry: bool = True):
        """按文字定位物理坐标 (x,y)。UIA→OCR 多策略，带缓存；未命中强制刷新重试一次。"""
        text = (text or "").strip()
        if not text:
            return None
        for force in (False, True) if retry else (False,):
            elems = agent_locator.get_screen_elements(force=force)
            hit = agent_locator.find_element(text, elems)
            if hit:
                return hit
        return None

    def summarize(self) -> str:
        """当前屏幕可点文字元素清单（供模型换方案）"""
        return agent_locator.summarize(agent_locator.get_screen_elements())

    # ---------- 移动：真人式最优轨迹 ----------
    def move(self, x, y):
        agent_screen.move_mouse(int(x), int(y))

    # ---------- 点击：文本精准 / 坐标两级 + 自动校验纠偏 ----------
    def _snap(self, x: int, y: int, elems, radius: int = 5):
        """若坐标落在某文字元素矩形内(含容差)，吸附到该元素中心，否则返回原坐标。
        用于自动纠偏：模型给的图标/图形坐标若恰好落在文字控件上，吸附到控件中心更精准。"""
        for e in elems:
            w, h = e.get("w", 0), e.get("h", 0)
            if w <= 0 or h <= 0:
                continue
            ex, ey = e["x"], e["y"]
            if abs(x - ex) <= w // 2 + radius and abs(y - ey) <= h // 2 + radius:
                return ex, ey
        return x, y

    def _element_at(self, x: int, y: int, elems, radius: int = 5) -> str:
        """返回包含坐标 (x,y) 的文字元素名称；无则返回空串（用于点击后校验落点）"""
        for e in elems:
            w, h = e.get("w", 0), e.get("h", 0)
            if w <= 0 or h <= 0:
                continue
            ex, ey = e["x"], e["y"]
            if abs(x - ex) <= w // 2 + radius and abs(y - ey) <= h // 2 + radius:
                return e.get("text", "")
        return ""

    def click_text(self, text: str, button: str = "left"):
        """按文字精准点击；返回 (坐标, 结果文本)。未命中返回 (None, 提示)。"""
        hit = self.find(text)
        if not hit:
            return None, f"[未找到文字「{text}」] 可用元素：{self.summarize()}"
        x, y = hit
        agent_screen.click_physical(x, y, button, 1)
        return (x, y), f"已按文字「{text}」精确定位并点击 ({x},{y})"

    def click(self, x=None, y=None, text=None, button: str = "left", clicks: int = 1):
        """统一点击入口：优先 text 精准定位，其次坐标并自动纠偏+校验，最后当前光标。"""
        if text:
            hit = self.find(text)
            if not hit:
                return None, f"[未找到文字「{text}」] 可用元素：{self.summarize()}"
            x, y = hit
        if x is None or y is None:
            agent_screen.click(None, None, button, clicks)
            return None, f"已点击当前鼠标位置 {button} 键 x{clicks}"
        # 坐标点击：自动纠偏（吸附到最近文字元素中心）+ 点击后校验落点
        elems = agent_locator.get_screen_elements()
        sx, sy = self._snap(int(x), int(y), elems)
        agent_screen.click(sx, sy, button, clicks)
        msg = f"已点击 ({sx}, {sy}) {button} 键 x{clicks}"
        if (sx, sy) != (int(x), int(y)):
            msg += "（已吸附到最近文字元素中心自动纠偏）"
        hit_name = self._element_at(sx, sy, elems)
        if hit_name:
            msg += f"（落点校验：在「{hit_name}」控件内）"
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