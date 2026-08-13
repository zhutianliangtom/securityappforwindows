---
name: ui-automation
description: 界面自动化：screenshot 截图观察、click_text 按文字点击、move_mouse/click/zoom_in 精确鼠标操作、type_text/press_key 键盘输入、list_windows/capture_window 只截指定窗口、clipboard 剪贴板
---

# ui-automation：屏幕观察与鼠标键盘操控

当需要操作界面、点击按钮、输入文字、观察屏幕时使用本技能。

## 1. 观察
- 需要了解当前界面时先 screenshot 截屏观察
- 只操作某个窗口时：list_windows 找到目标窗口 → capture_window(window) 只截该窗口，避开其他窗口干扰

## 2. 点击（按优先级）
- 文字类目标（按钮/菜单/输入框）：click_text(text)，系统 UIA+OCR 自动定位文字像素中心，无需自己估算坐标
- 图标/图形目标：move_mouse 移动 → 截图看红色准星是否套住目标 → 未对准按偏移修正坐标 → 对准后 click
- 目标太小：zoom_in(x, y) 放大后按细刻度读数，再以该坐标 click（系统自动换算）

## 3. 输入
- 键盘：press_key(键)；输入文本：type_text(text)
- 剪贴板：clipboard(action=write, text) 写入，clipboard(action=read) 读取

## 4. 原则
- 操作结果不确定时截图验证；失败先自查再换方案，禁止盲目重复点击
- 系统会自动把截图坐标换算为真实屏幕坐标，不要手动换算
