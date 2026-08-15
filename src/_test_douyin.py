"""复现：抖音网页版登录弹窗的关闭按钮到底在哪（主文档/iframe/shadow）"""
import time

import winapp_migrator.core.agent_browser as ab

c = ab.controller()
ok, msg = c.start(engine='edge', headless=False)
print('START:', ok, msg)
if not ok:
    raise SystemExit(1)
time.sleep(1)
c.navigate('https://www.douyin.com/')
time.sleep(6)   # 等待弹窗出现

print('=== 页面标题/URL ===')
print('title:', c._eval('document.title')['text'])
print('url:', c._eval('location.href')['text'])

print('=== 帧树（是否有 iframe）===')
s = c._active_session
c._ensure_runtime(s)
for _ in range(2):
    c._call('Runtime.evaluate', {'expression': '1', 'returnByValue': True}, session=s)
for f in c._get_frames(s):
    print('  frame:', f['frameId'][:8], 'parent:', f.get('parentId','')[:8] or '-')

print('=== 主文档 iframe 数量 ===')
print(c._eval('document.querySelectorAll("iframe").length')['text'])

print('=== 登录弹窗相关节点 ===')
r = c._eval(r"""(function(){
  var out = [];
  var all = document.querySelectorAll('*');
  for (var i=0;i<all.length;i++){
    var el = all[i];
    var cls = (typeof el.className==='string'?el.className:'')||'';
    var id = el.id||'';
    var s = (cls+' '+id).toLowerCase();
    if (s.indexOf('login')>=0 || s.indexOf('close')>=0 || s.indexOf('modal')>=0 || s.indexOf('popup')>=0 || s.indexOf('dialog')>=0){
      var t = (el.innerText||'').trim().replace(/\s+/g,' ').slice(0,40);
      var r = el.getBoundingClientRect();
      if (r.width>0 && r.height>0)
        out.push({tag: el.tagName.toLowerCase(), cls: cls.slice(0,60), id: id.slice(0,40),
                  text: t, w: Math.round(r.width), h: Math.round(r.height)});
    }
  }
  return JSON.stringify(out.slice(0, 40));
})()""")
print('弹窗节点数:', '见下')
print(r['text'][:2000])

print('=== 可交互元素清单（前 30）===')
elems = c.get_interactive()
print('元素总数:', len(elems))
for e in elems[:30]:
    print(f"  [{e['id']}] ({e['label']}) class={e.get('class','')[:30]}")

print('=== 关闭按钮查找 ===')
print('find_close:', c._find_close())
print('find_by_text(关闭):', c.find_by_text('关闭'))
print('find_by_text(登录):', c.find_by_text('登录'))

c.stop()
print('DONE')
