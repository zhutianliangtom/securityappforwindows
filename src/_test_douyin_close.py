"""验证：抖音登录弹窗右上角图标关闭按钮能被识别并点击关闭"""
import time

import winapp_migrator.core.agent_browser as ab

c = ab.controller()
c.start(engine='edge', headless=False)
time.sleep(1)
c.navigate('https://www.douyin.com/')
time.sleep(5)

eid = c.find_by_text('登录')
print('登录按钮:', eid)
if eid:
    ok, msg, _ = c.click(eid=eid)
    print('点登录:', ok, msg)
time.sleep(2.5)

print('=== 弹窗是否存在 ===')
print('login-panel:', c._eval("!!document.getElementById('login-panel-new')")['text'])

print('=== 清单中应含「关闭」按钮 ===')
elems = c.get_interactive()
print('元素总数:', len(elems))
close_eid = 0
for e in elems:
    if '关闭' in (e.get('text') or ''):
        print(f"  命中: [{e['id']}] ({e['label']}) class={e.get('class','')[:40]}")
        close_eid = e['id']

print('=== find_by_text / find_close ===')
print('find_by_text(关闭):', c.find_by_text('关闭'))
print('find_close:', c._find_close())

print('=== 点击关闭按钮 ===')
if close_eid:
    ok, msg, _ = c.click(eid=close_eid)
    print('click:', ok, msg)
    time.sleep(1)
    print('弹窗是否消失:', c._eval("!!document.getElementById('login-panel-new')")['text'])

c.stop()
print('DONE')
