"""验证 CDP DOM pierce 能否穿透跨域 iframe 定位并点击关闭按钮。
主页面在 127.0.0.1:8765，iframe 在 127.0.0.1:8766（不同端口=不同源，contentDocument 对页面 JS 不可见）。"""
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import winapp_migrator.core.agent_browser as ab

IFRAME = '''<html><body style="margin:0">
<div id="modal" style="position:fixed;left:40px;top:60px;width:300px;height:150px;border:2px solid #333;background:#eee">
  <div style="text-align:right;padding:6px">
    <button aria-label="关闭" onclick="document.getElementById('modal').style.display='none';document.getElementById('status').innerText='已关闭'" style="cursor:pointer">×</button>
  </div>
  <div>iframe 弹窗内容</div>
</div>
<div id="status">弹窗未关</div>
</body></html>'''

MAIN = '''<html><body>
<h1>主页面</h1>
<iframe id="frame1" src="http://127.0.0.1:8766/inner" style="width:500px;height:300px;border:1px solid #999"></iframe>
</body></html>'''


def make_handler(page):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = page.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    return H


srv_a = HTTPServer(('127.0.0.1', 8765), make_handler(MAIN))
srv_b = HTTPServer(('127.0.0.1', 8766), make_handler(IFRAME))
threading.Thread(target=srv_a.serve_forever, daemon=True).start()
threading.Thread(target=srv_b.serve_forever, daemon=True).start()
time.sleep(0.5)

c = ab.controller()
ok, msg = c.start(engine='edge', headless=True)
print('START:', ok)
if not ok:
    srv_a.shutdown(); srv_b.shutdown(); raise SystemExit(1)
time.sleep(1)
c.navigate('http://127.0.0.1:8765/')
time.sleep(2)

print('=== 元素清单（应含跨域 iframe 内 × 关闭按钮）===')
elems = c.get_interactive()
print('元素数:', len(elems))
for e in elems:
    if '关闭' in e['text'] or '×' in e['text'] or 'close' in e['class'].lower():
        print('  命中:', e)
eid = c.find_by_text('关闭')
print('find_by_text(关闭) eid:', eid)

print('=== 定位坐标（应为主视口坐标）===')
pos = c._locate_point(eid) if eid else None
print('locate:', pos)

def read_inner_status(c):
    """通过 iframe 的执行上下文读取其内部 status 文本（跨域 iframe 也能读到）。"""
    s = c._active_session
    c._ensure_runtime(s)
    for _ in range(2):
        c._call('Runtime.evaluate', {'expression': '1', 'returnByValue': True}, session=s)
    frames = c._get_frames(s)
    for f in frames:
        if not f.get('parentId'):
            continue  # 跳过主文档
        ctx = c._frame_ctx.get((s, f['frameId']))
        if ctx is None:
            continue
        try:
            r = c._call('Runtime.evaluate', {
                'expression': "(function(){ var el=document.getElementById('status'); return el ? el.innerText : 'no-status'; })()",
                'returnByValue': True, 'contextId': ctx}, session=s)
            v = r.get('result', {}).get('value')
            if v:
                return v
        except Exception:
            continue
    return '未找到 iframe 文档'


print('=== 点击关闭按钮 ===')
if eid:
    ok, msg, _ = c.click(eid=eid)
    print('click:', ok, msg)

print('=== 跨域 iframe 内状态（点后应为已关闭）===')
print(read_inner_status(c))

c.stop()
srv_a.shutdown(); srv_b.shutdown()
print('DONE')
