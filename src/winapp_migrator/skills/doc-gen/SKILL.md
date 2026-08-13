---
name: doc-gen
description: 文档生成：用 create_docx/create_pptx/create_xlsx 自动生成 Word/PPT/Excel，配合 extract_text 验证内容
---

# doc-gen：Word / PPT / Excel 文档自动生成

当用户要求"做一份文档 / 生成 PPT / 整理成 Excel 表格"时使用本技能。

## 1. 确认需求
先问清：文档主题与内容要点、保存路径、格式（docx/pptx/xlsx）。
内容信息不足时用 ask_user 补齐，禁止编造数据。

## 2. 大胆设计，拒绝千篇一律（核心原则）
所有文档都默认商务深蓝风会让你看起来像模板机器。请根据内容主题主动选择配色、字体与布局，
通过每个工具的 style 参数定制，让每份文档都独一无二：
- 主题换色（style.theme）：科技/产品→tech(蓝)、环保/自然→green(墨绿)、
  党政/年节→red(朱红)、教育/学术→business(深蓝)或pastel(浅蓝)、
  高端/商务晚宴→black-gold(黑金)、创意/发布会→vivid(橙红)、
  暗色炫酷→dark、温馨/文艺→warm(橙棕)。
  也可直接传具体色值（base_color/heading_color/text_color/theme_color/header_fill 等）自由发挥。
- 字体（font_name）：正式文书用"宋体/仿宋"，文艺用"楷体"，默认微软雅黑。
- 布局：Word 可调行距/对齐/纸张方向；PPT 可选封面布局(纯色/左右分屏/居中简约)与要点符号
  (圆点/编号/箭头/对勾)；Excel 可自定义表头配色、隔行色、边框、字号、是否冻结/筛选。
- 每份文档至少换一个配色或布局参数，让作品符合内容气质，而不是套同一个模板。

## 3. 生成
- Word（create_docx）：path=保存路径，title=文档标题，paragraphs=[段落文本列表]，style=样式(可选)
  段落支持轻量标记增强结构：'# ' 一级标题、'## ' 二级标题、'### ' 三级标题、'- ' 项目符号，其余为正文。
  标题建议用标记分层（如 '# 一、概述' / '## 1.1 现状'），正文直接写内容。
- PPT（create_pptx）：path，title=总标题，slides=[{title: 页标题, bullets: [要点列表],
  image: 插图(可选), bg_color: 本页背景色(可选), title_color: 本页标题色(可选)}]，style=样式(可选)
  自动生成 16:9 标题页；每页为"标题+分隔线+要点"，每页要点建议 3-6 条。
- Excel（create_xlsx）：path，sheets=[{name: 工作表名, rows: [[单元格值]...],
  image: 插图(可选)}]，style=样式(可选)
  首行自动作表头（默认深蓝底白字并冻结）；纯数字字符串自动转数值，无需引号包裹数字。
- 图片素材（强制）：文档内容适合配图（汇报/产品介绍/感言/总结/宣传等）时，**必须优先调用
  image-gen 技能生成匹配主题的素材图**（文生图/图生图，生成后自动下载到桌面），
  并把生成的图片作为 image 参数插入到 Word/PPT/Excel 文档中（可用 {path, align, width}
  指定位置与大小，系统自动等比缩放不会溢出）。不要跳过配图直接生成无图文档。

## 4. 验证（必做）
生成后用 extract_text(path) 读取文件，确认标题、正文、中文、表格数据均正确。

## 5. 汇报
输出：文件路径、包含的章节/工作表、采用的配色主题与布局风格、内容摘要。
