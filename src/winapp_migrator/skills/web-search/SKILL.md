---
name: web-search
description: 联网搜索：web_search 搜索实时信息（新闻/文档/教程/代码），web_fetch 抓取网页或调用 API 接口
---

# web-search：联网搜索与网页抓取

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
给出结论并附来源 URL。
