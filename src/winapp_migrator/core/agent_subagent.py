"""子 Agent（Sub-Agent）：主 Agent 并发派发只读子任务

- run_sub_agent：单个子 Agent 的独立 LLM 循环（独立上下文 + 只读工具白名单）
- dispatch_sub_agents：多子任务并发执行并汇总（线程池，最多 4 并发，按任务顺序输出）
- explore_goal / search_goal：Explorer / Search 子 Agent 的任务指令模板

设计约束：子 Agent 只能使用只读工具（读文件/列目录/搜索/系统信息），
杜绝子任务未经主流程确认就修改文件或执行命令；每个子 Agent 上下文独立，
只把最终总结返回主 Agent，避免大规模探索/搜索撑爆主对话上下文。
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from winapp_migrator.core import agent_llm, agent_tools

# 子 Agent 可用工具白名单（全部只读）
READONLY_TOOLS = ("read_file", "list_directory", "search_files", "find_app",
                  "system_info", "get_time", "env_var")

_SUB_SYSTEM = """你是子 Agent：负责独立完成一项聚焦、只读的子任务，结果会被主 Agent 汇总使用。
规则：
1. 只使用提供的只读工具（读文件 / 列目录 / 搜索 / 系统信息），禁止修改任何文件或执行命令。
2. 先快速了解范围再动手，避免重复搜索或重复读取同一文件。
3. 输出精炼总结：关键路径与关键结论，不要整篇贴原文。
4. 找不到或无法完成时，明确说明已尝试的范围与原因。"""


def _sub_tools(allowed=None) -> list:
    """子 Agent 可用工具 schema（与只读白名单取交集）"""
    names = set(allowed or READONLY_TOOLS) & set(READONLY_TOOLS)
    return [t for t in agent_tools.tool_schemas()
            if t["function"]["name"] in names]


def _compress(messages: list) -> list:
    """子 Agent 上下文过长时压缩：保留 system + 首条 user（任务目标）+ 最近 12 条"""
    return messages[:2] + messages[-12:]


def run_sub_agent(llm, goal, allowed=None, max_rounds=8, stop=None, on_status=None) -> str:
    """运行一个子 Agent，返回其最终文本总结"""
    goal = (goal or "").strip()
    if not goal:
        return "（空任务）"
    messages = [{"role": "system", "content": _SUB_SYSTEM},
                {"role": "user", "content": agent_llm.build_content(goal)}]
    tools = _sub_tools(allowed)
    for _ in range(max(int(max_rounds or 8), 1)):
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
        for c in calls:
            if stop and stop():
                return "（子任务已停止）"
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"]["arguments"] or "{}")
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                args = {}
            if on_status:
                on_status(f"子Agent: {name}")
            try:
                text = agent_tools.execute_tool(name, args).get("text", "")
            except Exception as e:
                text = f"[工具错误] {name}: {e}"
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": text})
            if len(messages) > 30:
                messages = _compress(messages)
    return "（子 Agent 达到最大轮数，以上为部分结果）"


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
                                       max_rounds=t.get("max_rounds", 8),
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
