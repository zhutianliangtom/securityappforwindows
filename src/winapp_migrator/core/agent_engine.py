"""Agent 引擎：循环"浏览器观察 → 调用工具 → 验证结果"

- 流式输出：LLM 逐 token 回调（UI 实时显示）
- 工具调用：内置工具 + MCP 工具；每个工具执行前回调 confirm（UI 弹窗每步确认）
- 浏览器：AI 用 browser_open/navigate/snapshot/click 等独立浏览器工具操控网页，
  browser_snapshot 返回的页面截图作为视觉输入
- 沙盒：危险工具即使批准也由 agent_tools 硬拒绝
- tokens：发送前预计算（estimate），响应后累计实际 usage
"""

import json
import os
import queue
import re
import threading
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import QImage

from winapp_migrator.core import agent_llm, agent_tools, agent_skills, agent_subagent, agent_tts
from winapp_migrator.core.agent_screen import virtual_desktop

# 开发类工具：动手开发/修改代码前必须先确认用户开发规则（首次调用被拦截，规则确认后下一轮放行）
_DEV_TOOLS = frozenset({"write_file", "edit_file", "delete_file",
                        "run_command", "create_skill", "dispatch_sub_agents"})

# 朗读分段：只在句末标点处切句（逗号/换行不切，避免零散 API 调用造成卡顿）
_TTS_SENT_END = ("。", "！", "？", "！？", "……", "…", "！", "?", "…")
# 累积到该长度才触发一次合成（过短句子合并，减少 API 往返）
_TTS_MIN_SEG = 18
# 无句末标点时达到该长度强制切分（保证长句也能边输出边朗读）
_TTS_MAX_SEG = 60

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
    timeout=None 表示不做时间上限：只有 stop 可中断，长任务持续到完成（如子 Agent）。
    """
    box = {}

    def run():
        try:
            box["v"] = fn()
        except Exception as e:
            box["e"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    deadline = None if timeout is None else time.time() + timeout
    while True:
        if not t.is_alive():
            break
        if stop_event.is_set():
            break
        if deadline is not None and time.time() >= deadline:
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
                 ask_user=None, on_reasoning=None, auto_vd: bool = False,
                 text_only: bool = False, memory_enabled: bool = True,
                 direct: bool = False):
        """
        on_delta: Callable[[str], None]      流式文本增量
        on_status: Callable[[str], None]     步骤状态（如"正在思考/执行工具 click"）
        on_result: Callable[[str, str], None] 工具执行结果（工具名, 输出文本）
        confirm: Callable[[str, dict], bool] 工具执行前确认；None 表示自动放行（测试用）
        ask_user: Callable[[dict], str]      ask_user 提问回调（阻塞式，返回用户回答）
        on_reasoning: Callable[[str], None]  流式思考过程增量
        auto_vd: bool 任务自动在独立虚拟桌面执行（开始新建并切入，结束自动返回主桌面），
                 实现"完全静默无感"：AI 操作不打扰用户主桌面
        text_only: bool 纯文本模型（无图像输入），过滤截图/视觉工具
        memory_enabled: bool 记忆开关，关闭时过滤 save_memory/load_memory 工具
        direct: bool 直接工作模式（无确认直行）：跳过开发规则确认与技能路由硬拦截，
                减少询问/约束，直接调用必要技能与命令完成任务
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
        self.text_only = text_only
        self.memory_enabled = memory_enabled
        self.direct = direct
        self._messages: list = []
        self.tokens = {"prompt": 0, "completion": 0}
        self.last_estimate = 0       # 最近一次请求前的预计算（输入 tokens）
        self.end_state = ""          # 本轮结束状态: done|stopped|error
        self._stop = threading.Event()
        self._thread: threading.Thread = None
        self._builtin_names = {t["function"]["name"] for t in agent_tools.TOOLS}
        self._rules_confirmed = False   # 当前任务是否已确认开发规则
        self._skills_read = set()       # 已注入/已读取规范流程的技能名
        self._skill_consulted = set()   # 已做技能规范化拦截的工具名（每工具最多注入一次）
        self._auto_skills = []          # 按用户提示词自动匹配并注入的技能名
        # 自动朗读（用户要求"朗读/语音回复"时，AI 流式输出边生成边合成播放）
        self._tts_auto = False          # 本任务是否需要自动朗读
        self._tts_buf = ""              # 流式文本累积游标（未切分部分）
        self._tts_queue = queue.Queue()  # 待朗读句子队列（朗读线程消费）
        self._tts_finish = False        # 是否已停止接收新句子（完成后让队列读完）
        self._tts_stop = threading.Event()  # 立即停止朗读（用户手动停止时置位）
        self._tts_thread = None         # 朗读工作线程

    # ---------- 控制 ----------
    def stop(self):
        self._stop.set()
        self._tts_stop_read()   # 用户停止：立即停掉正在播放/合成的语音

    def reset_tokens(self):
        self.tokens = {"prompt": 0, "completion": 0, "cache_hit": 0, "cache_miss": 0}
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
        # 压缩边界不切断 assistant(tool_calls)/tool 回复配对：
        # 尾部起点若落在 tool 回复上，向前回退包含其 assistant，防止上游 400
        start = max(len(self._messages) - keep_recent, 1)
        while start > 1 and self._messages[start].get("role") == "tool":
            start -= 1
        head = self._messages[0]                       # system 提示
        recent = self._messages[start:]
        old = self._messages[1:start]
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

    def _auto_compress(self, keep_recent: int = 60) -> int:
        """上下文压缩：优先让当前模型自主生成摘要（保留关键信息），失败回退启发式合并。
        返回被合并的消息条数（0 表示无需压缩）。"""
        if len(self._messages) <= keep_recent + 1:
            return 0
        # 压缩边界不切断 assistant(tool_calls)/tool 回复配对
        start = max(len(self._messages) - keep_recent, 1)
        while start > 1 and self._messages[start].get("role") == "tool":
            start -= 1
        head = self._messages[0]
        recent = self._messages[start:]
        old = self._messages[1:start]
        summary = self._llm_summarize(old)   # 当前模型自主摘要（失败返回空串）
        if not summary:
            summary = self._heuristic_summary(old)
        self._messages = [head]
        if summary:
            self._messages.append({"role": "user",
                                   "content": agent_llm.build_content(summary)})
        self._messages.extend(recent)
        return len(old)

    def _llm_summarize(self, old: list) -> str:
        """调用当前模型对旧消息生成摘要（失败/超时返回空串，由调用方回退启发式）"""
        try:
            texts = []
            for m in old:
                c = m.get("content")
                if isinstance(c, str) and c:
                    texts.append(f"[{m.get('role')}] {c}")
                elif isinstance(c, list):
                    parts = [x.get("text") for x in c
                             if isinstance(x, dict) and x.get("type") == "text" and x.get("text")]
                    if parts:
                        texts.append(f"[{m.get('role')}] {' '.join(parts)}")
            joined = "\n".join(texts).strip()
            if not joined:
                return ""
            if len(joined) > 40000:   # 摘要输入截断保护：只保留更近的部分
                joined = joined[-40000:]
            sys_p = ("你是对话上下文压缩助手。把以下历史对话压缩为简洁摘要，保留："
                     "任务目标、已完成的关键步骤与结论、用户的偏好与约束、未解决的问题。"
                     "只输出摘要正文，不要任何前缀或解释。")
            res = self.llm.chat(
                [{"role": "system", "content": sys_p},
                 {"role": "user", "content": f"历史对话：\n{joined}"}],
                max_tokens=1024, stop=lambda: self._stop.is_set())
            return str(res.get("text") or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _heuristic_summary(old: list) -> str:
        """启发式摘要兜底：任务目标 + 旧消息尾部细节（与 compress_history 一致）"""
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
        return ("（上下文已压缩，以下是此前对话的关键信息）\n"
                + "\n".join(summary_parts)) if summary_parts else ""

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
                # 纯图片消息被全部剥离后会成为空数组，补占位文本防上游拒绝
                m["content"] = keep if keep else \
                    [{"type": "text", "text": "（截图已忽略）"}]

    @staticmethod
    def _strip_images(messages: list):
        """纯文本模型：移除全部 image_url 内容项（历史残留/自动截图均清理）。
        消息若因此只剩图，补占位文本，避免发送空 content 被上游拒绝"""
        for m in messages:
            c = m.get("content")
            if not isinstance(c, list):
                continue
            kept = [x for x in c
                    if not (isinstance(x, dict) and x.get("type") == "image_url")]
            if not kept:
                kept = [{"type": "text", "text": "（截图已忽略）"}]
            m["content"] = kept

    def start(self, user_input: str, agent_name: str = "", images: list = None,
              skills: list = None, direct: bool = None):
        """后台线程执行一轮任务；images: 用户拖入的图片 data URL 列表；
        skills: 手动调用的技能名列表（/技能名 提示），其 instruction 注入系统提示词；
        direct: 覆盖直接工作模式（None=沿用构造时设置）"""
        if direct is not None:
            self.direct = direct
        self._stop.clear()
        self._skills_read.clear()      # 每轮任务重置技能读取/注入状态
        self._skill_consulted.clear()
        self._thread = threading.Thread(target=self.run,
                                        args=(user_input, agent_name, images, skills),
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
        if not self.memory_enabled:
            # 记忆关闭：不暴露 save_memory/load_memory
            tools = [t for t in tools
                     if t["function"]["name"] not in ("save_memory", "load_memory")]
        if self.direct:
            # 直接工作模式：不暴露提问工具，AI 完全自主执行（即使调用也被 _execute 拦截）
            tools = [t for t in tools if t["function"]["name"] != "ask_user"]
        if self.mcp:
            # MCP 工具并入：与内置工具/其他服务器同名时跳过（内置优先），
            # 否则同名工具会让上游报 "Tool names must be unique"
            seen = {t["function"]["name"] for t in tools}
            for t in self.mcp.tool_schemas():
                name = t["function"]["name"]
                if name and name not in seen:
                    tools.append(t)
                    seen.add(name)
        return tools

    def _execute(self, name: str, args: dict, allow_dangerous: bool = False) -> dict:
        """执行内置或 MCP 工具，返回 {"text", "images"}"""
        if name == "tts_speak":
            # AI 主动调用朗读工具：停掉引擎的自动分段朗读，避免与 tts_speak 双重播放
            self._tts_stop_read()
        if self.auto_vd and name == "virtual_desktop":
            # 自动虚拟桌面接管时，禁止 AI 手动切换桌面（防止重复 new/back 打乱静默流程）
            return {"text": "[自动模式] 系统已在独立虚拟桌面执行本任务，结束后自动返回主桌面，无需手动切换", "images": []}
        if name == "ask_user":
            # 提问工具：不经沙盒/确认，直接向用户提问
            if self.direct:
                # 直接工作模式禁止提问：返回引导，让 AI 基于现有信息自主决策并继续
                return {"text": "[直接工作模式] 已禁止向用户提问，"
                                "请基于现有上下文自主判断并直接执行下一步。", "images": []}
            if self.ask_user:
                return {"text": self.ask_user(args), "images": []}
            return {"text": "[ask_user] 未接入提问面板", "images": []}
        if name == "read_file":
            # 命中技能 SKILL.md 即视为已读取该技能规范流程，放行其覆盖的工具
            mp = re.search(r"skills[\\/]([^\\/]+?)[\\/]SKILL\.md$",
                           str(args.get("path") or args.get("file") or ""))
            if mp:
                self._skills_read.add(mp.group(1))
        if name in agent_tools.SUB_AGENT_TOOLS:
            # 子 Agent 工具：并发派发子任务（可读写项目文件）；不做轮数与时间上限，
            # 长任务持续到完成或被用户停止（stop），与主 Agent 无轮数上限一致
            try:
                res = _call_with_stop(lambda: self._run_subagent_tool(name, args),
                                      self._stop, timeout=None)
                if res is None:   # stop 触发已放弃等待（子 Agent 仍在后台执行）
                    return {"text": "[已停止等待] 子 Agent 仍在后台执行，本轮已跳过", "images": []}
                return res
            except Exception as e:
                return {"text": f"[子Agent错误] {name}: {e}", "images": []}
        if name in self._builtin_names:
            # 内置工具（run_command 等）同样可能长时间阻塞 → 用带超时/可中断封装
            try:
                # run_command 不设时间上限：长命令持续到完成或用户停止；
                # 下载不设 40s 放弃：长任务由 UI 轮询快照渲染进度条，停止按钮可取消
                timeout = None if name == "run_command" else \
                    (3600.0 if name == "fast_download" else 40.0)
                res = _call_with_stop(
                    lambda: agent_tools.execute_tool(name, args, allow_dangerous=allow_dangerous),
                    self._stop, timeout=timeout)
                if res is None:   # stop 触发已放弃等待（工具仍在后台线程执行）
                    if name == "fast_download":
                        agent_tools.cancel_active_download()   # 停止即取消后台下载
                    return {"text": "[已停止等待] 工具仍在后台执行，本轮已跳过", "images": []}
                return res
            except TimeoutError:
                return {"text": f"[工具超时] {name} 无响应，已放弃（{timeout:.0f} 秒）", "images": []}
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

    # ---------- 子 Agent 工具（explorer / 搜索 / 通用并发分发） ----------
    def _run_subagent_tool(self, name: str, args: dict) -> dict:
        """子 Agent 工具执行：复用同一 LLM 客户端，派发子任务（可读写项目文件）并汇总结果"""
        args = args or {}
        tasks = []
        if name == "explore_project":
            tasks = [{"title": "探索项目",
                      "goal": agent_subagent.explore_goal(str(args.get("directory", ""))),
                      "allowed": ("list_directory", "read_file", "search_files")}]
        elif name == "search_large":
            dirs = [str(d) for d in (args.get("directories") or []) if str(d).strip()]
            tasks = [{"title": f"搜索「{args.get('query', '')}」",
                      "goal": agent_subagent.search_goal(
                          str(args.get("query", "")), dirs,
                          self._to_int(args.get("max_results"), 20)),
                      "allowed": ("search_files", "read_file", "list_directory")}]
        else:   # dispatch_sub_agents
            for i, t in enumerate((args.get("tasks") or []), 1):
                if isinstance(t, dict) and str(t.get("goal") or "").strip():
                    tasks.append({
                        "title": str(t.get("title") or f"子任务 {i}"),
                        "goal": str(t["goal"]),
                        "allowed": self._sub_allowed(str(t.get("tools") or "")),
                    })
        if not tasks:
            return {"text": f"[{name}] 缺少任务参数，无法派发子 Agent", "images": []}
        if self.on_status:
            self.on_status(f"正在派发 {len(tasks)} 个子 Agent 并发执行…")
        text = agent_subagent.dispatch_sub_agents(
            self.llm, tasks, stop=lambda: self._stop.is_set(),
            on_status=self.on_status)
        return {"text": text, "images": []}

    @staticmethod
    def _to_int(v, default: int) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _sub_allowed(tools_str: str):
        """子任务可用工具：与子 Agent 白名单取交集；空则用全部白名单工具"""
        if not tools_str:
            return None
        names = {x.strip() for x in str(tools_str).replace("，", ",").split(",") if x.strip()}
        inter = tuple(n for n in names if n in agent_subagent.SUB_AGENT_WHITELIST)
        return inter or None

    # ---------- 自动朗读（边输出边朗读 / 回复自动朗读） ----------
    def _on_stream_delta(self, s: str):
        """LLM 流式文本增量：转发面板显示，同时把完整句子切出投递给朗读线程"""
        if self.on_delta:
            self.on_delta(s)
        if self._tts_auto and s and not self._tts_finish:
            self._tts_buf += s
            self._tts_flush_sentences()

    def _tts_flush_sentences(self):
        """把累积文本按句末标点切成短句入队（未完成部分留在缓冲继续累积）。
        短句（长度 < _TTS_MIN_SEG）不立即切出，与后续文本合并成一句再合成，
        减少零散 API 调用导致的卡顿；无标点的长文本到 _TTS_MAX_SEG 强制切分，
        保证长句也能边输出边朗读。"""
        buf = self._tts_buf
        if not buf:
            return
        n = len(buf)
        # 找到最后一个句末标点位置
        cut = -1
        for i, ch in enumerate(buf):
            if ch in _TTS_SENT_END:
                cut = i + 1
        if cut > 0 and cut >= _TTS_MIN_SEG:
            # 有句末标点且长度足够 → 切出（含标点），剩余留缓冲
            seg, self._tts_buf = buf[:cut], buf[cut:]
        elif n >= _TTS_MAX_SEG:
            # 无足够标点但文本已超长 → 整体强制切出，保证长文持续朗读
            seg, self._tts_buf = buf, ""
        else:
            # 文本太短或只有半句：等待更多内容（finish 时统一入队）
            return
        seg = seg.strip()
        if seg:
            self._tts_queue.put(seg)

    def _tts_start_worker(self):
        """启动朗读线程：若上一轮线程仍在收尾（队列未读完）先等其退出，避免双播放源"""
        if self._tts_thread and self._tts_thread.is_alive():
            self._tts_thread.join(timeout=10)
        self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self._tts_thread.start()

    def _tts_worker(self):
        """朗读线程：逐句调 DashScope 流式合成，边合成边 pygame 播放（串行队列）"""
        if not agent_tools._tts_play_start():
            if self.on_status:
                self.on_status("自动朗读不可用：pygame 未安装或音频初始化失败，已跳过语音播放")
            return   # 播放器不可用：不合成（避免白耗 API）
        err_shown = False   # 只上报首次合成失败，避免刷屏
        while True:
            if self._tts_stop.is_set():
                break
            try:
                seg = self._tts_queue.get(timeout=0.5)
            except queue.Empty:
                if self._tts_finish:
                    break
                continue
            if self._tts_stop.is_set():
                break
            try:
                agent_tts.synthesize_stream(
                    seg, voice_id="", on_chunk=agent_tools._tts_play_chunk)
            except Exception as e:
                if not err_shown:
                    err_shown = True
                    if self.on_status:
                        self.on_status(f"自动朗读合成失败（已跳过本句）：{e}")
        agent_tools._tts_play_stop()

    def _tts_finish_read(self):
        """任务正常完成：停止接收新句子，残余文本入队，让朗读线程读完队列后自行退出"""
        if not self._tts_auto:
            return
        self._tts_finish = True
        if self._tts_buf.strip():
            self._tts_queue.put(self._tts_buf.strip())
            self._tts_buf = ""

    def _tts_stop_read(self):
        """立即停止朗读：清空队列并通知朗读线程退出（用户停止 / AI 主动 tts_speak 时）"""
        self._tts_stop.set()
        self._tts_finish = True
        self._tts_buf = ""
        while not self._tts_queue.empty():
            try:
                self._tts_queue.get_nowait()
            except queue.Empty:
                break

    # ---------- 主循环 ----------
    def _system_prompt(self, agent_name: str = "", skills: list = None) -> str:
        """构建系统提示词：每次都重新读取 settings.json，
        用户中途新增/修改的自定义规则在下一轮立即生效。
        自动匹配到的技能（_auto_skills）与手动指定技能合并注入，让 AI 先按技能流程执行。"""
        merged = list(skills or [])
        for s in (self._auto_skills or []):
            if s not in merged:
                merged.append(s)
        return agent_skills.build_system_prompt(agent_name, extra_skills=merged,
                                                text_only=self.text_only,
                                                memory_enabled=self.memory_enabled,
                                                direct=self.direct)

    @staticmethod
    def _rules_text() -> str:
        """真实读取用户自定义开发规则文本（settings.json 的 custom_rules）"""
        rules = [str(r).strip()
                 for r in (agent_skills.load_settings().get("custom_rules") or [])
                 if str(r).strip()]
        if not rules:
            return "（当前未设置自定义开发规则）"
        return "\n".join(f"- {r}" for r in rules)

    def run(self, user_input: str, agent_name: str = "", images: list = None,
            skills: list = None):
        self.end_state = ""
        self._rules_confirmed = False   # 每个新任务重新强制规则确认
        # 按用户提示词自动匹配技能并注入：简单提示词（如"生成一个毕业感言PPT"）也先走 skill 流程
        self._auto_skills = agent_skills.auto_skill_names(user_input)
        if self._auto_skills and self.on_status:
            self.on_status(f"正在调用技能: {', '.join(self._auto_skills)}")
            self.on_status(f"技能已调用: {', '.join(self._auto_skills)}")
        # 自动朗读：设置中「自动朗读」开关默认开启，或用户明确要求"朗读/语音回复"时开启。
        # AI 流式输出边生成边合成播放；未配置音色或 API Key 时给出提示并自动关闭（避免无声假象）。
        self._tts_finish = False
        self._tts_stop.clear()
        tts_cfg = agent_tts.load_config()
        self._tts_auto = bool(tts_cfg.get("auto_read", True)) or \
            agent_tts.has_read_intent(user_input)
        if self._tts_auto:
            if not tts_cfg.get("voice_id") or not agent_tts.load_api_key():
                self._tts_auto = False
                if self.on_status:
                    self.on_status("检测到朗读请求，但未配置音色或 DashScope API Key，"
                                   "已跳过自动朗读（可在设置-语音合成中配置）")
            else:
                self._tts_start_worker()
                if self.on_status:
                    self.on_status("已开启自动朗读：AI 输出时将边生成边播放语音")
        if not self._messages or self._messages[0].get("role") != "system":
            self._messages.insert(0, {"role": "system",
                                      "content": self._system_prompt(agent_name, skills)})
        else:
            self._messages[0]["content"] = self._system_prompt(agent_name, skills)
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
            # 工具循环不设轮数上限：用户可随时点击停止，上下文自动压缩防遗忘；
            # 每轮都检查 _stop，长任务可一直执行下去
            while True:
                if self._stop.is_set():
                    self.end_state = "stopped"
                    if self.on_status:
                        self.on_status("已停止")
                    return
                # 每轮重建系统提示词：用户中途新增/修改的规则在下一轮立即生效；
                # 内容未变化时不覆盖，保持发送前缀稳定利于上下文缓存命中
                new_prompt = self._system_prompt(agent_name, skills)
                if self._messages[0].get("content") != new_prompt:
                    self._messages[0]["content"] = new_prompt
                if self.on_status:
                    self.on_status("正在思考…")
                if self.text_only:
                    # 纯文本模型：发送副本剥离图片，不改存储历史 → 前缀稳定利于缓存命中
                    send_msgs = [dict(m) for m in self._messages]
                    self._strip_images(send_msgs)
                else:
                    self._prune_images(2)   # 视觉模型：历史截图只保留最近 2 张，防上下文膨胀
                    send_msgs = self._messages
                # 自动压缩：上下文过长时让当前模型自主摘要压缩（失败回退启发式），
                # 阈值/保留量取较大值：让 AI 记住最近 60 条完整消息，仅真正超长时才压缩
                if len(self._messages) > 200:
                    n = self._auto_compress(keep_recent=60)
                    if n and self.on_status:
                        self.on_status(f"上下文较长，已由模型自动摘要压缩 {n} 条旧消息")
                # tokens 预计算
                self.last_estimate = agent_llm.estimate_tokens(
                    "".join(m["content"] for m in self._messages if isinstance(m.get("content"), str)))
                result = self.llm.chat_stream(
                    send_msgs, tools=self._all_tools(), tool_choice="auto",
                    on_delta=self._on_stream_delta,
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
                answered = set()
                rules_just = False   # 本轮是否触发过开发规则确认（全部拦截后统一置位）
                for call in calls:
                    if self._stop.is_set():
                        # 补齐未执行工具的回复，保持 tool_calls 配对完整，防下一轮发送 400
                        for c in calls:
                            if c.get("id") and c["id"] not in answered:
                                self._messages.append({
                                    "role": "tool", "tool_call_id": c["id"],
                                    "content": "[已停止] 用户已停止任务，该工具未执行"})
                        self.end_state = "stopped"
                        return
                    name = call["function"]["name"]
                    # 技能路由硬拦截：被技能覆盖的工具，首次调用直接把该技能的规范流程
                    # 注入本轮上下文并拦截，强制按技能执行（防 AI 跳过 skill 直接裸调工具）。
                    # 每工具最多注入一次（_skill_consulted 记录）；已注入/已读的技能不再重复注入。
                    if not self.direct and name not in self._skill_consulted:
                        covered = agent_skills.skills_covering_tools([name]).get(name, [])
                        unseen = [s for s in covered if s not in self._skills_read]
                        if unseen:
                            self._skill_consulted.add(name)
                            sname = unseen[0]
                            skill = next((s for s in agent_skills.load_skills()
                                          if s.get("name") == sname), None)
                            body = (skill or {}).get("instruction") or ""
                            text = (f"[技能规范化] 工具「{name}」的操作由技能「{sname}」规范化，"
                                    f"已加载规范流程，请严格按以下流程执行"
                                    f"（含配图角度/位置等质量要求）：\n\n{body}\n\n"
                                    f"按此流程重新发起该工具调用。")
                            self._messages.append({"role": "tool", "tool_call_id": call["id"],
                                                   "content": text})
                            answered.add(call["id"])
                            if self.on_result:
                                self.on_result(name, text, [])
                            continue
                    if name in _DEV_TOOLS and not self._rules_confirmed and not self.direct:
                        # 动手开发前的强制规则读取：首次调用开发类工具不放行，
                        # 真实读取规则文本回给模型确认，下一轮重新发起再正常执行
                        rules_just = True
                        text = ("[开发前规则确认] 动手开发前必须先确认用户开发规则，"
                                "已读取规则文件，请严格遵守：\n" + self._rules_text()
                                + "\n规则已确认。现在重新发起你刚才的开发工具调用。")
                        self._messages.append({"role": "tool", "tool_call_id": call["id"],
                                               "content": text})
                        answered.add(call["id"])
                        if self.on_result:
                            self.on_result(name, text, [])
                        continue
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
                        answered.add(call["id"])
                        if self.on_result:
                            self.on_result(name, text, [])
                        last_failed = True
                        continue
                    # 技能阅读：read_file 命中 skills/<名>/SKILL.md 时，用"正在调用技能"替代"read_file"
                    skill_read = None
                    if name == "read_file":
                        _sm = re.search(r"skills[\\/]([^\\/]+?)[\\/]SKILL\.md$",
                                        str(args.get("path") or args.get("file") or ""))
                        if _sm:
                            skill_read = _sm.group(1)
                    if self.on_status:
                        self.on_status(f"正在调用技能: {skill_read}" if skill_read
                                       else f"待执行工具: {name}")
                    # 每步确认：用户显式确认（AskBeforeEdit）后放行危险操作；YOLO 下危险命令在 confirm 中拒绝。
                    # ask_user 提问工具本身无需"允许执行"确认（弹窗即用户交互）。
                    approved = True if name == "ask_user" \
                        else (self.confirm(name, args) if self.confirm else True)
                    if not approved:
                        text = "[用户拒绝执行此操作]"
                        imgs = []
                    else:
                        if self.on_status:
                            self.on_status(f"技能已调用: {skill_read}" if skill_read
                                           else f"正在执行: {name}")
                        res = self._execute(name, args, allow_dangerous=approved)
                        text, imgs = res["text"], res["images"]
                        if self.on_result:
                            # 压缩缩略图副本给 UI 展示（原图仍喂给模型视觉验证）
                            self.on_result(name, text,
                                           [_compress_data_url(u, 480) for u in imgs])
                    if _looks_failed(text):
                        last_failed = True
                    # 完整工具输出直接进入上下文（用户要求禁止上下文截断限制）
                    self._messages.append({
                        "role": "tool", "tool_call_id": call["id"],
                        "content": text,   # 纯字符串更兼容（部分 API 拒绝数组 content）
                    })
                    answered.add(call["id"])
                    if imgs:
                        last_images = imgs   # 本轮全部截图喂给下一轮视觉验证，不做裁剪
                if rules_just:
                    self._rules_confirmed = True   # 本轮已确认规则，下轮开发工具正常放行
                if last_images:
                    prompt = ("请观察最新屏幕截图，验证上一步操作结果并继续。"
                              if not last_failed else
                              "上一步工具调用失败，请结合截图分析原因（目标不在屏幕/坐标偏移/"
                              "弹窗未展开/参数错误），换方案重试（最多 2 次），仍失败则 ask_user 求助。")
                    self._messages.append({
                        "role": "user",
                        "content": agent_llm.build_content(prompt, last_images),
                    })
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
            # 朗读收尾：正常完成则让朗读线程把剩余文本读完；停止/出错则立即停
            if self.end_state == "done":
                self._tts_finish_read()
            else:
                self._tts_stop_read()
            # 任何结束路径（完成/停止/错误/超轮数）都返回用户桌面，AI 操作完全无感
            if switched:
                try:
                    virtual_desktop("back")
                except Exception:
                    pass

    def _accum_usage(self, usage, cache=None):
        if not usage:
            return
        self.tokens["prompt"] += int(usage.get("prompt_tokens", 0))
        self.tokens["completion"] += int(usage.get("completion_tokens", 0))
        if cache:
            self.tokens["cache_hit"] += int(cache.get("hit", 0))
            self.tokens["cache_miss"] += int(cache.get("miss", 0))
