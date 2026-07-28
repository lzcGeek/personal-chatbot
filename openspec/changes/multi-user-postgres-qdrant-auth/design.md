## Context

现有 `MemoryService` 先写 ChromaDB，再写 SQLite，并在关系库失败时补偿删除向量。该方式无法跨存储事务提交。API 没有认证，会话 ID 可被任意调用者读取和修改；MCP Manager 也使用全局工具路由。

## Goals / Non-Goals

**Goals:**
- 支持独立账号登录及可撤销 Cookie Session
- 让 PostgreSQL 成为业务事实源，Qdrant 只承担向量检索
- 在所有查询路径落实用户所有权
- 提供可重复的数据库启动、建表和应用启动流程

**Non-Goals:**
- 迁移旧 SQLite/ChromaDB 数据
- 团队工作区、组织和共享会话
- OAuth、邮箱验证、找回密码和多因素认证
- Redis 或独立任务队列

## Decisions

### 1. 身份与会话
- 密码使用 Argon2id 哈希，数据库只保存 `password_hash`
- Cookie 保存高熵随机 Session Token，PostgreSQL 只保存其 SHA-256
- Cookie 使用 HttpOnly、SameSite=Lax；生产环境必须启用 Secure
- 非安全 HTTP 方法校验双提交 CSRF Token 与 Origin

### 2. 用户边界
- `Conversation.user_id`、`MemoryEntry.user_id`、`McpServer.user_id` 为所有权字段
- `ChatMessage` 通过非空 `conversation_id` 继承所有权
- 路由使用 `resource.id + current_user.id` 联合过滤，禁止先按裸 ID 获取
- 会话和记忆 ID 使用 UUID；消息和 MCP 内部 ID 保留递增整数

### 3. 向量一致性
- 记忆正文只以 PostgreSQL 为准
- 写入记忆和 `vector_outbox` 在同一 PostgreSQL 事务完成
- Worker 使用 `FOR UPDATE SKIP LOCKED` 领取事件并幂等写入 Qdrant
- Qdrant Point ID 等于 `MemoryEntry.id`
- Qdrant payload 至少包含 `user_id`、`conversation_id`、`memory_id` 与 `revision`
- 查询必须同时过滤 `user_id` 与 `conversation_id`，返回 ID 后再从 PostgreSQL读取正文

### 4. 部署与迁移
- 保留 SQLAlchemy 2，使用 asyncpg 与 Alembic，不引入 Tortoise ORM
- Docker Compose 只启动 PostgreSQL 与 Qdrant，前后端继续本地运行
- 首次启动执行 `alembic upgrade head`，应用启动只做连接和 Qdrant collection 检查

## Risks / Trade-offs

- 内置 outbox worker 随 Web 进程运行，适合当前规模；规模扩大后应拆成独立 worker
- MCP 连接仍由单进程管理，多实例部署前需要增加连接归属策略
- 文件型 Skills 目前仍为全局共享资源，但所有修改接口要求登录
- Cookie Secure 在纯 HTTP 本地开发中必须关闭，生产环境必须打开
