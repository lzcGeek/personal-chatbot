# NPC Runtime：架构、API 与运维

## 兼容与安全边界

普通会话默认保持 `assistant`。角色资料、文档证据和模型输出都按不可信内容处理；工具、联网、知识库与媒体能力取服务器、会话、请求和角色权限的交集。角色无法通过人设扩大权限。PostgreSQL 保存角色、计划、记忆、摘要和媒体任务事实；Qdrant/Neo4j 与媒体文件均为可重建或可清理的派生数据。

群聊先持久化 `speaker_plan`，再严格按索引顺序生成。每个回复与 `(speaker_plan_id, speaker_plan_index)` 唯一绑定；失败重试从未完成索引继续，不重复已完成角色。自动路由只接受当前启用成员 ID，未知或重复输出使用确定性 fallback，日志只记录 reason code，不保存模型隐式推理。

长对话保留最近原文，并异步生成带连续消息边界和版本号的摘要。只有成功摘要进入上下文。结构化记忆使用混合冲突策略，场景状态使用 revision 乐观并发控制。

## 主要 API

| 功能 | API |
|---|---|
| 角色 CRUD、复制、归档、头像 | `/api/characters`、`/api/characters/{id}/avatar` |
| 会话模式与运行设置 | `PATCH /api/conversations/{id}/settings` |
| 会话成员 | `GET/PUT /api/conversations/{id}/members` |
| 场景状态 | `GET/PUT /api/conversations/{id}/state` |
| 记忆确认、失效、恢复、删除 | `/api/memories` |
| 摘要列表、重建、删除 | `/api/conversations/{id}/summaries` |
| 路由聊天参数 | `target_character_id`、`max_speakers`（`/api/chat/send|stream`） |
| 媒体能力 | `GET /api/media/capabilities` |
| 图片/TTS 任务 | `POST /api/media/messages/{message_id}/image|tts` |
| 任务状态与 SSE | `/api/media/tasks/{id}`、`/api/media/tasks/{id}/events` |
| 私有附件 | `/api/media/messages/{id}/attachments`、`/api/media/attachments/{id}` |
| 总体功能开关 | `GET /api/runtime-capabilities` |

Swagger 的请求/响应 schema 以运行中的 `/docs` 为准。Provider API Key、内部存储路径和隐藏推理不会出现在能力响应中。

## 分阶段启用

1. 备份 PostgreSQL，部署兼容代码，执行 `alembic upgrade head`；保持全部新增开关为 `false`。
2. 设置 `SINGLE_NPC_ENABLED=true`，验证角色 CRUD、权限与单角色历史。
3. 设置 `MEMORY_COMPRESSION_ENABLED=true`，观察摘要成功率和上下文裁剪指标；原始消息不会删除。
4. 设置 `GROUP_NPC_ENABLED=true`，先使用手动/提及，再开放轮询与自动路由；保持较小的服务器角色上限。
5. 单独配置并启用 `IMAGE_GENERATION_ENABLED` 或 `TTS_ENABLED`。Provider endpoint/key 仅由管理员环境变量提供；角色 profile 必须出现在允许列表。

开关互相独立。图片失败不影响 TTS 或文本，压缩关闭不影响原始历史与结构化记忆，群聊关闭不影响单 NPC，全部关闭时行为等同普通助手。

## 回滚

优先执行逻辑回滚：把五个功能开关设为 `false`，重启后端，再回滚前后端应用版本。新增表和可空列可暂时保留，不影响旧版本读取既有核心表。

确需回滚数据库时，先备份并在副本验证：`alembic downgrade 20260724_0004` 会移除角色、分层记忆、群聊计划和媒体任务表，可能丢失新增数据。Qdrant/Neo4j 索引可以从 PostgreSQL 重建；`backend/data/media` 可在确认不再需要后单独归档或清理。不要在未备份的生产库直接降级。

## 发布检查

- `python -m pytest -q tests`
- `npm test` 与 `npm run build`
- `alembic heads` 只能有一个 head
- 使用 `alembic upgrade head --sql` 与 `alembic downgrade head:base --sql` 验证双向脚本
- 有本地 PostgreSQL/Qdrant/Neo4j 时运行文档删除、向量隔离和 GraphRAG 集成测试
