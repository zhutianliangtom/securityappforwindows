import sys
sys.path.insert(0, "src")
from winapp_migrator.core import agent_engine, agent_llm

results = []
statuses = []

class F(agent_llm.LLMClient):
    def __init__(self):
        super().__init__(base_url="x", api_key="x", model="m")
        self.calls = 0
    def chat_stream(self, *a, **k):
        self.calls += 1
        if self.calls == 1:
            return {"text": "", "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "run_command", "arguments":
                    '{"command":"curl https://api.agnes-ai.cn/v1/images/generations -H \\"Authorization: Bearer sk-XXX\\" -H \\"Content-Type: application/json\\" -d \\'{\\"model\\":\\"agnes-image-2.1-flash\\",\\"prompt\\":\\"校园毕业照\\",\\"size\\":\\"1K\\",\\"ratio\\":\\"1:1\\",\\"extra_body\\":{\\"response_format\\":\\"url\\"}}\\'","wait":90}'}
            ]}
        return {"text": "done", "tool_calls": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

# YOLO = direct=True
e = agent_engine.AgentEngine(F(), on_result=lambda n, t, im: results.append((n, t)),
                             on_status=statuses.append, direct=True)
e.run("生成一张校园毕业照", agent_name="zhuzhu Copilot")
print("confirm结果:", results[0] if results else "无")
print("状态:", statuses)
# 检查是否被沙盒/用户拒绝
for n, t in results:
    if "拒绝" in t or "沙盒" in t:
        print(">>> 被拒绝:", t[:150])