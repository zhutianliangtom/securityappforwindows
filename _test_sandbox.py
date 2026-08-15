import sys
sys.path.insert(0, "src")
from winapp_migrator.core import agent_sandbox as s

# 更贴近 AI 真实构造的命令
cmds = [
    # 生成请求（单行，wait=90 是 run_command 的参数，不在命令串里）
    'curl https://api.agnes-ai.cn/v1/images/generations -H "Authorization: Bearer sk-XXX" -H "Content-Type: application/json" -d \'{"model":"agnes-image-2.1-flash","prompt":"校园毕业照","size":"1K","ratio":"1:1","extra_body":{"response_format":"url"}}\'',
    # 下载（技能示例：含 powershell 取桌面 + 管道 tr）
    'DESKTOP=$(powershell -NoProfile -Command "[Environment]::GetFolderPath(\'Desktop\')" | tr -d \'\\r\')\nTS=$(python -c "import time;print(int(time.time()))")\ncurl -o "$DESKTOP/图片_${TS}.png" "https://x/y.png" --connect-timeout 10 --max-time 60',
    # 多命令拼接（AI 可能把生成+保存合并）
    'curl https://api.agnes-ai.cn/v1/images/generations -d \'{"prompt":"a&b"}\' ; curl -o "C:/Users/zhuzhu/Desktop/x.png" "https://x/y.png"',
    # 用 powershell 包装 curl
    'powershell -Command "curl https://api.agnes-ai.cn/v1/images/generations -H \'Authorization: Bearer sk-XXX\'"',
]
for c in cmds:
    print("---")
    print(s.assess_command(c))