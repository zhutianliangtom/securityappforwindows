"""zhuzhu Copilot 的 LLM 客户端：OpenAI 兼容 /v1/chat/completions，流式（SSE）

- stream: true，逐 token 回调（on_delta）实现主流 Agent 的流式输出
- 工具调用：tools / tool_choice（流式 tool_calls 增量按 index 聚合）
- 图像输入：messages[].content[].image_url（支持 data URL 或 http(s) URL）
- tokens 预计算：发送前启发式估算（中文按字、英文按 4 字符），响应后取实际 usage
"""

import json
import os
import random
import time
import urllib.error
import urllib.request
from typing import Callable, List, Optional

DEFAULT_BASE_URL = "https://api.agnes-ai.cn/v1"
DEFAULT_MODEL = "agnes-2.5-flash"
DEFAULT_API_KEY = "sk-iydeFjzDmQr4Se3N6yxEjRHccWQbhSXLOSp27ZH5qhxathwR"
DEFAULT_PROVIDER_NAME = "默认服务商"   # 内置默认服务商（agnes），整行锁定不可删除/编辑
_UA = "WinAppMigrator/1.0 AgentClient"
_MAX_RETRIES = 3    # 请求失败（429/5xx/网络）自动重试次数
_RETRY_DELAY = 2.0  # 重试基础延迟（秒），指数退避

# 主流 coding/Agent 服务商预设（添加服务商时一键填入，仍需填写 Key 并通过连通性测试）。
# 模型名为 2026 主流可用名，仅作预填参考；若测试失败请按各平台控制台实际模型名修改。
PRESET_PROVIDERS = [
    # 火山方舟 Coding Plan：官方专属端点 /api/coding/v3（OpenAI 兼容），必须用 Coding
    # Plan 专属 API Key；切勿用 /api/v3（不消耗套餐额度、产生额外费用）。
    # 官方模型：ark-code-latest(控制台切换) / doubao-seed-2.1-turbo / doubao-seed-2.0-lite /
    # minimax-m3 / glm-5.2(glm-latest) / glm-5.3 / deepseek-v4-flash / deepseek-v4-pro / kimi-k2.7-code
    {"name": "火山方舟（Coding Plan）",
     "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
     "models": ["ark-code-latest", "deepseek-v4-flash", "deepseek-v4-pro",
                "kimi-k2.7-code", "doubao-seed-2.1-turbo", "glm-5.3", "minimax-m3"],
     "multimodal_models": [],
     "protocol": "chat",
     "desc": "火山方舟 Coding Plan 专属 OpenAI 端点（/api/coding/v3）；须用 Coding Plan 专属 API Key，"
             "勿用 /api/v3（不消耗套餐额度）。模型可在控制台切换（ark-code-latest）或直接填模型名"},
    # 方舟 Agent Plan：与 Coding Plan 是两套套餐/端点，必须区分——专属端点
    # /api/plan/v3（OpenAI 兼容，支持 Chat 与 Responses API），须用 Agent Plan
    # 专属 API Key（与 Coding Plan Key、通用火山 Key 均不同，请勿混用）。
    {"name": "火山方舟（Agent Plan）",
     "base_url": "https://ark.cn-beijing.volces.com/api/plan/v3",
     "models": ["ark-code-latest", "deepseek-v4-pro", "deepseek-v4-flash",
                "glm-5.3", "glm-5.2", "kimi-k3", "doubao-seed-2.1-turbo"],
     "multimodal_models": ["doubao-seed-2.0-lite"],
     "protocol": "chat",
     "desc": "方舟 Agent Plan 专属端点（/api/plan/v3，OpenAI 兼容，支持 Chat/Responses API）；"
             "须用 Agent Plan 专属 API Key（与 Coding Plan Key、通用火山 Key 均不同），"
             "官方推荐 Responses API 推理效果更好"},
    {"name": "火山方舟（通用）",
     "base_url": "https://ark.cn-beijing.volces.com/api/v3",
     "models": ["doubao-seed-2.1-pro", "doubao-seed-2.1-turbo"],
     "multimodal_models": ["doubao-1-5-vision-pro"],
     "protocol": "chat",
     "desc": "火山方舟数据面 API，模型名可用推理接入点 ID 或基础模型名"},
    # 智谱 GLM Coding Plan：必须用专属端点 /api/coding/paas/v4（OpenAI 兼容），
    # 用普通 /api/paas/v4 无法享受套餐额度且可能报错。支持 glm-5.3 / glm-4.7 / glm-4.7-flash
    {"name": "智谱（GLM Coding Plan）",
     "base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
     "models": ["glm-5.3", "glm-4.7", "glm-4.7-flash"],
     "multimodal_models": [],
     "protocol": "chat",
     "desc": "智谱 GLM Coding Plan 专属端点（/api/coding/paas/v4，OpenAI 兼容）；"
             "须订阅 GLM Coding Plan 并用其专属网关，否则无法享用套餐额度"},
    {"name": "智谱清言",
     "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "models": ["glm-5.3", "glm-5.2", "glm-4.7-flash"],
     "multimodal_models": ["glm-4v-plus"],
     "protocol": "chat",
     "desc": "智谱开放平台（OpenAI 兼容），glm-4.7-flash 为免费模型"},
    {"name": "DeepSeek",
     "base_url": "https://api.deepseek.com/v1",
     "models": ["deepseek-v4-pro", "deepseek-v4-flash"],
     "multimodal_models": [],
     "protocol": "chat",
     "desc": "DeepSeek 官方 API（V4 系列；deepseek-chat / deepseek-reasoner 已停用）"},
    {"name": "OpenAI",
     "base_url": "https://api.openai.com/v1",
     "models": ["gpt-5.4", "gpt-5.4-mini", "gpt-5.3"],
     "multimodal_models": ["gpt-5.4", "gpt-5.4-mini"],
     "protocol": "chat",
     "desc": "OpenAI 官方 API（GPT-5 系列；gpt-4o / gpt-4.1 已退役）"},
    {"name": "Kimi（月之暗面）",
     "base_url": "https://api.moonshot.cn/v1",
     "models": ["kimi-k3", "kimi-k2.6"],
     "multimodal_models": ["kimi-k2.6"],
     "protocol": "chat",
     "desc": "月之暗面 Kimi API（K3 / K2.6；moonshot-v1 已停用）"},
    {"name": "硅基流动",
     "base_url": "https://api.siliconflow.cn/v1",
     "models": ["deepseek-ai/DeepSeek-V4-Pro", "deepseek-ai/DeepSeek-V4-Flash",
                "zai-org/GLM-5.1"],
     "multimodal_models": ["Qwen/Qwen3-VL-32B-Instruct"],
     "protocol": "chat",
     "desc": "SiliconFlow 聚合平台（OpenAI 兼容）"},
]

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
# 各服务商按力度正确映射的 API 参数（依据各厂商官方文档 2026）
_DEEPSEEK_EFFORT = {"high": "high", "max": "max", "ultra": "max"}      # DeepSeek V4 思考模式仅 high/max
_GLM52_EFFORT = {"low": "minimal", "medium": "medium", "high": "high",
                 "max": "xhigh", "ultra": "max"}                        # GLM-5.2 全档位
_GLM53_EFFORT = {"low": "low", "medium": "high", "high": "high",
                 "max": "max", "ultra": "max"}                          # GLM-5.3 仅 max/high/low
_KIMI3_EFFORT = {"low": "low", "medium": "high", "high": "high",
                 "max": "max", "ultra": "max"}                          # Kimi K3 支持 low/high/max
_OPENAI_EFFORT = {"low": "low", "medium": "medium", "high": "high",
                  "max": "high", "ultra": "high"}                       # OpenAI o 系列


def build_effort_params(model: str, effort: str) -> dict:
    """把工作力度正确映射为当前模型的 API 参数（自动调节，无需手动开关）。

    依据各厂商官方文档（DeepSeek/智谱/Kimi/OpenAI，2026）：
    - DeepSeek V4：thinking.type 控制思考开关；reasoning_effort 仅 high/max，
      low/medium 映射为 high；关思考时不传 reasoning_effort（否则 400）
    - GLM-5.3：思考强制开启不可关，reasoning_effort 仅 max/high/low
    - GLM-5.2：thinking.type + reasoning_effort（max/xhigh/high/medium/low/minimal/none）
    - GLM-5/5.1/5v/5-turbo、GLM-4.5/4.6：仅 thinking.type（不支持 reasoning_effort，勿传）
    - GLM-4.7：强制思考，仅 thinking.type=enabled
    - Kimi K3：顶层 reasoning_effort（low/high/max，默认 max）
    - Kimi K2.6/K2.5：thinking.type（默认 enabled）
    - OpenAI o 系列/gpt-5：顶层 reasoning_effort（low/medium/high）
    - 其他模型（doubao/minimax/agnes 等）：不支持，返回空 dict（不发送任何参数）
    """
    m = (model or "").lower()
    eff = effort if effort in EFFORTS else "medium"
    if "deepseek" in m:
        # DeepSeek V4：思考模式与 reasoning_effort 强耦合（关了思考不能带 effort）
        if eff in ("low", "medium"):
            return {"thinking": {"type": "disabled"}}
        return {"thinking": {"type": "enabled"},
                "reasoning_effort": "max" if eff in ("max", "ultra") else "high"}
    if m.startswith("glm-5.3"):
        return {"thinking": {"type": "enabled"},
                "reasoning_effort": _GLM53_EFFORT.get(eff, "high")}
    if m.startswith("glm-5.2"):
        if eff == "low":
            return {"thinking": {"type": "disabled"}}
        return {"thinking": {"type": "enabled"},
                "reasoning_effort": _GLM52_EFFORT.get(eff, "medium")}
    if m.startswith("glm-4.7"):
        return {"thinking": {"type": "enabled"}}   # 强制思考，不可关闭
    if m.startswith("glm-4.5") or m.startswith("glm-4.6"):
        return {"thinking": {"type": "enabled" if eff in ("high", "max", "ultra") else "disabled"}}
    if m.startswith("glm-5"):
        return {"thinking": {"type": "enabled" if eff in ("high", "max", "ultra") else "disabled"}}
    if m.startswith("kimi-k3"):
        return {"reasoning_effort": _KIMI3_EFFORT.get(eff, "max")}
    if m.startswith(("kimi-k2.6", "kimi-k2.5")):
        return {"thinking": {"type": "enabled" if eff in ("high", "max", "ultra") else "disabled"}}
    if m.startswith(("o1", "o3", "o4", "o5", "gpt-5")):
        return {"reasoning_effort": _OPENAI_EFFORT.get(eff, "medium")}
    return {}


def is_text_only_model(model: str) -> bool:
    """自动识别纯文本模型：模型名含 TEXT_ONLY_KEYS 任一关键字"""
    m = (model or "").lower()
    return any(k in m for k in TEXT_ONLY_KEYS)


def load_model_config() -> dict:
    """从 settings.json 读取模型配置，未配置时返回默认。

    支持多服务商：settings["model"]["providers"] = [{name, base_url, api_key, models, protocol}]，
    "active" 指定当前使用的服务商名。返回当前服务商的 base_url/api_key/model/models/protocol，
    并附带完整 providers 列表供 UI 展示；兼容旧版单服务商字段（base_url/api_key/models）。
    另含 effort_models / effort / auto_effort / send_effort。
    """
    try:
        from winapp_migrator.core import agent_skills
        m = agent_skills.load_settings().get("model") or {}
        if not isinstance(m, dict):
            m = {}
        providers = [p for p in (m.get("providers") or [])
                     if isinstance(p, dict) and p.get("base_url")]
        # 兼容旧单服务商配置：无 providers 时从旧字段构建一个
        if not providers:
            single = {
                "name": str(m.get("provider_name") or "默认服务商"),
                "base_url": m.get("base_url") or DEFAULT_BASE_URL,
                "api_key": m.get("api_key") or DEFAULT_API_KEY,
                "models": [str(x).strip() for x in (m.get("models") or []) if str(x).strip()],
                "protocol": m.get("protocol") if m.get("protocol") in ("chat", "responses") else "chat",
            }
            single_model = str(m.get("model") or "").strip()
            if single_model and single_model not in single["models"]:
                single["models"].insert(0, single_model)
            # 仅内置默认场景（无任何模型配置）兜底 agnes 默认模型；用户服务商不加
            if not single["models"]:
                single["models"] = [DEFAULT_MODEL]
            providers = [single]
        # 规范化每个服务商（不向用户服务商默认注入 agnes 模型）
        for p in providers:
            p["name"] = str(p.get("name") or "服务商").strip() or "服务商"
            p["base_url"] = str(p.get("base_url") or DEFAULT_BASE_URL)
            p["api_key"] = str(p.get("api_key") or "")
            p["protocol"] = (p.get("protocol") if p.get("protocol") in ("chat", "responses")
                             else "chat")
            p["models"] = [str(x).strip() for x in (p.get("models") or []) if str(x).strip()]
            p["multimodal_models"] = [str(x).strip() for x in (p.get("multimodal_models") or [])
                                      if str(x).strip()]
        # 聚合所有服务商的模型作为统一路由池（不再区分「当前服务商」）
        all_models = []
        for p in providers:
            for mm in p["models"]:
                if mm not in all_models:
                    all_models.append(mm)
        first = providers[0]
        return {
            "base_url": first["base_url"],
            "api_key": first["api_key"],
            "model": all_models[0] if all_models else DEFAULT_MODEL,
            "models": all_models,
            "protocol": first["protocol"],
            "providers": providers,
            "effort_models": dict(m.get("effort_models") or {}),
            "effort": m.get("effort") if m.get("effort") in EFFORTS else "medium",
            "auto_effort": bool(m.get("auto_effort", True)),
            "send_effort": bool(m.get("send_effort", False)),
        }
    except Exception:
        default = {"name": "默认服务商", "base_url": DEFAULT_BASE_URL,
                   "api_key": DEFAULT_API_KEY, "models": [DEFAULT_MODEL],
                   "protocol": "chat"}
        return {"base_url": DEFAULT_BASE_URL, "api_key": DEFAULT_API_KEY,
                "model": DEFAULT_MODEL, "models": [DEFAULT_MODEL],
                "protocol": "chat", "providers": [default],
                "effort_models": {}, "effort": "medium",
                "auto_effort": True, "send_effort": False}


def provider_for_model(cfg: dict, model: str) -> dict:
    """返回包含指定模型的第一个服务商 dict（取其 base_url/api_key/protocol），找不到返回 {}"""
    for p in (cfg.get("providers") or []):
        if model in (p.get("models") or []):
            return p
    return {}


def is_default_provider(p: dict) -> bool:
    """是否内置默认服务商（agnes）：整行锁定，不可删除/编辑。
    按名称「默认服务商」或 agnes 默认地址识别（兼容旧配置与兜底生成）。"""
    if not isinstance(p, dict):
        return False
    return (str(p.get("name") or "") == DEFAULT_PROVIDER_NAME
            or str(p.get("base_url") or "").startswith(DEFAULT_BASE_URL))


def test_provider_connection(base_url: str, api_key: str, model: str,
                             protocol: str = "chat", timeout: float = 15.0) -> tuple:
    """真实连通性测试：用最小 chat/completions 请求验证 base_url + api_key + 模型可用。
    全程真实 API 调用，不 mock；返回 (ok, message)，失败附具体 HTTP/网络错误便于排障。"""
    base_url = (base_url or "").strip().rstrip("/")
    api_key = (api_key or "").strip()
    model = (model or "").strip()
    if not base_url or not api_key or not model:
        return False, "请填写完整的接口地址、API Key 与模型名"
    url = f"{base_url}/chat/completions"
    payload = {"model": model,
               "messages": [{"role": "user", "content": "ping"}],
               "max_tokens": 1, "stream": False}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": _UA,
                 "Authorization": f"Bearer {api_key}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            return True, f"连接成功（HTTP {resp.status}），Key 与模型「{model}」可用"
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = (e.read().decode("utf-8", "replace") or "")[:200]
        except Exception:
            pass
        return False, f"HTTP {e.code}：{detail or '请求被拒绝（请检查地址/Key/模型名）'}"
    except urllib.error.URLError as e:
        return False, f"网络错误：{e.reason}"
    except Exception as e:
        return False, f"测试失败：{e}"


def analyze_connection_error(context: str) -> str:
    """用默认 AI 分析服务商连通性失败原因并给出修复建议（排障助手）。

    始终走内置默认 API（与用户自定义配置无关），失败时返回空串由调用方兜底。
    返回简短中文建议（2-5 条），便于用户在连通性测试失败后快速定位（如
    Coding Plan 端点/专属 Key/模型名/协议等）。"""
    prompt = ("你是 API 接入排障助手。用户配置的 AI 服务商连通性测试失败，"
              "请分析失败信息，给出最可能的原因与可操作修复建议（简洁中文 2-5 条，不要客套）。\n"
              f"失败信息：{(context or '').strip()[:800]}")
    try:
        # 使用流式请求以支持 responses 协议
        llm = LLMClient(
            base_url=DEFAULT_BASE_URL,
            api_key=DEFAULT_API_KEY,
            model=DEFAULT_MODEL
        )
        res = llm.chat_stream([
            {"role": "system", "content": "你是 API 接入排障助手，只输出简洁的中文分析与建议。"},
            {"role": "user", "content": prompt},
        ])
        return str(res.get("text") or "").strip()
    except Exception:
        return ""


def is_vision_model(cfg: dict, model: str) -> bool:
    """模型是否具备视觉能力：显式标记为多模态（multimodal_models）优先，
    否则按模型名自动识别为非纯文本"""
    m = (model or "").strip()
    if not m:
        return False
    for p in (cfg.get("providers") or []):
        if m in (p.get("multimodal_models") or []):
            return True
    return not is_text_only_model(m)


def _model_tier(model: str) -> str:
    """按模型名后缀判断能力档位：flash/lite/mini/small/turbo≈轻量，pro/max/plus/ultra≈重量，其余通用"""
    m = (model or "").lower()
    if any(k in m for k in ("flash", "lite", "mini", "small", "turbo")):
        return "light"
    if any(k in m for k in ("pro", "max", "plus", "ultra", "reasoner")):
        return "heavy"
    return "general"


def requires_vision(text: str, images: list) -> bool:
    """是否需要视觉模型：本次带图，或为需看页面截图/浏览器操作的任务"""
    if images:
        return True
    t = (text or "").strip()
    if not t:
        return False
    keys = ("打开", "点击", "点一下", "登录", "点赞", "打卡", "截屏", "截图",
            "屏幕", "浏览器", "看视频", "刷视频", "鼠标", "输入框", "按钮",
            "帮我开", "帮我点", "帮我登", "打开网页")
    return any(k in t for k in keys)


def resolve_model(cfg: dict, effort: str = "medium", vision_needed: bool = False) -> str:
    """按工作力度路由模型（自动选择模式）。

    - 优先用户配置的 effort_models 映射（确定性）。
    - 否则按模型档位 + 能力选：轻量任务(low/medium)优先 flash 类轻量模型，
      重量任务(high/max/ultra)优先 pro 类重量模型。
    - vision_needed(视觉/截图任务)时先在视觉模型集合内路由。
    - 同档位多模型时随机挑选（避免死磕同一模型）。
    - 保证与引擎单例共用上下文：仅切换模型连接，不重建对话。
    """
    m = cfg or {}
    effort = effort if effort in EFFORTS else "medium"
    em = m.get("effort_models") or {}
    name = str(em.get(effort) or "").strip() or str(em.get("medium") or "").strip()
    if name:
        return name
    all_models = m.get("models") or []
    # 视觉任务：只在视觉模型内路由；无视觉模型时回退内置 agnes（视为视觉模型），
    # 否则纯文本模型看不到浏览器页面截图，无法理解网页状态
    if vision_needed:
        pool = [x for x in all_models if is_vision_model(m, x)]
        if not pool:
            return DEFAULT_MODEL
    else:
        pool = list(all_models)
    if not pool:
        return m.get("model") or DEFAULT_MODEL
    want = "light" if effort in ("low", "medium") else "heavy"
    tiers = [x for x in pool if _model_tier(x) == want]
    if not tiers:   # 无对应档位：用全部候选
        tiers = list(pool)
    return random.choice(tiers)


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


def assess_effort(text: str) -> str:
    """用默认轻量模型（agnes-2.5-flash）评估任务难度/工作量，返回 EFFORTS 之一。

    始终走内置默认 API（与用户自定义配置无关），保证评估模型不被隐藏；
    请求极小（max_tokens=8），评估失败时回退本地启发式估算 estimate_effort。
    """
    import re
    prompt = ("你是任务难度评估器。根据用户的任务描述评估工作量和复杂度，"
              "只输出一个等级词：low、medium、high、max 或 ultra，不要输出任何其他内容。\n"
              f"任务描述：{(text or '').strip()[:800]}")
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": "你是任务难度评估器，只输出 low/medium/high/max/ultra 之一。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 8,
    }
    try:
        req = urllib.request.Request(
            f"{DEFAULT_BASE_URL}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "User-Agent": _UA,
                     "Authorization": f"Bearer {DEFAULT_API_KEY}"},
            method="POST")
        # 网络/5xx 抖动自动重试，保证「内置 agnes 评估」更可靠地执行
        last = None
        for attempt in range(_MAX_RETRIES):
            try:
                raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
                resp = json.loads(raw)
                txt = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content", "") or ""
                m = re.search(r"\b(low|medium|high|max|ultra)\b", txt.lower())
                if m:
                    return m.group(1)
                break   # 有响应但格式不符：不再重试，走回退
            except Exception as e:   # noqa: BLE001
                last = e
                time.sleep(_RETRY_DELAY * (2 ** attempt))
        if last:
            raise last
    except Exception:
        pass
    return estimate_effort(text)   # 评估失败：回退本地估算，保证流程不中断


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


def _repair_tool_pairs(messages: list) -> list:
    """修复工具调用配对：assistant(tool_calls) 与其 tool 回复必须一一对应，
    否则上游会报 "tool_calls must be followed by tool messages" 400。

    覆盖场景：上下文压缩/截断切断配对、任务中途停止留下半截 tool_calls、
    历史持久化恢复的残缺状态。规则：
    - 孤儿 tool 消息（前面没有 assistant 声明该 call_id）→ 丢弃
    - assistant 中未被任何 tool 回复的 tool_call → 从 tool_calls 中剔除（保留文本）
    """
    pending = {}          # call_id -> 是否已收到回复（False=已回复）
    first = []
    for m in messages or []:
        if not isinstance(m, dict):
            first.append(m)
            continue
        if m.get("role") == "assistant" and m.get("tool_calls"):
            kept = [tc for tc in m["tool_calls"]
                    if isinstance(tc, dict) and tc.get("id")]
            nm = dict(m)
            if kept:
                nm["tool_calls"] = kept
                for tc in kept:
                    pending.setdefault(tc["id"], True)
            else:
                nm.pop("tool_calls", None)
            first.append(nm)
        elif m.get("role") == "tool":
            cid = m.get("tool_call_id")
            if cid and cid in pending:
                pending[cid] = False
                first.append(m)
            # 无对应声明的孤儿 tool 消息：丢弃
        else:
            first.append(m)
    out = []
    for m in first:
        if (isinstance(m, dict) and m.get("role") == "assistant"
                and m.get("tool_calls")):
            kept = [tc for tc in m["tool_calls"]
                    if pending.get(tc.get("id")) is False]
            nm = dict(m)
            if kept:
                nm["tool_calls"] = kept
            else:
                nm.pop("tool_calls", None)
            out.append(nm)
        else:
            out.append(m)
    return out


def _sanitize_messages(messages: list) -> list:
    """发送前统一清洗消息：剔除内容数组里的空文本/空图部分、空数组补占位文本、
    空 content 补空串，并修复 tool_calls/tool 回复配对完整性（见 _repair_tool_pairs）"""
    out = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        c = m.get("content")
        if isinstance(c, list):
            kept = []
            for x in c:
                if not isinstance(x, dict):
                    kept.append(x)
                    continue
                t = x.get("type")
                if t == "text":
                    if str(x.get("text") or "").strip():
                        kept.append(x)
                elif t == "image_url":
                    if (x.get("image_url") or {}).get("url"):
                        kept.append(x)
                else:
                    kept.append(x)
            if not kept:
                kept = [{"type": "text", "text": "（内容已忽略）"}]
            m = dict(m, content=kept)
        elif c is None:
            m = dict(m, content="")
        out.append(m)
    return _repair_tool_pairs(out)


def _to_responses_input(messages: list) -> list:
    """把 Chat Completions 格式的 messages 转为 Responses API 的 input 项数组。

    - system → 单独走 instructions 参数，不放入 input
    - assistant：文本内容 → message 项；工具调用 → function_call 项（必须回放，
      否则后续 function_call_output 因找不到对应 call_id 报 400）
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
        # assistant 的工具调用回放为 function_call 项（保留 call_id 供 function_call_output 匹配）
        if role == "assistant":
            for tc in m.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                items.append({"type": "function_call",
                              "call_id": str(tc.get("id") or ""),
                              "name": str(fn.get("name") or ""),
                              "arguments": str(fn.get("arguments") or "{}"),
                              "status": "completed"})
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
            "messages": _sanitize_messages(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        # 工作力度/思考参数：DeepSeek/GLM/Kimi 等的 effort_params（thinking/reasoning_effort）
        # 必须真正合入 chat/completions 请求体，否则上游拿不到力度参数
        if self.effort_params:
            payload.update(self.effort_params)
        elif self.reasoning_effort:
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

    def chat(self, messages: list, max_tokens: int = 1024,
             timeout: float = 60.0, stop: Optional[Callable[[], bool]] = None) -> dict:
        """非流式单次对话（内部小请求：上下文自主摘要等）。返回 {"text", "usage"}"""
        if self.protocol == "responses":
            raise AgentLLMError("responses 协议不支持内部摘要请求")
        payload = {
            "model": self.model,
            "messages": _sanitize_messages(messages),
            "stream": False,
            "max_tokens": max_tokens,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
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
                resp = urllib.request.urlopen(req, timeout=timeout)
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
        data = json.loads(resp.read().decode("utf-8", "replace"))
        msg = ((data.get("choices") or [{}])[0].get("message") or {})
        c = msg.get("content")
        if isinstance(c, list):   # 部分 API 返回分段数组
            text = "".join(str(x.get("text") or "") for x in c if isinstance(x, dict))
        else:
            text = str(c or "")
        return {"text": text, "usage": data.get("usage")}

    def _responses_stream(self, messages: list, tools=None,
                          on_delta=None, on_reasoning=None, stop=None) -> dict:
        """Responses API（/v1/responses）流式对话。返回结构与 chat_stream 一致。

        请求：instructions=system、input=消息项数组（工具结果用 function_call_output）、
        tools、stream、reasoning.effort（可选）。流解析见 _parse_responses_stream。
        """
        payload = {
            "model": self.model,
            "input": _to_responses_input(_sanitize_messages(messages)),
            "stream": True,
            "store": False,
        }
        if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
            sys_txt = messages[0].get("content")
            if isinstance(sys_txt, str) and sys_txt.strip():
                payload["instructions"] = sys_txt
        if self.effort_params:
            # Responses 协议：effort 参数映射到 reasoning.effort；thinking 等不适用则忽略
            if "reasoning_effort" in self.effort_params:
                payload["reasoning"] = {"effort": self.effort_params["reasoning_effort"]}
        elif self.reasoning_effort:
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


# ============================================================
# 模型配置加密存储（本地 JSON 文件加密）
# ============================================================
# 密钥派生：Windows MachineGuid（每台机器唯一，注册表 HKLM\SOFTWARE\Microsoft\Cryptography）
# XOR + base64 混淆，防止 settings.json 明文暴露用户的 API Key 和模型配置

def _machine_key() -> bytes:
    """从 Windows MachineGuid 派生 32 字节加密密钥（机器唯一，重装系统会变）"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Cryptography") as k:
            guid, _ = winreg.QueryValueEx(k, "MachineGuid")
        # 用 MachineGuid 的 SHA-256 作为密钥
        import hashlib
        return hashlib.sha256(guid.encode()).digest()
    except OSError:
        # 兜底：用用户名 + 主机名（跨机器不通用但至少不裸露）
        import hashlib
        seed = f"{os.environ.get('USERNAME','')}{os.environ.get('COMPUTERNAME','')}zhuzhu_copilot"
        return hashlib.sha256(seed.encode()).digest()


def _xor_encrypt(data: str) -> str:
    """XOR + base64 加密（utf-8 明文 → base64 密文）"""
    if not data:
        return data
    key = _machine_key()
    raw = data.encode("utf-8")
    result = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    import base64
    return base64.urlsafe_b64encode(result).decode("ascii")


def _xor_decrypt(data: str) -> str:
    """XOR + base64 解密（base64 密文 → utf-8 明文）。
    注意必须先 base64 解码再做 XOR，否则解不出原文（旧实现即为此 bug）。"""
    if not data:
        return data
    key = _machine_key()
    import base64
    try:
        raw = base64.urlsafe_b64decode(data.encode("ascii"))
    except Exception:
        return data
    result = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    return result.decode("utf-8", "replace")


def encrypt_model_config(model_section: dict) -> dict:
    """将 model 配置节加密后存入 settings.json。
    
    返回一个新 dict，其中 model 字段替换为加密后的 {"_encrypted": true, "data": "<cipher>"}。
    外部调用方用此返回值安全存储。
    """
    if not model_section or not isinstance(model_section, dict):
        return model_section
    raw = json.dumps(model_section, ensure_ascii=False, separators=(",", ":"))
    return {"_encrypted": True, "data": _xor_encrypt(raw)}


def decrypt_model_config(model_section: dict) -> dict:
    """解密 settings.json 中的 model 配置节。
    
    若 model_section 包含 _encrypted 标记则解密还原；否则原样返回（兼容旧版明文配置）。
    """
    if not isinstance(model_section, dict):
        return model_section
    if not model_section.get("_encrypted"):
        return model_section  # 旧版明文，直接返回
    cipher = model_section.get("data")
    if not cipher:
        return model_section
    try:
        plain = _xor_decrypt(cipher)
        return json.loads(plain)
    except Exception:
        return model_section  # 解密失败（如换机器），回退旧数据
