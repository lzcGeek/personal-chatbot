# 项目启动指南

当前项目使用以下服务：

- PostgreSQL：保存账号、Session、会话、消息、文档元数据、分块正文和处理任务
- Qdrant：保存可重建的会话记忆与文档向量索引
- Neo4j：保存带文档来源的实体、事实和关系图谱
- 本地文档目录：保存上传的 PDF、DOCX、TXT 和 Markdown 原文件
- FastAPI：后端 API，端口 `8021`
- Vue 3 + Vite：前端，端口 `5173`

默认数据库端口：

- PostgreSQL：`127.0.0.1:5434`
- Qdrant HTTP：`http://127.0.0.1:6335`
- Qdrant Dashboard：`http://127.0.0.1:6335/dashboard`
- Neo4j Browser：`http://127.0.0.1:7475`
- Neo4j Bolt：`bolt://127.0.0.1:7688`

> 项目使用独立的 `5434`、`6335/6336`、`7475/7688` 端口，不会占用这些数据库的常见默认端口。

## 现在如何完整启动（直接照着执行）

适用于项目已经安装过依赖、`.env` 和 `backend\.venv` 已存在的情况。先启动 Docker Desktop，然后打开三个 PowerShell 终端。下面三段命令不要全部粘贴到同一个终端，因为后端和前端命令会持续运行。

### 终端 1：启动三个数据库

```powershell
cd <项目根目录>
docker compose up -d postgres qdrant neo4j
docker compose ps
```

正常情况下应看到：

- `newagent-postgres-1`：`Up` 或 `healthy`
- `newagent-qdrant-1`：`Up` 或 `healthy`
- `newagent-neo4j-1`：`Up`

如果镜像已经下载过，这一步通常只需要几秒。数据库启动后，这个终端可以关闭；容器会继续在后台运行。

### 终端 2：升级数据库表并启动后端

```powershell
cd <项目根目录>\backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8021 --reload
```

看到下面两类信息表示后端启动成功：

```text
Uvicorn running on http://127.0.0.1:8021
Application startup complete.
```

这个终端必须保持打开。可以在浏览器检查：

- 健康检查：`http://127.0.0.1:8021/api/health`
- API 文档：`http://127.0.0.1:8021/docs`

健康检查应返回：

```json
{"status":"ok"}
```

### 终端 3：启动前端

```powershell
cd <项目根目录>\frontend
npm run dev
```

看到 `Local: http://localhost:5173/` 后保持该终端打开，然后访问：

`http://localhost:5173`

登录后点击右上角设置按钮，可以进入“知识库”上传文档。文档状态变为“文本可检索”后即可在聊天中提问；变为“图谱完成”后会同时使用 Neo4j 关系检索。

角色、群聊、记忆压缩、图片和 TTS 默认关闭。升级数据库后，按 `NPC_RUNTIME.md` 的分阶段顺序修改 `.env`，每次重启后端使开关生效。图片/TTS 未配置时不会阻止后端启动或文本聊天。

### 启动失败时快速检查

```powershell
cd <项目根目录>
docker compose ps
docker compose logs --tail 100 postgres qdrant neo4j
```

再检查端口：

```powershell
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in 5173, 8021, 5434, 6335, 7475, 7688 } |
  Select-Object LocalAddress, LocalPort, OwningProcess
```

如果提示找不到 `.venv`、依赖或 `.env`，不要继续日常启动，先执行下一节的“首次启动”。

## 一、首次启动

以下命令均在 Windows PowerShell 中执行。

### 1. 配置环境变量

在项目根目录执行：

```powershell
cd <项目根目录>
Copy-Item .env.example .env
```

如果 `.env` 已经存在，不要覆盖。确认其中已经填写：

```env
OPENAI_BASE_URL=你的模型接口地址
OPENAI_API_KEY=你的模型密钥
OPENAI_MODEL=聊天模型名称

EMBEDDING_BASE_URL=你的 Embedding 接口地址
EMBEDDING_API_KEY=你的 Embedding 密钥
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536
EMBEDDING_REQUEST_TIMEOUT_SECONDS=60
EMBEDDING_MAX_RETRIES=2

DOCUMENT_WORKER_CONCURRENCY=2
DOCUMENT_EMBEDDING_BATCH_SIZE=8
DOCUMENT_EMBEDDING_CONCURRENCY=4
```

`DATABASE_URL` 和 `QDRANT_URL` 未填写时会使用项目内的本地默认值。

以上文档并发参数表示：最多同时索引 2 份文档，每次 Embedding 请求携带 8 个 Chunk，所有文档合计最多同时发出 4 个 Embedding 请求。当前所用兼容接口要求单批不超过 10，因此默认使用 8；供应商返回批量上限错误时，Worker 还会自动二分批次继续处理。若上游返回 `429`，优先把 `DOCUMENT_EMBEDDING_CONCURRENCY` 降为 `2`；不要直接把三个参数同时调大。

### 2. 启动 PostgreSQL、Qdrant 和 Neo4j

先启动 Docker Desktop 或你本机使用的 Docker 引擎，然后在项目根目录执行：

```powershell
cd <项目根目录>
docker compose up -d postgres qdrant neo4j
docker compose ps
```

首次执行可能需要下载镜像。看到三个服务都为 `running` 或 `healthy` 后再继续。Neo4j Browser 的本地默认登录是 `neo4j` / `newagent-graph`，生产环境必须修改密码。

### 3. 安装后端依赖并建表

```powershell
cd <项目根目录>\backend

# 仅在 backend/.venv 不存在时创建
python -m venv .venv

.\.venv\Scripts\pip.exe install -e ".[dev]"
.\.venv\Scripts\alembic.exe upgrade head
```

`alembic upgrade head` 会在 PostgreSQL 中创建或升级表结构，不需要手动执行 SQL。

### 4. 安装前端依赖

```powershell
cd <项目根目录>\frontend
npm install
```

## 二、日常启动

每次开发启动需要三个终端。

### 终端 1：数据库

```powershell
cd <项目根目录>
docker compose up -d postgres qdrant neo4j
docker compose ps
```

### 终端 2：后端

```powershell
cd <项目根目录>\backend
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8021 --reload
```

后端地址：`http://127.0.0.1:8021`

- API 文档：`http://127.0.0.1:8021/docs`
- 健康检查：`http://127.0.0.1:8021/api/health`

### 终端 3：前端

```powershell
cd <项目根目录>\frontend
npm run dev
```

前端地址：`http://localhost:5173`

首次打开页面时注册账号，之后使用账号密码登录。前端通过 Cookie Session 调用后端，无需手动填写 Token。

## 三、停止服务

### 推荐：按顺序优雅关闭

1. 在前端终端按 `Ctrl+C`。
2. 在后端终端按 `Ctrl+C`，等待 Uvicorn 输出关闭完成。
3. 停止 PostgreSQL、Qdrant 和 Neo4j：

```powershell
cd <项目根目录>
docker compose stop
```

`docker compose stop` 只停止容器，不删除 PostgreSQL、Qdrant 或 Neo4j 数据。

### 找不到终端时：统一关闭整个应用

下面的命令会关闭监听 `5173` 的前端和监听 `8021` 的后端，然后安全停止数据库容器：

```powershell
cd <项目根目录>

$appPorts = 5173, 8021
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in $appPorts } |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object {
    Stop-Process -Id $_ -ErrorAction SilentlyContinue
  }

docker compose stop
```

下次可以使用 `docker compose start`，也可以直接执行 `docker compose up -d postgres qdrant neo4j`。

### 直接关机时数据是否保留

会保留。当前数据库使用 Docker 命名卷持久化：

- PostgreSQL：`newagent_newagent_postgres_data`
- Qdrant：`newagent_newagent_qdrant_data`
- Neo4j：`newagent_newagent_neo4j_data`
- 上传原文件：`<项目根目录>\backend\data\documents`
- 生成媒体：`<项目根目录>\backend\data\media`

关机、重启电脑、停止 Docker Desktop、执行 `docker compose stop`，以及执行不带 `-v` 的 `docker compose down`，都不会删除这些数据卷。下次启动容器后，账号、聊天记录、记忆正文和向量索引仍然存在。

如果电脑在数据库写入过程中突然断电，PostgreSQL 通常会通过 WAL 自动恢复，Qdrant 也会从持久化存储重新加载；但任何程序在异常断电时都存在少量未完成写入或文件系统损坏风险。因此正常情况下建议先执行上述关闭命令，再关机。

删除容器但保留数据卷：

```powershell
docker compose down
```

> 不要随意执行 `docker compose down -v`。其中 `-v` 会永久删除 PostgreSQL、Qdrant 和 Neo4j 数据卷。上传原文件位于宿主机目录，不会被该命令删除，但失去数据库元数据后也不能正常使用。

## 四、常用检查命令

查看容器状态：

```powershell
docker compose ps
```

查看数据库日志：

```powershell
docker compose logs -f postgres qdrant neo4j
```

查看当前数据库迁移版本：

```powershell
cd <项目根目录>\backend
.\.venv\Scripts\alembic.exe current
```

检查 Qdrant：浏览器访问 `http://127.0.0.1:6335/dashboard`。

检查 Neo4j：浏览器访问 `http://127.0.0.1:7475`，本地 Bolt 地址填写 `bolt://127.0.0.1:7688`。

## 五、文档知识库使用方法

1. 登录后点击右上角设置按钮，进入“知识库”。
2. 上传 PDF、DOCX、TXT 或 Markdown，单文件默认不超过 25 MB。
3. 状态变成“文本可检索”后即可在聊天中提问；显示“图谱完成”后还会参与关系和多跳检索。
4. 回答下方的“参考了 N 处个人资料”可展开查看文件名、页码或章节和原文片段。
5. 删除文档会异步删除原文件、PostgreSQL 分块、Qdrant 向量和 Neo4j 来源事实；“删除中”消失后才表示完整删除。

PDF 默认使用 `PDF_PARSER_MODE=auto`：普通页面使用 pypdf Layout，检测到表格时使用 pdfplumber 提取成保留表头和行列的 Markdown；表格提取异常会自动降级为 Layout 文本。若只需要文本布局解析，可在 `.env` 设置 `PDF_PARSER_MODE=layout` 后重启后端。

解析器或切块配置改变后，已经完成索引的文档不会自动变化。当前需要删除旧文档并重新上传，才能重新解析、分块、向量化并按需重建图谱。

扫描版 PDF 当前没有内置 OCR，若 PDF 只有图片而没有文本层，处理会提示“未找到可提取文本”。

## 六、生产环境注意事项

- 必须通过 HTTPS 提供服务，并设置 `COOKIE_SECURE=true`。
- 设置 `ALLOW_REGISTRATION=false` 可关闭公开注册。
- PostgreSQL 密码、Qdrant API Key 和模型密钥应使用强随机值。
- Neo4j 密码必须改为强随机值，并且不要把 7474/7687 直接暴露到公网。
- 不要提交 `.env` 文件。
- PostgreSQL 是业务数据的事实来源，应定期备份；Qdrant 索引可以从 PostgreSQL 重建。
