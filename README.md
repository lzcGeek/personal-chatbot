# Memory MCP Chatbot

一个具有长期语义记忆、MCP 工具集成和文件化 Skills 的浏览器聊天机器人。

## 项目结构

```
├── backend/          # Python FastAPI 后端
│   ├── app/
│   │   ├── api/      # 路由：chat / memories / mcp / skills
│   │   ├── core/     # 配置、数据库
│   │   ├── models/   # SQLAlchemy ORM 模型
│   │   ├── services/ # LLM 客户端、记忆服务、MCP 管理器等
│   │   └── schemas/  # Pydantic 校验模型
│   ├── data/         # 运行时数据（db + chroma）
│   └── .venv/        # Python 虚拟环境
├── frontend/         # Vue 3 + Vite 前端
│   └── src/
│       ├── api/      # Axios + SSE 流式请求
│       ├── components/ # ChatWindow / ChatInput / MessageBubble
│       ├── stores/   # Pinia 状态管理
│       └── types/    # TypeScript 类型
├── skills/           # 文件化 Skill（SKILL.md）
└── .env              # 模型配置
```

## 前置条件

- **Python** ≥ 3.10
- **Node.js** ≥ 18（你的环境：`/c/Users/MR/AppData/Local/nvm/v24.15.0`）
- 一个提供 **OpenAI 兼容 API** 的模型服务

## 首次安装

```bash
# 1. 后端虚拟环境 + 依赖
cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"

# 2. 前端依赖
cd ../frontend
npm install

# 3. 创建配置文件
cd ..
cp .env.example .env
# 编辑 .env 填入你的模型地址、密钥和模型名
```

## 配置文件 `.env`

```env
OPENAI_BASE_URL=http://你的模型服务地址/v1
OPENAI_API_KEY=你的密钥
OPENAI_MODEL=你的模型名称
```

## 启动

需要开两个终端。

### 终端 1 — 后端

```bash
# 启动
.venv/Scripts/python -m uvicorn app.main:app \
  --app-dir backend \
  --host 127.0.0.1 \
  --port 8021

# 停止：Ctrl + C
```

启动后访问 `http://127.0.0.1:8021/docs` 查看 API 文档。

### 终端 2 — 前端

```bash
# 先设置 Node.js 路径
export PATH="/c/Users/MR/AppData/Local/nvm/v24.15.0:$PATH"

# 启动
npm run dev --prefix frontend

# 停止：Ctrl + C
```

启动后访问 `http://127.0.0.1:5173` 使用聊天界面。

## 数据说明

| 数据 | 位置 | 重启后 |
|---|---|---|
| 聊天记录 | `backend/data/chatbot.db` → `chat_messages` 表 | ✅ 磁盘持久化 |
| MCP 配置 | `backend/data/chatbot.db` → `mcp_servers` 表 | ✅ |
| 记忆文字 | `backend/data/chatbot.db` → `memory_entries` 表 | ✅ |
| 记忆向量 | `backend/data/chroma/` | ✅ |
| 页面状态 | 浏览器内存 | ❌ 刷新重新加载 |

ChromaDB 首次写入记忆时会下载约 79 MB 的嵌入模型，需要网络。下载失败不会阻塞基础聊天，但长期语义记忆不可用。

## API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| POST | `/api/chat/send` | 同步聊天 |
| POST | `/api/chat/stream` | 流式聊天（SSE） |
| GET | `/api/chat/history` | 分页历史 |
| GET | `/api/memories` | 记忆列表 |
| DELETE | `/api/memories/{id}` | 删除记忆 |
| POST | `/api/mcp/servers` | 添加 MCP 服务 |
| GET | `/api/mcp/servers` | MCP 服务列表 |
| DELETE | `/api/mcp/servers/{id}` | 删除 MCP 服务 |
| GET | `/api/skills` | Skill 列表 |
| POST | `/api/skills/reload` | 热重载 Skills |
