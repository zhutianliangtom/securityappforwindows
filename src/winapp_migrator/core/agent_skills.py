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
     "instruction": ("你可以通过截图观察屏幕，用鼠标点击/输入文本完成用户请求。标准流程：\n"
                     "1. 任务开始先截图观察当前屏幕环境，并用 get_screen_size 确认分辨率。\n"
                     "2. 每步操作前用一句话说明意图。\n"
                     "3. 坐标必须基于最近截图换算像素位置，禁止凭空估计。\n"
                     "4. 操作后立即截图验证结果：目标出现才继续；失败则分析截图差异、修正坐标/方案重试。\n"
                     "5. 全部完成截图确认最终结果。")},
    {"name": "complex-task", "description": "复杂任务：拆解为步骤清单，逐步执行并验证",
     "instruction": ("1. 把复杂任务拆解为可独立验证的步骤清单，按依赖顺序排列，先输出计划再动手。\n"
                     "2. 每步执行前说明意图；执行后截图/读取结果验证，成功才进入下一步。\n"
                     "3. 步骤失败时先自查原因（截图差异、坐标偏移、路径错误、名称不符），"
                     "换方案重试（最多 2 次），仍失败用 ask_user 向用户求助，禁止盲目重复。\n"
                     "4. 需要定位应用/文件时先用 find_app / search_files；信息不足用 ask_user 澄清。\n"
                     "5. 步骤多时每完成一个阶段用 save_memory 保存进度，上下文被压缩后先 load_memory 恢复。\n"
                     "6. 全部完成后输出总结：完成项、最终结果、关键产出位置。")},
    {"name": "brainstorming", "description": "头脑风暴：先理清需求，再制定计划并交用户审核",
     "instruction": ("1. 先用 ask_user 依次澄清需求：目标、范围、约束、输入/输出与验收标准，"
                     "直到需求完全明确（禁止在信息不足时猜测执行）。\n"
                     "2. 需求明确后进入方案设计：提出 2-3 个可行方案并对比优缺点、成本与风险，"
                     "用 ask_user 征询用户选择。\n"
                     "3. 方案确认后，按 writing-plans 技能的流程制定详细执行计划："
                     "把任务拆解为可独立验证的小步骤，每步写明目标与验证方式。\n"
                     "4. 将完整计划作为文档输出（文字/列表，或 write_file 写入计划文件），"
                     "并请用户审核：确认计划、或提出修改与补充意见。\n"
                     "5. 用户审核通过后才开始执行；执行中每步完成后验证再继续，任何变更先与用户确认。")},
    {"name": "writing-plans", "description": "为多步骤任务制定详细执行计划",
     "instruction": ("1. 把任务拆解为可独立执行的小步骤，每步写明目标、动作与验证方式，按依赖顺序排列。\n"
                     "2. 将完整计划作为文档输出（文字/列表，或 write_file 写入计划文件），"
                     "并请用户审核确认后再执行。\n"
                     "3. 按计划逐步执行，每步完成后截图或读取结果验证再继续；计划变更先与用户确认。")},
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
    {"name": "skill-create", "description": "技能创建：根据用户自然语言描述自动生成市场标准 SKILL.md 技能并加载",
     "instruction": ("1. 倾听用户对技能的描述，提炼出：技能名（英文，字母/数字/下划线/连字符，≤50 字符）、"
                     "一句话用途简介、执行流程正文。\n"
                     "2. 用 create_skill 工具创建：instruction 写清触发条件、执行步骤与规则（markdown）。\n"
                     "3. 创建成功后提示：已可通过 /技能名 或对话描述调用；若用户描述的是可复用的流程，适合沉淀为技能。")},
]

DEFAULT_AGENTS = [
    {"name": "zhuzhu Copilot", "description": "zhuzhu Copilot：观察屏幕并操控电脑高质量完成任务",
     "persona": "你是 zhuzhu Copilot，运行在 Windows 上的桌面 AI 助手，性格谨慎可靠、注重安全，"
                "擅长把复杂任务拆解为可验证的小步骤，每步先想清楚后果再动手，"
                "操作后必截图验证，失败时先自查再换方案，直到任务高质量完成。",
     "rules": [
         "1. 复杂任务先拆解为步骤清单，按依赖顺序执行，每步完成后截图验证再进入下一步。",
         "2. 每次操作前用一句话说明意图（会弹窗由用户确认）。",
         "3. 操作后先截图验证结果：目标出现才继续；失败则读截图分析原因并换方案重试，禁止盲目重复。",
         "4. 截图已统一缩放到宽 1280px 并叠加红色网格与像素刻度（X 轴顶部黄色数字、"
         "Y 轴左侧青色数字，每 2 格标注一个，数字即该线处的图像像素值）。"
         "截图上另有红色准星=当前鼠标位置（标注物理坐标 cursor(x,y)）。"
         "图标目标用准星对齐：move_mouse 移动鼠标 → 截图看准星是否套住目标 → "
         "未对准按准星与目标的偏移修正坐标，对准后 click（坐标=鼠标当前位置），一次点准；"
         "禁止用屏幕分辨率做任何换算（系统会自动换算到真实屏幕坐标）。",
         "5. 打开应用前先用 find_app 精确定位可执行路径，避免猜错名称；找不到时用 search_files 兜底。",
         "6. 文件操作（查找/创建/修改/删除/读取）优先在工作目录内执行：用户设置了工作目录时，"
         "未指定完整路径默认在工作目录内执行，相对路径也基于工作目录解析；同时避开系统关键目录"
         "（Windows、Program Files 等），删除系统关键目录内容会被沙盒拒绝。",
         "6.1 涉及具体窗口的任务（浏览器/编辑器/对话框等）先 list_windows 找到目标窗口，"
         "再用 capture_window 只截该窗口（避开其他窗口干扰），在窗口截图内用 click 按刻度点击（坐标自动换算）。",
         "7. 用户需求不明确、缺少关键信息（目标文件/目标对象/期望结果）时，"
         "必须先调用 ask_user 提问，严禁猜测执行。",
         "8. 完成任务后总结：做了什么、结果如何、关键输出在哪，不要做多余操作。",
         "9. 精确点击：目标是按钮/菜单/对话框等**文字类元素**时，优先用 click_text"
         "按文字精确定位（系统 UIA+OCR 自动找文字像素中心，无需自己估算坐标）；"
         "纯图标/图形无文字时，用准星对齐法（见规则 4）：先 move_mouse 粗定位，"
         "截图看准星，未对准修正坐标再 move_mouse，对准后 click。"
         "目标小看不清时先 zoom_in 放大再对齐，未命中修正重试。",
         "10. 点击后截图验证：未命中时根据截图里准星与目标的视觉偏移修正坐标重试"
         "（最多 2 次），禁止盲目重复点击。",
         "11. 长/复杂任务管理：任务步骤多时，先输出执行计划再动手；"
         "每完成一个阶段用 save_memory 保存进度与关键状态（已完成/下一步）；"
         "上下文被自动压缩后，先用 load_memory 恢复任务目标与进度，避免遗忘开头。",
         "12. 失败纠错：工具调用失败（超时/未找到/被拒绝）时，"
         "先读截图分析原因（目标不在屏幕/坐标偏移/弹窗未展开/参数错误），"
         "再换方案重试（文字→click_text，图标→准星对齐，看不清→zoom_in，仍不明→ask_user）；"
         "同一操作最多重试 2 次，之后必须换方案或问用户，禁止无脑循环。",
     ],
     "tool_instructions": {
         "screenshot": {
             "理解": "截取当前整个屏幕（AI 视觉模型直接看到截图），同时返回屏幕上的文字元素清单"
                    "（如「确定」@(100,50)），这些坐标是 UIA/OCR 精确定位的像素坐标，可据此用 click_text 点击。"
                    "截图上的红色准星=当前鼠标位置（标注 cursor(物理x,物理y)），用于图标目标的对齐。",
             "执行拆分": ["任务开始先截图观察当前屏幕环境并获取文字元素清单",
                          "操作后立即截图验证结果是否生效",
                          "截图内容与目标不符时，分析差异并调整方案"],
         },
         "get_screen_size": {
             "理解": "获取屏幕分辨率，供模型了解显示范围。",
             "执行拆分": ["操作前先获取分辨率，了解可用屏幕范围"],
         },
         "click_text": {
             "理解": "按文字精确定位点击：输入目标文字（如 确定/开始/菜单项），系统用 UIA+OCR 找到该文字像素中心并点击，像素级精确。"
                    "复杂页面优先用它：弹窗/下拉菜单/深层页面里的按钮都有文字，先展开再按文字点，比盲猜坐标可靠。",
             "执行拆分": ["判断目标是否有可见文字，有则传该文字给 click_text",
                          "目标在弹窗/菜单里时，先点击展开（点入口菜单项），再对目标文字 click_text",
                          "点击后截图验证目标是否被正确触发",
                          "未找到文字或点击未生效时，换 click 准星对齐"],
         },
         "click": {
             "理解": "在指定像素坐标点击鼠标。**图标/图形目标用准星对齐法**：先 move_mouse 把鼠标移到目标附近"
                    "（可先用截图网格刻度粗读数），再截图看红色准星=鼠标位置是否套住目标；"
                    "未对准则按准星与目标的偏移修正坐标再次 move_mouse，对准后调用 click（坐标=鼠标当前位置）一次点准。"
                    "文字类目标优先用 click_text。",
             "执行拆分": ["先 move_mouse 粗定位，截图看准星是否套住目标",
                          "未对准：看准星相对目标往哪个方向偏了多少，修正坐标再 move_mouse，重复直到套住",
                          "对准后 click（坐标=鼠标当前位置），点击后截图验证",
                          "未触发时按准星偏移继续修正（最多 2 次）"],
         },
         "type_text": {
             "理解": "向当前焦点窗口输入文本（支持中文），可含 enter/tab 等特殊键。",
             "执行拆分": ["确保目标输入框已获得焦点（先点击再输入）",
                          "输入后截图验证内容正确",
                          "需换行/提交时用 enter"],
         },
         "find_app": {
             "理解": "秒查已安装应用路径（开始菜单/桌面/注册表，带缓存），返回可启动的完整路径候选。",
             "执行拆分": ["打开应用前先精确查找可执行路径",
                          "候选多时选择最匹配用户意图的一个"],
         },
         "run_command": {
             "理解": "在系统终端执行命令（受沙盒约束）。默认等待 wait 秒（默认5）；超时未结束且 force_quit=true 则强制结束，否则转入后台运行，用 check_command 轮询进度。",
             "执行拆分": ["分析命令安全性（删除/格式化/关机等一律拒绝）",
                          "长任务自主决定 wait/force_quit：预计挂起或无输出则 force_quit=true，需要看进度则 false+check_command 轮询",
                          "说明意图并等待确认",
                          "执行并读取输出",
                          "截图验证屏幕变化"],
         },
         "check_command": {
             "理解": "轮询后台运行命令（run_command 转入后台的）的进度与最新输出。",
             "执行拆分": ["上一步 run_command 返回了后台命令 ID 时，用 check_command 持续轮询直到结束",
                          "不传 cmd_id 可先列出全部后台命令"],
         },
         "write_file": {
             "理解": "创建或覆盖写入文本文件（相对路径基于工作目录；删除系统关键目录仍被沙盒拒绝）。",
             "执行拆分": ["确认目标路径合法（禁止删除系统关键目录）",
                          "说明写入目标文件并等待确认",
                          "执行写入",
                          "截图或读取文件确认结果"],
         },
         "read_file": {
             "理解": "读取文本文件内容（相对路径基于工作目录）。",
             "执行拆分": ["确认目标路径合法",
                          "读取文件",
                          "向用户摘要关键内容"],
         },
         "delete_file": {
             "理解": "删除文件或空目录（相对路径基于工作目录；删除系统关键目录内容被沙盒拒绝，非空目录用 run_command）。",
             "执行拆分": ["确认要删除的对象与路径无误",
                          "删除文件/空目录",
                          "确认删除结果"],
         },
         "list_windows": {
             "理解": "枚举当前可见窗口（标题+编号）。涉及具体窗口的任务（浏览器/编辑器/对话框等）先调用它确认目标窗口，避免全屏截图中其他窗口干扰。",
             "执行拆分": ["任务涉及特定窗口时先 list_windows 找到目标窗口",
                          "根据标题判断哪个窗口是用户目标"],
         },
         "capture_window": {
             "理解": "截取指定窗口（只截该窗口，避开其他窗口遮挡/干扰），返回窗口截图与窗口内文字元素清单。"
                    "窗口图带坐标刻度，后续 click 的窗口内读数会自动换算回屏幕坐标，无需自己换算。",
             "执行拆分": ["先用 list_windows 拿到目标窗口（标题或编号），再 capture_window",
                          "在窗口截图内观察/定位目标元素",
                          "用 click 按窗口图刻度点击（坐标自动换算），点击后截图验证"],
         },
     },
     "system_prompt": ("你是 zhuzhu Copilot，桌面自动化助手。通过截图观察屏幕，使用工具（移动/点击鼠标、"
                        "输入文本、执行白名单命令、读写文件、管理记忆）帮用户完成任务。\n"
                        "高质量完成任务的方法论：\n"
                        "1. 任务开始先截图观察环境，用 get_screen_size 确认分辨率。\n"
                        "2. 复杂任务拆解为步骤清单，逐步执行、逐步验证。\n"
                        "3. 每步操作后立即截图验证：成功才继续，失败先分析原因再换方案重试。\n"
                        "4. 打开应用先 find_app 定位路径；找不到目标用 search_files 兜底。"
                        "文件操作（查找/创建/修改/删除/读取）优先在工作目录内执行："
                        "设置了工作目录时，未指定完整路径默认在工作目录内，相对路径基于工作目录解析。\n"
                        "4.1 涉及具体窗口的任务：先 list_windows 找到目标窗口，"
                        "再 capture_window 只截该窗口（避开其他窗口干扰），在窗口截图内用 click 按刻度点击（坐标自动换算）。\n"
                        "5. 精确点击（按优先级）："
                        "① 目标有可见文字（按钮/菜单/输入框/对话框）→ 用 click_text 按文字定位，"
                        "系统 UIA+OCR 自动找文字像素中心，像素级精确，无需自己给坐标；"
                        "② 图标/图形目标 → 用「准星对齐法」：先 move_mouse 把鼠标移到目标附近"
                        "（可先按截图网格刻度粗读数），再截图查看红色准星=当前鼠标位置（标注物理坐标）；"
                        "若准星未套住目标，根据准星与目标的视觉偏移修正坐标再次 move_mouse，"
                        "直到准星对准目标后再调用 click（坐标=鼠标当前位置），一次点准；"
                        "③ 目标太小看不清 → 先 zoom_in 放大目标区域，再按放大图重复准星对齐。"
                        "点击后截图验证，未命中用准星偏移修正重试（最多 2 次）。\n"
                        "6. 全部完成后向用户总结结果。"),
     "skills": ["screen_operate", "complex-task"], "tools": []},
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


def _skills_dir() -> Path:
    """市场标准技能目录：~/.winapp_migrator/agent/skills/<name>/SKILL.md"""
    return CONFIG_DIR / "skills"


def _parse_skill_md(text: str) -> dict:
    """解析 SKILL.md：--- frontmatter（name/description）--- + 正文 instruction

    市场标准格式（Claude Skills / Trae Skill）。无 frontmatter 时仅返回正文。
    """
    s = (text or "").strip()
    if not s:
        return {}
    name = desc = ""
    body = s
    if s.startswith("---"):
        end = s.find("\n---", 3)
        if end > 0:
            fm = s[3:end].strip()
            body = s[end + 4:].strip()
            for line in fm.splitlines():
                line = line.strip()
                if line.startswith("name:"):
                    name = line[len("name:"):].strip().strip("\"'")
                elif line.startswith("description:"):
                    desc = line[len("description:"):].strip().strip("\"'")
    if not body:
        return {}
    return {"name": name, "description": desc, "instruction": body}


def load_md_skills() -> list:
    """扫描市场标准技能目录，返回 [{name,description,instruction,source:'md'}]"""
    out = []
    try:
        root = _skills_dir()
        if not root.is_dir():
            return out
        for d in sorted(root.iterdir()):
            f = d / "SKILL.md"
            if not d.is_dir() or not f.is_file():
                continue
            s = _parse_skill_md(f.read_text(encoding="utf-8", errors="replace"))
            if s:
                s["source"] = "md"
                out.append(s)
    except Exception:
        pass
    return out


def create_md_skill(name: str, description: str, instruction: str) -> tuple:
    """以用户自然语言描述为基础，生成市场标准 SKILL.md 技能并注册。

    返回 (ok: bool, message: str)。生成后 load_skills 立即加载生效。
    """
    import re
    name = (name or "").strip()
    if not name:
        return False, "技能名不能为空"
    if not re.match(r"^[A-Za-z0-9_-]{1,50}$", name):
        return False, "技能名仅支持字母/数字/下划线/连字符（≤50 字符）"
    description = (description or "").strip() or name
    instruction = (instruction or "").strip()
    if not instruction:
        return False, "技能说明（instruction）不能为空"
    try:
        d = _skills_dir() / name
        d.mkdir(parents=True, exist_ok=True)
        md = (f"---\nname: {name}\ndescription: {description}\n---\n\n"
              f"{instruction}\n")
        (d / "SKILL.md").write_text(md, encoding="utf-8")
        return True, f"已创建技能「{name}」（{d / 'SKILL.md'}），已加载生效"
    except OSError as e:
        return False, f"创建技能失败: {e}"


def import_skill_file(path: str) -> tuple:
    """导入市场标准技能：SKILL.md 单文件 或 含 SKILL.md 的 zip 包。

    单文件 → 复制为 skills/<name>/SKILL.md（name 取 frontmatter 或文件名）；
    zip → 按包内目录解压到 skills/（含 resources 等附属文件），
    防止路径穿越。返回 (ok, message)；导入后 load_skills 立即生效。
    """
    import re as _re
    import zipfile
    p = Path(path or "")
    if not p.is_file():
        return False, "文件不存在"
    try:
        if p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as z:
                md_entries = [i for i in z.infolist()
                              if not i.is_dir()
                              and i.filename.replace("\\", "/").endswith("SKILL.md")]
                if not md_entries:
                    return False, "压缩包内未找到 SKILL.md"
                root = _skills_dir()
                root.mkdir(parents=True, exist_ok=True)
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    rel = info.filename.replace("\\", "/")
                    if rel.startswith("/") or ".." in rel.split("/"):
                        return False, "压缩包内含非法路径（拒绝导入）"
                    target = (root / rel).resolve()
                    if not str(target).startswith(str(root.resolve())):
                        return False, "压缩包内含越界路径（拒绝导入）"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(info))
            md_path = root / md_entries[0].filename.replace("\\", "/")
        else:
            text = p.read_text(encoding="utf-8", errors="replace")
            name = (_parse_skill_md(text).get("name") or "").strip() or p.stem.strip()
            if not _re.match(r"^[A-Za-z0-9_-]{1,50}$", name):
                return False, "技能名仅支持字母/数字/下划线/连字符（≤50 字符）"
            md_path = _skills_dir() / name / "SKILL.md"
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(text, encoding="utf-8")
        s = _parse_skill_md(md_path.read_text(encoding="utf-8", errors="replace"))
        if not s:
            return False, "SKILL.md 内容为空或格式不正确"
        return True, f"已导入技能「{s.get('name') or md_path.parent.name}」并即时生效"
    except OSError as e:
        return False, f"导入失败: {e}"


def load_skills() -> list:
    """全部技能：内置 skills.json + 内置核心技能兜底 + 市场标准 md 技能（skills/<name>/SKILL.md）

    md 技能与 JSON 同名时以 JSON 为准（JSON 优先）。每次调用实时扫描，新增 md 技能即时生效。
    """
    merged = list(_load("skills.json", DEFAULT_SKILLS))
    seen = {s.get("name") for s in merged if s.get("name")}
    # 内置核心技能兜底：缺失时补充（保证 skill-create 等始终可用）
    for s in DEFAULT_SKILLS:
        if s.get("name") and s.get("name") not in seen:
            merged.append(s)
            seen.add(s.get("name"))
    for s in load_md_skills():
        if s.get("name") and s.get("name") not in seen:
            merged.append(s)
    return merged


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


def load_settings() -> dict:
    """加载用户设置 settings.json：
    custom_rules(规则数组) / custom_system_prompt(提示词补充) /
    custom_safe_commands(bash 白名单) / memory_enabled(记忆开关) /
    model({base_url, api_key, model})
    """
    path = CONFIG_DIR / "settings.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(s: dict) -> bool:
    """写入用户设置 settings.json"""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_DIR / "settings.json", "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
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


def build_system_prompt(agent_name: str = "", extra_skills: list = None,
                        text_only: bool = False, memory_enabled: bool = True) -> str:
    """构造 system prompt：人设 persona + 基础提示 + 严格规则 + 工具执行规范 + 技能说明 + 工具列表

    extra_skills: 手动调用的技能名列表（/技能名 提示），其 instruction 注入本任务系统提示词。
    text_only: 纯文本模型（无视觉输入），追加禁用截图/视觉引导。
    memory_enabled: 记忆开关，关闭时追加禁用记忆工具引导。
    自定义规则 / 自定义系统提示词从 settings.json 读取并追加。
    """
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

    skills = list(agent.get("skills", [])) + list(extra_skills or [])
    if skills:
        inst = skill_instructions(skills)
        if inst:
            prompt += "\n\n" + inst
    if extra_skills:
        prompt += ("\n\n本次任务要求严格按上述指定技能（/技能名 手动调用）的流程执行，"
                   "先按其 instruction 组织步骤再行动。")
    prompt += ("\n\n可用内置工具：screenshot(截屏观察)、list_windows/capture_window(枚举并只截指定窗口，"
               "避免其他窗口干扰)、get_screen_size(分辨率)、"
               "ask_user(需求不明确时向用户提问)、"
               "find_app(秒查已安装应用路径)、search_files(工作目录内快速查找文件，未设工作目录则搜用户常用目录)、"
               "move_mouse/click/drag/scroll(鼠标)、press_key/type_text(键盘)、"
               "run_command(执行命令，可设 wait/force_quit，长任务用 check_command 轮询进度)、"
               "read_file/write_file/edit_file/delete_file/list_directory(文件读写改删列，相对路径基于工作目录)、"
               "save_memory/load_memory(本地长期记忆)。"
               "若连接了 MCP 服务器，其工具同样可用。")
    prompt += ("\n\n提问机制：当用户需求不明确、缺少关键信息时，必须先调用 ask_user 向用户提问。"
               "提问时尽量给出 options 建议选项方便用户直接点选；"
               "需要用户从多个候选中挑选（可多项）时，设置 multi_select=true 以多选问答方式让用户复选；"
               "获得明确回答后再继续执行；严禁在信息不足时猜测执行。")
    prompt += ("\n\n记忆：你有本地长期记忆文件 memory.md。遇到用户偏好、重要结论、约定、常用路径等"
               "值得长期记住的信息时，调用 save_memory 保存；新任务开始或需要回忆过往信息时，"
               "自行决定是否调用 load_memory 查看。")
    if text_only:
        prompt += ("\n\n当前为纯文本模型（不支持图像输入）：禁止调用任何截图/窗口截图/视觉定位相关工具"
                   "（screenshot、capture_window、capture_zoom 等），本环境不会提供图像。"
                   "请通过文本工具（read_file、run_command、list_directory 等）完成用户请求。")
    if not memory_enabled:
        prompt += "\n\n当前未开启记忆功能：不要调用 save_memory / load_memory。"
    settings = load_settings()
    rules = settings.get("custom_rules") or []
    valid = [str(r).strip() for r in rules if str(r).strip()]
    if valid:
        rules_path = CONFIG_DIR / "settings.json"
        prompt += (f"\n\n用户自定义开发规则（每次执行操作前必须查看并严格遵守，"
                   f"原始文件：{rules_path}）：\n"
                   + "\n".join(f"- {r}" for r in valid))
        prompt += (f"\n当用户询问开发规则/项目规则/我们的规则等内容时，"
                   f"必须调用 read_file 工具读取 {rules_path} 的 custom_rules 字段，"
                   f"原样逐条如实回答；严禁凭记忆、猜测或编造规则内容。")
    extra_prompt = (settings.get("custom_system_prompt") or "").strip()
    if extra_prompt:
        prompt += "\n\n用户自定义系统提示词补充：\n" + extra_prompt
    return prompt
