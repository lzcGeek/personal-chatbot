import io
import os
import uuid
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import UploadFile
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy import delete, func, select

from app.api.documents import list_documents
from app.core.config import get_settings
from app.core.database import SessionLocal, close_database
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.chat_message import ChatMessage
from app.models.conversation import Conversation
from app.models.user import User
from app.services.document_index_worker import ClaimedEvent, DocumentIndexWorker
from app.services.document_storage import DocumentStorage
from app.services.document_vector_store import DocumentVectorStore
from app.services.document_knowledge_service import DocumentKnowledgeService
from app.services.chat_service import ChatService
from app.services.context_builder import ContextBuilder
from app.services.graph_store import GraphStore
from app.services.llm_client import LlmTurn


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1",
    reason="requires local PostgreSQL, Qdrant and Neo4j",
)


def make_user(user_id: uuid.UUID, prefix: str) -> User:
    return User(
        id=user_id,
        username=f"{prefix}-{user_id}",
        normalized_username=f"{prefix}-{user_id}",
        display_name="Integration test",
        password_hash="test-only",
    )


async def make_qdrant_client(settings) -> AsyncQdrantClient:
    client = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    if not await client.collection_exists(settings.qdrant_document_collection):
        await client.create_collection(
            collection_name=settings.qdrant_document_collection,
            vectors_config=models.VectorParams(
                size=settings.embedding_dimension, distance=models.Distance.COSINE
            ),
        )
    return client


@pytest.mark.asyncio
async def test_full_document_deletion_cleans_all_stores(tmp_path) -> None:
    settings = get_settings()
    user_id, document_id, chunk_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    storage = DocumentStorage(tmp_path / "documents", max_upload_bytes=1024)
    stored = await storage.save_upload(
        UploadFile(filename="delete-me.txt", file=io.BytesIO(b"Alice owns Atlas.")),
        user_id,
        document_id,
        ".txt",
    )
    qdrant = await make_qdrant_client(settings)
    vector_store = DocumentVectorStore(qdrant, settings.qdrant_document_collection)
    graph_store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    document = Document(
        id=document_id,
        user_id=user_id,
        original_filename="delete-me.txt",
        media_type="text/plain",
        sha256=stored.sha256,
        byte_size=stored.byte_size,
        storage_path=str(stored.path),
        status="deleting",
        embedding_model=settings.embedding_model,
    )
    chunk = DocumentChunk(
        id=chunk_id,
        document_id=document_id,
        user_id=user_id,
        ordinal=0,
        content="Alice owns Atlas.",
        context_text="Alice owns Atlas.",
        embedding_status="ready",
    )
    worker = DocumentIndexWorker(
        session_factory=SessionLocal,
        storage=storage,
        parser=None,  # type: ignore[arg-type]
        chunker=None,  # type: ignore[arg-type]
        embedding_service=None,  # type: ignore[arg-type]
        vector_store=vector_store,
        graph_store=graph_store,
        graph_extractor=None,
        poll_seconds=1,
        max_attempts=2,
    )

    try:
        await graph_store.initialize()
        async with SessionLocal() as session:
            session.add(make_user(user_id, "delete"))
            await session.flush()
            session.add_all([document, chunk])
            await session.commit()

        await vector_store.upsert(
            chunk_id, document_id, user_id, 1,
            [0.01] * settings.embedding_dimension, None, None,
        )
        await graph_store.index_document(
            document,
            [chunk],
            {chunk_id: [{
                "subject": "Alice", "subject_type": "Person", "predicate": "owns",
                "object": "Atlas", "object_type": "Project",
                "source_text": "Alice owns Atlas.", "confidence": 1.0,
            }]},
        )

        await worker._delete_document(  # noqa: SLF001
            ClaimedEvent(
                id=0,
                document_id=document_id,
                user_id=user_id,
                operation="delete_document",
                revision=1,
            )
        )

        async with SessionLocal() as session:
            remaining_chunks = await session.scalar(
                select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id)
            )
            deleted_document = await session.get(Document, document_id)
        points, _ = await qdrant.scroll(
            collection_name=settings.qdrant_document_collection,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(
                    key="document_id", match=models.MatchValue(value=str(document_id))
                )]
            ),
            limit=10,
        )

        assert remaining_chunks == 0
        assert deleted_document is not None and deleted_document.status == "deleted"
        assert points == []
        assert await graph_store.search("Alice", user_id) == []
        assert not stored.path.exists()
    finally:
        await vector_store.delete_document(user_id, document_id)
        await graph_store.delete_document(user_id, document_id)
        await graph_store.close()
        await qdrant.close()
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
        await close_database()


@pytest.mark.asyncio
async def test_document_list_and_graph_search_are_user_scoped() -> None:
    settings = get_settings()
    first_user_id, second_user_id = uuid.uuid4(), uuid.uuid4()
    first_document_id, second_document_id = uuid.uuid4(), uuid.uuid4()
    graph_store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    users = [make_user(first_user_id, "isolation"), make_user(second_user_id, "isolation")]
    documents = [
        Document(
            id=document_id,
            user_id=user_id,
            original_filename=filename,
            media_type="text/plain",
            sha256="0" * 64,
            byte_size=1,
            storage_path=f"temporary/{document_id}",
            status="ready",
            embedding_model=settings.embedding_model,
        )
        for user_id, document_id, filename in (
            (first_user_id, first_document_id, "first-user.txt"),
            (second_user_id, second_document_id, "second-user.txt"),
        )
    ]
    chunks = [
        SimpleNamespace(
            id=uuid.uuid4(), ordinal=0, page_number=None, section="Private",
            content=f"Alice owns {secret}.",
        )
        for secret in ("First Secret", "Second Secret")
    ]

    try:
        await graph_store.initialize()
        async with SessionLocal() as session:
            session.add_all(users)
            await session.flush()
            session.add_all(documents)
            await session.commit()

        listed = await list_documents(user=users[0])
        assert [item.id for item in listed] == [first_document_id]

        for document, chunk, secret in zip(
            documents, chunks, ("First Secret", "Second Secret"), strict=True
        ):
            await graph_store.index_document(
                document,
                [chunk],
                {chunk.id: [{
                    "subject": "Alice", "subject_type": "Person", "predicate": "owns",
                    "object": secret, "object_type": "Secret",
                    "source_text": f"Alice owns {secret}.", "confidence": 1.0,
                }]},
            )

        first_results = await graph_store.search("Alice", first_user_id)
        second_results = await graph_store.search("Alice", second_user_id)
        assert {item["document_id"] for item in first_results} == {str(first_document_id)}
        assert {item["document_id"] for item in second_results} == {str(second_document_id)}
    finally:
        await graph_store.delete_document(first_user_id, first_document_id)
        await graph_store.delete_document(second_user_id, second_document_id)
        await graph_store.close()
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id.in_((first_user_id, second_user_id))))
            await session.commit()
        await close_database()


class FixedEmbedding:
    def __init__(self, dimension: int) -> None:
        self.vector = [0.02] * dimension

    async def embed(self, text: str) -> list[float]:
        return self.vector


class NoMemory:
    async def search(self, query, user_id, conversation_id):
        return []

    async def extract_and_store(self, *args, **kwargs):
        return []


class NoTools:
    def openai_tools(self, user_id, allow_network=False):
        return []

    def has_network_tools(self, user_id):
        return False

    def is_network_tool(self, user_id, exposed_name):
        return False


class NoSkills:
    def prompt_section(self, name):
        return None


class CitationLlm:
    async def complete(self, messages, tools=None, temperature=0.7):
        assert "[Source 1]" in messages[0]["content"]
        return LlmTurn(content="该项目采用混合检索。[Source 1]")

    async def extract_facts(self, user_content, assistant_content):
        return []


@pytest.mark.asyncio
async def test_retrieval_to_persisted_chat_citation_flow() -> None:
    settings = get_settings()
    user_id, conversation_id = uuid.uuid4(), uuid.uuid4()
    document_id, chunk_id = uuid.uuid4(), uuid.uuid4()
    qdrant = await make_qdrant_client(settings)
    vector_store = DocumentVectorStore(qdrant, settings.qdrant_document_collection)
    embedding = FixedEmbedding(settings.embedding_dimension)
    user = make_user(user_id, "citation")
    document = Document(
        id=document_id,
        user_id=user_id,
        original_filename="architecture.md",
        media_type="text/markdown",
        sha256="1" * 64,
        byte_size=100,
        storage_path=f"temporary/{document_id}",
        status="ready",
        graph_status="ready",
        embedding_model=settings.embedding_model,
    )
    chunk = DocumentChunk(
        id=chunk_id,
        document_id=document_id,
        user_id=user_id,
        ordinal=0,
        content="该项目采用向量和知识图谱混合检索。",
        context_text="架构说明：该项目采用向量和知识图谱混合检索。",
        section="检索架构",
        embedding_status="ready",
    )

    try:
        async with SessionLocal() as session:
            session.add(user)
            await session.flush()
            session.add(Conversation(id=conversation_id, user_id=user_id, title="Citation"))
            session.add(document)
            await session.flush()
            session.add(chunk)
            await session.commit()

        await vector_store.upsert(
            chunk_id, document_id, user_id, 1, embedding.vector, None, "检索架构"
        )
        knowledge = DocumentKnowledgeService(
            embedding_service=embedding,  # type: ignore[arg-type]
            vector_store=vector_store,
            graph_store=None,
            result_limit=4,
            relevance_threshold=0.1,
        )
        memory = NoMemory()
        tools = NoTools()
        context = ContextBuilder(
            skill_loader=NoSkills(),  # type: ignore[arg-type]
            memory_service=memory,  # type: ignore[arg-type]
            document_knowledge_service=knowledge,
            mcp_manager=tools,  # type: ignore[arg-type]
            recent_message_limit=10,
            max_context_characters=20000,
        )
        chat = ChatService(
            session_factory=SessionLocal,
            llm_client=CitationLlm(),  # type: ignore[arg-type]
            context_builder=context,
            mcp_manager=tools,  # type: ignore[arg-type]
            memory_service=memory,  # type: ignore[arg-type]
            max_tool_rounds=2,
        )

        assistant = await chat.send("项目采用什么检索？", user_id, conversation_id)
        await asyncio.sleep(0)

        assert assistant.citations[0]["filename"] == "architecture.md"
        assert assistant.citations[0]["section"] == "检索架构"
        async with SessionLocal() as session:
            persisted = await session.get(ChatMessage, assistant.id)
        assert persisted is not None and persisted.citations == assistant.citations
    finally:
        await vector_store.delete_document(user_id, document_id)
        await qdrant.close()
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
        await close_database()
