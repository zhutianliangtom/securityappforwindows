import paramiko, threading, time, webbrowser, os, sys

SSH_HOST = "39.104.28.191"
SSH_USER = "root"
SSH_PASS = "windows10ztlZTL"
LOCAL_PORT = 8080
REMOTE_HOST = "127.0.0.1"
REMOTE_PORT = 8080

print("Connecting SSH tunnel...")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect(SSH_HOST, port=22, username=SSH_USER, password=SSH_PASS, timeout=10)
    print(f"SSH connected to {SSH_HOST}")
except Exception as e:
    print(f"SSH connection failed: {e}")
    sys.exit(1)

# 建立端口转发
transport = client.get_transport()
try:
    transport.request_port_forward("", LOCAL_PORT)
    print(f"Port forwarding established: localhost:{LOCAL_PORT} -> {REMOTE_HOST}:{REMOTE_PORT}")
except Exception as e:
    print(f"Port forwarding failed: {e}")
    sys.exit(1)

# 后台运行线程保持隧道
def keep_alive():
    while True:
        time.sleep(60)

threading.Thread(target=keep_alive, daemon=True).start()

# 打开浏览器
time.sleep(1)
url = f"http://127.0.0.1:{LOCAL_PORT}"
print(f"Opening browser: {url}")
webbrowser.open(url)
print("Browser opened. Press Ctrl+C to exit.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nClosing tunnel...")
    transport.cancel_port_forward("", LOCAL_PORT)
    client.close()
    print("Done.")
