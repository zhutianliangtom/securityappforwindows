"""MCP（Model Context Protocol）客户端：支持 stdio 与 SSE 两种传输

- stdio：子进程 + newline-delimited JSON-RPC（tools/list、tools/call）
- SSE：HTTP GET /sse 建立事件流，POST /messages 发请求
- 多服务器聚合：tools 按 server 前缀去重命名，供 LLM function calling 使用
"""

import json
import queue
import subprocess
import threading
import urllib.request
import urllib.error

MCP_VERSION = "2024-11-05"
_REQ_TIMEOUT = 30


class McpError(Exception):
    pass


class _StdioTransport:
    def __init__(self, command: str, args: list):
        try:
            self._proc = subprocess.Popen(
                [command, *args], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception as e:
            raise McpError(f"启动 MCP 服务器失败: {e}")
        self._pending: dict = {}
        self._lock = threading.Lock()
        self._id = 0
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self):
        try:
            for line in self._proc.stdout:
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line.decode("utf-8", "replace"))
                except json.JSONDecodeError:
                    continue
                if isinstance(msg, dict) and "id" in msg:
                    q = self._pending.pop(msg["id"], None)
                    if q:
                        q.put(msg)
        except Exception:
            pass

    def request(self, method: str, params: dict) -> dict:
        with self._lock:
            self._id += 1
            rid = self._id
            q = queue.Queue()
            self._pending[rid] = q
        payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        try:
            self._proc.stdin.write(json.dumps(payload).encode() + b"\n")
            self._proc.stdin.flush()
        except Exception as e:
            raise McpError(f"MCP 发送失败: {e}")
        try:
            resp = q.get(timeout=_REQ_TIMEOUT)
        except queue.Empty:
            raise McpError(f"MCP 请求超时: {method}")
        if "error" in resp:
            raise McpError(f"MCP 错误: {resp['error']}")
        return resp.get("result", {})

    def close(self):
        try:
            self._proc.terminate()
        except Exception:
            pass


class _SSETransport:
    def __init__(self, url: str):
        self._url = url
        self._messages_url = None
        self._pending: dict = {}
        self._lock = threading.Lock()
        self._id = 0
        self._ready = threading.Event()
        threading.Thread(target=self._read_loop, daemon=True).start()
        if not self._ready.wait(timeout=_REQ_TIMEOUT):
            raise McpError(f"MCP SSE 初始化超时: {url}")

    def _read_loop(self):
        try:
            resp = urllib.request.urlopen(self._url, timeout=_REQ_TIMEOUT)
            buf = ""
            for raw in resp:
                buf += raw.decode("utf-8", "replace")
                while "\n\n" in buf:
                    chunk, buf = buf.split("\n\n", 1)
                    for line in chunk.splitlines():
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if not data:
                            continue
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(obj, dict) and obj.get("endpoint"):
                            self._messages_url = obj["endpoint"]
                            self._ready.set()
                            continue
                        if isinstance(obj, dict) and "id" in obj:
                            q = self._pending.pop(obj["id"], None)
                            if q:
                                q.put(obj)
        except Exception:
            pass
        finally:
            self._ready.set()

    def request(self, method: str, params: dict) -> dict:
        if not self._messages_url:
            raise McpError("MCP SSE 未获得 messages 端点")
        with self._lock:
            self._id += 1
            rid = self._id
            q = queue.Queue()
            self._pending[rid] = q
        body = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method,
                           "params": params}).encode()
        req = urllib.request.Request(
            self._messages_url, data=body,
            headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=_REQ_TIMEOUT)
        except urllib.error.HTTPError as e:
            raise McpError(f"MCP POST 失败: {e.code}")
        except urllib.error.URLError as e:
            raise McpError(f"MCP POST 网络错误: {e.reason}")
        try:
            resp = q.get(timeout=_REQ_TIMEOUT)
        except queue.Empty:
            raise McpError(f"MCP 请求超时: {method}")
        if "error" in resp:
            raise McpError(f"MCP 错误: {resp['error']}")
        return resp.get("result", {})

    def close(self):
        pass


class McpClient:
    """单个 MCP 服务器连接：stdio 或 sse"""

    def __init__(self, name: str, config: dict):
        self.name = name
        self._transport = None
        self._used: set = set()      # 已用的原始工具名（避免跨服务器重名）
        self._call_map: dict = {}    # schema 工具名 -> MCP 原始工具名
        typ = config.get("type", "stdio")
        if typ == "stdio":
            self._transport = _StdioTransport(config["command"], config.get("args", []))
        elif typ == "sse":
            self._transport = _SSETransport(config["url"])
        else:
            raise McpError(f"不支持的 MCP 传输类型: {typ}")
        self._init()

    def _init(self):
        self._transport.request("initialize", {
            "protocolVersion": MCP_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "winapp-migrator", "version": "1.0"},
        })
        # notifications/initialized（无 id 的通知，直接发送即可）
        try:
            self._transport.request("notifications/initialized", {})
        except McpError:
            pass

    def list_tools(self) -> list:
        """返回 OpenAI function schema 列表"""
        result = self._transport.request("tools/list", {})
        out = []
        for t in result.get("tools", []):
            raw = t.get("name", "")
            fname = raw if raw not in self._used else f"{self.name}_{raw}"
            self._used.add(raw)
            self._call_map[fname] = raw
            out.append({
                "type": "function",
                "function": {
                    "name": fname,
                    "description": t.get("description", "") or "",
                    "parameters": t.get("inputSchema") or {"type": "object",
                                                           "properties": {}},
                },
            })
        return out

    def call_tool(self, name: str, arguments: dict) -> str:
        raw = self._call_map.get(name, name)
        result = self._transport.request("tools/call", {"name": raw, "arguments": arguments})
        texts = []
        for item in result.get("content", []):
            if item.get("type") == "text":
                texts.append(item.get("text", ""))
        text = "\n".join(texts) or "(空结果)"
        if result.get("isError"):
            text = f"[MCP 工具错误] {text}"
        return text

    def close(self):
        if self._transport:
            self._transport.close()


class McpManager:
    """管理多个 MCP 服务器，聚合工具供 LLM 使用"""

    def __init__(self):
        self._clients: dict = {}
        self._name_to_server: dict = {}
        self._tools: list = []
        self.errors: list = []   # 各服务器连接失败信息

    def connect_all(self, servers: list) -> list:
        """servers: [{"name","type","command","args"|"url"}]，返回聚合后的工具 schema"""
        self._tools = []
        self.errors = []
        for cfg in servers:
            name = cfg.get("name", "mcp")
            try:
                client = McpClient(name, cfg)
                self._clients[name] = client
                for schema in client.list_tools():
                    fname = schema["function"]["name"]
                    self._name_to_server[fname] = name
                    self._tools.append(schema)
            except McpError as e:
                self.errors.append(f"[{name}] {e}")
        return self._tools

    def tool_schemas(self) -> list:
        return self._tools

    def call_tool(self, name: str, arguments: dict) -> str:
        server = self._name_to_server.get(name)
        if not server:
            raise McpError(f"未知 MCP 工具: {name}")
        return self._clients[server].call_tool(name, arguments)

    def close_all(self):
        for c in self._clients.values():
            try:
                c.close()
            except Exception:
                pass
        self._clients.clear()
        self._name_to_server.clear()
        self._tools = []
