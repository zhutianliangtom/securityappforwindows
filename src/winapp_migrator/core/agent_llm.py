"""AI Agent 的 LLM 客户端：OpenAI 兼容 /v1/chat/completions，流式（SSE）

- stream: true，逐 token 回调（on_delta）实现主流 Agent 的流式输出
- 工具调用：tools / tool_choice（流式 tool_calls 增量按 index 聚合）
- 图像输入：messages[].content[].image_url（支持 data URL 或 http(s) URL）
- tokens 预计算：发送前启发式估算（中文按字、英文按 4 字符），响应后取实际 usage
"""

import json
import time
import urllib.error
import urllib.request
from typing import Callable, List, Optional

DEFAULT_BASE_URL = "https://api.agnes-ai.cn/v1"
DEFAULT_MODEL = "agnes-2.5-flash"
DEFAULT_API_KEY = "sk-iydeFjzDmQr4Se3N6yxEjRHccWQbhSXLOSp27ZH5qhxathwR"
_UA = "WinAppMigrator/1.0 AgentClient"
_MAX_RETRIES = 3    # 请求失败（429/5xx/网络）自动重试次数
_RETRY_DELAY = 2.0  # 重试基础延迟（秒），指数退避

# 纯文本模型关键字（子串匹配）：命中即视为不支持图像输入，禁用截图/视觉能力。
# 只收录"确定无视觉"的文本模型名/前缀，避免误伤 gpt-4o / qwen-vl / glm-4v / hunyuan-vision 等视觉模型
TEXT_ONLY_KEYS = (
    "deepseek",                # deepseek-chat / deepseek-reasoner / deepseek-v4-* 均无视觉
    "glm-4-flash", "glm-4-air", "glm-4-long",     # 智谱文本（glm-4v 有视觉，不匹配）
    "qwen-turbo", "qwen-plus", "qwen-max", "qwen-long", "qwen-lite",  # 通义文本系列
    "moonshot-v1",             # Kimi 旧版文本模型
    "gpt-3.5",                 # OpenAI 旧文本模型（gpt-4o 含视觉，不匹配）
    "text-davinci", "text-babbage", "text-curie", "text-ada",
    "llama-2", "llama3-8b", "llama3-70b", "llama-3-8b", "llama-3-70b",
    "mistral-7b", "mistral-8x", "mixtral",        # Mistral 文本系列
    "phi-3", "phi-4",                            # 微软 Phi 文本
    "gemma-2",                                   # Google 文本（gemma-3 起含视觉，不收录）
    "chatglm", "yi-34b", "yi-large", "baichuan",  # 开源文本
    "ernie-bot", "minimax", "abab",              # 百度文心 / MiniMax 文本
    "spark-lite", "spark-v3",                    # 讯飞星火文本
    "hunyuan-turbo", "hunyuan-lite",             # 腾讯混元文本（hunyuan-vision 不匹配）
)

# 工作力度档位（从轻到重）：决定"力度→模型"路由与是否加大推理
EFFORTS = ("low", "medium", "high", "max", "ultra")
# 发送给 API 的 reasoning_effort 取值（OpenAI 兼容仅支持 low/medium/high，max/ultra 折算为 high）
_REASONING_EFFORT = {"low": "low", "medium": "medium", "high": "high",
                     "max": "high", "ultra": "high"}


def is_text_only_model(model: str) -> bool:
    """自动识别纯文本模型：模型名含 TEXT_ONLY_KEYS 任一关键字"""
    m = (model or "").lower()
    return any(k in m for k in TEXT_ONLY_KEYS)


def load_model_config() -> dict:
    """从 settings.json 读取模型配置，未配置时返回默认。

    返回完整配置（含同服务商多模型与力度路由）：
    base_url / api_key / model(主模型=首个) / models(全部模型名) /
    effort_models(力度→模型) / effort(当前力度) / auto_effort(自动按难度) /
    send_effort(是否向 API 发送 reasoning_effort)
    """
    try:
        from winapp_migrator.core import agent_skills
        m = agent_skills.load_settings().get("model") or {}
        if not isinstance(m, dict):
            m = {}
        models = [str(x).strip() for x in (m.get("models") or []) if str(x).strip()]
        single = str(m.get("model") or "").strip()
        if single and single not in models:
            models.insert(0, single)
        return {
            "base_url": m.get("base_url") or DEFAULT_BASE_URL,
            "api_key": m.get("api_key") or DEFAULT_API_KEY,
            "model": models[0] if models else DEFAULT_MODEL,
            "models": models or [DEFAULT_MODEL],
            "effort_models": dict(m.get("effort_models") or {}),
            "effort": m.get("effort") if m.get("effort") in EFFORTS else "medium",
            "auto_effort": bool(m.get("auto_effort", True)),
            "send_effort": bool(m.get("send_effort", False)),
            "protocol": m.get("protocol") if m.get("protocol") in ("chat", "responses") else "chat",
        }
    except Exception:
        return {"base_url": DEFAULT_BASE_URL, "api_key": DEFAULT_API_KEY,
                "model": DEFAULT_MODEL, "models": [DEFAULT_MODEL],
                "effort_models": {}, "effort": "medium",
                "auto_effort": True, "send_effort": False, "protocol": "chat"}


def _default_effort_models(models: list) -> dict:
    """力度→模型的默认路由：多模型时首个视为最强（pro）用于 high/max/ultra，
    末个最轻（flash）用于 low/medium；单模型时全部同款"""
    if not models:
        return {}
    if len(models) == 1:
        return {e: models[0] for e in EFFORTS}
    return {"low": models[-1], "medium": models[-1],
            "high": models[0], "max": models[0], "ultra": models[0]}


def resolve_model(cfg: dict, effort: str = "medium") -> str:
    """按工作力度解析应使用的模型名：优先用户配置的 effort_models 映射，
    否则按模型列表默认路由，最后回退主模型/默认模型"""
    m = cfg or {}
    effort = effort if effort in EFFORTS else "medium"
    em = m.get("effort_models") or {}
    name = str(em.get(effort) or "").strip() or str(em.get("medium") or "").strip()
    if name:
        return name
    models = m.get("models") or []
    if models:
        return _default_effort_models(models).get(effort) or models[0]
    return m.get("model") or DEFAULT_MODEL


def estimate_effort(text: str) -> str:
    """按任务难度智能估算工作力度：文本越长、关键操作词越多 → 力度越重"""
    t = (text or "").strip()
    if not t:
        return "medium"
    n = len(t)
    hard = ("分析", "编写", "开发", "调试", "配置", "迁移", "优化", "卸载",
            "安装", "重构", "计划", "步骤", "然后", "并且", "同时", "多个",
            "项目", "代码", "构建", "测试", "部署")
    hits = sum(1 for k in hard if k in t)
    if n >= 300 or (n >= 100 and hits >= 2):
        return "ultra"
    if n >= 100 or (n >= 40 and hits >= 1) or hits >= 3:
        return "max"
    if n >= 60 or (n >= 25 and hits >= 1) or hits >= 2:
        return "high"
    if n >= 12:
        return "medium"
    return "low"


def reasoning_effort_for(effort: str) -> str:
    """工作力度 → API 的 reasoning_effort 参数值（max/ultra 折算为 high）"""
    return _REASONING_EFFORT.get(effort if effort in EFFORTS else "medium")


class AgentLLMError(Exception):
    pass


def estimate_tokens(text: str) -> int:
    """启发式估算文本 tokens（无 tiktoken 依赖）：中文约 1/字，英文约 1/4 字符"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return int(cjk + (len(text) - cjk) / 4) + 4


def estimate_image_tokens() -> int:
    """单张截图约估 tokens（OpenAI 中尺寸近似）"""
    return 765


def build_content(text: str = "", images: Optional[List[str]] = None) -> list:
    """构造 OpenAI 兼容 content 列表：文本 + image_url（data URL 或 http(s) URL）。

    detail="high"：要求 API 以高细节处理截图，防止自动降采样把叠加的坐标
    网格刻度压成无法辨认的小字，是精确点击的基础保障。
    """
    parts = []
    if text:
        parts.append({"type": "text", "text": text})
    for img in images or []:
        parts.append({"type": "image_url",
                      "image_url": {"url": img, "detail": "high"}})
    return parts or [{"type": "text", "text": ""}]


def _to_responses_input(messages: list) -> list:
    """把 Chat Completions 格式的 messages 转为 Responses API 的 input 项数组。

    - system → 单独走 instructions 参数，不放入 input
    - assistant：只保留文本内容（function_call 项不回放），空内容跳过
    - tool → {"type":"function_call_output","call_id","output"}
    - user/assistant 文本/图片 → {"type":"message","role","content":[...]}
    """
    items = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "system":
            continue
        if role == "tool":
            items.append({"type": "function_call_output",
                          "call_id": str(m.get("tool_call_id") or ""),
                          "output": str(m.get("content") or "")})
            continue
        if role not in ("user", "assistant"):
            continue
        c = m.get("content")
        if isinstance(c, list):
            parts = []
            for x in c:
                if not isinstance(x, dict):
                    continue
                if x.get("type") == "text" and x.get("text"):
                    parts.append({"type": "input_text", "text": x["text"]})
                elif x.get("type") == "image_url":
                    url = (x.get("image_url") or {}).get("url")
                    if url:
                        parts.append({"type": "input_image", "image_url": url})
            if parts:
                items.append({"type": "message", "role": role, "content": parts})
        else:
            text = str(c or "").strip()
            if text:
                items.append({"type": "message", "role": role,
                              "content": [{"type": "input_text", "text": text}]})
    return items


def _parse_responses_stream(stream, on_delta=None, on_reasoning=None, stop=None) -> dict:
    """解析 Responses API 的 SSE 流（event: / data: 行），返回 {text, tool_calls, usage, cache}。

    事件：response.output_text.delta（正文）、response.function_call_arguments.delta（工具参数，
    按 item_id 聚合）、response.output_item.done / response.completed（工具结果与 usage）、
    response.reasoning_text.delta（思考过程）、error（上游错误）。
    """
    text_parts: List[str] = []
    calls: dict = {}        # item_id -> {"id","name","args"}
    usage = None
    try:
        while True:
            if stop and stop():
                raise AgentLLMError("已停止")
            raw = stream.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if not data:
                continue
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            t = obj.get("type") or ""
            if t == "response.completed":
                resp = obj.get("response") or {}
                usage = resp.get("usage") or usage
                for it in resp.get("output") or []:
                    if isinstance(it, dict) and it.get("type") == "function_call":
                        cid = it.get("id") or ""
                        cur = calls.setdefault(cid, {"id": "", "name": "", "args": ""})
                        cur["id"] = it.get("call_id") or cur["id"]
                        if it.get("name"):
                            cur["name"] = it["name"]
                        if it.get("arguments"):
                            cur["args"] = it["arguments"]
            elif t == "response.output_item.added":
                it = obj.get("item") or {}
                if isinstance(it, dict) and it.get("type") == "function_call":
                    cid = it.get("id") or ""
                    if cid not in calls:
                        calls[cid] = {"id": "", "name": it.get("name", ""), "args": ""}
            elif t == "response.output_item.done":
                it = obj.get("item") or {}
                if isinstance(it, dict) and it.get("type") == "function_call":
                    cid = it.get("id") or ""
                    cur = calls.setdefault(cid, {"id": "", "name": "", "args": ""})
                    cur["id"] = it.get("call_id") or cur["id"]
                    if it.get("name"):
                        cur["name"] = it["name"]
                    if it.get("arguments"):
                        cur["args"] = it["arguments"]
            elif t == "response.function_call_arguments.delta":
                cur = calls.setdefault(str(obj.get("item_id") or ""),
                                       {"id": "", "name": "", "args": ""})
                cur["args"] += str(obj.get("delta") or "")
            elif t == "response.output_text.delta":
                d = obj.get("delta")
                if d:
                    text_parts.append(d)
                    if on_delta:
                        on_delta(d)
            elif t in ("response.reasoning_text.delta",
                       "response.reasoning_summary_text.delta",
                       "response.reasoning_effort.delta"):
                d = obj.get("delta")
                if d and on_reasoning:
                    on_reasoning(d)
            elif t == "error":
                msg = obj.get("message") or (obj.get("error") or {})
                if isinstance(msg, dict):
                    msg = msg.get("message", "")
                if msg:
                    raise AgentLLMError(str(msg))
    except AgentLLMError:
        raise
    except Exception as e:
        raise AgentLLMError(f"读取响应失败: {e}")

    calls_out = [{"id": calls[i]["id"] or i, "type": "function",
                  "function": {"name": calls[i]["name"],
                               "arguments": calls[i]["args"] or "{}"}}
                 for i in sorted(calls) if calls[i]["name"]]
    hit = int((usage or {}).get("prompt_cache_hit_tokens") or 0)
    miss = int((usage or {}).get("prompt_cache_miss_tokens") or 0)
    details = (usage or {}).get("prompt_tokens_details") or {}
    if not hit:
        hit = int(details.get("cached_tokens") or 0)
    if not miss:
        miss = max(0, int((usage or {}).get("prompt_tokens") or 0) - hit)
    return {"text": "".join(text_parts), "tool_calls": calls_out, "usage": usage,
            "cache": {"hit": hit, "miss": miss}}


class LLMClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL,
                 api_key: str = DEFAULT_API_KEY, model: str = DEFAULT_MODEL,
                 timeout: float = 60.0, protocol: str = "chat"):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or DEFAULT_API_KEY
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout
        # 接口协议：chat = /v1/chat/completions（默认）；responses = /v1/responses
        self.protocol = (protocol or "chat").lower() or "chat"
        # 由上层按工作力度设置；None 表示不发送（兼容不支持该参数的 API）
        self.reasoning_effort = None

    def chat_stream(self, messages: list,
                    tools: Optional[list] = None,
                    tool_choice="auto",
                    on_delta: Optional[Callable[[str], None]] = None,
                    on_reasoning: Optional[Callable[[str], None]] = None,
                    stop: Optional[Callable[[], bool]] = None) -> dict:
        """流式对话。返回 {text, tool_calls, usage}。

        tool_calls: [{"id","type":"function","function":{"name","arguments"}}]
        usage: {"prompt_tokens","completion_tokens","total_tokens"} 或 None
        on_reasoning: 思考过程增量（delta.reasoning_content / thinking），不保证所有模型返回
        """
        if self.protocol == "responses":
            return self._responses_stream(messages, tools, on_delta, on_reasoning, stop)
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "User-Agent": _UA,
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST")
        # 请求失败自动重试（429 限流 / 5xx / 网络抖动），指数退避；重试全程响应 stop
        resp = None
        last_err = None
        for attempt in range(_MAX_RETRIES):
            if stop and stop():
                raise AgentLLMError("已停止")
            try:
                resp = urllib.request.urlopen(req, timeout=self.timeout)
                break
            except urllib.error.HTTPError as e:
                last_err = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
                if e.code in (429, 500, 502, 503, 504) and attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAY * (attempt + 1))
                    continue
                raise AgentLLMError(last_err)
            except urllib.error.URLError as e:
                last_err = f"网络错误: {e.reason}"
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAY * (attempt + 1))
                    continue
                raise AgentLLMError(last_err)
        if resp is None:
            raise AgentLLMError(last_err or "请求失败")

        text_parts: List[str] = []
        tool_calls: dict = {}   # index -> {id, name, args}
        usage = None
        try:
            # 手动 readline 循环：每次迭代前检查 stop，命中立即断开连接，无需等下一行数据
            while True:
                if stop and stop():
                    resp.close()
                    raise AgentLLMError("已停止")
                raw = resp.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if obj.get("usage"):
                    usage = obj["usage"]
                for ch in obj.get("choices") or []:
                    delta = ch.get("delta") or {}
                    # 思考过程（reasoning_content / thinking），逐段流式回调
                    rc = delta.get("reasoning_content") or delta.get("thinking")
                    if rc:
                        if on_reasoning:
                            on_reasoning(rc)
                    content = delta.get("content")
                    if content:
                        text_parts.append(content)
                        if on_delta:
                            on_delta(content)
                    for tc in delta.get("tool_calls") or []:
                        idx = tc.get("index", 0)
                        cur = tool_calls.setdefault(idx, {"id": "", "name": "", "args": ""})
                        if tc.get("id"):
                            cur["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            cur["name"] += fn["name"]
                        if fn.get("arguments"):
                            cur["args"] += fn["arguments"]
        except AgentLLMError:
            raise
        except Exception as e:
            raise AgentLLMError(f"读取响应失败: {e}")

        calls = [{"id": tool_calls[i]["id"], "type": "function",
                  "function": {"name": tool_calls[i]["name"],
                               "arguments": tool_calls[i]["args"] or "{}"}}
                 for i in sorted(tool_calls)]
        # 上下文缓存统计（DeepSeek 返回 prompt_cache_hit/miss_tokens；
        # 部分服务商在 prompt_tokens_details.cached_tokens 提供命中数）
        hit = int((usage or {}).get("prompt_cache_hit_tokens") or 0)
        miss = int((usage or {}).get("prompt_cache_miss_tokens") or 0)
        details = (usage or {}).get("prompt_tokens_details") or {}
        if not hit:
            hit = int(details.get("cached_tokens") or 0)
        if not miss:
            miss = max(0, int((usage or {}).get("prompt_tokens") or 0) - hit)
        return {"text": "".join(text_parts), "tool_calls": calls, "usage": usage,
                "cache": {"hit": hit, "miss": miss}}

    def _responses_stream(self, messages: list, tools=None,
                          on_delta=None, on_reasoning=None, stop=None) -> dict:
        """Responses API（/v1/responses）流式对话。返回结构与 chat_stream 一致。

        请求：instructions=system、input=消息项数组（工具结果用 function_call_output）、
        tools、stream、reasoning.effort（可选）。流解析见 _parse_responses_stream。
        """
        payload = {
            "model": self.model,
            "input": _to_responses_input(messages),
            "stream": True,
            "store": False,
        }
        if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
            sys_txt = messages[0].get("content")
            if isinstance(sys_txt, str) and sys_txt.strip():
                payload["instructions"] = sys_txt
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        if tools:
            payload["tools"] = [
                {"type": "function", "name": t["function"]["name"],
                 "parameters": t["function"].get("parameters", {})}
                for t in tools if isinstance(t, dict)]
        req = urllib.request.Request(
            f"{self.base_url}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "User-Agent": _UA,
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST")
        resp = None
        last_err = None
        for attempt in range(_MAX_RETRIES):
            if stop and stop():
                raise AgentLLMError("已停止")
            try:
                resp = urllib.request.urlopen(req, timeout=self.timeout)
                break
            except urllib.error.HTTPError as e:
                last_err = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
                if e.code in (429, 500, 502, 503, 504) and attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAY * (attempt + 1))
                    continue
                raise AgentLLMError(last_err)
            except urllib.error.URLError as e:
                last_err = f"网络错误: {e.reason}"
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAY * (attempt + 1))
                    continue
                raise AgentLLMError(last_err)
        if resp is None:
            raise AgentLLMError(last_err or "请求失败")
        return _parse_responses_stream(resp, on_delta, on_reasoning, stop)
