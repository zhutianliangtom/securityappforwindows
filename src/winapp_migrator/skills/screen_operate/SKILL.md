---
name: screen_operate
description: 屏幕操控：screenshot 截取目标窗口并给出元素编号清单、click/click_text 按文字或编号点击、type_text 输入、move_mouse/zoom_in（仅纯图标）、press_key 键盘
---

# screen_operate：屏幕操控

当需要操作界面、点击按钮、输入文本时使用本技能。

1. 需要了解界面时先 `screenshot`，返回**可点击/输入元素的编号清单 [id] (类型) 文字**。
2. 每步操作前用一句话说明意图。
3. **点击/输入只按清单里的 [id] 或文字**（click(id=..) / click_text(text=..) / type_text target/id），
   系统精确定位像素，禁止自己估坐标；只有无文字的纯图标才用 move_mouse+click 坐标。
4. 界面变化后先 `refresh_screen` 刷新清单；操作结果不确定时 `screenshot` 验证：
   目标出现才继续；失败则分析原因、换方案重试。
5. 全部完成后确认最终结果（需要时截图）。