import os
import tempfile
import time

import winapp_migrator.core.agent_browser as ab

html = '''
<html><body>
<button onclick="window.__r='A'">普通按钮</button>
<div id="host"></div>
<script>
  var host = document.getElementById('host');
  var sr = host.attachShadow({mode:'open'});
  sr.innerHTML = '<button aria-label="关闭shadow" onclick="window.__r=\'SHADOW_CLOSE\'">✕</button>';
</script>
</body></html>
'''
p = os.path.join(tempfile.gettempdir(), 'wm_browser_test9.html')
with open(p, 'w', encoding='utf-8') as f:
    f.write(html)

c = ab.controller()
c.start(engine='edge', headless=True)
time.sleep(1)
c.navigate('file:///' + p.replace('\\', '/'))
time.sleep(1.5)

print('=== 直接检查 shadowRoot ===')
r = c.eval("var h=document.getElementById('host'); JSON.stringify({hasSR: !!h.shadowRoot, inner: h.shadowRoot ? h.shadowRoot.innerHTML : ''})")
print('eval:', r['text'])

print('=== 测试 shadow 内 querySelectorAll ===')
r = c.eval("var h=document.getElementById('host'); var btns=h.shadowRoot.querySelectorAll('button').length; JSON.stringify({n:btns})")
print('eval2:', r['text'])

print('=== 手动跑 walkDoc 测试 shadow 递归 ===')
c.eval("window.__dbg=[]; window.__walk=function(doc,oL,oT,fn){var ns;try{ns=doc.querySelectorAll('button, a, [aria-label]')}catch(e){ns=[]}for(var i=0;i<ns.length;i++){var el=ns[i];var r=el.getBoundingClientRect();if(r.width<1||r.height<1)continue;fn(el)}var all=doc.querySelectorAll('*');for(var s=0;s<all.length;s++){var host=all[s];var sr=host.shadowRoot;if(sr){window.__dbg.push('SR on '+host.tagName);window.__walk(sr,0,0,fn)}}}")
r = c.eval("window.__walk(document,0,0,function(el){window.__dbg.push(el.tagName+':'+el.getAttribute('aria-label'))}); JSON.stringify(window.__dbg)")
print('walk dbg:', r['text'])

c.stop()
os.remove(p)
print('DONE')