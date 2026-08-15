import os
import tempfile
import time

import winapp_migrator.core.agent_browser as ab

# iframe 内容：带关闭按钮的弹窗
iframe_html = '''
<html><body style="margin:0">
<div id="modal" style="position:fixed;left:30px;top:30px;width:300px;height:150px;border:1px solid #333;background:#eee">
  <div style="text-align:right;padding:6px">
    <button aria-label="关闭" onclick="parent.closeModal('iframe')" style="cursor:pointer">×</button>
  </div>
  <div>iframe 弹窗内容</div>
</div>
</body></html>
'''
p_iframe = os.path.join(tempfile.gettempdir(), 'wm_iframe_inner.html')
with open(p_iframe, 'w', encoding='utf-8') as f:
    f.write(iframe_html)

# 主页面：嵌入 iframe（同源 file:// 域），iframe 弹窗关闭后主页面状态变化
main_html = '''
<html><body>
<h1>主页面</h1>
<div id="status">弹窗未关</div>
<iframe id="frame1" src="%s" style="width:500px;height:300px;border:1px solid #999"></iframe>
<script>
  function closeModal(origin){
    var fr = document.getElementById('frame1');
    fr.style.display = 'none';
    document.getElementById('status').innerText = '已关闭(' + origin + ')';
  }
  window.closeModal = closeModal;
</script>
</body></html>
''' % ('file:///' + p_iframe.replace('\\', '/'))

p_main = os.path.join(tempfile.gettempdir(), 'wm_iframe_main.html')
with open(p_main, 'w', encoding='utf-8') as f:
    f.write(main_html)

c = ab.controller()
ok, msg = c.start(engine='edge', headless=True)
print('START:', ok)
if not ok:
    os.remove(p_main); os.remove(p_iframe); raise SystemExit(1)
time.sleep(1)
c.navigate('file:///' + p_main.replace('\\', '/'))
time.sleep(2)

print('=== 元素清单（应含 iframe 内的 × 关闭按钮）===')
print(c.summarize())

print('=== 1. find_close 定位 iframe 内关闭按钮 ===')
eid = c._find_close()
print('find_close eid:', eid)

print('=== 2. 点击关闭按钮 ===')
if eid:
    before = c._page_snapshot_marker()
    ok, msg, _ = c.click(eid=eid)
    print('click:', ok, msg)
    after = c._page_snapshot_marker()
    print('指纹变化:', before != after)
    print('主页面状态:', c.eval("document.getElementById('status').innerText")['text'])

c.stop()
os.remove(p_main); os.remove(p_iframe)
print('DONE')