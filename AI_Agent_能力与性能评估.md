# AI Agent 能力与性能评估报告

- 评估日期：2026-08-14
- 评估对象：`WinAppMigrator` 内置 AI Agent（源码目录 `src/winapp_migrator/core` 与 `ui`）
- 评估方式：源码静态审查（功能与性能两手评估）

---

## 第一部分：AI Agent 能力评估

### 1. 评估总览

核心能力覆盖完整（9 项中 8 项可用），基础工程扎实（沙盒、编码、超时、tool_calls 配对保护均做得完善）。主要短板为「无 TODO 工具」和「编辑/压缩类能力精度不足」。

| 能力 | 工具 | 评分 | 状态 | 关键限制 |
|---|---|---|---|---|
| 读 | `read_file` | 4.0 | 成熟 | 200KB 上限；返回截断 30KB；无行号/二进制 |
| 写 | `write_file` | 4.0 | 成熟 | 500KB 上限；仅 UTF-8；无追加/增量写 |
| 编辑 | `edit_file` | 3.0 | 不足 | 仅整段替换首处；长文本易误替换；无回滚 |
| 查找 | `find_app` / `search_files` | 4.0 | 成熟 | 快速缓存；限用户目录；无文件内容检索 |
| 搜索 | `web_search` / `search_large` | 4.0 | 成熟 | 依赖 Bing 抓取；无专用搜索 API；子 Agent 兜底 |
| 新建 | `write_file` / `create_docx|pptx|xlsx` / `create_skill` | 4.0 | 成熟 | 文档体系齐全；无项目脚手架/模板库 |
| 待办 | 无（TODOS 缺失） | 0 | 缺失 | 无任务清单/计划拆分；长任务无进度可见性 |
| 运行命令 | `run_command` / `check_command` | 4.0 | 成熟 | 后台运行+轮询；编码鲁棒；Windows 限定 |
| 压缩上下文 | 引擎自动压缩 | 3.5 | 自动 | 200 条消息才触发；摘要丢弃图像 |

**平均 3.4 / 5。**

### 2. 逐项评估

#### 2.1 读（read_file）— 4/5 成熟
- 200KB 上限、返回截断 30KB、UTF-8/GBK 双解码回退、沙盒路径校验，工程细节到位。
- 短板：只读全文，无行号/偏移定位；无二进制/大文件分段读；30KB 截断可能让模型对长文件只见开头。

#### 2.2 写（write_file）— 4/5 成熟
- 500KB 上限、自动建目录、UTF-8 写入。
- 短板：无追加模式、无增量写。模型写大文件只能整体覆盖，易破坏未改动部分。

#### 2.3 编辑（edit_file）— 3/5 不足（最大隐患）
- 实现为「old_text → new_text 精确替换第一处」（`agent_tools.py::_edit_file`）。
- 长文本因上下文截断导致 `old_text` 无法精确匹配 → 反复「未找到」重试；
- 文件中多处出现同一 `old_text` 时只替换第一处，可能改错位置（无唯一性校验）；
- 无变更回滚/确认，改错即丢。

#### 2.4 查找（find_app / search_files）— 4/5 成熟
- `find_app` 带缓存秒查已装应用；`search_files` 并行遍历用户目录。
- 短板：仅按文件名模糊匹配，无内容检索（grep 语义）；范围限用户目录，系统盘命中差。

#### 2.5 搜索（web_search / search_large）— 4/5 成熟
- `web_search` 基于 Bing 抓取；`search_large` 走子 Agent 跨目录多轮搜索并读上下文确认。
- 短板：Bing 静态抓取易被反爬、可用性依赖网络；子 Agent 不能执行命令，遇二进制/超大目录受限。

#### 2.6 新建 — 4/5 成熟
- 覆盖最全：`write_file` + `create_docx/create_pptx/create_xlsx/generate_image/create_skill`。
- 短板：无项目脚手架工具、无模板库。

#### 2.7 TODO / 任务清单 — 0/5 缺失（必须补齐）
- 全项目搜索确认：无任何 todo/plan/任务清单工具（唯一命中的 `task_list` 是下载对话框 UI 控件）。
- 多步任务无进度可见性，中断后无法恢复「做到哪一步」；
- 与上下文压缩配合时，没有结构化任务状态可保留，压缩后易遗忘中间步骤。

#### 2.8 运行命令（run_command / check_command）— 4/5 成熟
- 后台命令注册表 + reader 线程排空管道防阻塞 + OEM 代码页处理 GBK + taskkill 进程树 + 沙盒危险命令拦截。
- 短板：`shell=True` 无 `cwd` 参数（相对路径基于进程工作目录而非 WORKDIR）；无交互式 stdin；无输出长度上限。

#### 2.9 压缩上下文 — 3.5/5 可用
- `_auto_compress`：LLM 自主摘要（40KB 截断保护 + 1024 token 输出）+ 启发式兜底，边界保护不切断 tool_calls 配对。
- 短板：按消息条数（>200）触发而非 token 感知，长截图任务可能早爆；摘要丢弃图像（`_prune_images(2)` 只留最近 2 张）；摘要以 user 角色插入语义不当。

### 3. 基础设施亮点（无需改动）

- 工具循环健壮性：非法 JSON 参数回提示不静默执行；停止时补齐 tool 配对防 400；技能路由硬拦截；开发规则强制确认。
- 子 Agent 并发：线程池 4 并发 + 工具白名单 + 独立上下文。
- 沙盒分级：路径三态、系统关键进程保护、curl 管道执行拦截。

### 4. 优化建议（按优先级）

| 优先级 | 建议 | 说明 |
|---|---|---|
| P0 | 新增 `create_todo / update_todo` 工具 | 仿 Trae 的 TodoWrite：JSON 持久化（`~/.winapp_migrator/agent/todos.json`），状态机 pending/in_progress/completed，引擎每轮注入清单摘要；压缩时自动保留未完成任务状态 |
| P1 | `edit_file` 增加唯一性校验 | 匹配 >1 处时拒绝并返回出现次数，防误替换；增加 `search_replace`（多行精确匹配）或 `apply_patch`（unified diff）；增加 `undo_file` 回滚 |
| P1 | 压缩触发改为 token 感知 | 用已有 `estimate_tokens` 估算，接近模型窗口 70% 时触发；摘要结果带压缩标记 |
| P2 | 读写命令细节 | `read_file` 支持 offset/limit 分段；`write_file` 支持 append；`run_command` 支持 cwd/stdin/max_output |
| P3 | 长期能力 | 项目脚手架 `new_project`；web_search 接专用搜索 API；子 Agent 只读 git 命令 |

---

## 第二部分：App 性能评估（AI 生成流畅度与交互流畅度）

### 1. 评估总览

架构层面**线程模型正确**（网络请求、工具执行、TTS 均在后台线程），流式 UI 有 60ms 节流，整体设计优于多数同类工具。**主要瓶颈集中在「主线程全量重渲染」与「主线程持久化 IO+图片压缩」两处**，在长输出生成后期与会话切换/任务结束时会出现可感知卡顿。

| 维度 | 评分 | 结论 |
|---|---|---|
| 引擎线程隔离（后台执行） | 5.0 | 优秀 |
| 流式 UI 刷新节流 | 4.0 | 良好（60ms 批量） |
| 长输出渲染效率 | 2.5 | **主要瓶颈（O(n²) markdown 全量重渲染）** |
| 交互响应（输入/按钮/停止） | 4.0 | 良好 |
| 会话切换 / 持久化 | 3.0 | **主线程 IO + PIL 压缩，有顿感** |
| 上下文 / 内存管理 | 4.0 | 良好（图片裁剪、自动压缩） |

**总体 3.7 / 5。**

### 2. AI 生成时是否卡顿

#### 2.1 设计良好的部分
- **引擎线程独立**：`AgentEngine.run` 运行在 `threading.Thread` 后台线程，SSE 流式解析、工具执行、截图压缩（`_compress_data_url`）均不占用 UI 线程。
- **跨线程信号安全**：`delta_signal / status_signal / result_signal / reasoning_signal` 等均为 `pyqtSignal`，引擎线程 emit → 主线程槽自动队列执行。
- **流式刷新节流**：`_refresh_ai_html` 用 `QTimer.singleShot(60ms)` 合并高频 token 刷新为每 60ms 一次批量 `setText`，避免每个 token 全量重建。
- **降低渲染量的设计**：思考过程默认折叠、工具执行结果默认折叠、截图缩略图独立成块、resize 防抖 160ms、历史批量加载跳过淡入动画。

#### 2.2 主要卡顿点（按严重程度）
1. **【严重】O(n²) markdown 全量重渲染**
   - 流式期间每 60ms 对**完整累积文本**调用 `_render_text(seg["raw"])` 重新解析（`agent_panel.py::_build_ai_html` → `_md_to_html`），并对全部历史段（历史+当前）重建 HTML。
   - 输出越长，每帧解析成本越高 → 长回答（数万 token）生成后期帧耗时显著上升，表现为「越说越卡」。
2. **【中等】滚动无节流**
   - 每个 delta 都调用 `_scroll_bottom()` 触发滚动条 relayout，与 60ms HTML 重建叠加，加剧高频抖动。
3. **【中等】大工具结果单帧开销**
   - `_on_result` 中 20KB 以内结果一次性转义 + setText，大输出瞬间仍可能卡一帧。

#### 2.3 结论
短回答/中等输出流畅；**长输出（>5k token）生成后期存在可感知卡顿，根因是主线程全量 markdown 重渲染**，而非网络或线程模型问题。

### 3. 交互是否流畅

#### 3.1 设计良好的部分
- 发送/停止按钮转圈动画用 QTimer 80ms 驱动，不阻塞；任务结束通过 400ms `_refresh_meta` 轮询统一收尾，不依赖脆弱的时序判断。
- 输入框自动高度用 `singleShot(0)` 延迟；会话下拉/新建均为轻量操作。
- 停止响应：`stop()` 置位后引擎循环每轮检查，工具执行可被 `_call_with_stop` 中断，大部分场景可及时停止。

#### 3.2 主要卡顿点（按严重程度）
1. **【严重】主线程同步持久化 + PIL 图片压缩**
   - `_persist_current`（任务结束、会话切换、关闭窗口时）在主线程调用 `engine.save_context()`，内部对上下文里**每张图片 data_url 做 PIL resize 压缩**（`agent_engine.py::save_context`）。
   - 长对话多截图场景：保存可能阻塞 UI 数百毫秒至数秒，表现为「任务完成瞬间顿住」或「切换会话卡一下」。
2. **【中等】会话切换全量重绘**
   - `_switch_to` 在主线程加载 UI json 并 `_render_history_all()` 全量重绘气泡，长会话切换有短暂顿感。
3. **【中等】关闭窗口延迟**
   - `closeEvent` 同步执行 `engine.stop() + join(3) + _persist_current`，大会话下关闭窗口可能延迟。

#### 3.3 结论
日常交互（输入、按钮、短任务）流畅；**会话切换、任务结束、关闭窗口三个时点存在主线程阻塞风险**，根因是持久化/重绘在主线程同步执行。

### 4. 其他性能观察

- **上下文无截断增长**：工具完整输出直接进上下文（用户要求禁止截断），token 成本线性增长直到 200 条消息触发压缩；压缩时 LLM 摘要同步阻塞引擎循环（任务停顿，UI 有 spinner）。
- **内存友好**：视觉历史只保留最近 2 张截图（`_prune_images(2)`），避免上下文膨胀。
- **tokens 估算**：每轮 `estimate_tokens` 对全部消息做 join，消息多时成本线性上升（可接受）。

### 5. 优化建议（按优先级）

| 优先级 | 建议 | 说明 |
|---|---|---|
| P0 | 流式**增量渲染** | 流式期间不再全量重建：对当前 text 段缓存已渲染 HTML，仅渲染新增片段（或流式期仅渲染尾部 N 字符预览、输出结束后全量渲染一次） |
| P0 | **滚动节流** | `_scroll_bottom` 改为计时器合并（如 100ms），或仅在 HTML 重建帧内滚动一次 |
| P1 | 持久化移出主线程 | `_persist_current` 拆为「小 UI 文件同步快速保存 + 模型上下文（含图片压缩）后台异步保存」；任务结束时先存 UI，上下文异步落盘 |
| P1 | 会话切换异步化 | `_switch_to` 的 load + 全量重绘放后台线程，先显示加载态，完成后一次性切图 |
| P2 | 大结果显示截断阈值降低 | `_on_result` 显示截断从 20KB 降至 8KB，完整内容仍返回模型 |
| P2 | closeEvent 异步收尾 | `join(3)` 缩短或改后台收尾，避免关闭窗口等待 |

### 6. 性能优化关键代码定位

| 问题 | 位置 |
|---|---|
| 引擎后台线程 | `agent_engine.py::run`（`threading.Thread` 启动） |
| 流式 60ms 节流 | `agent_panel.py::_refresh_ai_html / _apply_refresh_ai_html` |
| O(n²) 全量渲染 | `agent_panel.py::_build_ai_html` → `_render_text(seg["raw"])` |
| 每 token 滚动 | `agent_panel.py::_on_delta` → `_scroll_bottom()` |
| 主线程图片压缩持久化 | `agent_panel.py::_persist_current` → `agent_engine.py::save_context` |
| 会话切换全量重绘 | `agent_panel.py::_switch_to` → `_render_history_all` |
| 关闭同步收尾 | `agent_panel.py::closeEvent` |

---

## 结论汇总

1. **能力侧**：8/9 能力可用且工程扎实，唯一缺失是 TODO 工具；编辑精度与上下文压缩触发时机是主要短板。
2. **性能侧**：线程模型正确、流式节流到位；两处主线程瓶颈（全量 markdown 重渲染、持久化图片压缩）是卡顿主因。
3. **建议落地顺序**：先补 TODO 工具（能力 P0）→ 流式增量渲染 + 滚动节流（性能 P0）→ 持久化异步化（性能 P1）→ 编辑唯一性校验（能力 P1）。
