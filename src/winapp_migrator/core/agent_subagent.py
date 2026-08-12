"""子 Agent（Sub-Agent）：主 Agent 并发派发子任务，加速多文件迭代

- run_sub_agent：单个子 Agent 的独立 LLM 循环（独立上下文 + 工具白名单）
- dispatch_sub_agents：多子任务并发执行并汇总（线程池，最多 4 并发，按任务顺序输出）
- explore_goal / search_goal：Explorer / Search 子 Agent 的任务指令模板

设计约束：子 Agent 可读写项目文件（创建/编辑/删除），用于并行迭代代码；
不暴露命令执行工具（run_command），并发执行无法逐条向用户确认，避免危险命令。
每个子 Agent 上下文独立，只把最终总结返回主 Agent，避免大规模探索/搜索撑爆主对话上下文。
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from winapp_migrator.core import agent_llm, agent_tools

# 子 Agent 可用工具白名单：读 + 编辑/创建/删除（迭代项目需要改代码）
SUB_AGENT_WHITELIST = ("read_file", "write_file", "edit_file", "delete_file",
                       "list_directory", "search_files", "find_app",
                       "system_info", "get_time", "env_var")

_SUB_SYSTEM = """你是子 Agent：负责独立完成一项聚焦的子任务，结果会被主 Agent 汇总使用。
规则：
1. 使用提供的工具完成子任务：可读取/列目录/搜索，也可创建、编辑、删除项目文件（write_file / edit_file / delete_file）。
2. 禁止执行任何命令（run_command 不可用）；修改文件前先读取相关内容，避免破坏已有逻辑。
3. 先快速了解范围再动手，避免重复搜索或重复读取同一文件。
4. 输出精炼总结：关键路径、关键结论与所做的修改，不要整篇贴原文。
5. 找不到或无法完成时，明确说明已尝试的范围与原因。"""


def _sub_tools(allowed=None) -> list:
    """子 Agent 可用工具 schema（与白名单取交集）"""
    names = set(allowed or SUB_AGENT_WHITELIST) & set(SUB_AGENT_WHITELIST)
    return [t for t in agent_tools.tool_schemas()
            if t["function"]["name"] in names]


def _compress(messages: list) -> list:
    """子 Agent 上下文过长时压缩：保留 system + 首条 user（任务目标）+ 最近 12 条；
    截断边界若落在 tool 回复上则向前回退，避免切断 assistant(tool_calls)/tool 配对"""
    start = max(len(messages) - 12, 2)
    while start > 2 and messages[start].get("role") == "tool":
        start -= 1
    return messages[:2] + messages[start:]


def _sub_system_prompt() -> str:
    """子 Agent 系统提示词：基础规则 + 用户自定义规则（每次派发时读取，保证及时生效）"""
    from winapp_migrator.core import agent_skills
    rules = [str(r).strip()
             for r in (agent_skills.load_settings().get("custom_rules") or [])
             if str(r).strip()]
    if not rules:
        return _SUB_SYSTEM
    from pathlib import Path
    rules_path = Path.home() / ".winapp_migrator" / "agent" / "settings.json"
    return (_SUB_SYSTEM
            + "\n\n用户自定义开发规则（每次执行操作前必须查看并严格遵守，"
            f"原始文件：{rules_path}）：\n"
            + "\n".join(f"- {r}" for r in rules)
            + f"\n当用户询问开发规则/项目规则/我们的规则等内容时，"
              f"必须调用 read_file 工具读取 {rules_path} 的 custom_rules 字段，"
              f"原样逐条如实回答；严禁凭记忆、猜测或编造规则内容。")


def run_sub_agent(llm, goal, allowed=None, stop=None, on_status=None) -> str:
    """运行一个子 Agent，返回其最终文本总结。

    不做轮数限制：任务持续到完成或被用户停止（stop），与主 Agent 一致；
    上下文过长由 _compress 自动压缩并保留任务目标，防止长任务遗忘开头。
    """
    goal = (goal or "").strip()
    if not goal:
        return "（空任务）"
    messages = [{"role": "system", "content": _sub_system_prompt()},
                {"role": "user", "content": agent_llm.build_content(goal)}]
    tools = _sub_tools(allowed)
    # 实际可执行白名单 = 子 Agent 白名单 ∩ 允许集：模型幻觉调用非白名单工具时直接拒绝
    whitelist = set(allowed or SUB_AGENT_WHITELIST) & set(SUB_AGENT_WHITELIST)
    # 开发类工具：动手改代码前必须先确认用户开发规则（首次调用被拦截，确认后下轮放行）
    dev_tools = frozenset({"write_file", "edit_file", "delete_file"})
    rules_confirmed = False
    while True:
        if stop and stop():
            return "（子任务已停止）"
        try:
            res = llm.chat_stream(messages, tools=tools, tool_choice="auto",
                                  stop=stop)
        except agent_llm.AgentLLMError as e:
            return f"子 Agent 调用失败: {e}"
        calls = res["tool_calls"]
        if not calls:
            return res["text"] or "（子 Agent 无输出）"
        messages.append({"role": "assistant",
                         "content": res["text"] or None, "tool_calls": calls})
        rules_just = False   # 本轮是否触发过规则确认（全部拦截后统一置位）
        for c in calls:
            if stop and stop():
                return "（子任务已停止）"
            name = c["function"]["name"]
            if name in dev_tools and not rules_confirmed:
                # 动手开发前的强制规则读取：首次调用开发类工具不放行，
                # 真实读取规则文本回给模型确认，下一轮重新发起再正常执行
                rules_just = True
                from winapp_migrator.core import agent_skills
                rules = [str(r).strip()
                         for r in (agent_skills.load_settings().get("custom_rules") or [])
                         if str(r).strip()]
                block = "\n".join(f"- {r}" for r in rules) if rules else "（当前未设置自定义开发规则）"
                messages.append({"role": "tool", "tool_call_id": c["id"],
                                 "content": ("[开发前规则确认] 动手开发前必须先确认用户开发规则，"
                                             "已读取规则文件，请严格遵守：\n" + block
                                             + "\n规则已确认。现在重新发起你刚才的开发工具调用。")})
                continue
            try:
                args = json.loads(c["function"]["arguments"] or "{}")
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                # 参数非法 JSON：把错误回给模型重新生成，避免以空参误调用
                messages.append({"role": "tool", "tool_call_id": c["id"],
                                 "content": ("[工具参数错误] tool_calls.arguments 不是合法 JSON，"
                                             "请检查参数格式（字符串需正确转义引号）并重新发起该工具调用。")})
                continue
            if name not in whitelist:
                messages.append({"role": "tool", "tool_call_id": c["id"],
                                 "content": f"[沙盒] 子 Agent 只允许只读工具，已拒绝调用 {name}"})
                continue
            if on_status:
                on_status(f"子Agent: {name}")
            try:
                text = agent_tools.execute_tool(name, args).get("text", "")
            except Exception as e:
                text = f"[工具错误] {name}: {e}"
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": text})
            if len(messages) > 30:
                messages = _compress(messages)
        if rules_just:
            rules_confirmed = True   # 本轮已确认规则，下轮开发工具正常放行


def dispatch_sub_agents(llm, tasks, stop=None, on_status=None, max_workers=4) -> str:
    """并发派发多个子 Agent 并汇总（按任务原始顺序输出）"""
    tasks = [t for t in (tasks or [])
             if isinstance(t, dict) and str(t.get("goal") or "").strip()]
    if not tasks:
        return "（没有可派发的子任务）"
    n = min(max(int(max_workers or 4), 1), len(tasks))

    def _one(i, t):
        try:
            return i, t, run_sub_agent(llm, t.get("goal", ""),
                                       allowed=t.get("allowed"),
                                       stop=stop, on_status=on_status)
        except Exception as e:
            return i, t, f"子 Agent 异常: {e}"

    results = {}
    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = {ex.submit(_one, i, t): i for i, t in enumerate(tasks)}
        for f in as_completed(futs):
            i, t, text = f.result()
            results[i] = text
    parts = []
    for i, t in enumerate(tasks):
        title = str(t.get("title") or f"子任务 {i + 1}")
        parts.append(f"【子任务 {i + 1}】{title}\n{results.get(i, '（无结果）')}")
    return "\n\n".join(parts)


def explore_goal(directory: str) -> str:
    """Explorer 子 Agent 任务指令：探索并理解一个项目"""
    d = (directory or "").strip()
    return (f"探索并理解项目目录「{d}」：\n"
            "1. 用 list_directory 查看目录结构（根目录与关键子目录，跳过 build/缓存/虚拟环境等无关目录）。\n"
            "2. 用 read_file 读取 README、说明与入口/配置文件（如 README.md、main.py、pyproject.toml、"
            "package.json），了解用途、技术栈、模块划分与启动方式。\n"
            "3. 用 search_files 定位关键字（如 main、entry）辅助判断入口。\n"
            "4. 输出项目概览：用途与技术栈、目录/模块结构、入口文件、构建或运行方式、值得注意的要点（≤400 字）。")


def search_goal(query: str, dirs: list = None, max_results: int = 20) -> str:
    """Search 子 Agent 任务指令：大规模搜索并汇总"""
    q = (query or "").strip()
    scope = "、".join(str(d).strip() for d in (dirs or []) if str(d).strip()) \
        or "工作目录/用户常用目录"
    m = max(int(max_results or 20), 1)
    return (f"大规模搜索关键词「{q}」，范围：{scope}，最多保留 {m} 条命中。\n"
            "1. 用 search_files 对目标目录逐个搜索（必要时分目录多次调用）。\n"
            "2. 对重要命中用 read_file 读取相关片段确认匹配原因。\n"
            "3. 汇总输出：命中文件清单（绝对路径 + 匹配原因/摘要），按相关度排序，最多 "
            f"{m} 条；无命中说明已搜索的范围。")
