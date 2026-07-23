## Context

当前聊天页面（`ChatWindow.vue`）仅包含消息列表和输入框。MCP 和 Skill 的后端 API 已完备，需要新增前端管理界面。

前端技术栈：Vue 3 + Pinia + TypeScript，自定义 CSS，无 UI 组件库。设计需保持简洁，避免引入重量级依赖。

## Goals / Non-Goals

**Goals:**
- 在聊天页面增加设置侧边栏，不影响现有聊天布局
- MCP Tab：列表 + 添加表单 + 删除
- Skill Tab：列表 + 新建编辑器 + 重载
- 保持纯 CSS 风格，不引入 UI 库
- 表单按传输类型动态切换字段

**Non-Goals:**
- 不引入 Monaco Editor 等重型编辑器（用 `<textarea>`）
- 不支持从 GitHub 导入 Skill
- 不支持 MCP Server 编辑（只支持增删）
- 不修改后端代码

## Decisions

### 1. 组件结构：侧边栏模式
- **选择**：在 ChatWindow 右侧加一个可折叠的 `<aside>` 侧边栏
- **原因**：聊天界面为主、管理界面为辅，侧边栏不打断聊天流。参考 ChatGPT 设置面板模式
- **替代方案**：独立路由 / 弹窗 → 独立路由打断聊天，弹窗在小屏幕上体验差

### 2. 状态管理：复用 Chat Store 不新增
- **选择**：不新建 Pinia store，直接在组件内用 `ref` + API 调用管理 MCP 和 Skill 状态
- **原因**：两个 Tab 的状态很简单（1 个列表 + 1 个表单），新增 store 过度设计。后续需要跨组件共享时再抽
- **替代方案**：`useMcpStore` + `useSkillStore` → 当前无跨组件共享需求

### 3. MCP 表单：传输类型驱动字段切换
- **选择**：选择 stdio 时显示 command + args 字段，选择 SSE/HTTP 时显示 URL 字段
- **原因**：后端 Pydantic schema 已约束，前端只需跟随类型展示对应字段
- **字段映射**：
  - stdio: `command` (必填), `args` (选填，逗号分隔), `env` (选填)
  - sse: `url` (必填)
  - http: `url` (必填)

### 4. Skill 编辑器：简单 textarea
- **选择**：用 `<textarea>` 渲染 YAML frontmatter + Markdown body 的编辑区
- **原因**：Skill 文件结构简单（frontmatter + content），不需要语法高亮。后续可换 CodeMirror 轻量方案
- **模板**：新建时自动填入 frontmatter 骨架（`name:` / `description:` / `---` / 内容区）

### 5. Skill 本地创建：写入文件系统
- **问题**：用户在浏览器编辑 SKILL.md，但文件要落到 `skills/` 目录才能被 loader 扫描
- **选择**：新增 `POST /api/skills` 后端接口，接收 name + description + content，在 `skills/` 目录下创建 `{name}/SKILL.md`
- **原因**：浏览器无法直接写服务器文件系统，必须通过 API 中转
- **影响**：这是唯一需要后端改动的地方——新增约 15 行代码

## Risks / Trade-offs

- **[R] Skill 文件名冲突**：同名 Skill 已存在时 → 后端返回 409，前端提示覆盖确认
- **[R] MCP 连接超时**：添加 stdio Server 时需验证连接，可能阻塞 UI → 加 loading 状态 + 超时提示
- **[R] 侧边栏在小屏幕上挤占聊天空间** → Media query 自动隐藏为全屏覆盖模式
