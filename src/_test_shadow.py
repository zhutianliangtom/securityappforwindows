import os
import tempfile
import time

import winapp_migrator.core.agent_browser as ab

html = '''
<html><body>
<button id="a" onclick="window.__r='A'">普通按钮</button>
<button aria-label="关闭" onclick="window.__r='CLOSE'">×</button>
<div id="host"></div>
<script>
  // shadow DOM 内放一个关闭按钮
  var host = document.getElementById('host');
  var sr = host.attachShadow({mode:'open'});
  sr.innerHTML = '<button aria-label="关闭shadow" onclick="window.__r=\'SHADOW_CLOSE\'">✕</button>';
</script>
<div id="out">none</div>
</body></html>
'''
p = os.path.join(tempfile.gettempdir(), 'wm_browser_test8.html')
with open(p, 'w', encoding='utf-8') as f:
    f.write(html)

c = ab.controller()
ok, msg = c.start(engine='edge', headless=True)
print('START:', ok)
time.sleep(1)
c.navigate('file:///' + p.replace('\\', '/'))
time.sleep(1.5)

print('=== 元素清单（应含 shadow DOM 内关闭按钮）===')
print(c.summarize())

print('=== 1. 普通按钮 ===')
ok, msg, _ = c.click(text='普通按钮')
print(ok, msg, '=> 触发:', c.eval("window.__r")['text'])

print('=== 2. find_close（主文档 aria-label 关闭）===')
c.eval("window.__r=''")
eid = c._find_close()
print('find_close eid:', eid, '(应命中主文档 × 或 shadow ✕ 之一)')
if eid:
    ok, msg, _ = c.click(eid=eid)
    print('click:', ok, msg, '=> 触发:', c.eval("window.__r")['text'])

c.stop()
os.remove(p)
print('DONE')