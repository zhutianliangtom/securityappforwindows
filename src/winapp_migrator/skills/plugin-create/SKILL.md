---
name: plugin-create
description: 插件创建：根据用户自然语言描述自动生成可运行插件（MCP server + SKILL.md 技能 + 脚本/资源/示例）并加载
---

# plugin-create：创建新插件

1. 倾听用户对插件的描述，确认插件类型：
   - `mcp`：仅提供工具能力（MCP server）
   - `skill`：仅沉淀为标准技能（SKILL.md）
   - `combined`：同时提供技能与 MCP 工具（默认）
2. 用 create_plugin 工具创建，description 写清插件要做什么、提供哪些能力。
3. 创建成功后提示：插件已统一存入插件目录，MCP 工具与技能均已自动登记即时生效；
   用户可在设置-插件页查看/管理/停用/删除；MCP 服务器需在设置-插件页保存后自动重连。
4. 若用户描述的是可复用的独立能力，适合沉淀为插件；若只是流程，用 skill-create 即可。
