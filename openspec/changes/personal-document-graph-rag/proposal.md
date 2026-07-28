## Why

当前系统只能从聊天中抽取会话记忆，不能接收和检索用户自己的 PDF、Word、TXT 等资料，也无法通过实体关系完成跨文档、多跳问答。个人助手需要一套可追溯、可删除、按用户隔离的文档知识库，并让回答尽量由上传资料中的证据支撑。

## What Changes

- 新增多格式文档上传、解析、状态查询、列表和删除能力
- 新增结构化分块、句子窗口、文档元数据和独立 Qdrant 文档索引
- 新增 Neo4j 知识图谱，抽取并保存可溯源的实体、事实和关系
- 新增向量检索与图检索融合、结果去重和重排流程
- 聊天回答注入原文片段与图路径证据，并返回文档、页码和章节引用
- 所有文件、分块、向量和图事实按当前用户隔离，并通过 `document_id` 保持全链路溯源
- 删除文档时通过 PostgreSQL outbox 幂等清理 Qdrant、Neo4j 和原始文件
- 分阶段交付：先实现文档 RAG 基础，再接入 Neo4j 混合 GraphRAG

## Capabilities

### New Capabilities

- `document-knowledge-management`: 文档上传、解析、处理状态、持久化、列表和可恢复删除生命周期
- `document-vector-indexing`: 结构化分块、句子窗口、Embedding、Qdrant 文档索引和元数据过滤
- `knowledge-graph-indexing`: 实体关系抽取、实体归一、事实溯源、Neo4j 存储和按文档清理
- `hybrid-graph-retrieval`: 查询理解、向量与图谱联合检索、重排、引用和证据约束回答

### Modified Capabilities

- `chat-core`: 已认证聊天在生成回答前检索当前用户的个人文档知识，并在结果中携带引用

## Impact

- 后端新增文档 API、文档模型、解析器、索引 worker、GraphRAG 检索与引用模型
- PostgreSQL 新增 documents、document_chunks 和 document_outbox 等表
- Qdrant 新增独立文档 Collection，现有聊天记忆 Collection 保持不变
- Docker Compose 新增 Neo4j 和对应持久化卷
- 前端新增知识库管理界面、上传进度、处理状态、删除和引用展示
- 新增 PDF、Word、multipart 上传与 Neo4j 客户端依赖
- 上传内容被视为不可信数据，需要文件大小/类型校验和提示注入隔离
