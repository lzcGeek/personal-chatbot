## Why

当前 MCP Server 和 Skill 只能通过 curl 或 API 文档页面管理，配置流程繁琐且门槛高。需要在聊天界面内提供可视化管理入口，让用户可以直接在网页上增删 MCP 服务、创建和管理 Skill，降低使用门槛。

## What Changes

- 在聊天页面新增一个设置侧边栏，包含"MCP 管理"和"Skill 管理"两个 Tab
- MCP 管理 Tab：列出已注册的 MCP Server（名称、传输类型、连接状态、工具数量），提供添加表单（stdio 填 command/args，HTTP/SSE 填 URL）和删除按钮
- Skill 管理 Tab：展示已加载的 Skill 列表（名称、描述），提供新建 SKILL.md 的简易文本编辑器，以及热重载按钮
- 后端 API 已具备（`GET/POST/DELETE /api/mcp/servers`、`GET /api/skills`、`POST /api/skills/reload`），本 change 纯前端工作

## Capabilities

### New Capabilities
- `frontend-mcp-ui`: 前端 MCP 服务可视化管理（增删查、状态展示、表单按传输类型切换字段）
- `frontend-skill-ui`: 前端 Skill 可视化管理（列表、新建 SKILL.md 编辑器、热重载）

### Modified Capabilities
- `skill-system`: 新增 `POST /api/skills` 端点，接收 name + description + content 并在 `skills/{name}/` 下创建 SKILL.md，支持同名冲突返回 409。其余需求不变。

## Impact

- 新增 Vue 组件：`SettingsPanel.vue`、`McpTab.vue`、`SkillTab.vue`
- 新增 Pinia store：`useMcpStore.ts`、`useSkillStore.ts`
- 或扩展现有 `chatStore` 不新增 store
- 新增前端 API 调用：`api/mcp.ts`、`api/skills.ts`
- 修改 `ChatWindow.vue` 添加设置侧边栏入口
- 纯前端改动，后端零变更
