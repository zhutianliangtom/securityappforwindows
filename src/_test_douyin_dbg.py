"""debug: 抖音弹窗容器的 position/z-index，以及 scanPopupClose 候选"""
import time

import winapp_migrator.core.agent_browser as ab

c = ab.controller()
c.start(engine='edge', headless=False)
time.sleep(1)
c.navigate('https://www.douyin.com/')
time.sleep(5)
eid = c.find_by_text('登录')
if eid:
    c.click(eid=eid)
time.sleep(2.5)

print('=== #login-panel-new 及其祖先的定位样式 ===')
r = c._eval(r"""(function(){
  var el = document.getElementById('login-panel-new');
  if (!el) return 'no-panel';
  var out = [];
  var cur = el;
  while (cur && cur !== document.body){
    var cs = getComputedStyle(cur);
    var rr = cur.getBoundingClientRect();
    out.push({tag: cur.tagName.toLowerCase(), id: cur.id, cls: (typeof cur.className==='string'?cur.className:'').slice(0,40),
              pos: cs.position, z: cs.zIndex,
              x: Math.round(rr.left), y: Math.round(rr.top), w: Math.round(rr.width), h: Math.round(rr.height)});
    cur = cur.parentElement;
  }
  return JSON.stringify(out);
})()""")
print(r['text'])

print('=== 弹窗容器 = fixed 的层 ===')
r2 = c._eval(r"""(function(){
  var out = [];
  var all = document.querySelectorAll('*');
  for (var i=0;i<all.length;i++){
    var el = all[i];
    var cs = getComputedStyle(el);
    if (cs.position !== 'fixed') continue;
    var rr = el.getBoundingClientRect();
    if (rr.width < 200 || rr.height < 200) continue;
    var s = ((typeof el.className==='string'?el.className:'')||'') + ' ' + (el.id||'');
    out.push({id: el.id, cls: s.slice(0,50), z: cs.zIndex, x: Math.round(rr.left), y: Math.round(rr.top), w: Math.round(rr.width), h: Math.round(rr.height)});
  }
  return JSON.stringify(out);
})()""")
print(r2['text'][:1200])

c.stop()
print('DONE')
