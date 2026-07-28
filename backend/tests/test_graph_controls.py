import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import documents as documents_api
from app.models.conversation import Conversation
from app.models.document import Document
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.services.document_knowledge_service import DocumentKnowledgeService
from app.services.memory_service import MemoryService


def test_legacy_defaults_and_chat_payload_remain_compatible() -> None:
    request = ChatRequest(message="hello", conversation_id=uuid.uuid4())

    assert request.allow_network is False
    assert request.client_request_id is None
    assert Conversation.__table__.c.retrieval_mode.default.arg == "auto"
    assert Document.__table__.c.graph_mode.default.arg == "inherit"


def test_legacy_history_message_shape_remains_unchanged() -> None:
    created_at = datetime.now(timezone.utc)
    message = SimpleNamespace(
        id=1,
        role="assistant",
        content="hello",
        status="complete",
        citations=[],
        allow_network=False,
        client_request_id=None,
        created_at=created_at,
    )

    serialized = ChatService.serialize_message(message)  # type: ignore[arg-type]

    assert serialized == {
        "id": 1,
        "role": "assistant",
        "content": "hello",
        "status": "complete",
        "citations": [],
        "allow_network": False,
        "client_request_id": None,
        "created_at": created_at.isoformat(),
    }


class FakeEmbedding:
    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, text: str):
        self.calls += 1
        return [0.1]


class FakeVectorStore:
    async def search(self, **kwargs):
        return []


class FailingGraphStore:
    def __init__(self) -> None:
        self.calls = 0

    async def search(self, query, user_id, limit):
        self.calls += 1
        raise RuntimeError("graph unavailable")


class UnusedSession:
    async def execute(self, statement):
        raise AssertionError("database should not be queried without vector matches")


@pytest.mark.asyncio
async def test_document_retrieval_modes_skip_disabled_services_and_report_degradation() -> None:
    embedding = FakeEmbedding()
    graph = FailingGraphStore()
    service = DocumentKnowledgeService(
        embedding_service=embedding,  # type: ignore[arg-type]
        vector_store=FakeVectorStore(),  # type: ignore[arg-type]
        graph_store=graph,  # type: ignore[arg-type]
        result_limit=5,
        relevance_threshold=0.5,
    )
    user_id = uuid.uuid4()

    assert await service.search(UnusedSession(), "query", user_id, "off") == []  # type: ignore[arg-type]
    assert embedding.calls == 0
    assert await service.search(UnusedSession(), "query", user_id, "vector") == []  # type: ignore[arg-type]
    assert embedding.calls == 1
    assert graph.calls == 0

    degradations: list[str] = []
    assert await service.search(  # type: ignore[arg-type]
        UnusedSession(), "query", user_id, "hybrid", degradations
    ) == []
    assert graph.calls == 1
    assert "document_graph_retrieval_failed" in degradations


def test_document_rerank_prefers_specific_lexical_evidence() -> None:
    formats_query = "NewAgent 支持上传哪些文档格式？"
    formats = {
        "filename": "PERSONAL_GRAPH_RAG.md",
        "section": "目标",
        "content": "用户可以上传 PDF、DOCX、TXT 和 Markdown。",
        "context_text": "用户可以上传 PDF、DOCX、TXT 和 Markdown 文档。",
    }
    generic = {
        "filename": "README.md",
        "section": "架构",
        "content": "文档完成后标记为文本可检索。",
        "context_text": "文档完成后标记为文本可检索。",
    }
    assert DocumentKnowledgeService._lexical_relevance(
        formats_query, formats
    ) > DocumentKnowledgeService._lexical_relevance(formats_query, generic)

    indexing_query = "用户上传文档后会经过哪些主要索引步骤？"
    indexing = {
        "filename": "PERSONAL_GRAPH_RAG.md",
        "section": "写入流程",
        "content": "API 验证上传文件，Worker 分块并写入向量索引。",
        "context_text": "文档 embedding 写入 Qdrant，实体和事实写入 Neo4j。",
    }
    isolation = {
        "filename": "PERSONAL_GRAPH_RAG.md",
        "section": "多用户安全边界",
        "content": "文档按用户隔离，同名实体不会跨用户合并。",
        "context_text": "所有数据库查询都限制当前 user_id。",
    }
    assert DocumentKnowledgeService._lexical_relevance(
        indexing_query, indexing
    ) > DocumentKnowledgeService._lexical_relevance(indexing_query, isolation)


def test_graph_weight_is_high_only_for_explicit_relationship_queries() -> None:
    service = DocumentKnowledgeService(
        embedding_service=None,  # type: ignore[arg-type]
        vector_store=None,  # type: ignore[arg-type]
        graph_store=None,
        result_limit=6,
        relevance_threshold=0.5,
    )

    assert service._route_query("Alice 和 Atlas 之间是什么关系？") == (6, 1.08)
    assert service._route_query("为什么图谱失败后仍能检索？") == (3, 0.45)


def test_document_rerank_uses_failure_terms_instead_of_generic_topic_terms() -> None:
    query = "如果文档的知识图谱构建失败，用户是否还能检索该文档？为什么？"
    failure_handling = {
        "filename": "PERSONAL_GRAPH_RAG.md",
        "section": "写入流程",
        "content": "图谱任务拥有独立失败和重试状态；失败不阻塞文本 RAG。",
        "context_text": "图谱构建失败只降低增强能力，可以重试。",
    }
    overview = {
        "filename": "PERSONAL_GRAPH_RAG.md",
        "section": "目标",
        "content": "系统异步构建文本向量和知识图谱，并联合检索两类证据。",
        "context_text": "用户可以上传文档并使用知识图谱检索。",
    }

    assert DocumentKnowledgeService._lexical_relevance(
        query, failure_handling
    ) > DocumentKnowledgeService._lexical_relevance(query, overview)


class EmptyMemoryEmbedding:
    async def embed(self, text: str):
        return [0.1]


class EmptyMemoryStore:
    async def search(self, *args, **kwargs):
        return []


@pytest.mark.asyncio
async def test_legacy_memory_search_signature_and_empty_result_remain_supported() -> None:
    service = MemoryService(
        session_factory=None,  # type: ignore[arg-type]
        embedding_service=EmptyMemoryEmbedding(),  # type: ignore[arg-type]
        vector_store=EmptyMemoryStore(),  # type: ignore[arg-type]
        embedding_model="test",
        relevance_threshold=0.5,
        result_limit=5,
    )

    assert await service.search("query", uuid.uuid4(), uuid.uuid4()) == []


class AsyncContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeGraphSession(AsyncContext):
    def __init__(self, document, active_event_id=None) -> None:
        self.document = document
        self.active_event_id = active_event_id
        self.added = []

    def begin(self):
        return AsyncContext()

    async def execute(self, statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.document)

    async def scalar(self, statement):
        return self.active_event_id

    def add(self, value):
        self.added.append(value)

    async def refresh(self, value):
        return None


def ready_document(user_id: uuid.UUID):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        original_filename="notes.md",
        media_type="text/markdown",
        byte_size=10,
        status="ready",
        processing_phase="ready",
        graph_mode="disabled",
        graph_status="skipped",
        error_message=None,
        revision=7,
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )


def graph_request(*, available: bool = True):
    service = object() if available else None
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(graph_store=service, graph_extractor=service)
        )
    )


@pytest.mark.asyncio
async def test_graph_build_rejects_unavailable_service_before_database_work() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await documents_api._queue_graph(  # noqa: SLF001
            uuid.uuid4(), user, graph_request(available=False), rebuild=False
        )
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_graph_build_hides_unowned_or_nonready_document(monkeypatch) -> None:
    session = FakeGraphSession(document=None)
    monkeypatch.setattr(documents_api, "SessionLocal", lambda: session)
    user = SimpleNamespace(id=uuid.uuid4())

    with pytest.raises(HTTPException) as exc_info:
        await documents_api._queue_graph(  # noqa: SLF001
            uuid.uuid4(), user, graph_request(), rebuild=False
        )

    assert exc_info.value.status_code == 404
    assert session.added == []


@pytest.mark.asyncio
async def test_graph_build_is_revision_scoped_and_idempotent(monkeypatch) -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    document = ready_document(user.id)
    session = FakeGraphSession(document=document)
    monkeypatch.setattr(documents_api, "SessionLocal", lambda: session)

    result = await documents_api._queue_graph(  # noqa: SLF001
        document.id, user, graph_request(), rebuild=False
    )

    assert result.graph_mode == "enabled"
    assert result.graph_status == "queued"
    assert len(session.added) == 1
    assert session.added[0].revision == document.revision

    duplicate_session = FakeGraphSession(document=document, active_event_id=99)
    monkeypatch.setattr(documents_api, "SessionLocal", lambda: duplicate_session)
    await documents_api._queue_graph(  # noqa: SLF001
        document.id, user, graph_request(), rebuild=True
    )
    assert duplicate_session.added == []
