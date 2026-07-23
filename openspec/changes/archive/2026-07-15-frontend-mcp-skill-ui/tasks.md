## 1. Backend — Skill 创建 API

- [x] 1.1 Add POST /api/skills endpoint to routes (`backend/app/api/skills.py`), accepting `{name, description, content}`, creating `skills/{name}/SKILL.md`, returning 201/409/422
- [x] 1.2 Add Pydantic schema `SkillCreate` in `backend/app/schemas/skill.py` with field validation

## 2. Frontend API Layer

- [x] 2.1 Add MCP API functions (`frontend/src/api/mcp.ts`): `getMcpServers()`, `addMcpServer()`, `deleteMcpServer(id)`
- [x] 2.2 Add Skills API functions (`frontend/src/api/skills.ts`): `getSkills()`, `createSkill()`, `reloadSkills()`

## 3. Settings Panel Shell

- [x] 3.1 Create `SettingsPanel.vue` with sliding sidebar, backdrop overlay, and Tab switcher (MCP / Skills)
- [x] 3.2 Add toggle button to `ChatWindow.vue` header to open/close settings panel

## 4. MCP Management Tab

- [x] 4.1 Create `McpTab.vue` — server list with name, transport type icon, status badge, tool count
- [x] 4.2 Implement add-server form with transport type selector that toggles fields (stdio: command/args, SSE/HTTP: URL)
- [x] 4.3 Implement delete with confirmation dialog
- [x] 4.4 Add loading and error states

## 5. Skill Management Tab

- [x] 5.1 Create `SkillTab.vue` — loaded skill list with name, description, load status
- [x] 5.2 Implement new-skill textarea editor with YAML frontmatter skeleton template
- [x] 5.3 Implement save-new-skill flow with validation and conflict error handling
- [x] 5.4 Implement hot-reload button with success feedback

## 6. Polish

- [x] 6.1 Add responsive media query — full-width overlay panel on mobile
- [x] 6.2 Verify entire flow: add MCP server → list update, create Skill → reload → list update, delete MCP → list update
