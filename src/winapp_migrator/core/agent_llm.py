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

# 纯文本模型关键字（子串匹配）：命中即视为不支持图像输入，禁用截图/视觉能力
TEXT_ONLY_KEYS = ("deepseek",)


def is_text_only_model(model: str) -> bool:
    """自动识别纯文本模型：模型名含 TEXT_ONLY_KEYS 任一关键字"""
    m = (model or "").lower()
    return any(k in m for k in TEXT_ONLY_KEYS)


def load_model_config() -> dict:
    """从 settings.json 读取模型配置（base_url/api_key/model），未配置时返回默认"""
    try:
        from winapp_migrator.core import agent_skills
        m = agent_skills.load_settings().get("model") or {}
        return {
            "base_url": m.get("base_url") or DEFAULT_BASE_URL,
            "api_key": m.get("api_key") or DEFAULT_API_KEY,
            "model": m.get("model") or DEFAULT_MODEL,
        }
    except Exception:
        return {"base_url": DEFAULT_BASE_URL, "api_key": DEFAULT_API_KEY,
                "model": DEFAULT_MODEL}


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


class LLMClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL,
                 api_key: str = DEFAULT_API_KEY, model: str = DEFAULT_MODEL, timeout: float = 60.0):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or DEFAULT_API_KEY
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout

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
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
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
        return {"text": "".join(text_parts), "tool_calls": calls, "usage": usage}
