import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import winapp_migrator.core.agent_browser as ab

IFRAME = '''<html><body style="margin:0">
<div id="modal" style="position:fixed;left:30px;top:30px;width:300px;height:150px;border:2px solid #333;background:#eee">
  <div style="text-align:right;padding:6px">
    <button aria-label="关闭" onclick="parent.closeModal('iframe')" style="cursor:pointer">×</button>
  </div>
  <div>iframe 弹窗内容</div>
</div>
</body></html>'''

MAIN = '''<html><body>
<h1>主页面</h1>
<div id="status">弹窗未关</div>
<iframe id="frame1" src="/inner" style="width:500px;height:300px;border:1px solid #999"></iframe>
<script>
  window.closeModal = function(origin){
    document.getElementById('frame1').style.display = 'none';
    document.getElementById('status').innerText = '已关闭(' + origin + ')';
  };
</script>
</body></html>'''


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = IFRAME.encode() if self.path == '/inner' else MAIN.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = HTTPServer(('127.0.0.1', 8765), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.5)

c = ab.controller()
ok, msg = c.start(engine='edge', headless=True)
print('START:', ok)
if not ok:
    srv.shutdown(); raise SystemExit(1)
time.sleep(1)
c.navigate('http://127.0.0.1:8765/')
time.sleep(2)

print('=== 元素清单（应含 iframe 内 × 关闭按钮）===')
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
srv.shutdown()
print('DONE')