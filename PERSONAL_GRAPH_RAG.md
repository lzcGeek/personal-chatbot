# 个人文档 GraphRAG 方案

## 目标

用户可以上传 PDF、DOCX、TXT 和 Markdown。系统保留原文件与可追溯来源，异步构建文本向量和知识图谱；聊天时联合检索两类证据，并返回文件名、页码或章节引用。删除文档时，所有派生数据必须一并删除。

## 数据职责

- PostgreSQL 是事实源：账号、会话、文档元数据、文档分块、处理状态、任务 outbox 和消息引用。
- 本地 `backend/data/documents` 保存原文件，目录按 `user_id/document_id` 隔离。
- Qdrant 保存可重建的文档片段向量，payload 至少包含 `user_id`、`document_id` 和 `chunk_id`。
- Neo4j 保存 `User`、`Document`、`Chunk`、`Entity`、`Fact` 以及来源关系。Fact 保存文档、片段、原文和置信度，不创建失去来源的裸关系。

## 写入流程

1. API 验证 Cookie Session、扩展名、MIME 和大小。
2. 原文件落盘并计算 SHA-256；PostgreSQL 同一事务写入 Document 和 outbox。上传可选择 `inherit`、`enabled` 或 `disabled` 图谱模式；disabled 仍继续文本与向量索引。
3. Worker 解析页码或章节，进行结构分块和相邻句窗口扩展。
4. 片段正文写入 PostgreSQL，embedding 写入 Qdrant；完成后立即提交并将文档标记为文本可检索。
5. 同一事务写入独立的 `index_graph` outbox，图谱 Worker 以受限并发从片段中抽取显式实体与事实，再保存置信度和原文到 Neo4j。
6. 图谱任务拥有独立的排队、处理、失败和重试状态；失败只降低增强能力，可在界面重试，不阻塞文本 RAG、其他文档或删除任务。

## 查询流程

1. 当前用户的问题生成 embedding。
2. Qdrant 必须按 `user_id` 过滤；候选 chunk ID 回 PostgreSQL 再做所有权和文档状态校验。
3. 会话可选择 `auto`、`off`、`vector` 或 `hybrid` 检索模式；关系型问题在允许图检索时提高图谱证据权重。Neo4j 路径检索同样强制按 `user_id` 限制，并限制路径深度。
4. 文本窗口和图事实按相关度、置信度与查询类型融合、去重和重排。
5. 证据以 `<document-evidence>` 边界注入，明确视为不可信资料，不能覆盖系统指令或触发工具。
6. 回答使用 `[Source N]`，消息同时保存结构化 citation，前端可展开查看来源。

关闭或跳过图谱不会关闭文本 RAG。已跳过的文档可以在文本就绪后显式补建或重建图谱；混合检索遇到图服务失败时保留向量证据并报告降级状态。

## 删除与一致性

删除 API 先把文档置为 `deleting` 并写入高优先级 outbox。核心 Worker 优先领取删除任务，并以幂等方式分阶段删除 Qdrant 文档向量、Neo4j Chunk/Fact 和孤立 Entity、本地原文件、PostgreSQL 分块，最后将文档标记为 `deleted`。删除与图谱抽取按文档串行化，避免抽取完成后重新写入已删除数据；任一步失败都会保留任务并指数退避重试，达到上限后显示可重试的删除失败状态。

## 多用户安全边界

- 用户身份只取自服务端 Session，接口不接受客户端指定的 `user_id`。
- PostgreSQL 查询、Qdrant filter 和 Neo4j Cypher 都包含当前 `user_id`。
- 向量命中后仍回 PostgreSQL 校验所有权，不能仅信任 Qdrant payload。
- 同名实体按用户分别链接，不会跨用户合并。

## 当前限制与后续增强

- 扫描版 PDF 尚未包含 OCR，需要后续接入 PaddleOCR 或云 OCR。
- 当前图谱实体链接使用用户内规范化名称；可继续增加别名、实体消歧和人工修正。
- 大文档逐块图谱抽取会消耗模型调用；生产环境可增加批处理、摘要层和成本配额。
- 可继续加入 BM25/稀疏向量、RRF、Cross-Encoder 重排和社区摘要，以提升精确率与全局问题能力。
