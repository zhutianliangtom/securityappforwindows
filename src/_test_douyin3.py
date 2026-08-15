"""复现第三步：dump 登录弹窗内所有元素，定位关闭按钮真实结构"""
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

print('=== 弹窗 #login-panel-new 内所有元素 ===')
r = c._eval(r"""(function(){
  var panel = document.getElementById('login-panel-new');
  if (!panel) return 'no-panel';
  var out = [];
  var all = panel.querySelectorAll('*');
  for (var i=0;i<all.length;i++){
    var el = all[i];
    var r2 = el.getBoundingClientRect();
    if (r2.width < 8 || r2.height < 8) continue;
    var tag = el.tagName.toLowerCase();
    var cls = (typeof el.className==='string'?el.className:'')||'';
    var aria = el.getAttribute('aria-label')||'';
    var ttl = el.getAttribute('title')||'';
    var txt = (el.innerText||'').trim().replace(/\s+/g,' ').slice(0,20);
    var vis = getComputedStyle(el).position;
    if (tag==='svg' || tag==='path' || aria || ttl || vis==='absolute' || vis==='fixed' || cls.indexOf('close')>=0 || txt==='×' || txt==='✕' || txt==='X' || txt==='x'){
      out.push({tag: tag, cls: cls.slice(0,40), aria: aria.slice(0,30), ttl: ttl.slice(0,30),
                txt: txt, pos: vis, x: Math.round(r2.left), y: Math.round(r2.top),
                w: Math.round(r2.width), h: Math.round(r2.height)});
    }
  }
  return JSON.stringify(out.slice(0, 60));
})()""")
print(r['text'][:3000])

print('=== 弹窗右上角区域(620-1000, 110-170) 所有元素 ===')
r2 = c._eval(r"""(function(){
  var out = [];
  var all = document.querySelectorAll('*');
  for (var i=0;i<all.length;i++){
    var el = all[i];
    var r3 = el.getBoundingClientRect();
    if (r3.width < 5 || r3.height < 5) continue;
    if (r3.left > 600 && r3.right < 1020 && r3.top > 100 && r3.bottom < 180){
      var tag = el.tagName.toLowerCase();
      var cls = (typeof el.className==='string'?el.className:'')||'';
      var aria = el.getAttribute('aria-label')||'';
      var txt = (el.innerText||'').trim().replace(/\s+/g,' ').slice(0,20);
      out.push({tag: tag, cls: cls.slice(0,40), aria: aria.slice(0,30), txt: txt,
                x: Math.round(r3.left), y: Math.round(r3.top), w: Math.round(r3.width), h: Math.round(r3.height)});
    }
  }
  return JSON.stringify(out);
})()""")
print(r2['text'][:2000])

print('=== 是否有 shadow DOM 弹窗宿主 ===')
r3 = c._eval(r"""(function(){
  var n = 0; var hosts = [];
  var all = document.querySelectorAll('*');
  for (var i=0;i<all.length;i++){
    if (all[i].shadowRoot){ n++; hosts.push({tag: all[i].tagName.toLowerCase(), id: all[i].id, cls: (typeof all[i].className==='string'?all[i].className:'').slice(0,30)}); }
  }
  return JSON.stringify({count: n, hosts: hosts.slice(0,10)});
})()""")
print(r3['text'][:800])

c.stop()
print('DONE')
