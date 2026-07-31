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
    assert request.include_retrieval_context is False
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


def test_full_retrieval_context_is_transient_and_opt_in() -> None:
    full_context = "表格上下文" * 500
    citations = [
        {
            "chunk_id": str(uuid.uuid4()),
            "excerpt": full_context[:1000],
            "_retrieval_context": full_context,
        }
    ]

    persisted, retrieval_context = ChatService._split_retrieval_context(citations)
    assert persisted == [
        {"chunk_id": citations[0]["chunk_id"], "excerpt": full_context[:1000]}
    ]
    assert retrieval_context == [full_context]
    assert "_retrieval_context" in citations[0]

    created_at = datetime.now(timezone.utc)
    message = SimpleNamespace(
        id=1,
        role="assistant",
        content="answer",
        status="complete",
        citations=persisted,
        allow_network=False,
        client_request_id=None,
        created_at=created_at,
        _retrieval_context=retrieval_context,
    )
    normal = ChatService.serialize_message(message)  # type: ignore[arg-type]
    traced = ChatService.serialize_message(  # type: ignore[arg-type]
        message, include_retrieval_context=True
    )

    assert "retrieval_context" not in normal
    assert traced["retrieval_context"] == [full_context]
    assert traced["citations"] == persisted


class FakeEmbedding:
    def __init__(self) -> None:
        self.calls = 0
        self.last_text = None

    async def embed(self, text: str):
        self.calls += 1
        self.last_text = text
        return [0.1]


class FakeVectorStore:
    def __init__(self) -> None:
        self.last_limit = None

    async def search(self, **kwargs):
        self.last_limit = kwargs["limit"]
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
    vector_store = FakeVectorStore()
    graph = FailingGraphStore()
    service = DocumentKnowledgeService(
        embedding_service=embedding,  # type: ignore[arg-type]
        vector_store=vector_store,  # type: ignore[arg-type]
        graph_store=graph,  # type: ignore[arg-type]
        result_limit=5,
        relevance_threshold=0.5,
        vector_candidate_limit=30,
    )
    user_id = uuid.uuid4()

    assert await service.search(UnusedSession(), "query", user_id, "off") == []  # type: ignore[arg-type]
    assert embedding.calls == 0
    assert await service.search(UnusedSession(), "query", user_id, "vector") == []  # type: ignore[arg-type]
    assert embedding.calls == 1
    assert vector_store.last_limit == 30
    assert graph.calls == 0

    degradations: list[str] = []
    assert await service.search(  # type: ignore[arg-type]
        UnusedSession(), "query", user_id, "hybrid", degradations
    ) == []
    assert graph.calls == 1
    assert "document_graph_retrieval_failed" in degradations


@pytest.mark.asyncio
async def test_document_retrieval_strips_only_trailing_answer_instruction() -> None:
    embedding = FakeEmbedding()
    service = DocumentKnowledgeService(
        embedding_service=embedding,  # type: ignore[arg-type]
        vector_store=FakeVectorStore(),  # type: ignore[arg-type]
        graph_store=None,
        result_limit=6,
        relevance_threshold=0.5,
        vector_candidate_limit=30,
    )
    main_question = "Has the ratio improved between FY2023 and FY2022?"
    full_question = (
        main_question
        + " If this is not a useful metric, then state that and explain why."
    )

    await service.search(  # type: ignore[arg-type]
        UnusedSession(), full_question, uuid.uuid4(), "vector"
    )

    assert embedding.last_text == main_question
    assert DocumentKnowledgeService._retrieval_query(
        "What failed? Which retry eventually succeeded?"
    ) == "What failed? Which retry eventually succeeded?"


def test_english_stop_terms_do_not_inflate_lexical_coverage() -> None:
    terms = DocumentKnowledgeService._lexical_terms(
        "Has AMCOR's quick ratio improved or declined between FY2023 and FY2022?"
    )

    assert terms == {
        "amcor", "quick", "ratio", "improved", "declined", "2023", "2022"
    }
    query_terms = DocumentKnowledgeService._query_lexical_terms(
        "Has AMCOR's quick ratio improved or declined between FY2023 and FY2022?"
    )
    assert query_terms == {"amcor", "quick", "ratio", "2023", "2022"}


def test_retrieval_query_expands_derived_metrics_and_acquisitions() -> None:
    ratio = DocumentKnowledgeService._expand_retrieval_query(
        "Has AMCOR's quick ratio improved between FY2023 and FY2022?"
    )
    acquisitions = DocumentKnowledgeService._expand_retrieval_query(
        "What acquisitions did AMCOR complete?"
    )

    assert "cash equivalents" in ratio
    assert "trade receivables" in ratio
    assert "current liabilities" in ratio
    assert "purchase consideration" in acquisitions
    assert "acquisitions and divestitures" in acquisitions
    assert "equity interest" in acquisitions


def test_filename_match_is_weaker_than_body_match() -> None:
    query = "What acquisitions did AMCOR complete?"
    filename_only = {
        "filename": "AMCOR_acquisitions.pdf",
        "section": None,
        "content": "General company overview.",
        "context_text": "General company overview.",
    }
    body_match = {
        "filename": "AMCOR.pdf",
        "section": "Acquisitions",
        "content": "The company completed an acquisition.",
        "context_text": "Purchase consideration for the acquired business.",
    }

    assert DocumentKnowledgeService._lexical_relevance(
        query, body_match
    ) > DocumentKnowledgeService._lexical_relevance(query, filename_only)


@pytest.mark.asyncio
async def test_missing_graph_store_skips_graph_routing_entirely() -> None:
    class VectorOnlyService(DocumentKnowledgeService):
        def _route_query(self, query: str) -> tuple[int, float]:
            raise AssertionError("graph routing must not run without a graph store")

    service = VectorOnlyService(
        embedding_service=FakeEmbedding(),  # type: ignore[arg-type]
        vector_store=FakeVectorStore(),  # type: ignore[arg-type]
        graph_store=None,
        result_limit=6,
        relevance_threshold=0.5,
        vector_candidate_limit=30,
    )

    assert await service.search(  # type: ignore[arg-type]
        UnusedSession(), "普通文本问题", uuid.uuid4(), "auto"
    ) == []


def test_document_dedup_detects_only_nearby_overlapping_contexts() -> None:
    base = {
        "document_id": "document-a",
        "chunk_id": "chunk-10",
        "chunk_ordinal": 10,
        "page_number": 5,
        "context_text": "alpha beta gamma delta epsilon",
    }
    nearby_overlap = {
        **base,
        "chunk_id": "chunk-11",
        "chunk_ordinal": 11,
        "context_text": "alpha beta gamma delta epsilon",
    }
    distant_overlap = {
        **nearby_overlap,
        "chunk_id": "chunk-30",
        "chunk_ordinal": 30,
    }
    other_document = {
        **nearby_overlap,
        "document_id": "document-b",
    }

    assert DocumentKnowledgeService._is_near_duplicate(nearby_overlap, [base]) is True
    assert DocumentKnowledgeService._is_near_duplicate(distant_overlap, [base]) is False
    assert DocumentKnowledgeService._is_near_duplicate(other_document, [base]) is False


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

    service = DocumentKnowledgeService(
        embedding_service=None,  # type: ignore[arg-type]
        vector_store=None,  # type: ignore[arg-type]
        graph_store=None,
        result_limit=6,
        relevance_threshold=0.45,
    )
    assert service._ranking_score(formats_query, {**formats, "evidence_type": "text", "score": 0.5}) > service._ranking_score(
        formats_query, {**generic, "evidence_type": "text", "score": 0.5}
    )


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
