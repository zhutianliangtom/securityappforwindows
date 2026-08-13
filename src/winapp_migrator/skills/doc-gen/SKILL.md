---
name: doc-gen
description: 文档生成：用 create_docx/create_pptx/create_xlsx 自动生成 Word/PPT/Excel，配合 extract_text 验证内容
---

# doc-gen：Word / PPT / Excel 文档自动生成

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
- 图片素材：可根据实际情况调用 image-gen 技能生成所需图片素材（文生图/图生图），
  生成后自动下载到桌面；生成的图片可以直接插入到 Word/PPT/Excel 文档中。

## 3. 验证（必做）
生成后用 extract_text(path) 读取文件，确认标题、正文、中文、表格数据均正确。

## 4. 汇报
输出：文件路径、包含的章节/工作表、内容摘要。