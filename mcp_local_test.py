"""本地 MCP server 连接调用测试：stdio 传输，复用项目现有 agent_mcp.McpManager

验证流程：连接（initialize）→ 工具枚举（tools/list）→ 工具调用（tools/call）。
用法：python mcp_local_test.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from winapp_migrator.core.agent_mcp import McpManager, McpError  # noqa: E402

SERVER = {
    "name": "local-test",
    "type": "stdio",
    "command": sys.executable,
    "args": [str(ROOT / "mcp_servers" / "local_mcp_server.py")],
}


def main() -> int:
    mgr = McpManager()
    try:
        tools = mgr.connect_all([SERVER])
        if mgr.errors:
            print("[失败] 连接错误:", mgr.errors)
            return 1
        print(f"[OK] 连接成功，发现 {len(tools)} 个工具：")
        for t in tools:
            print("   -", t["function"]["name"], "-", t["function"]["description"])

        # 调用各工具（真实结果）
        calls = [
            ("system_info", {}),
            ("get_time", {}),
            ("env_var", {"name": "OS"}),
            ("read_file", {"path": str(ROOT / "README.md")}),
            ("list_dir", {"path": str(ROOT / "src" / "winapp_migrator" / "core")}),
        ]
        for name, args in calls:
            try:
                out = mgr.call_tool(name, args)
                preview = out[:150].replace("\n", " ⏎ ")
                print(f"[OK] {name} -> {preview}")
            except McpError as e:
                print(f"[失败] {name} 调用异常: {e}")
                return 1
        return 0
    finally:
        mgr.close_all()


if __name__ == "__main__":
    sys.exit(main())
