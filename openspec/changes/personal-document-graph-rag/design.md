## Context

NewAgent 已有多用户 Cookie Session、PostgreSQL 业务事实源、Qdrant 会话记忆索引和 outbox worker。新增个人知识库后，原始文件、文本分块、向量索引和知识图谱将形成四类存储；任何上传、重试和删除都必须按 `user_id + document_id` 可追溯，并且不能让一个用户检索到另一个用户的资料。

Datawhale 的索引优化建议“索引小块、生成时扩展上下文”，并利用文档、章节、页码等元数据先过滤后搜索。GraphRAG 采用知识图谱构建、图检索和增强生成三阶段，同时保留原文证据以避免纯图谱丢失叙述细节。

## Goals / Non-Goals

**Goals:**

- 支持已认证用户上传、查看和删除 PDF、DOCX、TXT、Markdown
- 保留文档、页码、章节、分块和原文的完整溯源
- 使用句子窗口和结构化元数据构建独立 Qdrant 文档索引
- 使用 Neo4j 保存可按来源删除的实体、事实和关系
- 混合向量片段与图路径，生成带引用且证据优先的回答
- 所有跨存储操作可重试、幂等，删除最终覆盖全部副本

**Non-Goals:**

- 第一阶段不处理扫描 PDF OCR、图片理解、音视频和旧 Office `.doc`
- 不允许 LLM 生成并直接执行任意 Python 或不受约束的 Cypher
- 不实现团队共享知识库、公开链接或跨用户图谱融合
- 不在首次版本实现 Microsoft GraphRAG 的完整社区检测和多层社区摘要

## Decisions

### 1. 四层存储职责

- PostgreSQL 保存 documents、document_chunks、处理状态、错误、来源元数据和 outbox，是文档知识的事实源。
- 原始文件保存到按用户和文档 UUID 分层的本地持久化目录；未来可替换为 S3/MinIO。
- Qdrant 使用独立 `document_chunks_v1` Collection，仅保存可重建的向量和过滤 payload，不与聊天记忆混用。
- Neo4j 保存实体与可溯源事实，使用独立持久化卷。

相比只使用 Neo4j，混合存储可以保留解释性原文；相比只使用 Qdrant，图谱能显式表达跨文档实体关系和多跳路径。

### 2. 文档与分块标识

每个文件生成 UUID `document_id`，每个分块生成 UUID `chunk_id`。所有 Qdrant Point、Neo4j Fact、文件路径和 PostgreSQL 记录都携带 `user_id + document_id`。文件内容计算 SHA-256，用于同一用户内的幂等检测，不按文件名判断重复。

### 3. 解析和句子窗口

解析器按 MIME 和扩展名双重校验选择实现：PDF 保留页码，DOCX 保留标题/段落，TXT/Markdown 保留章节。分块以结构边界优先，再按句子和字符预算切分；Embedding 使用精确的中心块，`context_text` 保存相邻块窗口供生成阶段使用。

### 4. 异步索引状态机

上传请求仅完成文件落盘和 PostgreSQL 事务，状态从 `uploaded` 进入 `processing`。Document worker 执行解析、分块、向量化和图谱抽取，并更新 `ready` 或 `failed`。每个阶段使用 revision 和幂等 upsert，避免重试产生重复 Point 或 Fact。

第一阶段允许 worker 与 Web 进程同部署；生产多实例前拆为独立进程。

### 5. 可溯源知识图谱

Neo4j 使用 `User`、`Document`、`Chunk`、`Entity`、`Fact` 节点。事实不直接建成不可溯源的普通边，而是通过 Fact 节点连接主语、谓语和宾语，并保存 `document_id`、`chunk_id`、原文、时间和置信度。共享 Entity 可被多个文档引用；删除文档只删除其 Chunk/Fact，随后清理孤立 Entity。

### 6. 混合检索与回答约束

查询阶段执行：查询理解与实体定位、Qdrant 元数据过滤向量召回、Neo4j 限定用户的一至两跳子图探索、证据合并去重、重排、句子窗口扩展。简单叙述性问题优先文本证据；关系和多跳问题提高图证据权重。

生成 Prompt 明确区分“系统指令”和“不可信文档证据”，要求关键断言引用文件名、页码或章节；证据不足时必须说明无法从知识库确认。

### 7. 删除协议

删除 API 在 PostgreSQL 将文档标记为 `deleting` 并写入 outbox。Worker 依次按 `user_id + document_id` 删除 Qdrant Point、Neo4j Fact/Chunk、原始文件和 PostgreSQL Chunk，成功后将文档标记 `deleted`。每一步可重复执行；部分失败保持 retry 状态，不提前向用户声明全部删除完成。

### 8. 安全边界

限制文件大小、扩展名和 MIME；文件名不参与真实路径拼接；解析在受控库中完成。上传文本作为不可信证据，不能覆盖 System Prompt、触发工具或执行其中的命令。所有列表、下载、检索、状态和删除查询必须带当前 `user_id`。

## Risks / Trade-offs

- [LLM 实体抽取可能产生错误关系] → 保存原文、置信度和来源，回答时同时提供图证据与文本证据
- [Neo4j 增加部署复杂度] → 分阶段交付，文档向量 RAG 可在图服务暂不可用时降级运行
- [解析大型文档耗时且占用内存] → 限制大小、异步处理、按页流式解析并记录失败状态
- [跨存储删除短暂不一致] → PostgreSQL tombstone + outbox 重试，所有检索排除 `deleting/deleted` 文档
- [Embedding 或抽取模型变更] → 保存模型名和 revision，支持按文档重建索引
- [Prompt injection 存在于私人文档] → 明确证据分隔、禁止文档触发工具、输出引用并保留人工核验入口

## Migration Plan

1. 添加依赖、环境变量、Neo4j Compose 服务和持久化卷。
2. 通过 Alembic 新增文档表，不修改现有聊天/记忆数据。
3. 创建 Qdrant 文档 Collection 和 Neo4j 约束。
4. 上线文档上传、解析、向量索引、检索和删除。
5. 再启用图谱抽取与混合检索；图服务不可用时自动退化为向量 RAG。
6. 回滚时停止新 worker 和入口；保留 PostgreSQL 文档记录与文件卷，Qdrant/Neo4j 索引均可重建。

## Open Questions

- 首次版本的单文件大小上限默认设为 25 MB，可通过环境变量调整。
- OCR 与图片型 PDF 留待后续独立能力实现。
- 第一阶段使用当前 OpenAI 兼容模型完成实体关系抽取，后续根据评估结果决定是否引入专用 IE 模型和 Reranker。
