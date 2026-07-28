## Why

当前系统使用全局 SQLite、ChromaDB 和无认证 API。会话、消息、记忆与 MCP 服务都没有用户所有权，无法安全支持多个账号；ChromaDB 与 SQLite 的先后双写也无法形成事务。

## What Changes

- 新增 PostgreSQL 用户、服务端会话、业务数据和向量 outbox 模型
- 新增 Argon2id 密码哈希与 HttpOnly Cookie Session 登录
- 会话、消息、记忆和 MCP 服务按当前用户隔离
- 用显式 Embedding 服务与 Qdrant 替换 ChromaDB
- PostgreSQL 作为事实源，Qdrant 作为可重建索引，使用 outbox 可靠同步
- 新增登录/注册界面、Docker Compose 和部署文档
- 不迁移原 SQLite/ChromaDB 数据

## Capabilities

### New Capabilities
- `user-authentication`: 注册、登录、退出、当前用户和服务端会话管理
- `user-data-isolation`: 所有用户业务数据和工具配置按所有者隔离
- `vector-memory-storage`: PostgreSQL 记忆事实源、Qdrant 检索索引与 outbox 同步
- `database-deployment`: PostgreSQL 与 Qdrant 的容器化启动和健康检查

### Modified Capabilities
- `conversation-management`: 会话 CRUD 只作用于当前用户
- `chat-core`: 聊天和历史接口必须验证会话所有权
- `chat-memory`: 记忆按用户及会话过滤，删除通过 outbox 清理 Qdrant
- `mcp-integration`: MCP 服务及工具路由按用户隔离

## Impact

- 后端数据模型、认证依赖、路由、聊天服务、记忆服务和 MCP 管理器
- 前端登录状态、Cookie/CSRF 请求和 UUID 会话 ID
- 依赖、环境变量、Alembic 初始化迁移和 Docker Compose
- 原 SQLite 与 ChromaDB 运行目录不再被应用使用
