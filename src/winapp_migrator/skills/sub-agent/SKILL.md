---
name: sub-agent
description: 子任务调度：dispatch_sub_agents 并行派发互不依赖的子任务、explore_project 快速了解新项目、search_large 大规模跨目录搜索
---

# sub-agent：子任务并行调度与大规模搜索

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
汇总各子任务结果、项目概览或搜索命中清单。
