# NewAgent

一个支持多用户、个人文档知识库、混合 GraphRAG、长期语义记忆、MCP 工具与文件化 Skills 的浏览器聊天助手。

## 当前架构

- 前端：Vue 3 + Vite + Pinia
- 后端：FastAPI + SQLAlchemy Async
- 业务数据与账号：PostgreSQL
- 向量索引：Qdrant
- 知识图谱：Neo4j
- 文档处理：PDF / DOCX / TXT / Markdown 解析、结构分块、异步索引与来源引用
- 登录：服务端不透明 Cookie Session
- 密码：Argon2id 单向哈希（Base64 不是密码加密方案）
- 数据库版本：Alembic

所有会话、消息、文档、向量和图谱查询都按 `user_id` 隔离。PostgreSQL 是业务与文档正文的事实来源，Qdrant 保存可重建的向量索引，Neo4j 保存带来源的实体和事实；后台通过 outbox 执行可重试索引与完整删除。

完整设计、安全边界和故障恢复说明见 `MULTI_USER_REFACTOR.md`，规范变更位于 `openspec/changes/multi-user-postgres-qdrant-auth/`。

个人文档与知识图谱方案见 `PERSONAL_GRAPH_RAG.md`，对应 OpenSpec 变更位于 `openspec/changes/personal-document-graph-rag/`。

聊天输入区的“联网”开关仅授权本次回答调用标记为“需要联网”的 MCP 工具；它不关闭模型 API 或 MCP 后台重连。联网关闭时后端会同时过滤工具并在执行入口拒绝调用。LLM 瞬时故障会在首 token 前有限重试，可选上下文或联网工具失败则降级回答并在界面提示。

知识库上传支持按文档选择“跟随系统默认 / 构建图谱 / 不构建图谱”。关闭图谱只跳过 Neo4j 关系抽取，文档仍会完成文本解析和 Qdrant 向量索引。聊天还可按会话选择“自动 / 关闭知识库 / 仅向量文本 / 向量 + 图谱”；混合模式下图服务故障会降级使用可用的向量证据。

## 可选 NPC 运行时

项目现支持用户私有角色、单 NPC、多 NPC 顺序编排、分层记忆、滚动摘要、共享场景状态以及可选图片/TTS。普通助手仍是默认兼容路径；所有新增运行能力可独立关闭，未配置媒体 Provider 时聊天保持纯文本。

- 角色：在“设置 → 角色”维护人设、场景、示例对话、工具/知识/联网/媒体权限和头像。
- 群聊：支持手动、`@角色名`、轮询和受限自动路由；每轮角色数与连续生成数同时受会话和服务器上限约束。
- 混合记忆：明确纠正自动替代，状态变化保留历史版本，推断冲突等待确认，可共存事实不会互相覆盖；原始聊天消息始终保留。
- 记忆管理：在“设置 → 记忆”查看来源、作用域、有效性、摘要覆盖范围，并进行确认、失效、恢复、删除和摘要重建。
- 媒体：完整文本先落库，再异步生成图片或语音；附件按用户授权下载，媒体失败不改变文本消息。

详细架构、API、开关顺序和回滚方案见 [NPC_RUNTIME.md](NPC_RUNTIME.md)。

## 第一次使用：从启动到 NPC 对话

### 1. 先开启需要的功能

项目根目录的 `.env` 是实际运行配置，`.env.example` 只是示例。NPC 功能默认关闭。首次体验角色聊天，建议至少加入：

```env
SINGLE_NPC_ENABLED=true
GROUP_NPC_ENABLED=true
MEMORY_COMPRESSION_ENABLED=true
NETWORK_TOOLS_ENABLED=true
```

修改 `.env` 后必须重启后端。只刷新浏览器不会使开关生效。图片和语音还需要单独配置 Provider，不能只把开关改为 `true`。

| 开关 | 作用 | 未开启时的表现 |
|---|---|---|
| `SINGLE_NPC_ENABLED` | 单角色 NPC 会话 | 提示“单角色 NPC 尚未启用” |
| `GROUP_NPC_ENABLED` | 多角色群聊与发言路由 | 提示“多角色编排尚未启用” |
| `MEMORY_COMPRESSION_ENABLED` | 长对话滚动摘要 | 保留原始消息，但不自动压缩长历史 |
| `NETWORK_TOOLS_ENABLED` | 允许调用标记为联网的 MCP 工具 | 即使勾选“联网”也不会提供网络工具 |
| `IMAGE_GENERATION_ENABLED` | 图片生成 | 图片按钮不可用；还需配置图片 Provider |
| `TTS_ENABLED` | 语音合成 | 语音按钮不可用；还需配置 TTS Provider |

### 2. 启动依赖、后端和前端

在项目根目录启动数据服务：

```powershell
docker compose up -d postgres qdrant neo4j
docker compose ps
```

启动后端：

```powershell
cd backend
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8021
```

另开一个终端启动前端：

```powershell
cd frontend
npm run dev
```

打开 `http://127.0.0.1:5173`。后端健康检查为 `http://127.0.0.1:8021/api/health`，接口文档为 `http://127.0.0.1:8021/docs`。

### 3. 创建角色

1. 登录后打开右上角“设置”。
2. 进入“角色”页签，创建角色。
3. 至少填写名称；人设、性格、场景、开场白和示例对话均可后补。
4. 角色权限只能缩小服务器能力，不能通过人设获得服务器没有开放的联网、工具、知识库或媒体权限。
5. 角色创建后，将它加入需要使用的会话。

### 4. 选择会话模式

| 模式 | 谁来回答 | 适用场景 |
|---|---|---|
| 普通助手 `assistant` | 默认 AI 助手 | 原有问答、知识库问答，不需要角色 |
| 单角色 `single_character` | 固定由一个角色回答 | 单 NPC 剧情、陪伴或角色扮演 |
| 多角色 `group` | 由发言路由选择一个或多个角色 | NPC 小队、酒馆群聊、主持人与玩家互动 |

旧会话默认是普通助手。切换模式不会删除旧消息。切换到其他会话时，原会话若仍在生成，侧栏会显示“生成中”；切回后可继续看到生成状态和内容。界面不会保存或展示模型隐藏推理，只显示“正在思考”“正在生成回复”等用户可见状态以及最终回答。

### 5. 多角色“发言路由”怎么选

发言路由只决定群聊中本轮由谁回答，不会创建无限自治循环。

| 路由 | 行为 | 示例 |
|---|---|---|
| 手动指定 `manual` | 每次发送前由用户选择角色 | 指定“商人”回答价格问题 |
| 提及 `mention` | 根据消息里的 `@角色名` 选择角色 | `@骑士 去检查城门` |
| 轮询 `round_robin` | 按成员顺序轮流选择下一个角色 | 国王 → 骑士 → 商人 |
| 自动 `auto` | 模型从当前启用成员中选择 | “谁了解森林？”可能选择猎人 |

自动路由只能选择当前会话内已启用的角色，并受到“本轮最多角色”和服务器上限约束。想要行为最稳定时使用“手动指定”或“提及”。

### 6. 记忆与摘要

- 最近消息：直接参与当前对话。
- 共享记忆：当前会话中的所有角色都可能使用。
- 角色私有记忆：只提供给对应角色。
- 滚动摘要：长对话达到阈值后异步生成，用于减少上下文占用；不会删除原始消息。
- 混合冲突策略：用户明确纠正时替代旧事实；状态变化保留历史版本；模型不确定的冲突等待确认；能够同时成立的事实并存。

在“设置 → 记忆”中可以查看来源、作用域和有效状态，也可以失效、恢复、删除记忆或重建摘要。

### 7. 文档上传与图谱开关

上传 PDF、DOCX、TXT 或 Markdown 时可以选择：

| 图谱模式 | 结果 |
|---|---|
| 跟随系统默认 `inherit` | 使用服务器的 Neo4j 配置 |
| 构建图谱 `enabled` | 完成文本/向量索引后，再异步抽取实体和关系 |
| 不构建图谱 `disabled` | 跳过 Neo4j，但文档仍可通过文本向量检索 |

会话的知识检索模式：

- 自动：保持兼容行为，按问题类型融合可用证据。
- 关闭知识库：本会话不查询文档向量和图谱。
- 仅向量文本：使用 Qdrant，不查询 Neo4j。
- 向量 + 图谱：融合两者；Neo4j 故障时降级使用向量结果。

“文本可检索”和“图谱增强完成”是两个独立状态。图谱失败不表示整个文档不可用。

### 8. “联网”到底是什么意思

输入框下面的“联网”不是浏览器联网状态，也不会自动提供网页搜索。它只表示：**本次回答允许调用已经配置、已连接并标记为需要联网的 MCP 工具**。

要真正使用联网能力，必须同时满足：

1. `.env` 中 `NETWORK_TOOLS_ENABLED=true`。
2. 在“设置 → MCP”中添加了可联网的 MCP 服务器或搜索工具。
3. MCP 服务器状态为已连接，并且成功发现了工具。
4. 该服务器或工具被标记为“需要联网”。
5. 当前角色和本次请求都允许联网及工具调用。

如果提示“未找到可用网络工具”，通常不是网络断开，而是当前没有符合以上条件的 MCP 工具。即使没有 MCP 网络工具，OpenAI 兼容模型 API 仍会按 `.env` 的地址工作；“联网”开关不控制模型 API 自身。

判断是否真的使用了联网工具，可以观察：

- 设置页中 MCP 服务器是否显示已连接、是否列出了工具。
- 回答过程中是否出现工具调用结果或联网失败/降级提示。
- 后端日志是否记录对应 MCP 工具调用。
- 只勾选复选框但没有任何工具调用，不代表本轮实际访问了网络。

### 9. 图片与语音

图片和 TTS 都是可选后处理：文本回答会先完成并保存，然后才创建媒体任务。需要在 `.env` 配置 Provider 地址、API Key、模型和允许的 profile，再开启对应开关并重启后端。媒体生成失败不会删除或改变文本回答。

### 10. 常见提示

| 提示 | 原因与处理 |
|---|---|
| 单角色 NPC 尚未启用 | 设置 `SINGLE_NPC_ENABLED=true`，重启后端 |
| 多角色编排尚未启用 | 设置 `GROUP_NPC_ENABLED=true`，重启后端 |
| 未找到可用网络工具 | 检查联网总开关、MCP 连接、工具发现和角色权限 |
| 图谱跳过 | 上传时选择了不构建图谱；文本向量检索仍可用 |
| 图谱不可用/失败 | 检查 Neo4j；可继续使用向量检索并稍后重试图谱 |
| 未配置图片或语音 Provider | 配置对应 Provider 和允许 profile，开启开关后重启 |
| 正在思考状态切换后消失 | 更新到当前前端代码；生成状态现在按会话独立保存 |

## 前置条件

- Python 3.10+
- Node.js 18+
- Docker（用于 PostgreSQL、Qdrant 与 Neo4j）
- 可用的 OpenAI 兼容聊天与 Embeddings API

## 首次安装

```powershell
Copy-Item .env.example .env
# 编辑 .env，填写模型地址、密钥、聊天模型和嵌入模型

docker compose up -d postgres qdrant neo4j

cd backend
python -m venv .venv
.\.venv\Scripts\pip.exe install -e ".[dev]"
.\.venv\Scripts\alembic.exe upgrade head

cd ..\frontend
npm install
```

已有部署升级前请备份 PostgreSQL，然后执行 `alembic upgrade head`。旧会话继续使用 `assistant`，旧消息无角色归属，旧记忆按会话共享处理，旧文档分别使用 `graph_mode=inherit` 与 `retrieval_mode=auto`。回滚时先关闭新增功能开关并回滚应用；新增表可保留，确需降级时再在备份验证后执行 `alembic downgrade 20260724_0004`。

重试与联网总开关可通过 `LLM_REQUEST_TIMEOUT_SECONDS`、`LLM_MAX_RETRIES`、`LLM_RETRY_BASE_SECONDS` 和 `NETWORK_TOOLS_ENABLED` 配置。建议上线后观察生成错误率、降级率和重试成功率；若重试导致上游请求量明显放大，优先将 `LLM_MAX_RETRIES` 调低至 1 或 0。

默认端口：PostgreSQL `127.0.0.1:5434`，Qdrant Dashboard `http://127.0.0.1:6335/dashboard`，Neo4j Browser `http://127.0.0.1:7475`。

## 启动应用

后端：

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8021
```

前端（另一个终端）：

```powershell
cd frontend
npm run dev
```

访问 `http://127.0.0.1:5173`，首次使用先注册。API 文档位于 `http://127.0.0.1:8021/docs`。

## 常用维护命令

```powershell
docker compose ps
docker compose logs -f postgres qdrant neo4j
docker compose stop
docker compose down
```

`docker compose down` 不删除数据卷。只有明确不再需要数据时才使用 `docker compose down -v`。

## 安全提示

生产环境必须使用 HTTPS，并设置 `COOKIE_SECURE=true`。建议同时把 Session Cookie 名称改为 `__Host-newagent_session`，配置固定的 `ALLOWED_ORIGINS`，并为 PostgreSQL 使用强密码。不要把 `.env` 提交到版本库。
