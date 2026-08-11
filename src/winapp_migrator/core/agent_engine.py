"""Agent 引擎：循环"截屏分析 → 调用工具 → 截图验证"

- 流式输出：LLM 逐 token 回调（UI 实时显示）
- 工具调用：内置工具 + MCP 工具；每个工具执行前回调 confirm（UI 弹窗每步确认）
- 截图验证闭环：工具执行后自动截屏并作为下一轮视觉输入
- 沙盒：危险工具即使批准也由 agent_tools 硬拒绝
- tokens：发送前预计算（estimate），响应后累计实际 usage
"""

import json
import threading

from winapp_migrator.core import agent_llm, agent_tools, agent_skills
from winapp_migrator.core.agent_screen import capture_screen_data_url

# 会改变屏幕、需要执行后自动截图验证的工具
_SCREEN_CHANGING = {"click", "drag", "scroll", "press_key", "type_text",
                    "move_mouse", "run_command"}


class AgentEngine:
    def __init__(self, llm: agent_llm.LLMClient,
                 mcp_manager=None,
                 on_delta=None, on_status=None, on_result=None, confirm=None,
                 ask_user=None):
        """
        on_delta: Callable[[str], None]      流式文本增量
        on_status: Callable[[str], None]     步骤状态（如"正在思考/执行工具 click"）
        on_result: Callable[[str, str], None] 工具执行结果（工具名, 输出文本）
        confirm: Callable[[str, dict], bool] 工具执行前确认；None 表示自动放行（测试用）
        ask_user: Callable[[dict], str]      ask_user 提问回调（阻塞式，返回用户回答）
        """
        self.llm = llm
        self.mcp = mcp_manager
        self.on_delta = on_delta
        self.on_status = on_status
        self.on_result = on_result
        self.confirm = confirm
        self.ask_user = ask_user
        self._messages: list = []
        self.tokens = {"prompt": 0, "completion": 0}
        self.last_estimate = 0       # 最近一次请求前的预计算（输入 tokens）
        self._stop = threading.Event()
        self._thread: threading.Thread = None
        self._builtin_names = {t["function"]["name"] for t in agent_tools.TOOLS}

    # ---------- 控制 ----------
    def stop(self):
        self._stop.set()

    def reset_tokens(self):
        self.tokens = {"prompt": 0, "completion": 0}
        self.last_estimate = 0

    def clear_history(self):
        """清空全部对话上下文与 tokens（新对话从零开始）"""
        self._messages = []
        self.reset_tokens()

    def compress_history(self, keep_recent: int = 2) -> int:
        """启发式压缩上下文：保留最近 keep_recent 条消息完整，更早的文本合并为一条摘要。

        返回被合并的消息条数（0 表示无需压缩）。
        """
        if len(self._messages) <= keep_recent + 1:
            return 0
        head = self._messages[0]                       # system 提示
        recent = self._messages[-keep_recent:]
        old = self._messages[1:-keep_recent]
        parts = []
        for m in old:
            c = m.get("content")
            if isinstance(c, str) and c:
                parts.append(c)
            elif isinstance(c, list):
                for x in c:
                    if isinstance(x, dict) and x.get("type") == "text" and x.get("text"):
                        parts.append(x["text"])
        summary = ("（上下文已压缩，以下是此前对话的摘要）\n"
                   + "\n".join(parts[-2000:]) if parts else "")
        self._messages = [head]
        if summary:
            self._messages.append({"role": "user",
                                   "content": agent_llm.build_content(summary)})
        self._messages.extend(recent)
        return len(old)

    def _prune_images(self, max_keep=2):
        """历史中的截图只保留最近 max_keep 张，其余剥离 image_url 只留文本，防止上下文膨胀"""
        seen = 0
        for m in reversed(self._messages):
            c = m.get("content")
            if not isinstance(c, list):
                continue
            keep, drop = [], []
            for x in c:
                if isinstance(x, dict) and x.get("type") == "image_url":
                    if seen < max_keep:
                        seen += 1
                        keep.append(x)
                    else:
                        drop.append(x)
                else:
                    keep.append(x)
            if drop:
                m["content"] = keep

    def start(self, user_input: str, agent_name: str = ""):
        """后台线程执行一轮任务"""
        self._stop.clear()
        self._thread = threading.Thread(target=self.run, args=(user_input, agent_name),
                                        daemon=True)
        self._thread.start()

    def join(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)

    # ---------- 工具 ----------
    def _all_tools(self) -> list:
        tools = list(agent_tools.tool_schemas())
        if self.mcp:
            tools.extend(self.mcp.tool_schemas())
        return tools

    def _execute(self, name: str, args: dict, allow_dangerous: bool = False) -> dict:
        """执行内置或 MCP 工具，返回 {"text", "images"}"""
        if name == "ask_user":
            # 提问工具：不经沙盒/确认，直接向用户提问
            if self.ask_user:
                return {"text": self.ask_user(args), "images": []}
            return {"text": "[ask_user] 未接入提问面板", "images": []}
        if name in self._builtin_names:
            return agent_tools.execute_tool(name, args, allow_dangerous=allow_dangerous)
        if self.mcp:
            return {"text": self.mcp.call_tool(name, args), "images": []}
        return {"text": f"[未知工具] {name}", "images": []}

    # ---------- 主循环 ----------
    def run(self, user_input: str, agent_name: str = ""):
        system = agent_skills.build_system_prompt(agent_name)
        if not self._messages or self._messages[0].get("role") != "system":
            self._messages.insert(0, {"role": "system", "content": system})
        else:
            self._messages[0]["content"] = system  # 切换 Agent 时更新系统提示
        self._messages.append({"role": "user",
                               "content": agent_llm.build_content(user_input)})
        try:
            for _ in range(30):  # 最多 30 轮工具循环，防死循环
                if self._stop.is_set():
                    if self.on_status:
                        self.on_status("已停止")
                    return
                if self.on_status:
                    self.on_status("正在思考…")
                self._prune_images(2)  # 截图只保留最近 2 张，控制上下文体积
                # tokens 预计算
                self.last_estimate = agent_llm.estimate_tokens(
                    "".join(m["content"] for m in self._messages if isinstance(m.get("content"), str)))
                result = self.llm.chat_stream(
                    self._messages, tools=self._all_tools(), tool_choice="auto",
                    on_delta=self.on_delta,
                    stop=lambda: self._stop.is_set())
                self._accum_usage(result["usage"])

                calls = result["tool_calls"]
                if not calls:
                    self._messages.append({"role": "assistant",
                                           "content": result["text"] or "(完成)"})
                    if self.on_status:
                        self.on_status("完成")
                    return

                # 组装 assistant 消息（含 tool_calls）
                self._messages.append({
                    "role": "assistant",
                    "content": result["text"] or None,
                    "tool_calls": calls,
                })
                last_images = []
                for call in calls:
                    if self._stop.is_set():
                        return
                    name = call["function"]["name"]
                    try:
                        args = json.loads(call["function"]["arguments"] or "{}")
                        if not isinstance(args, dict):
                            args = {}
                    except json.JSONDecodeError:
                        args = {}
                    if self.on_status:
                        self.on_status(f"待执行工具: {name}")
                    # 每步确认：用户显式确认（AskBeforeEdit）后放行危险操作；YOLO 下危险命令在 confirm 中拒绝。
                    # ask_user 提问工具本身无需"允许执行"确认（弹窗即用户交互）。
                    approved = True if name == "ask_user" \
                        else (self.confirm(name, args) if self.confirm else True)
                    if not approved:
                        text = "[用户拒绝执行此操作]"
                        imgs = []
                    else:
                        if self.on_status:
                            self.on_status(f"正在执行: {name}")
                        res = self._execute(name, args, allow_dangerous=approved)
                        text, imgs = res["text"], res["images"]
                        if self.on_result:
                            self.on_result(name, text)
                        # 操作类工具无截图时自动截屏验证（截图验证闭环）
                        if not imgs and name in _SCREEN_CHANGING:
                            try:
                                imgs = [capture_screen_data_url()]
                            except Exception:
                                imgs = []
                    self._messages.append({
                        "role": "tool", "tool_call_id": call["id"],
                        "content": text,   # 纯字符串更兼容（部分 API 拒绝数组 content）
                    })
                    if imgs:
                        last_images = [imgs[-1]]
                if last_images:
                    self._messages.append({
                        "role": "user",
                        "content": agent_llm.build_content("请观察最新屏幕截图，验证上一步操作结果并继续。",
                                                           last_images),
                    })
            if self.on_status:
                self.on_status("已达到最大工具轮数，自动结束")
        except agent_llm.AgentLLMError as e:
            if self.on_status:
                self.on_status(f"错误: {e}")
        except Exception as e:
            if self.on_status:
                self.on_status(f"错误: {e}")

    def _accum_usage(self, usage):
        if not usage:
            return
        self.tokens["prompt"] += int(usage.get("prompt_tokens", 0))
        self.tokens["completion"] += int(usage.get("completion_tokens", 0))
