## Why

需要一个轻量级的网页聊天机器人，具备记忆能力和可扩展的 MCP 工具/Skill 插件机制。现有的 nekro-agent 功能完善但过于复杂（多平台适配、Docker 沙箱、NoneBot 框架等），本项目只需提取其核心的聊天、记忆、MCP 和 Skill 模式，构建一个简洁、可直接在网页上使用的单用户聊天应用。

## What Changes

- 新建 Python FastAPI 后端项目，提供聊天 API、MCP 管理 API、Skill 管理 API
- 新建 Vue 3 前端项目，提供简洁的聊天界面
- 实现对话记忆功能：聊天历史持久化 + 向量化语义记忆检索
- 实现 MCP (Model Context Protocol) 集成：支持连接外部 MCP Server，将其工具注入聊天上下文
- 实现 Skill 系统：支持加载 Markdown 格式的 Skill 定义文件，注入系统提示词
- 支持 OpenAI 兼容的 LLM API（可切换不同模型提供商）

## Capabilities

### New Capabilities
- `chat-core`: 核心聊天功能 — 消息收发、流式响应、多轮对话、Markdown 渲染
- `chat-memory`: 对话记忆系统 — 聊天历史存储、向量化语义记忆、记忆检索与注入
- `mcp-integration`: MCP 工具集成 — MCP Server 连接管理、工具发现、聊天中调用 MCP 工具
- `skill-system`: Skill 插件系统 — Skill 文件的加载/管理、系统提示词注入

### Modified Capabilities
<!-- No existing capabilities to modify — this is a new project -->

## Impact

- 新项目，不影响现有代码
- 后端依赖：Python 3.10+, FastAPI, SQLite (本地数据库), ChromaDB (向量记忆), OpenAI SDK
- 前端依赖：Vue 3, Vite, Pinia (状态管理), Axios
- 开发环境：前端 Vite 代理到后端 FastAPI 端口
