import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import conversations as conversations_api
from app.models.compression_job import CompressionJob
from app.models.conversation_state import ConversationState
from app.models.conversation_summary import ConversationSummary
from app.models.memory_entry import MemoryEntry
from app.schemas.conversation import ConversationStateUpdate
from app.services.compression_service import CompressionService
from app.services.context_builder import ContextBuilder
from app.services.memory_service import MemoryService


class AsyncContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class StateSession(AsyncContext):
    def __init__(self, conversation_id: uuid.UUID) -> None:
        self.conversation_id = conversation_id
        self.state = None
        self.ownership_statement = None

    def begin(self):
        return AsyncContext()

    async def scalar(self, statement):
        self.ownership_statement = statement
        return self.conversation_id

    async def get(self, model, key, **kwargs):
        return self.state

    def add(self, value):
        self.state = value

    async def refresh(self, value):
        return None


@pytest.mark.asyncio
async def test_scene_state_rejects_a_stale_revision(monkeypatch) -> None:
    conversation_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    session = StateSession(conversation_id)
    monkeypatch.setattr(conversations_api, "SessionLocal", lambda: session)

    first = await conversations_api.update_conversation_state(
        conversation_id,
        ConversationStateUpdate(
            expected_revision=0,
            state={"location": "gate"},
            source_message_ids=[1],
        ),
        user,
    )

    assert first["revision"] == 1
    assert "FOR UPDATE" in str(session.ownership_statement)
    with pytest.raises(HTTPException) as exc_info:
        await conversations_api.update_conversation_state(
            conversation_id,
            ConversationStateUpdate(
                expected_revision=0,
                state={"location": "tower"},
                source_message_ids=[2],
            ),
            user,
        )
    assert exc_info.value.status_code == 409
    assert session.state.state_json == {"location": "gate"}


def test_scene_state_payload_has_bounded_unique_provenance() -> None:
    with pytest.raises(ValidationError):
        ConversationStateUpdate(
            expected_revision=0,
            state={"location": "gate"},
            source_message_ids=[1, 1],
        )
    with pytest.raises(ValidationError):
        ConversationStateUpdate(
            expected_revision=0,
            state={"notes": "x" * 50_001},
        )


def test_context_budget_keeps_priority_order_and_is_deterministic() -> None:
    sections = [
        ("platform", "platform"),
        ("permissions", "permissions"),
        ("memory", "memory-is-too-large"),
        ("summary", "summary"),
    ]

    first = ContextBuilder._bounded_sections(sections, 31)  # noqa: SLF001
    second = ContextBuilder._bounded_sections(sections, 31)  # noqa: SLF001

    assert first == second
    content, included = first
    assert content == "platform\n\npermissions\n\nsummary"
    assert included == {"platform", "permissions", "summary"}


def test_context_budget_retains_platform_when_even_it_must_be_truncated() -> None:
    content, included = ContextBuilder._bounded_sections(  # noqa: SLF001
        [("platform", "platform-policy"), ("optional", "other")], 5
    )

    assert content == "platf"
    assert included == {"platform"}


class ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


class QuerySession(AsyncContext):
    def __init__(self, rows=None, scalar_value=None) -> None:
        self.rows = rows or []
        self.scalar_value = scalar_value
        self.statements = []
        self.added = []
        self.committed = False

    async def execute(self, statement):
        self.statements.append(statement)
        return ScalarRows(self.rows)

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_value

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_memory_listing_is_scoped_to_owner_and_conversation() -> None:
    session = QuerySession()
    service = MemoryService(
        session_factory=lambda: session,  # type: ignore[arg-type]
        embedding_service=None,  # type: ignore[arg-type]
        vector_store=None,  # type: ignore[arg-type]
        embedding_model="test",
        relevance_threshold=0,
        result_limit=5,
    )

    await service.list_entries(uuid.uuid4(), uuid.uuid4())

    sql = str(session.statements[0])
    assert "memory_entries.user_id" in sql
    assert "memory_entries.conversation_id" in sql


@pytest.mark.asyncio
async def test_summary_regeneration_range_is_validated_and_deduplicated() -> None:
    session = QuerySession(rows=[4, 5, 6], scalar_value=None)
    service = CompressionService(
        session_factory=lambda: session,  # type: ignore[arg-type]
        llm_client=None,  # type: ignore[arg-type]
        trigger_messages=40,
        keep_recent=20,
        poll_seconds=1,
        max_attempts=3,
    )

    queued = await service.enqueue_range(uuid.uuid4(), uuid.uuid4(), 4, 6)

    assert queued is True
    assert isinstance(session.added[0], CompressionJob)
    assert session.committed is True
    assert "chat_messages.status" in str(session.statements[0])


def test_layered_memory_tables_are_removed_with_the_owned_conversation() -> None:
    for model in (MemoryEntry, ConversationSummary, ConversationState, CompressionJob):
        conversation_fk = next(
            fk for fk in model.__table__.c.conversation_id.foreign_keys
            if fk.target_fullname == "conversations.id"
        )
        assert conversation_fk.ondelete == "CASCADE"


def test_legacy_memory_defaults_to_shared_scope_without_a_character() -> None:
    assert MemoryEntry.__table__.c.scope.default.arg == "conversation_shared"
    assert MemoryEntry.__table__.c.character_id.nullable is True


class FakeEmbedding:
    async def embed(self, text):
        return [0.1, 0.2]


class FakeScopedVectorStore:
    def __init__(self, hits) -> None:
        self.hits = hits
        self.kwargs = None

    async def search(self, vector, **kwargs):
        self.kwargs = kwargs
        return self.hits


@pytest.mark.asyncio
async def test_retrieval_query_allows_shared_and_current_character_only() -> None:
    conversation_id = uuid.uuid4()
    user_id = uuid.uuid4()
    character_id = uuid.uuid4()
    shared = SimpleNamespace(
        id=uuid.uuid4(), content="shared", metadata_json={}, scope="conversation_shared"
    )
    private = SimpleNamespace(
        id=uuid.uuid4(), content="private", metadata_json={}, scope="character_private"
    )
    session = QuerySession(rows=[shared, private])
    vectors = FakeScopedVectorStore([(shared.id, 0.9), (private.id, 0.8)])
    service = MemoryService(
        session_factory=lambda: session,  # type: ignore[arg-type]
        embedding_service=FakeEmbedding(),  # type: ignore[arg-type]
        vector_store=vectors,  # type: ignore[arg-type]
        embedding_model="test",
        relevance_threshold=0.1,
        result_limit=5,
    )

    result = await service.search("gate", user_id, conversation_id, character_id)

    sql = str(session.statements[0])
    assert "memory_entries.scope" in sql
    assert "memory_entries.character_id" in sql
    assert "memory_entries.validity" in sql
    assert vectors.kwargs["character_id"] == character_id
    assert [item["content"] for item in result] == ["shared", "private"]


@pytest.mark.asyncio
async def test_summary_listing_is_owner_scoped(monkeypatch) -> None:
    conversation_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    now = datetime.now(timezone.utc)
    summary = SimpleNamespace(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        start_message_id=1,
        end_message_id=8,
        version=2,
        status="complete",
        content="summary",
        error_message=None,
        created_at=now,
        updated_at=now,
    )

    class SummarySession(QuerySession):
        async def scalar(self, statement):
            self.statements.append(statement)
            return conversation_id

    session = SummarySession(rows=[summary])
    monkeypatch.setattr(conversations_api, "SessionLocal", lambda: session)

    response = await conversations_api.list_conversation_summaries(conversation_id, user)

    assert response["summaries"][0]["version"] == 2
    assert "conversations.user_id" in str(session.statements[0])
    assert "conversation_summaries.user_id" in str(session.statements[1])
