"""skills / agents / MCP 服务器配置：JSON 文件加载（启动时读取，可热改）

配置目录：~/.winapp_migrator/agent/
- skills.json      技能：[{"name","description","instruction"}]
- agents.json      助手：[{"name","description","system_prompt","skills":[],"tools":[]}]
- mcp_servers.json MCP：[{"name","type":"stdio|sse","command","args"|"url"}]
目录/文件不存在时使用内置默认值，首次运行自动生成示例文件。
"""

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".winapp_migrator" / "agent"

DEFAULT_SKILLS = [
    {"name": "screen_operate", "description": "屏幕操控（截图分析、鼠标点击、键盘输入）",
     "instruction": ("你可以截图观察屏幕，并用鼠标点击/输入文本完成用户请求。"
                     "每次操作前说明意图，操作后截图验证结果。")},
]

DEFAULT_AGENTS = [
    {"name": "桌面助手", "description": "通用桌面自动化助手：观察屏幕并操控电脑完成任务",
     "system_prompt": ("你是运行在 Windows 上的桌面 AI 助手。通过截图观察屏幕，使用工具"
                       "（移动/点击鼠标、输入文本、执行白名单命令）帮用户完成任务。\n"
                       "规则：\n"
                       "1. 每次操作前用一句话说明意图（会弹窗由用户确认）。\n"
                       "2. 操作后先截图验证结果再继续。\n"
                       "3. 坐标必须基于最近一次截图与 get_screen_size 的分辨率计算。\n"
                       "4. 完成目标后总结结果，不要做多余操作。"),
     "skills": ["screen_operate"], "tools": []},
]


def _load(name: str, default: list) -> list:
    path = CONFIG_DIR / name
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else default
    except Exception:
        return default


def _ensure_samples():
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        for name, default in (("skills.json", DEFAULT_SKILLS),
                              ("agents.json", DEFAULT_AGENTS),
                              ("mcp_servers.json", [])):
            path = CONFIG_DIR / name
            if not path.exists():
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(default, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def load_skills() -> list:
    return _load("skills.json", DEFAULT_SKILLS)


def load_agents() -> list:
    return _load("agents.json", DEFAULT_AGENTS)


def load_mcp_servers() -> list:
    return _load("mcp_servers.json", [])


def skill_instructions(skill_names: list) -> str:
    """把所选技能的 instruction 拼装成 system prompt 附加段落"""
    by_name = {s.get("name"): s for s in load_skills()}
    parts = []
    for n in skill_names or []:
        s = by_name.get(n)
        if s and s.get("instruction"):
            parts.append(s["instruction"])
    return "\n".join(parts)


def build_system_prompt(agent_name: str = "") -> str:
    """构造 system prompt：Agent 基础提示 + 所选技能说明 + 内置工具列表"""
    agent = next((a for a in load_agents() if a.get("name") == agent_name), None) \
        or DEFAULT_AGENTS[0]
    prompt = agent.get("system_prompt", "")
    skills = agent.get("skills", [])
    if skills:
        inst = skill_instructions(skills)
        if inst:
            prompt += "\n\n" + inst
    prompt += ("\n\n可用内置工具：screenshot(截屏观察)、get_screen_size(分辨率)、"
               "move_mouse/click/drag/scroll(鼠标)、press_key/type_text(键盘)、"
               "run_command(白名单命令)、read_file(读文件)。"
               "若连接了 MCP 服务器，其工具同样可用。")
    return prompt
