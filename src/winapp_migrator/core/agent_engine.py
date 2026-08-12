"""Agent 引擎：循环"截屏分析 → 调用工具 → 截图验证"

- 流式输出：LLM 逐 token 回调（UI 实时显示）
- 工具调用：内置工具 + MCP 工具；每个工具执行前回调 confirm（UI 弹窗每步确认）
- 截图验证闭环：工具执行后自动截屏并作为下一轮视觉输入
- 沙盒：危险工具即使批准也由 agent_tools 硬拒绝
- tokens：发送前预计算（estimate），响应后累计实际 usage
"""

import json
import threading
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import QImage

from winapp_migrator.core import agent_llm, agent_tools, agent_skills
from winapp_migrator.core.agent_screen import capture_screen_data_url, virtual_desktop

# 会改变屏幕、需要执行后自动截图验证的工具
_SCREEN_CHANGING = {"click", "click_text", "drag", "scroll", "press_key", "type_text",
                    "move_mouse", "run_command", "virtual_desktop"}

# 对话上下文持久化路径
CONTEXT_FILE = agent_skills.CONFIG_DIR / "context.json"


def _looks_failed(text: str) -> bool:
    """工具返回文本是否含失败/异常特征（用于触发纠错提示）"""
    return bool(text and any(k in text for k in
                             ("失败", "错误", "未找到", "拒绝", "超时", "[工具", "[沙盒", "[MCP")))


def _compress_data_url(data_url: str, max_width: int = 320, quality: int = 80) -> str:
    """把图片 data URL 压缩为小尺寸 JPEG（保存上下文时防止文件过大）"""
    import base64
    try:
        if not isinstance(data_url, str) or not data_url.startswith("data:image"):
            return data_url
        _, _, b64 = data_url.partition(",")
        img = QImage.fromData(base64.b64decode(b64))
        if img.isNull():
            return data_url
        if img.width() > max_width:
            img = img.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "JPEG", quality)
        return "data:image/jpeg;base64," + base64.b64encode(bytes(ba)).decode()
    except Exception:
        return data_url


def _call_with_stop(fn, stop_event, timeout: float = 30.0):
    """在独立 daemon 线程中执行 fn；超时或 stop 触发时放弃（线程后台自动回收）。

    解决 MCP 等无超时阻塞调用导致引擎线程无法中断、AI 无法停止的问题。
    """
    box = {}

    def run():
        try:
            box["v"] = fn()
        except Exception as e:
            box["e"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not t.is_alive():
            break
        if stop_event.is_set():
            break
        time.sleep(0.1)
    if t.is_alive():
        if stop_event.is_set():
            return None   # 用户停止：放弃等待（线程后台自动回收）
        raise TimeoutError("工具执行超时")
    if "e" in box:
        raise box["e"]
    return box.get("v")


class AgentEngine:
    def __init__(self, llm: agent_llm.LLMClient,
                 mcp_manager=None,
                 on_delta=None, on_status=None, on_result=None, confirm=None,
                 ask_user=None, on_reasoning=None, auto_vd: bool = False):
        """
        on_delta: Callable[[str], None]      流式文本增量
        on_status: Callable[[str], None]     步骤状态（如"正在思考/执行工具 click"）
        on_result: Callable[[str, str], None] 工具执行结果（工具名, 输出文本）
        confirm: Callable[[str, dict], bool] 工具执行前确认；None 表示自动放行（测试用）
        ask_user: Callable[[dict], str]      ask_user 提问回调（阻塞式，返回用户回答）
        on_reasoning: Callable[[str], None]  流式思考过程增量
        auto_vd: bool 任务自动在独立虚拟桌面执行（开始新建并切入，结束自动返回主桌面），
                 实现"完全静默无感"：AI 操作不打扰用户主桌面
        """
        self.llm = llm
        self.mcp = mcp_manager
        self.on_delta = on_delta
        self.on_status = on_status
        self.on_result = on_result
        self.confirm = confirm
        self.ask_user = ask_user
        self.on_reasoning = on_reasoning
        self.auto_vd = auto_vd
        self._messages: list = []
        self.tokens = {"prompt": 0, "completion": 0}
        self.last_estimate = 0       # 最近一次请求前的预计算（输入 tokens）
        self.end_state = ""          # 本轮结束状态: done|stopped|error|max_rounds
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

    # ---------- 上下文持久化（重启保留对话） ----------
    def save_context(self, path=CONTEXT_FILE) -> bool:
        """把对话上下文（不含 system）保存到磁盘；图片压缩后存储"""
        path = Path(path)
        msgs = []
        for m in self._messages:
            if not isinstance(m, dict) or m.get("role") == "system":
                continue
            c = m.get("content")
            if isinstance(c, list):
                out = []
                for x in c:
                    if isinstance(x, dict) and x.get("type") == "image_url":
                        url = (x.get("image_url") or {}).get("url", "")
                        out.append({"type": "image_url",
                                    "image_url": {"url": _compress_data_url(url)}})
                    else:
                        out.append(x)
                m = dict(m)
                m["content"] = out
            msgs.append(m)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(msgs, f, ensure_ascii=False)
            return True
        except Exception:
            return False

    def load_context(self, path=CONTEXT_FILE) -> int:
        """从磁盘恢复上下文，返回恢复的消息条数（0 表示无历史）"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                msgs = json.load(f)
            if isinstance(msgs, list):
                self._messages = [m for m in msgs
                                  if isinstance(m, dict) and m.get("role") != "system"]
            return len(self._messages)
        except Exception:
            return 0

    def clear_context(self, path=CONTEXT_FILE):
        """删除持久化上下文文件（配合 /clear 使用）"""
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            pass

    def compress_history(self, keep_recent: int = 2) -> int:
        """启发式压缩上下文：保留最近 keep_recent 条消息完整，更早的文本合并为一条摘要。

        摘要保留最初的任务目标 + 旧消息尾部细节，长任务压缩后不遗忘开头目标。
        返回被合并的消息条数（0 表示无需压缩）。
        """
        if len(self._messages) <= keep_recent + 1:
            return 0
        head = self._messages[0]                       # system 提示
        recent = self._messages[-keep_recent:]
        old = self._messages[1:-keep_recent]
        parts, first_goal = [], ""
        for m in old:
            c = m.get("content")
            texts = []
            if isinstance(c, str) and c:
                texts.append(c)
            elif isinstance(c, list):
                for x in c:
                    if isinstance(x, dict) and x.get("type") == "text" and x.get("text"):
                        texts.append(x["text"])
            joined = "\n".join(texts)
            if joined:
                if not first_goal and m.get("role") == "user":
                    first_goal = joined[:500]
                parts.append(joined)
        summary_parts = []
        if first_goal:
            summary_parts.append(f"任务目标：{first_goal}")
        tail = "\n".join(parts)
        if tail:
            summary_parts.append(tail[-1500:])
        summary = ("（上下文已压缩，以下是此前对话的关键信息）\n"
                   + "\n".join(summary_parts)) if summary_parts else ""
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

    def start(self, user_input: str, agent_name: str = "", images: list = None):
        """后台线程执行一轮任务；images: 用户拖入的图片 data URL 列表"""
        self._stop.clear()
        self._thread = threading.Thread(target=self.run,
                                        args=(user_input, agent_name, images),
                                        daemon=True)
        self._thread.start()

    def join(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)

    # ---------- 工具 ----------
    def _all_tools(self) -> list:
        tools = list(agent_tools.tool_schemas())
        if self.auto_vd:
            # 自动虚拟桌面接管时，不再暴露 virtual_desktop 工具（避免 AI 重复切桌面）
            tools = [t for t in tools if t["function"]["name"] != "virtual_desktop"]
        if self.mcp:
            tools.extend(self.mcp.tool_schemas())
        return tools

    def _execute(self, name: str, args: dict, allow_dangerous: bool = False) -> dict:
        """执行内置或 MCP 工具，返回 {"text", "images"}"""
        if self.auto_vd and name == "virtual_desktop":
            # 自动虚拟桌面接管时，禁止 AI 手动切换桌面（防止重复 new/back 打乱静默流程）
            return {"text": "[自动模式] 系统已在独立虚拟桌面执行本任务，结束后自动返回主桌面，无需手动切换", "images": []}
        if name == "ask_user":
            # 提问工具：不经沙盒/确认，直接向用户提问
            if self.ask_user:
                return {"text": self.ask_user(args), "images": []}
            return {"text": "[ask_user] 未接入提问面板", "images": []}
        if name in self._builtin_names:
            # 内置工具（run_command 等）同样可能长时间阻塞 → 用带超时/可中断封装
            try:
                res = _call_with_stop(
                    lambda: agent_tools.execute_tool(name, args, allow_dangerous=allow_dangerous),
                    self._stop, timeout=40.0)
                if res is None:   # stop 触发已放弃等待（工具仍在后台线程执行）
                    return {"text": "[已停止等待] 工具仍在后台执行，本轮已跳过", "images": []}
                return res
            except TimeoutError:
                return {"text": f"[工具超时] {name} 无响应，已放弃（40 秒）", "images": []}
            except Exception as e:
                return {"text": f"[工具错误] {name}: {e}", "images": []}
        if self.mcp:
            # MCP 调用无超时可能卡死 → 用带超时/可中断封装
            try:
                text = _call_with_stop(lambda: self.mcp.call_tool(name, args),
                                       self._stop, timeout=30.0)
                return {"text": text, "images": []}
            except TimeoutError:
                return {"text": f"[MCP 超时] 工具 {name} 无响应，已放弃（30 秒）", "images": []}
            except Exception as e:
                return {"text": f"[MCP 错误] {e}", "images": []}
        return {"text": f"[未知工具] {name}", "images": []}

    # ---------- 主循环 ----------
    def run(self, user_input: str, agent_name: str = "", images: list = None):
        self.end_state = ""
        system = agent_skills.build_system_prompt(agent_name)
        if not self._messages or self._messages[0].get("role") != "system":
            self._messages.insert(0, {"role": "system", "content": system})
        else:
            self._messages[0]["content"] = system  # 切换 Agent 时更新系统提示
        self._messages.append({"role": "user",
                               "content": agent_llm.build_content(user_input, images)})
        # 静默虚拟桌面：任务开始切到独立桌面，结束自动返回主桌面（finally 兜底所有结束路径）
        switched = False
        if self.auto_vd:
            try:
                virtual_desktop("new")
                switched = True
                if self.on_status:
                    self.on_status("已在独立虚拟桌面开始工作")
            except Exception:
                switched = False
        try:
            for _ in range(50):  # 最多 50 轮工具循环（配合自动压缩支持长任务），防死循环
                if self._stop.is_set():
                    self.end_state = "stopped"
                    if self.on_status:
                        self.on_status("已停止")
                    return
                if self.on_status:
                    self.on_status("正在思考…")
                self._prune_images(6)  # 历史截图保留最近 6 张，避免过度压缩模型视觉输入
                # 自动压缩：上下文过长时合并旧消息（保留任务目标），防止长任务中 AI 遗忘开头
                if len(self._messages) > 45:
                    n = self.compress_history(keep_recent=8)
                    if n and self.on_status:
                        self.on_status(f"上下文较长，已自动压缩 {n} 条旧消息")
                # tokens 预计算
                self.last_estimate = agent_llm.estimate_tokens(
                    "".join(m["content"] for m in self._messages if isinstance(m.get("content"), str)))
                result = self.llm.chat_stream(
                    self._messages, tools=self._all_tools(), tool_choice="auto",
                    on_delta=self.on_delta,
                    on_reasoning=self.on_reasoning,
                    stop=lambda: self._stop.is_set())
                self._accum_usage(result["usage"])

                calls = result["tool_calls"]
                if not calls:
                    self.end_state = "done"
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
                last_failed = False
                for call in calls:
                    if self._stop.is_set():
                        self.end_state = "stopped"
                        return
                    name = call["function"]["name"]
                    try:
                        args = json.loads(call["function"]["arguments"] or "{}")
                        if not isinstance(args, dict):
                            args = {}
                    except json.JSONDecodeError:
                        # 工具参数非法 JSON：不静默执行，返回提示让模型重新生成合法参数，
                        # 避免以空参误调用或直接向上游抛 400
                        text = ("[工具参数错误] tool_calls.arguments 不是合法 JSON，"
                                "请检查参数格式（字符串需正确转义引号）并重新发起该工具调用。")
                        self._messages.append({"role": "tool", "tool_call_id": call["id"],
                                               "content": text})
                        if self.on_result:
                            self.on_result(name, text, [])
                        last_failed = True
                        continue
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
                        # 操作类工具（点击/输入等）无截图时自动截屏验证（点击完成后必须截图验证闭环）
                        if not imgs and name in _SCREEN_CHANGING:
                            try:
                                imgs = [capture_screen_data_url()]
                            except Exception:
                                imgs = []
                        if self.on_result:
                            # 压缩缩略图副本给 UI 展示（原图仍喂给模型视觉验证）
                            self.on_result(name, text,
                                           [_compress_data_url(u, 480) for u in imgs])
                    if _looks_failed(text):
                        last_failed = True
                    self._messages.append({
                        "role": "tool", "tool_call_id": call["id"],
                        "content": text,   # 纯字符串更兼容（部分 API 拒绝数组 content）
                    })
                    if imgs:
                        last_images = imgs   # 本轮全部截图喂给下一轮视觉验证，不做裁剪
                if last_images:
                    prompt = ("请观察最新屏幕截图，验证上一步操作结果并继续。"
                              if not last_failed else
                              "上一步工具调用失败，请结合截图分析原因（目标不在屏幕/坐标偏移/"
                              "弹窗未展开/参数错误），换方案重试（最多 2 次），仍失败则 ask_user 求助。")
                    self._messages.append({
                        "role": "user",
                        "content": agent_llm.build_content(prompt, last_images),
                    })
            if self.on_status:
                self.on_status("已达到最大工具轮数，自动结束")
            self.end_state = "max_rounds"
        except agent_llm.AgentLLMError as e:
            # 用户主动停止（含 LLM 层"已停止"）优先识别为 stopped，而不是 error
            stopped = self._stop.is_set()
            self.end_state = "stopped" if stopped else "error"
            if self.on_status:
                self.on_status("已停止" if stopped else f"错误: {e}")
        except Exception as e:
            stopped = self._stop.is_set()
            self.end_state = "stopped" if stopped else "error"
            if self.on_status:
                self.on_status("已停止" if stopped else f"错误: {e}")
        finally:
            # 任何结束路径（完成/停止/错误/超轮数）都返回用户桌面，AI 操作完全无感
            if switched:
                try:
                    virtual_desktop("back")
                except Exception:
                    pass

    def _accum_usage(self, usage):
        if not usage:
            return
        self.tokens["prompt"] += int(usage.get("prompt_tokens", 0))
        self.tokens["completion"] += int(usage.get("completion_tokens", 0))
