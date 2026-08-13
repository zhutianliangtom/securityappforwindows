"""skills / agents / MCP 服务器配置：JSON 文件加载（启动时读取，可热改）

技能已统一为市场标准 md 格式（~/.winapp_migrator/agent/skills/<name>/SKILL.md），
skills.json 仅保留用户自建的非内置 JSON 技能（内置旧 JSON 条目加载时自动迁移移除）。
配置目录：~/.winapp_migrator/agent/
- skills.json      用户自建技能（可选）：[{"name","description","instruction"}]
- agents.json      助手：[{"name","description","persona","rules","tool_instructions","system_prompt","skills":[],"tools":[]}]
                    persona: 人设描述；rules: 规则约束数组；tool_instructions: {工具名: {"理解": str, "执行拆分": [str]}}
- mcp_servers.json MCP：[{"name","type":"stdio|sse","command","args"|"url"}]
目录/文件不存在时使用内置默认值，首次运行自动生成示例文件。
"""

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

CONFIG_DIR = Path.home() / ".winapp_migrator" / "agent"

# 技能体系统一为市场标准 md 格式（SKILL.md），JSON 技能已废弃：
# 原 JSON 技能（screen_operate/complex-task/brainstorming/writing-plans/
# test-driven-development/systematic-debugging/skill-create）已迁移至
# _BUILTIN_MD_SKILLS 内置 md 模板；code-review 由随包技能提供（见 skills/）。
# 保留空列表仅为兼容 _ensure_samples / load_skills 的兜底逻辑。
DEFAULT_SKILLS = []

# 内置 md 技能模板：首次运行时自动生成到 skills/<name>/SKILL.md（市场标准格式，以 SKILL.md 为核心）。
# 不加入 DEFAULT_SKILLS（JSON 优先会覆盖 md 版，导致用户编辑 SKILL.md 不生效）。
_BUILTIN_MD_SKILLS = {
    "download-skill": {
        "description": "技能下载安装：在 GitHub 上搜索市场标准 SKILL.md 技能，下载并导入本地配置生效",
        "instruction": """# download-skill：GitHub 技能搜索、下载与导入

当用户要求"下载 / 安装 / 寻找某个 skill（技能）"时，按以下流程执行。

## 1. 确认需求
用 ask_user 与用户确认：技能名称/关键词、用途、是否有已知 GitHub 仓库地址。
信息不足时禁止猜测，先问清楚。

## 2. 在 GitHub 上定位技能
候选仓库判断标准：仓库根目录或 skills/ 子目录存在 SKILL.md（含 --- name / description --- frontmatter）。
- 用户提供仓库地址：先 run_command 执行 `git ls-remote <仓库地址>` 验证仓库可访问；
- 用户只给名称/关键词：依次探测常用市场仓库（git ls-remote 验证存在后浅克隆）：
  - https://github.com/anthropics/skills
  - https://github.com/anthropics/claude-code
  - 其他含 SKILL.md 的 skills 聚合仓库
  找不到时用 ask_user 请用户提供具体仓库地址，不要编造 URL。
- 用 `git clone --depth 1 <仓库> <临时目录>` 浅克隆后，用 list_directory / read_file
  在仓库内查找 SKILL.md，读取 frontmatter 确认技能 name 与 description 是否匹配用户需求。

## 3. 下载前确认（强制）
用 ask_user 向用户展示以下信息并征得同意：
- 仓库地址
- 技能名与 description
- SKILL.md 内容摘要（前若干行）
用户确认后才下载；用户拒绝则停止并说明。

## 4. 下载
- 整仓浅克隆：git clone --depth 1 <仓库> <临时目录>（临时目录建议 %TEMP% 下）
- 有 zip 或 raw 文件直链：用 fast_download 工具下载到本地
- 单文件：下载 SKILL.md 的 raw 内容

## 5. 导入本地并配置
- 目标目录：~/.winapp_migrator/agent/skills/<技能名>/SKILL.md
- 用 import_skill_file 导入（支持 SKILL.md 单文件或含 SKILL.md 的 zip），
  或把下载到的 SKILL.md 复制到目标目录
- 验证：read_file 确认 SKILL.md 已写入目标位置；技能系统实时扫描，导入后立即可用

## 6. 汇报
输出总结：技能名、来源仓库、安装路径、调用方式（/技能名 或自然语言描述）。""",
    },
    "doc-gen": {
        "description": "文档生成：用 create_docx/create_pptx/create_xlsx 自动生成 Word/PPT/Excel，配合 extract_text 验证内容",
        "instruction": """# doc-gen：Word / PPT / Excel 文档自动生成

当用户要求"做一份文档 / 生成 PPT / 整理成 Excel 表格"时使用本技能。

## 1. 确认需求
先问清：文档主题与内容要点、保存路径、格式（docx/pptx/xlsx）。
内容信息不足时用 ask_user 补齐，禁止编造数据。

## 2. 生成（已内置商务专业风美化，无需传样式参数）
- Word（create_docx）：path=保存路径，title=文档标题，paragraphs=[段落文本列表]
  段落支持轻量标记增强结构：'# ' 一级标题、'## ' 二级标题、'- ' 项目符号，其余为正文。
  标题建议用标记分层（如 '# 一、概述' / '## 1.1 现状'），正文直接写内容。
- PPT（create_pptx）：path，title=总标题，slides=[{title: 页标题, bullets: [要点列表]}]
  自动生成 16:9 标题页（深蓝底白字）；每页为"深蓝标题+分隔线+要点"，每页要点建议 3-6 条。
- Excel（create_xlsx）：path，sheets=[{name: 工作表名, rows: [[单元格值]...]}]
  首行自动作深蓝表头并冻结；纯数字字符串自动转数值，无需引号包裹数字。

## 3. 验证（必做）
生成后用 extract_text(path) 读取文件，确认标题、正文、中文、表格数据均正确。

## 4. 汇报
输出：文件路径、包含的章节/工作表、内容摘要。""",
    },
    "web-search": {
        "description": "联网搜索：web_search 搜索实时信息（新闻/文档/教程/代码），web_fetch 抓取网页或调用 API 接口",
        "instruction": """# web-search：联网搜索与网页抓取

当需要查询实时信息、查找资料、调用网络接口时使用本技能。

## 1. 搜索
web_search(query=搜索关键词, max_results=返回条数)：
- 适合：新闻、文档、教程、代码示例、产品信息等实时内容
- 返回标题+URL+摘要，先读摘要判断相关性，再决定是否抓详情

## 2. 抓取详情
web_fetch(url=地址)，默认 GET；
- 调用 API：method=POST/PUT/DELETE，headers 传鉴权头（如 {"Authorization": "Bearer xxx"}），
  body 传请求体（JSON 字符串或原始文本）
- 响应过长会截断，可指定 max_chars 调整

## 3. 信息不足时
换关键词重搜或用 ask_user 向用户确认方向，禁止编造内容与链接。

## 4. 汇报
给出结论并附来源 URL。""",
    },
    "file-ops": {
        "description": "文件操作：read_file/write_file/edit_file/delete_file/list_directory 读写改删列文件，search_files 模糊查找",
        "instruction": """# file-ops：文件读写改删与查找

当需要读取、创建、修改、删除文件或查找文件时使用本技能。

## 1. 定位
- 知道路径：直接用 read_file / write_file / edit_file / delete_file / list_directory
  （相对路径基于工作目录，未设工作目录则基于用户目录）
- 不知道路径：search_files(query=文件名关键字, folder=限定目录可选) 模糊查找

## 2. 操作要点
- 读：read_file(path)，大文件分段读取
- 写：write_file(path, content)，会覆盖已存在文件，写前先确认目标
- 改：edit_file(path, old_text, new_text)，只替换首次匹配，old_text 需在文件中唯一
- 删：delete_file(path)
- 列目录：list_directory(path)

## 3. 注意事项
- 修改前先 read_file 了解原文，避免改错
- 系统关键目录（Windows、Program Files 等）的删除会被沙盒拒绝
- 操作后建议 read_file 验证结果""",
    },
    "system-admin": {
        "description": "系统管理：find_app 定位应用、system_info/get_time/env_var 查系统信息、optimize_memory 清理内存、uninstall_app 卸载、migrate_app 迁移应用",
        "instruction": """# system-admin：系统信息查询与应用管理

当需要查询系统信息、定位应用、清理内存、卸载或迁移应用时使用本技能。

## 1. 查询类（无副作用）
- system_info：主机名/系统版本/CPU 核心数/物理内存
- get_time：当前时间
- env_var(name)：读取环境变量

## 2. 定位应用
find_app(query=应用名)：秒查已安装应用的可启动路径，比逐层截图找图标高效。

## 3. 重量级操作（工具内部会弹用户确认）
- optimize_memory：清理内存（终止可安全退出的后台进程、压缩工作集）
- uninstall_app(name)：卸载应用（先调自带卸载器再清理残留）
- migrate_app(name, target)：把应用迁移到其他盘
先向用户说明影响，确认后再执行；完成后汇报结果。""",
    },
    "ui-automation": {
        "description": "界面自动化：screenshot 截图观察、click_text 按文字点击、move_mouse/click/zoom_in 精确鼠标操作、type_text/press_key 键盘输入、list_windows/capture_window 只截指定窗口、clipboard 剪贴板",
        "instruction": """# ui-automation：屏幕观察与鼠标键盘操控

当需要操作界面、点击按钮、输入文字、观察屏幕时使用本技能。

## 1. 观察
- 需要了解当前界面时先 screenshot 截屏观察
- 只操作某个窗口时：list_windows 找到目标窗口 → capture_window(window) 只截该窗口，避开其他窗口干扰

## 2. 点击（按优先级）
- 文字类目标（按钮/菜单/输入框）：click_text(text)，系统 UIA+OCR 自动定位文字像素中心，无需自己估算坐标
- 图标/图形目标：move_mouse 移动 → 截图看红色准星是否套住目标 → 未对准按偏移修正坐标 → 对准后 click
- 目标太小：zoom_in(x, y) 放大后按细刻度读数，再以该坐标 click（系统自动换算）

## 3. 输入
- 键盘：press_key(键)；输入文本：type_text(text)
- 剪贴板：clipboard(action=write, text) 写入，clipboard(action=read) 读取

## 4. 原则
- 操作结果不确定时截图验证；失败先自查再换方案，禁止盲目重复点击
- 系统会自动把截图坐标换算为真实屏幕坐标，不要手动换算""",
    },
    "cmd-ops": {
        "description": "命令执行与下载：run_command 执行命令（含白名单/沙盒约束）、check_command 轮询后台命令、fast_download 高速下载文件",
        "instruction": """# cmd-ops：命令执行、轮询与下载

当需要在终端执行命令、下载文件时使用本技能。

## 1. 执行命令
run_command(command=命令, wait=等待秒数默认5, force_quit=是否超时强杀)：
- 危险命令（删除/格式化/关机等）会被沙盒拒绝，先想清楚再执行
- 短命令：默认 wait=5 等输出；启动 GUI 应用建议 wait=1
- 长任务：wait 秒内未完成且 force_quit=false 会转入后台，返回命令 ID
- 预计长时间挂起/无输出的命令：force_quit=true 防阻塞

## 2. 轮询后台命令
check_command(cmd_id=命令ID) 查询进度与最新输出；不传 cmd_id 列出全部后台命令。

## 3. 下载文件
fast_download(url=下载地址, dest_dir=保存目录留空用工作目录)：多段并发高速下载，自动探测文件名，支持断点续传。

## 4. 汇报
输出：命令执行结果/退出码、下载的文件路径。""",
    },
    "memory": {
        "description": "长期记忆：save_memory 追加保存用户偏好/重要结论/约定/路径到本地记忆，load_memory 读取全部记忆",
        "instruction": """# memory：本地长期记忆

当需要记住跨任务信息或回忆过往内容时使用本技能。

## 1. 保存（主动）
遇到值得长期记住的信息时调用 save_memory(content=内容)：
- 用户偏好、习惯、语言要求
- 重要结论、决策、约定
- 常用路径、工作目录、文件位置
每条自动带时间戳追加，单条 ≤8000 字符，不会覆盖旧记录。

## 2. 读取
load_memory() 读取本地记忆文件 memory.md 全部内容。
新任务开始、或需要回忆过往信息时自行决定是否调用。

## 3. 原则
- 只存真正长期有价值的信息，临时性内容不必存
- 每次任务结束前回顾是否有值得保存的内容""",
    },
    "sub-agent": {
        "description": "子任务调度：dispatch_sub_agents 并行派发互不依赖的子任务、explore_project 快速了解新项目、search_large 大规模跨目录搜索",
        "instruction": """# sub-agent：子任务并行调度与大规模搜索

当任务包含多个互不依赖的子任务、需要快速了解项目、或搜索范围很大时使用本技能。

## 1. 并行派发
dispatch_sub_agents(tasks=[{title: 标题, goal: 目标与要求}]):
- 适合：大规模读取/搜索/探索、多文件并行处理
- 子任务 1-8 个，每个 goal 写清"要做什么、输出什么"
- 子 Agent 可读写文件但不能执行命令；执行类工作留在主 Agent

## 2. 了解新项目
explore_project(directory=项目目录)：生成目录结构、读 README 与关键入口，
输出项目概览（用途/技术栈/模块结构/入口/构建方式）。接手新项目先用它。

## 3. 大规模搜索
search_large(query=关键词, directories=目录列表可选, max_results=条数)：
跨目录多轮搜索并汇总命中，适合范围大、文件多的场景；
小范围/单文件查找用 search_files 更轻量。

## 4. 汇报
汇总各子任务结果、项目概览或搜索命中清单。""",
    },
    "skill-mgmt": {
        "description": "技能创建：create_skill 根据用户自然语言描述自动生成市场标准 SKILL.md 技能并立即加载生效",
        "instruction": """# skill-mgmt：创建新技能

当用户要求"创建一个技能 / 把某个能力做成 skill"时使用本技能。

## 1. 确认需求
用 ask_user 问清：技能要做什么（触发场景）、执行流程、注意事项。
信息不足禁止猜测。

## 2. 创建
create_skill(name=技能名, description=用途简介, instruction=执行流程正文)：
- name：仅字母/数字/下划线/连字符，≤50 字符（如 doc-gen）
- instruction：markdown 正文，写清触发条件、分步流程、注意事项
- 生成到 skills/<name>/SKILL.md，创建后立即生效

## 3. 验证与汇报
创建后说明：技能名、调用方式（/技能名 或自然语言描述）、是否已生效。
市场已有同名技能时，建议先询问用户是否仍要创建（避免覆盖）。""",
    },
    # ---- 原 JSON 技能迁移（统一为市场标准 md）----
    "screen_operate": {
        "description": "屏幕操控：截图观察、鼠标点击、键盘输入，坐标基于截图换算",
        "instruction": """# screen_operate：屏幕操控

当需要操作界面、点击按钮、输入文本时使用本技能。

1. 任务开始用 get_screen_size 确认分辨率，需要了解界面时先截图观察当前屏幕环境。
2. 每步操作前用一句话说明意图。
3. 坐标必须基于最近截图换算像素位置，禁止凭空估计。
4. 操作结果不确定时截图验证：目标出现才继续；失败则分析截图差异、修正坐标/方案重试。
5. 全部完成后确认最终结果（需要时截图）。""",
    },
    "complex-task": {
        "description": "复杂任务：拆解为可独立验证的步骤清单，逐步执行并验证",
        "instruction": """# complex-task：复杂任务拆解执行

1. 把复杂任务拆解为可独立验证的步骤清单，按依赖顺序排列，先输出计划再动手。
2. 每步执行前说明意图；执行后确认结果正确（不确定时截图验证），成功才进入下一步。
3. 步骤失败时先自查原因（截图差异、坐标偏移、路径错误、名称不符），
   换方案重试（最多 2 次），仍失败用 ask_user 向用户求助，禁止盲目重复。
4. 需要定位应用/文件时先用 find_app / search_files；信息不足用 ask_user 澄清。
5. 步骤多时每完成一个阶段用 save_memory 保存进度，上下文被压缩后先 load_memory 恢复。
6. 全部完成后输出总结：完成项、最终结果、关键产出位置。""",
    },
    "brainstorming": {
        "description": "头脑风暴：先理清需求，再制定计划并交用户审核",
        "instruction": """# brainstorming：需求澄清与方案计划

当任务目标、范围或验收标准不明确时使用本技能，先想清楚再动手。

1. 先用 ask_user 一次性澄清需求：目标、范围、约束、输入/输出与验收标准
   （合并为一次提问，避免逐项追问）；仍有疑问再做少量补充，禁止编造需求内容。
2. 需求明确后进入方案设计：提出 2-3 个可行方案并对比优缺点、成本与风险，
   用 ask_user 征询用户选择。
3. 方案确认后，按 writing-plans 技能的流程制定详细执行计划：
   把任务拆解为可独立验证的小步骤，每步写明目标与验证方式。
4. 将完整计划作为文档输出（文字/列表，或 write_file 写入计划文件），
   并请用户审核：确认计划、或提出修改与补充意见。
5. 用户审核通过后才开始执行；执行中每步完成后验证再继续，任何变更先与用户确认。""",
    },
    "writing-plans": {
        "description": "为多步骤任务制定详细执行计划，交用户审核后再执行",
        "instruction": """# writing-plans：制定执行计划

1. 把任务拆解为可独立执行的小步骤，每步写明目标、动作与验证方式，按依赖顺序排列。
2. 将完整计划作为文档输出（文字/列表，或 write_file 写入计划文件），
   并请用户审核确认后再执行。
3. 按计划逐步执行，每步完成后确认结果验证再继续；计划变更先与用户确认。""",
    },
    "test-driven-development": {
        "description": "测试驱动开发：先写测试再实现，红-绿-重构循环",
        "instruction": """# test-driven-development：测试驱动开发

1. 先用 write_file 编写针对目标行为的测试用例。
2. 运行测试确认失败（红）。
3. 实现最小可用代码使测试通过（绿），必要时重构（重构）。
4. 重复直到所有用例通过并汇报结果。""",
    },
    "systematic-debugging": {
        "description": "系统化调试：复现问题、假设根因、逐一验证，不靠猜测",
        "instruction": """# systematic-debugging：系统化调试

1. 复现问题并读取相关日志/输出（run_command 或 read_file）。
2. 提出最可能的 2-3 个根因假设，按可能性排序。
3. 逐个用最小实验验证假设，排除一个再验证下一个。
4. 定位根因后修复，再复现验证已解决。""",
    },
    "skill-create": {
        "description": "技能创建：根据用户自然语言描述自动生成市场标准 SKILL.md 技能并加载",
        "instruction": """# skill-create：创建新技能

1. 倾听用户对技能的描述，提炼出：技能名（英文，字母/数字/下划线/连字符，≤50 字符）、
   一句话用途简介、执行流程正文。
2. 用 create_skill 工具创建：instruction 写清触发条件、执行步骤与规则（markdown）。
3. 创建成功后提示：已可通过 /技能名 或对话描述调用；若用户描述的是可复用的流程，适合沉淀为技能。""",
    },
}

DEFAULT_AGENTS = [
    {"name": "zhuzhu Copilot", "description": "zhuzhu Copilot：观察屏幕并操控电脑高质量完成任务",
     "persona": "你是 zhuzhu Copilot，运行在 Windows 上的桌面 AI 助手，性格谨慎可靠、注重安全，"
                "擅长把复杂任务拆解为可验证的小步骤，每步先想清楚后果再动手，"
                "需要确认屏幕状态时调用 screenshot 截图验证，失败时先自查再换方案，直到任务高质量完成。",
     "rules": [
         "1. 复杂任务先拆解为步骤清单，按依赖顺序执行，每步完成后确认结果正确再进入下一步"
         "（需要确认屏幕状态时用 screenshot 截图验证）。",
         "2. 每次操作前用一句话说明意图（会弹窗由用户确认）。",
         "3. 操作结果不确定时截图验证：目标出现才继续；失败则分析原因并换方案重试，禁止盲目重复。",
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
         "7. 用户需求不明确、缺少关键信息时，优先基于上下文合理推断并自主推进；"
         "仅在推断会明显做错方向（目标文件/对象/期望结果不明）、或涉及不可逆/危险操作时，"
         "用 ask_user 一次问清，严禁编造关键信息。",
         "8. 完成任务后总结：做了什么、结果如何、关键输出在哪，不要做多余操作。",
         "9. 精确点击：目标是按钮/菜单/对话框等**文字类元素**时，优先用 click_text"
         "按文字精确定位（系统 UIA+OCR 自动找文字像素中心，无需自己估算坐标）；"
         "纯图标/图形无文字时，用准星对齐法（见规则 4）：先 move_mouse 粗定位，"
         "截图看准星，未对准修正坐标再 move_mouse，对准后 click。"
         "目标小看不清时先 zoom_in 放大再对齐，未命中修正重试。",
         "10. 点击后如结果不确定可截图确认：未命中时根据截图里准星与目标的视觉偏移修正坐标重试"
         "（最多 2 次），禁止盲目重复点击。",
         "11. 长/复杂任务管理：任务步骤多时，先输出执行计划再动手；"
         "每完成一个阶段用 save_memory 保存进度与关键状态（已完成/下一步）；"
         "上下文被自动压缩后，先用 load_memory 恢复任务目标与进度，避免遗忘开头。",
         "12. 失败纠错：工具调用失败（超时/未找到/被拒绝）时，"
         "需要时截图分析原因（目标不在屏幕/坐标偏移/弹窗未展开/参数错误），"
         "再换方案重试（文字→click_text，图标→准星对齐，看不清→zoom_in，仍不明→ask_user）；"
         "同一操作最多重试 2 次，之后必须换方案或问用户，禁止无脑循环。",
     ],
     "tool_instructions": {
         "screenshot": {
             "理解": "截取当前整个屏幕（AI 视觉模型直接看到截图），同时返回屏幕上的文字元素清单"
                    "（如「确定」@(100,50)），这些坐标是 UIA/OCR 精确定位的像素坐标，可据此用 click_text 点击。"
                    "截图上的红色准星=当前鼠标位置（标注 cursor(物理x,物理y)），用于图标目标的对齐。",
             "执行拆分": ["需要了解当前界面/验证结果时截图",
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
                          "点击后结果不确定时截图验证目标是否被正确触发",
                          "未找到文字或点击未生效时，换 click 准星对齐"],
         },
         "click": {
             "理解": "在指定像素坐标点击鼠标。**图标/图形目标用准星对齐法**：先 move_mouse 把鼠标移到目标附近"
                    "（可先用截图网格刻度粗读数），再截图看红色准星=鼠标位置是否套住目标；"
                    "未对准则按准星与目标的偏移修正坐标再次 move_mouse，对准后调用 click（坐标=鼠标当前位置）一次点准。"
                    "文字类目标优先用 click_text。",
             "执行拆分": ["先 move_mouse 粗定位，截图看准星是否套住目标",
                          "未对准：看准星相对目标往哪个方向偏了多少，修正坐标再 move_mouse，重复直到套住",
                          "对准后 click（坐标=鼠标当前位置），点击后按需截图确认",
                          "未触发时按准星偏移继续修正（最多 2 次）"],
         },
         "type_text": {
             "理解": "向当前焦点窗口输入文本（支持中文），可含 enter/tab 等特殊键。",
             "执行拆分": ["确保目标输入框已获得焦点（先点击再输入）",
                          "输入后按需截图确认内容正确",
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
                          "需要时截图确认屏幕变化"],
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
                          "读取文件确认结果"],
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
                          "用 click 按窗口图刻度点击（坐标自动换算），点击后按需截图确认"],
         },
     },
     "system_prompt": ("你是 zhuzhu Copilot，桌面自动化助手。通过截图观察屏幕，使用工具（移动/点击鼠标、"
                        "输入文本、执行白名单命令、读写文件、管理记忆）帮用户完成任务。\n"
                        "高质量完成任务的方法论：\n"
                        "1. 任务开始用 get_screen_size 确认分辨率，需要了解界面时截图观察环境。\n"
                        "2. 复杂任务拆解为步骤清单，逐步执行、逐步验证。\n"
                        "3. 每步操作后确认结果正确再继续（不确定时截图验证）；失败先分析原因再换方案重试。\n"
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
                        "点击后如需确认可截图，未命中用准星偏移修正重试（最多 2 次）。\n"
                        "6. 全部完成后向用户总结结果。"),
     "skills": ["screen_operate", "complex-task"], "tools": []},
]


# 技能加载缓存：输入框 textChanged 等高频路径避免每次全量扫盘。
# 失效依据：skills.json 的 mtime + skills 目录内所有 SKILL.md 的 (目录名, mtime, size) 指纹，
# 任何技能导入/删除/编辑（含用户手改 SKILL.md）都会导致指纹变化而自动失效，保证热改即时生效。
_SKILLS_CACHE = {"all_key": None, "all_list": None, "md_key": None, "md_list": None,
                 "stamp": 0.0}
_MIGRATE_STATE = {"mtime": 0, "clean": False}
_SKILLS_TTL = 2.0   # 快速路径有效期（秒）：期间直接返回缓存，零磁盘 IO


def _skills_fresh() -> bool:
    """TTL 快速路径：高频调用（输入框 textChanged）期间零 IO 直接命中缓存。
    修改类操作（导入/删除/创建）会显式失效缓存，保证即时生效。"""
    return time.time() - _SKILLS_CACHE["stamp"] < _SKILLS_TTL


def _invalidate_skills_cache() -> None:
    """修改技能后显式失效缓存（导入/删除/创建），下次调用重新扫盘"""
    _SKILLS_CACHE.update(all_key=None, all_list=None, md_key=None, md_list=None, stamp=0.0)


def _file_mtime(path: Path):
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _md_key(root: Path) -> str:
    """skills 目录指纹：所有 SKILL.md 的 (目录名, mtime, size) 摘要"""
    parts = []
    try:
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            f = d / "SKILL.md"
            if f.is_file():
                st = f.stat()
                parts.append(f"{d.name}:{st.st_mtime_ns}:{st.st_size}")
    except OSError:
        pass
    return "|".join(parts)


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


def _shipped_skills_dir() -> Path:
    """随应用分发的内置技能资源目录：打包后为 _MEIPASS/skills，开发模式为 src/winapp_migrator/skills"""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", "."))
        return base / "skills"
    return Path(__file__).resolve().parent.parent / "skills"


def ensure_md_skills() -> None:
    """确保内置 md 技能存在：内置模板（_BUILTIN_MD_SKILLS）+ 随包分发的技能资源，
    用户技能目录缺失时自动生成/复制（不覆盖用户已有或修改过的技能）"""
    root = _skills_dir()
    for name, cfg in _BUILTIN_MD_SKILLS.items():
        f = root / name / "SKILL.md"
        if f.is_file():
            continue
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(
                f"---\nname: {name}\ndescription: {cfg['description']}\n---\n\n"
                f"{cfg['instruction'].strip()}\n", encoding="utf-8")
        except OSError:
            pass
    # 随包分发技能：用户目录缺失同名技能时整体复制（含 resources 附属文件）
    shipped = _shipped_skills_dir()
    if shipped.is_dir():
        for d in shipped.iterdir():
            if not d.is_dir() or not (d / "SKILL.md").is_file():
                continue
            target = root / d.name
            if (target / "SKILL.md").is_file():
                continue
            try:
                shutil.copytree(d, target)
            except OSError:
                pass


def load_md_skills() -> list:
    """扫描市场标准技能目录，返回 [{name,description,instruction,source:'md'}]。
    TTL 快速路径：有效期内的重复调用零 IO 直接返回缓存；修改操作显式失效。"""
    if _skills_fresh() and _SKILLS_CACHE["md_list"] is not None:
        return _SKILLS_CACHE["md_list"]
    ensure_md_skills()
    root = _skills_dir()
    key = _md_key(root)
    if _SKILLS_CACHE["md_key"] == key and _SKILLS_CACHE["md_list"] is not None:
        _SKILLS_CACHE["stamp"] = time.time()
        return _SKILLS_CACHE["md_list"]
    out = []
    try:
        if root.is_dir():
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
    _SKILLS_CACHE["md_key"] = key
    _SKILLS_CACHE["md_list"] = out
    _SKILLS_CACHE["stamp"] = time.time()
    return out


def delete_skill(name: str) -> tuple:
    """删除用户技能：md 技能（skills/<name> 目录含 resources）与 skills.json 中的条目；
    内置技能（DEFAULT_SKILLS JSON 与 _BUILTIN_MD_SKILLS md 模板）拒绝删除。返回 (ok, message)。"""
    import shutil
    name = (name or "").strip()
    if not name:
        return False, "技能名不能为空"
    builtin = {s.get("name") for s in DEFAULT_SKILLS} | set(_BUILTIN_MD_SKILLS)
    if name in builtin:
        return False, f"「{name}」是内置技能，不可删除"
    removed = False
    # 1. md 技能目录（SKILL.md + resources 等附属文件）
    d = _skills_dir() / name
    if d.is_dir():
        try:
            shutil.rmtree(d)
            removed = True
        except OSError as e:
            return False, f"删除技能目录失败: {e}"
    # 2. skills.json 中的同名条目
    try:
        data = _load("skills.json", DEFAULT_SKILLS)
        if any(s.get("name") == name for s in data):
            data = [s for s in data if s.get("name") != name]
            with open(CONFIG_DIR / "skills.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            removed = True
    except OSError:
        pass
    if not removed:
        return False, f"未找到技能「{name}」"
    _invalidate_skills_cache()
    return True, f"已删除技能「{name}」并即时生效"


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
        _invalidate_skills_cache()
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
        _invalidate_skills_cache()
        return True, f"已导入技能「{s.get('name') or md_path.parent.name}」并即时生效"
    except OSError as e:
        return False, f"导入失败: {e}"


def _migrate_legacy_json_skills() -> None:
    """迁移旧 JSON 技能：技能已统一为市场标准 md（SKILL.md），
    若 skills.json 中存在已内置化的旧 JSON 条目则自动移除（保留用户自建技能），
    避免 JSON 优先覆盖 md 版本导致 SKILL.md 编辑不生效。
    带 mtime 状态缓存：文件未变化且已清理干净时跳过重复读取。"""
    global _MIGRATE_STATE
    try:
        path = CONFIG_DIR / "skills.json"
        if not path.is_file():
            return
        mt = _file_mtime(path)
        if _MIGRATE_STATE["clean"] and _MIGRATE_STATE["mtime"] == mt:
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return
        builtin = set(_BUILTIN_MD_SKILLS) | {"code-review"}
        leftover = [s for s in data
                    if isinstance(s, dict) and s.get("name") not in builtin]
        _MIGRATE_STATE["mtime"] = mt
        _MIGRATE_STATE["clean"] = len(leftover) == len(data)
        if not _MIGRATE_STATE["clean"]:
            path.write_text(json.dumps(leftover, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    except Exception:
        pass


def load_skills() -> list:
    """全部技能：内置 skills.json + 内置核心技能兜底 + 市场标准 md 技能（skills/<name>/SKILL.md）

    md 技能与 JSON 同名时以 JSON 为准（JSON 优先）。每次调用实时扫描，新增 md 技能即时生效。
    TTL 快速路径：有效期内的重复调用零 IO 直接返回缓存；修改操作显式失效。
    """
    if _skills_fresh() and _SKILLS_CACHE["all_list"] is not None:
        return _SKILLS_CACHE["all_list"]
    _migrate_legacy_json_skills()
    key = (_file_mtime(CONFIG_DIR / "skills.json"), _md_key(_skills_dir()))
    if _SKILLS_CACHE["all_key"] == key and _SKILLS_CACHE["all_list"] is not None:
        _SKILLS_CACHE["stamp"] = time.time()
        return _SKILLS_CACHE["all_list"]
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
    _SKILLS_CACHE["all_key"] = key
    _SKILLS_CACHE["all_list"] = merged
    _SKILLS_CACHE["stamp"] = time.time()
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


def skill_md_path(name: str) -> str:
    """技能 SKILL.md 绝对路径（引擎技能路由拦截的提示用）"""
    return str(_skills_dir() / name / "SKILL.md")


def skills_covering_tools(tool_names) -> dict:
    """返回 {工具名: [技能名, ...]}：instruction 文本中明确提及该底层工具的技能。
    引擎硬拦截用：被技能覆盖的工具，调用前须先 read_file 对应 SKILL.md 获取规范流程。
    工具名按词边界匹配（前后非字母数字下划线），避免 click 误匹配 click_text 等。"""
    out = {}
    for s in load_skills():
        inst = s.get("instruction", "") or ""
        name = s.get("name", "") or ""
        if not inst or not name:
            continue
        for t in tool_names:
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(t)}(?![A-Za-z0-9_])", inst):
                out.setdefault(t, []).append(name)
    return out


def _skill_router_block() -> str:
    """技能路由段：列出全部可用技能（name：description），
    强制 AI 任务命中技能时先 read_file 读取对应 SKILL.md 完整流程再执行，
    禁止跳过技能直接裸调工具（保证规范流程优先于裸工具调用）。"""
    skills = [s for s in load_skills()
              if s.get("name") and s.get("description")]
    if not skills:
        return ""
    lines = [f"- {s['name']}：{s['description']}" for s in skills]
    return ("\n\n技能路由（必须遵守）：执行任务前先判断下方技能列表是否有匹配项；"
            "命中时必须先用 read_file 读取技能目录 "
            "~/.winapp_migrator/agent/skills/<技能名>/SKILL.md 获取完整流程"
            "（找不到该文件时用 list_directory/search_files 在 skills 目录定位），"
            "严格按其 instruction 组织步骤后再调用底层工具，禁止跳过技能直接裸调工具：\n"
            + "\n".join(lines))


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
    prompt += _skill_router_block()
    prompt += ("\n\n可用内置工具：screenshot(截屏观察)、list_windows/capture_window(枚举并只截指定窗口，"
               "避免其他窗口干扰)、get_screen_size(分辨率)、"
               "ask_user(需求不明确时向用户提问)、"
               "find_app(秒查已安装应用路径)、search_files(工作目录内快速查找文件，未设工作目录则搜用户常用目录)、"
               "web_search(联网搜索，实时信息/新闻/文档，返回标题+URL+摘要)、"
               "web_fetch(联网请求 URL：GET/POST/PUT/DELETE 抓网页、调 API、读接口)、"
               "clipboard(读写剪贴板)、"
               "extract_text(提取文档文本：txt/csv/docx/pptx/xlsx，pdf 需装 pypdf)、"
               "create_docx(生成 Word 文档：标题+段落)、create_pptx(生成 PPT：标题+每页要点)、"
               "create_xlsx(生成 Excel：多工作表二维数据)、"
               "move_mouse/click/drag/scroll(鼠标)、press_key/type_text(键盘)、"
               "run_command(执行命令，可设 wait/force_quit，长任务用 check_command 轮询进度)、"
               "read_file/write_file/edit_file/delete_file/list_directory(文件读写改删列，相对路径基于工作目录)、"
               "save_memory/load_memory(本地长期记忆)。"
               "若连接了 MCP 服务器，其工具同样可用。")
    prompt += ("\n\n提问机制：尽量自主完成，减少打扰。需求不明确时优先基于上下文与已有信息合理推断，"
               "先推进低风险步骤；仅当关键信息缺失且推断会明显做错方向、或涉及不可逆/危险操作/需要用户拍板时，"
               "才调用 ask_user 提问，并把多个待确认项合并为一次询问（给出 options 建议选项方便点选，"
               "多选场景设置 multi_select=true），避免逐项追问；严禁编造关键信息冒充真实内容。")
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
