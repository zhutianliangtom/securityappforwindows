import os
import tempfile
import time

import winapp_migrator.core.agent_browser as ab

html = '''
<html><body>
<button onclick="window.__r='A'">普通按钮</button>
<div id="host"></div>
<script>
  window.__srSet = false;
  var host = document.getElementById('host');
  try {
    var sr = host.attachShadow({mode:'open'});
    sr.innerHTML = '<button id="shbtn" aria-label="关闭shadow" onclick="window.__r=\'SHADOW_CLOSE\'">✕</button>';
    window.__srSet = true;
  } catch(e) { window.__srErr = String(e); }
</script>
</body></html>
'''
p = os.path.join(tempfile.gettempdir(), 'wm_browser_test10.html')
with open(p, 'w', encoding='utf-8') as f:
    f.write(html)

c = ab.controller()
c.start(engine='edge', headless=True)
time.sleep(1)
c.navigate('file:///' + p.replace('\\', '/'))
time.sleep(1.5)

print('=== 脚本是否成功 attach shadow ===')
r = c.eval("JSON.stringify({set: window.__srSet, err: window.__srErr || ''})")
print('eval:', r['text'])

print('=== host 是否有 shadowRoot ===')
r = c.eval("var h=document.getElementById('host'); JSON.stringify({sr: !!h.shadowRoot, btn: h.shadowRoot ? h.shadowRoot.querySelector('#shbtn') ? 'found' : 'no' : 'no-sr'})")
print('eval2:', r['text'])

c.stop()
os.remove(p)
print('DONE')