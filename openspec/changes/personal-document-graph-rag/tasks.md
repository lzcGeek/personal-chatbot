## 1. Infrastructure and Data Model

- [x] 1.1 Add document parsing, multipart and Neo4j dependencies plus environment settings
- [x] 1.2 Add Neo4j service and persistent volume to Docker Compose
- [x] 1.3 Add Document, DocumentChunk and DocumentOutbox models with user ownership and processing states
- [x] 1.4 Add Alembic migration for document knowledge tables

## 2. Document Lifecycle

- [x] 2.1 Implement safe user/document file storage with SHA-256 and configurable size limits
- [x] 2.2 Implement PDF, DOCX, TXT and Markdown parsers with page/section provenance
- [x] 2.3 Implement structure-aware chunking and sentence context windows
- [x] 2.4 Add authenticated upload, list, status, retry and delete APIs

## 3. Vector Document RAG

- [x] 3.1 Create a Qdrant document Collection with user/document/chunk payload indexes
- [x] 3.2 Implement idempotent document indexing and deletion worker stages
- [x] 3.3 Implement filtered document retrieval with PostgreSQL ownership recheck and context expansion
- [x] 3.4 Inject retrieved document evidence into chat and stream structured citations

## 4. Frontend Knowledge Base

- [x] 4.1 Add document API client and Pinia knowledge-base store
- [x] 4.2 Add upload, processing status, retry and delete UI
- [x] 4.3 Display answer citations with filename and page or section

## 5. Knowledge Graph

- [x] 5.1 Initialize Neo4j driver, constraints and health lifecycle
- [x] 5.2 Implement structured entity/fact extraction with source provenance and confidence
- [x] 5.3 Implement idempotent graph upsert, source deletion and orphan cleanup
- [x] 5.4 Implement user-scoped entity linking and bounded graph-path retrieval

## 6. Hybrid Retrieval and Safety

- [x] 6.1 Add query routing, vector/graph evidence fusion, deduplication and reranking
- [x] 6.2 Enforce untrusted-document prompt boundaries and insufficient-evidence behavior
- [x] 6.3 Add document and graph retrieval configuration and operational documentation

## 7. Verification

- [x] 7.1 Add parser, chunker, storage and upload validation tests
- [x] 7.2 Add cross-user document, vector and graph isolation tests
- [x] 7.3 Verify deletion removes file, chunks, vectors and graph facts with retry behavior
- [x] 7.4 Run Alembic, backend tests/import checks, frontend build and end-to-end citation flow
