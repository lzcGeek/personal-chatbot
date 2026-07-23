## Context

本项目参考 nekro-agent 的架构模式，但大幅简化：去除多平台适配器、Docker 沙箱、NoneBot 框架、多用户管理、知识库等复杂功能，仅保留核心聊天能力，并添加 MCP 和 Skill 集成。

技术约束：
- 单用户使用，无需认证系统（可后续添加）
- 本地运行，数据存储在本地 SQLite
- 前端仅需一个聊天页面

## Goals / Non-Goals

**Goals:**
- Python FastAPI 后端，提供聊天 API（支持流式响应）、MCP 管理 API、Skill 管理 API
- Vue 3 前端，单页面聊天界面，支持 Markdown 渲染和流式显示
- 对话记忆：短期记忆（最近 N 轮对话）+ 长期记忆（向量化语义检索）
- MCP 集成：通过 MCP SDK 连接外部 MCP Server，自动发现工具并注入聊天上下文
- Skill 系统：加载 Markdown 格式的 Skill 文件，作为系统提示词的一部分注入

**Non-Goals:**
- 多平台适配（QQ、微信等）
- Docker 沙箱代码执行
- 多用户认证与权限管理
- 知识库/RAG 文档管理
- 插件市场、云端服务
- 定时任务、邮件等辅助功能

## Decisions

### 1. 后端框架：FastAPI
- **选择**：FastAPI + Uvicorn
- **原因**：nekro-agent 已验证此方案；原生支持 async/await、自动生成 API 文档、流式响应 (SSE)
- **替代方案**：Flask — 不支持原生 async，流式响应实现复杂

### 2. 数据库：SQLite
- **选择**：SQLite + SQLAlchemy (async)
- **原因**：单用户场景无需 PostgreSQL；零配置、文件级存储、方便备份
- **替代方案**：PostgreSQL — 功能过剩，增加部署复杂度

### 3. 向量记忆：ChromaDB
- **选择**：ChromaDB (嵌入式模式)
- **原因**：轻量级、Python 原生、无需独立服务；自动将对话摘要向量化存储，支持语义检索
- **替代方案**：Qdrant — 需要额外部署服务，对单用户场景过重

### 4. LLM 调用：OpenAI SDK
- **选择**：openai Python SDK，兼容 OpenAI / Anthropic / 本地模型
- **原因**：大部分 LLM 提供商支持 OpenAI 兼容 API；单一 SDK 覆盖多提供商
- **配置**：通过环境变量配置 `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`

### 5. MCP 集成：mcp Python SDK
- **选择**：使用 `mcp` 官方 Python SDK 作为 MCP Client
- **原因**：标准 MCP 协议实现，支持 stdio/SSE/HTTP 传输
- **架构**：维护 MCP Server 连接池，启动时连接、定期健康检查，工具列表注入到系统提示词

### 6. Skill 系统：文件型
- **选择**：参考 Claude Code Skill 格式，每个 Skill 是一个包含 `SKILL.md` 的目录
- **原因**：结构清晰、易于创建和分享、无需编程即可扩展
- **加载**：启动时扫描 `skills/` 目录，读取 SKILL.md 的 frontmatter + 内容，注入系统提示词

### 7. 前端：Vue 3 + Vite
- **选择**：Vue 3 (Composition API) + Vite + Pinia
- **原因**：用户指定 Vue 技术栈；Vite 开发体验优秀；Pinia 是 Vue 3 官方推荐状态管理
- **UI 方案**：使用简单的自定义 CSS（不引入 UI 组件库，保持轻量）

### 8. 项目结构：Monorepo
- **选择**：`backend/` + `frontend/` 双目录结构，根目录统一管理
- **原因**：后端前端独立开发部署，但保持版本一致；Vite 开发代理到 FastAPI

## Risks / Trade-offs

- **[R] SQLite 并发限制**：单用户场景无并发压力。如需多用户，后续迁移到 PostgreSQL
- **[R] ChromaDB 嵌入式模式**：数据量大时检索性能可能下降。可后续切换 Qdrant 服务
- **[R] MCP Server 连接不稳定**：实现自动重连 + 工具调用失败时的降级策略（提示用户工具不可用）
- **[R] 记忆系统隐私**：对话内容存储在本地 SQLite 文件，需注意文件权限
- **[R] 前端无 UI 组件库**：开发速度可能较慢，但保持轻量且完全可控
