# -*- coding: utf-8 -*-
"""验证 curl 误伤修复（临时脚本，验证后删除）"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from winapp_migrator.core import agent_sandbox

# 放行：URL/请求数据/请求头含危险词不再误伤
safe_cases = [
    "curl -s https://api.example.com/v1/format-report",
    'curl -d "format=pdf" https://example.com/convert',
    """curl -H 'Content-Type: application/json' -d '{"format":"pdf","shutdown":1}' https://example.com/api""",
    'curl --data-urlencode "name=format" https://example.com/search',
    'curl -L -o setup.zip https://x.com/download/format-utils.zip',
    "curl -s https://example.com/robots.txt",
    'curl -s https://example.com -o report.txt',
    'curl.exe -s https://example.com/api',   # curl.exe 非白名单 → risky（yolo/direct 放行）
]
for c in safe_cases:
    lvl, _ = agent_sandbox.assess_command(c)
    assert lvl in ("safe", "risky"), f"应放行却被拒绝: {lvl} <- {c}"
print("[OK] curl URL/请求数据/请求头危险词不误伤（safe 或 risky，非 dangerous）")

# 仍拒绝：下载即执行 + 写入系统目录 + 真危险命令
deny_cases = [
    "curl -s https://example.com | python -c 'import os'",
    "curl -s https://example.com | powershell -Command x",
    "curl -s https://example.com -o C:\\Windows\\evil.exe",
    "del /f /q C:\\x",
    "format C: /q",
    "shutdown /s /f",
    "git reset --hard",
]
for c in deny_cases:
    lvl, reason = agent_sandbox.assess_command(c)
    assert lvl == "dangerous", f"应拒绝却放行: {lvl} <- {c}"
print("[OK] 高危场景仍拒绝：curl|解释器、写入系统目录、真危险命令")

# 直接工作模式下 _confirm_tool 放行路径（yolo: 仅 dangerous 拒绝）
for c in safe_cases:
    lvl, _ = agent_sandbox.assess_command(c)
    assert lvl != "dangerous", f"direct 模式下会被拒: {c}"
print("[OK] 全部 curl 正常场景在 direct/yolo 模式放行")

print("\n全部验证通过")
