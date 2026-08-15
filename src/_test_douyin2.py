"""复现第二步：点击登录按钮 → 触发登录弹窗 → 分析关闭按钮结构"""
import time

import winapp_migrator.core.agent_browser as ab

c = ab.controller()
ok, msg = c.start(engine='edge', headless=False)
print('START:', ok, msg)
if not ok:
    raise SystemExit(1)
time.sleep(1)
c.navigate('https://www.douyin.com/')
time.sleep(5)

print('=== 点击登录按钮 [16] ===')
eid = c.find_by_text('登录')
print('登录按钮 eid:', eid)
if eid:
    ok, msg, _ = c.click(eid=eid)
    print('click:', ok, msg)
time.sleep(3)

print('=== 点击后：登录弹窗相关节点 ===')
r = c._eval(r"""(function(){
  var out = [];
  var all = document.querySelectorAll('*');
  for (var i=0;i<all.length;i++){
    var el = all[i];
    var cls = (typeof el.className==='string'?el.className:'')||'';
    var id = el.id||'';
    var s = (cls+' '+id).toLowerCase();
    if (s.indexOf('login')>=0 || s.indexOf('close')>=0 || s.indexOf('modal')>=0 || s.indexOf('popup')>=0 || s.indexOf('dialog')>=0 || s.indexOf('qrcode')>=0 || s.indexOf('mask')>=0){
      var t = (el.innerText||'').trim().replace(/\s+/g,' ').slice(0,50);
      var r2 = el.getBoundingClientRect();
      if (r2.width>40 && r2.height>40)
        out.push({tag: el.tagName.toLowerCase(), cls: cls.slice(0,50), id: id.slice(0,40),
                  text: t, w: Math.round(r2.width), h: Math.round(r2.height),
                  x: Math.round(r2.left), y: Math.round(r2.top)});
    }
  }
  return JSON.stringify(out.slice(0, 30));
})()""")
print(r['text'][:2500])

print('=== 弹窗内可交互元素（新清单找关闭按钮）===')
elems = c.get_interactive()
print('元素总数:', len(elems))
for e in elems:
    t = (e.get('text') or '')
    cls = (e.get('class') or '').lower()
    if '关闭' in t or '×' in t or 'close' in cls or 'cancel' in cls or 'login' in cls or '扫码' in t or '登录' in t:
        print(f"  [{e['id']}] ({e['label']}) class={e.get('class','')[:40]}")
print('find_close:', c._find_close())

# 保存当前页面 HTML 中弹窗部分供分析
c.stop()
print('DONE')
