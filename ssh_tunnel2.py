import paramiko, threading, time, sys, select

SSH_HOST = "39.104.28.191"
SSH_USER = "root"
SSH_PASS = "windows10ztlZTL"
LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 8080
REMOTE_HOST = "127.0.0.1"
REMOTE_PORT = 8080

print("Connecting SSH...", flush=True)
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect(SSH_HOST, port=22, username=SSH_USER, password=SSH_PASS, timeout=15)
    print("SSH connected: %s" % SSH_HOST, flush=True)
except Exception as e:
    print("SSH connect failed: %s" % e, flush=True)
    sys.exit(1)

transport = client.get_transport()
transport.set_keepalive(30)

# 使用 transport 的 open_channel 创建到远程的通道，绑定本地监听
import socket
listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind((LOCAL_HOST, LOCAL_PORT))
listener.listen(100)
print("Listening on %s:%d -> %s:%d" % (LOCAL_HOST, LOCAL_PORT, REMOTE_HOST, REMOTE_PORT), flush=True)

stop = False

def forward(local_conn):
    try:
        chan = transport.open_channel("direct-tcpip", (REMOTE_HOST, REMOTE_PORT), local_conn.getpeername())
        while True:
            r, w, x = select.select([local_conn, chan], [], [])
            if local_conn in r:
                data = local_conn.recv(4096)
                if not data:
                    break
                chan.sendall(data)
            if chan in r:
                data = chan.recv(4096)
                if not data:
                    break
                local_conn.sendall(data)
    except Exception as e:
        pass
    finally:
        try: local_conn.close()
        except: pass
        try: chan.close()
        except: pass

while True:
    try:
        local_conn, addr = listener.accept()
        t = threading.Thread(target=forward, args=(local_conn,))
        t.daemon = True
        t.start()
    except KeyboardInterrupt:
        break

listener.close()
client.close()
print("Tunnel closed", flush=True)
