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

    # ---------- 点击：文本精准 / 坐标两级 ----------
    def click_text(self, text: str, button: str = "left"):
        """按文字精准点击；返回 (坐标, 结果文本)。未命中返回 (None, 提示)。"""
        hit = self.find(text)
        if not hit:
            return None, f"[未找到文字「{text}」] 可用元素：{self.summarize()}"
        x, y = hit
        agent_screen.click_physical(x, y, button, 1)
        return (x, y), f"已按文字「{text}」精确定位并点击 ({x},{y})"

    def click(self, x=None, y=None, text=None, button: str = "left", clicks: int = 1):
        """统一点击入口：优先 text 精准定位，其次坐标，最后当前光标。返回 (坐标, 结果文本)。"""
        if text:
            hit = self.find(text)
            if not hit:
                return None, f"[未找到文字「{text}」] 可用元素：{self.summarize()}"
            x, y = hit
        if x is None or y is None:
            agent_screen.click(None, None, button, clicks)
            return None, f"已点击当前鼠标位置 {button} 键 x{clicks}"
        agent_screen.click(int(x), int(y), button, clicks)
        return (int(x), int(y)), f"已点击 ({int(x)}, {int(y)}) {button} 键 x{clicks}"

    # ---------- 输入 / 滑动 ----------
    def type_text(self, text: str):
        agent_screen.type_text(text)

    def press(self, key: str):
        agent_screen.key_press(key)

    def scroll(self, delta: int):
        agent_screen.scroll(delta)


# 模块级单例：供 agent_tools 等复用同一控制器
_instance = None


def controller() -> ComputerController:
    global _instance
    if _instance is None:
        _instance = ComputerController()
    return _instance