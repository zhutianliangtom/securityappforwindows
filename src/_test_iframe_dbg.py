import os
import tempfile
import time

import winapp_migrator.core.agent_browser as ab

iframe_html = '<html><body><button onclick="window.__c=1">内部按钮</button></body></html>'
p_iframe = os.path.join(tempfile.gettempdir(), 'wm_iframe_inner.html')
with open(p_iframe, 'w', encoding='utf-8') as f:
    f.write(iframe_html)

main_html = '<html><body><h1>主</h1><iframe src="%s"></iframe></body></html>' % ('file:///' + p_iframe.replace('\\', '/'))
p_main = os.path.join(tempfile.gettempdir(), 'wm_iframe_main.html')
with open(p_main, 'w', encoding='utf-8') as f:
    f.write(main_html)

c = ab.controller()
c.start(engine='edge', headless=True)
time.sleep(1)
c.navigate('file:///' + p_main.replace('\\', '/'))
time.sleep(2)

print('=== 直接 eval：主文档是否有 iframe ===')
r = c.eval("JSON.stringify({frames: document.querySelectorAll('iframe').length, body: document.body.innerText.slice(0,50)})")
print('eval:', r['text'])

print('=== 尝试访问 iframe contentDocument ===')
r = c.eval("var f=document.querySelector('iframe'); f ? JSON.stringify({has: !!f.contentDocument, title: f.contentDocument && f.contentDocument.title}) : 'no-iframe'")
print('eval2:', r['text'])

print('=== 直接测试 walkDoc 引擎（单独运行）===')
c.eval("var __sel='button,a,input'; var __out=[]; function __walk(doc,oL,oT,fn){var ns;try{ns=doc.querySelectorAll(__sel)}catch(e){ns=[]}for(var i=0;i<ns.length;i++){var el=ns[i];var r=el.getBoundingClientRect();if(r.width<1||r.height<1)continue;if(fn(el,oL+r.left,oT+r.top)===false)return false}var fs=doc.querySelectorAll('iframe');for(var j=0;j<fs.length;j++){var fr=fs[j];var rr=fr.getBoundingClientRect();var idoc;try{idoc=fr.contentDocument}catch(e){idoc=null}if(idoc&&idoc!==doc){if(__walk(idoc,oL+rr.left,oT+rr.top,fn)===false)return false}}return true} __walk(document,0,0,function(el,aL,aT){__out.push(el.tagName)})")
r = c.eval("JSON.stringify(__out)")
print('walk result:', r['text'])

c.stop()
os.remove(p_main); os.remove(p_iframe)
print('DONE')