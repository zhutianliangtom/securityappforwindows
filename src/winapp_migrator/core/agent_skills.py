"""skills / agents / MCP 服务器配置：JSON 文件加载（启动时读取，可热改）

配置目录：~/.winapp_migrator/agent/
- skills.json      技能：[{"name","description","instruction"}]
- agents.json      助手：[{"name","description","persona","rules","tool_instructions","system_prompt","skills":[],"tools":[]}]
                    persona: 人设描述；rules: 规则约束数组；tool_instructions: {工具名: {"理解": str, "执行拆分": [str]}}
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
    {"name": "brainstorming", "description": "头脑风暴：需求探索与方案设计",
     "instruction": ("1. 用 ask_user 依次澄清用户意图、目标与约束，直到需求明确。\n"
                     "2. 提出 2-3 个可行方案并对比优缺点，征询用户选择。\n"
                     "3. 确认方案后再动手，不跳过任何确认步骤。")},
    {"name": "writing-plans", "description": "为多步骤任务制定详细执行计划",
     "instruction": ("1. 把任务拆解为可独立执行的小步骤，每步写明目标与验证方式。\n"
                     "2. 用文字/列表输出计划，必要时用 ask_user 请用户确认。\n"
                     "3. 按计划逐步执行，每步完成后截图或读取结果验证再继续。")},
    {"name": "test-driven-development", "description": "测试驱动开发：先写测试再实现",
     "instruction": ("1. 先用 write_file 编写针对目标行为的测试用例。\n"
                     "2. 运行测试确认失败（红）。\n"
                     "3. 实现最小可用代码使测试通过（绿），必要时重构（重构）。\n"
                     "4. 重复直到所有用例通过并汇报结果。")},
    {"name": "systematic-debugging", "description": "系统化调试：不靠猜测定位问题",
     "instruction": ("1. 复现问题并读取相关日志/输出（run_command 或 read_file）。\n"
                     "2. 提出最可能的 2-3 个根因假设，按可能性排序。\n"
                     "3. 逐个用最小实验验证假设，排除一个再验证下一个。\n"
                     "4. 定位根因后修复，再复现验证已解决。")},
    {"name": "code-review", "description": "代码审查：检查问题与改进点",
     "instruction": ("1. 用 read_file 读取待审查文件，list_directory 了解项目结构。\n"
                     "2. 按顺序检查：逻辑正确性、边界与错误处理、安全与权限、可维护性。\n"
                     "3. 输出审查结论：严重问题/一般问题/建议，逐条给出文件与行号。")},
]

DEFAULT_AGENTS = [
    {"name": "桌面助手", "description": "通用桌面自动化助手：观察屏幕并操控电脑完成任务",
     "persona": "你是运行在 Windows 上的桌面 AI 助手，性格谨慎可靠、注重安全，"
                "执行每步操作前都会先想清楚后果。",
     "rules": [
         "1. 每次操作前用一句话说明意图（会弹窗由用户确认）。",
         "2. 操作后先截图验证结果再继续。",
         "3. 坐标必须基于最近一次截图与 get_screen_size 的分辨率计算。",
         "4. 完成目标后总结结果，不要做多余操作。",
         "5. 读取/写入文件前必须先确认路径在用户目录内。",
         "6. 用户需求不明确、缺少关键信息（目标文件/目标对象/期望结果）时，"
         "必须先调用 ask_user 提问，严禁猜测执行。",
     ],
     "tool_instructions": {
         "run_command": {
             "理解": "在系统终端执行命令，返回命令输出文本；只读诊断命令优先。",
             "执行拆分": ["分析命令安全性（删除/格式化/关机等一律拒绝）",
                          "说明意图并等待确认",
                          "执行并读取输出",
                          "截图验证屏幕变化"],
         },
         "write_file": {
             "理解": "创建或覆盖写入文本文件，仅限用户目录。",
             "执行拆分": ["确认目标路径合法（用户目录内）",
                          "说明写入目标文件并等待确认",
                          "执行写入",
                          "截图或读取文件确认结果"],
         },
         "read_file": {
             "理解": "读取文本文件内容，仅限用户目录。",
             "执行拆分": ["确认目标路径合法",
                          "读取文件",
                          "向用户摘要关键内容"],
         },
         "save_memory": {
             "理解": "把任务中的关键信息（用户偏好、约定、路径）追加保存到本地记忆。",
             "执行拆分": ["判断信息是否值得长期记住",
                          "确认保存意图",
                          "写入记忆文件"],
         },
         "virtual_desktop": {
             "理解": "Windows 多桌面：new 新建独立桌面并切换过去（用户桌面内容不受影响），"
                     "在独立桌面完成任务后用 back 返回用户桌面。适合后台执行、不打扰用户的任务。",
             "执行拆分": ["用 new 新建并切到独立桌面（桌面为空，可自由操作）",
                          "在独立桌面完成全部任务（截图/点击/输入）",
                          "任务完成后用 back 返回用户桌面",
                          "回到用户桌面后总结结果"],
         },
     },
     "system_prompt": ("通过截图观察屏幕，使用工具（移动/点击鼠标、输入文本、"
                       "执行白名单命令、读写文件、管理记忆）帮用户完成任务。"
                       "需要后台静默执行、避免打扰用户时，先用 virtual_desktop 的 new 新建独立桌面，"
                       "在独立桌面完成任务，最后用 back 返回用户桌面再汇报结果。"),
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


def save_mcp_servers(servers: list) -> bool:
    """把 MCP 服务器配置写入 mcp_servers.json"""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_DIR / "mcp_servers.json", "w", encoding="utf-8") as f:
            json.dump(servers, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


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
    """构造 system prompt：人设 persona + 基础提示 + 严格规则 + 工具执行规范 + 技能说明 + 工具列表"""
    agent = next((a for a in load_agents() if a.get("name") == agent_name), None) \
        or DEFAULT_AGENTS[0]
    parts = []
    persona = agent.get("persona")
    if persona:
        parts.append(persona)
    system_prompt = agent.get("system_prompt", "")
    if system_prompt:
        parts.append(system_prompt)
    rules = agent.get("rules", [])
    if rules:
        parts.append("严格规则（必须遵守）：\n" + "\n".join(str(r) for r in rules))
    tool_ins = agent.get("tool_instructions") or {}
    if tool_ins:
        block = ["工具执行规范（每个工具先理解再按固定流程拆分执行）："]
        for tname, cfg in tool_ins.items():
            if not isinstance(cfg, dict):
                continue
            u = cfg.get("理解")
            steps = cfg.get("执行拆分")
            if u:
                block.append(f"- {tname}（{u}）")
            if steps:
                for i, st in enumerate(steps, 1):
                    block.append(f"  步骤{i}. {st}")
        parts.append("\n".join(block))
    prompt = "\n\n".join(parts)

    skills = agent.get("skills", [])
    if skills:
        inst = skill_instructions(skills)
        if inst:
            prompt += "\n\n" + inst
    prompt += ("\n\n可用内置工具：screenshot(截屏观察)、get_screen_size(分辨率)、"
               "ask_user(需求不明确时向用户提问)、"
               "find_app(秒查已安装应用路径)、search_files(用户目录快速查找文件)、"
               "move_mouse/click/drag/scroll(鼠标)、press_key/type_text(键盘)、"
               "run_command(白名单命令)、read_file/write_file/edit_file(读写编辑文件)、"
               "list_directory(列目录)、save_memory/load_memory(本地长期记忆)。"
               "若连接了 MCP 服务器，其工具同样可用。")
    prompt += ("\n\n提问机制：当用户需求不明确、缺少关键信息时，必须先调用 ask_user 向用户提问"
               "（可给出建议选项），获得明确回答后再继续执行；严禁在信息不足时猜测执行。")
    prompt += ("\n\n记忆：你有本地长期记忆文件 memory.md。遇到用户偏好、重要结论、约定、常用路径等"
               "值得长期记住的信息时，调用 save_memory 保存；新任务开始或需要回忆过往信息时，"
               "自行决定是否调用 load_memory 查看。")
    return prompt
