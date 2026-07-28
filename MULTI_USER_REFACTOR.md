# 多用户 PostgreSQL + Qdrant + Cookie Session 重构

## 架构结论

- PostgreSQL 是用户、Session、会话、消息、记忆正文、MCP 配置和向量同步状态的唯一事实源。
- Qdrant 是可重建的向量检索索引，不承担账号、权限或最终正文存储。
- 密码使用 Argon2id 哈希；浏览器仅保存 HttpOnly Session Cookie，数据库仅保存 Session Token 的 SHA-256。
- 所有业务数据都从认证依赖取得当前用户，客户端传入的用户 ID 不可信。
- 记忆与向量通过 PostgreSQL outbox 异步同步，避免不可事务化的跨库双写。

## 数据流

### 登录

1. 服务端按规范化用户名读取 `users`。
2. Argon2id 校验密码。
3. 生成随机 Session Token 和 CSRF Token。
4. PostgreSQL 保存 Session Token 哈希及到期时间。
5. 浏览器收到 HttpOnly Session Cookie 和可读 CSRF Cookie。

### 记忆写入

1. 对话完成后异步抽取事实。
2. PostgreSQL 同一事务写入 `memory_entries` 和 `vector_outbox`。
3. Worker 生成 embedding 并 upsert Qdrant。
4. Qdrant Point ID 使用 Memory UUID，payload 保存用户、会话与 revision。
5. Worker 更新 PostgreSQL 的 `embedding_status`。

### 记忆查询

1. 验证会话属于当前用户。
2. 生成查询 embedding。
3. Qdrant 同时过滤 `user_id` 与 `conversation_id`。
4. 使用候选 UUID 回 PostgreSQL 再次按所有权读取正文。

## 本地启动

### 1. 配置环境变量

复制 `.env.example` 为 `.env`，填写聊天模型与 embedding 模型配置。生产环境必须设置 `COOKIE_SECURE=true` 并通过 HTTPS 访问。

### 2. 启动 PostgreSQL 和 Qdrant

在项目根目录运行：

```bash
docker compose up -d postgres qdrant
docker compose ps
```

默认端口：

- PostgreSQL：`localhost:5434`（容器内 `5432`）
- Qdrant HTTP：`http://localhost:6335`（容器内 `6333`）
- Qdrant Dashboard：`http://localhost:6335/dashboard`

停止但保留数据：

```bash
docker compose stop
```

再次启动：

```bash
docker compose start
```

删除容器和数据库卷（会永久清空数据）：

```bash
docker compose down -v
```

### 3. 安装后端并建表

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/alembic upgrade head
```

### 4. 启动后端

从项目根目录运行：

```bash
backend/.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8021 --reload
```

健康检查：`http://127.0.0.1:8021/api/health`。

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`，首次使用时注册账号并登录。

## 生产注意事项

- 必须使用 HTTPS，并设置 `COOKIE_SECURE=true`。
- `ALLOW_REGISTRATION=false` 可关闭公开注册。
- 为 PostgreSQL、Qdrant 和模型 API 使用独立强密码/密钥。
- 备份 PostgreSQL 是恢复业务数据的核心；Qdrant 可以从 PostgreSQL 重新构建。
- 多 Web 实例部署前，建议将 outbox worker 与 MCP 连接管理拆为独立进程。
