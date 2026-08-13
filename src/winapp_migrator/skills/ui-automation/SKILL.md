---
name: ui-automation
description: 界面自动化（电脑操控专用子Agent技能）：screenshot 截取目标窗口并给出可点击元素编号清单、click/click_text 按编号或文字点击、type_text 按输入框输入、move_mouse/zoom_in 只用于纯图标、press_key 键盘、refresh_screen 刷新清单
---

# ui-automation：屏幕观察与鼠标键盘操控（电脑操控专用子 Agent）

当电脑操控专用子 Agent 需要在 GUI 里点击按钮、输入文字、观察屏幕时使用本技能。
主 Agent 不直接使用本技能，统一通过 control_ui 派发目标。

## 1. 观察（一次截图，拿到语义清单）
- 先 `screenshot` 截取当前目标窗口（前台应用），返回**可点击/输入元素的编号清单 [id] (类型) 文字**。
- 只操作某个窗口时：`list_windows` 找到目标窗口 → `capture_window(window)` 聚焦该窗口并返回其清单。
- 界面变化后（点击/输入后）先用 `refresh_screen` 刷新最新 [id] 清单，更快（无需重发大图）。

## 2. 点击 / 输入（**只按清单 id 或文字，禁止读坐标**）
- **首选 `click(id=编号)`** 或 `click_text(text=文字)`：系统按清单精确解析像素坐标并点击，100% 精准。
- **输入用 `type_text(text=..., id=编号)` 或 `type_text(text=..., target=文字)`**：先自动点击目标输入框再输入，最稳。
- 只有**无文字的纯图标/图形目标**才用坐标：`move_mouse(x,y)` 移动 → `screenshot` 看红色准星是否套住 → 未对准按偏移修正 → 对准后 `click(x,y)`；目标太小先 `zoom_in(x,y)` 放大。
- 其余任何时候都不要自己估坐标、读刻度、猜位置。

## 3. 键盘 / 剪贴板
- 键盘：`press_key`；`type_text` 可含 enter/tab 等键名。
- 剪贴板：`clipboard(action=write, text)` 写入，`clipboard(action=read)` 读取。

## 4. 原则
- **同一界面可连续做多步**：清单里的 [id] 在界面变化前一直有效，不必每步都截图。
- 操作结果不确定时 `screenshot` 验证；失败先自查再换方案，禁止盲目重复点击。
- 系统自动解析坐标，不要手动换算。