import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.memory_entry import MemoryEntry
from app.models.vector_outbox import VectorOutbox
from app.services.embedding_service import EmbeddingService
from app.services.qdrant_memory_store import QdrantMemoryStore


FactExtractor = Callable[[str, str], Awaitable[list[str]]]
CandidateExtractor = Callable[
    [str, str, list[dict[str, object]]], Awaitable[list[dict[str, object]]]
]
logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedding_service: EmbeddingService,
        vector_store: QdrantMemoryStore,
        embedding_model: str,
        relevance_threshold: float,
        result_limit: int,
    ) -> None:
        self.session_factory = session_factory
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        self.relevance_threshold = relevance_threshold
        self.result_limit = result_limit

    async def store_facts(
        self,
        facts: list[str],
        source_message_ids: list[int],
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        scope: str = "conversation_shared",
        character_id: uuid.UUID | None = None,
    ) -> list[MemoryEntry]:
        normalized = list(dict.fromkeys(fact.strip() for fact in facts if fact.strip()))
        if not normalized:
            return []
        entries = [
            MemoryEntry(
                user_id=user_id,
                conversation_id=conversation_id,
                content=fact,
                source_message_ids=source_message_ids,
                metadata_json={"kind": "conversation_fact"},
                scope=scope,
                character_id=character_id,
                embedding_model=self.embedding_model,
            )
            for fact in normalized
        ]
        async with self.session_factory() as session:
            async with session.begin():
                session.add_all(entries)
                await session.flush()
                session.add_all(
                    [
                        VectorOutbox(
                            memory_id=entry.id,
                            user_id=user_id,
                            conversation_id=conversation_id,
                            operation="upsert_memory",
                            revision=entry.embedding_revision,
                        )
                        for entry in entries
                    ]
                )
        return entries

    async def extract_and_store(
        self,
        user_content: str,
        assistant_content: str,
        source_message_ids: list[int],
        extractor: FactExtractor,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        scope: str = "conversation_shared",
        character_id: uuid.UUID | None = None,
    ) -> list[MemoryEntry]:
        facts = await extractor(user_content, assistant_content)
        return await self.store_facts(
            facts,
            source_message_ids,
            user_id=user_id,
            conversation_id=conversation_id,
            scope=scope,
            character_id=character_id,
        )

    async def extract_structured_and_store(
        self,
        user_content: str,
        assistant_content: str,
        source_message_ids: list[int],
        extractor: CandidateExtractor,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        scope: str = "conversation_shared",
        character_id: uuid.UUID | None = None,
    ) -> list[MemoryEntry]:
        existing = await self.search(
            user_content, user_id, conversation_id, character_id=character_id
        )
        candidates = await extractor(user_content, assistant_content, existing)
        now = datetime.now(timezone.utc)
        created: list[MemoryEntry] = []
        async with self.session_factory() as session:
            async with session.begin():
                for candidate in candidates:
                    content = str(candidate.get("content") or "").strip()
                    if not content:
                        continue
                    decision = str(candidate.get("decision") or "pending_confirmation")
                    replaced: MemoryEntry | None = None
                    raw_id = candidate.get("replaces_memory_id")
                    if raw_id and decision in {"replace_explicit", "state_change"}:
                        try:
                            replaced_id = uuid.UUID(str(raw_id))
                        except ValueError:
                            replaced_id = None
                        if replaced_id is not None:
                            replaced = await session.scalar(
                                select(MemoryEntry).where(
                                    MemoryEntry.id == replaced_id,
                                    MemoryEntry.user_id == user_id,
                                    MemoryEntry.conversation_id == conversation_id,
                                    MemoryEntry.scope == scope,
                                    MemoryEntry.character_id == character_id,
                                    MemoryEntry.validity == "active",
                                )
                            )
                    validity, replaced_validity = self._candidate_outcome(
                        decision, replaced is not None
                    )
                    accepted = validity == "active"
                    entry = MemoryEntry(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        character_id=character_id,
                        scope=scope,
                        content=content,
                        source_message_ids=source_message_ids,
                        metadata_json={"kind": "conversation_fact", "decision": decision},
                        embedding_model=self.embedding_model,
                        validity=validity,
                        embedding_status="pending" if accepted else "skipped",
                        conflict_reason=str(candidate.get("reason") or "")[:1000] or None,
                        effective_from=now if accepted else None,
                    )
                    session.add(entry)
                    await session.flush()
                    if replaced is not None:
                        replaced.validity = replaced_validity or "superseded"
                        replaced.effective_to = now
                        replaced.superseded_by_id = entry.id
                    if accepted:
                        session.add(
                            VectorOutbox(
                                memory_id=entry.id,
                                user_id=user_id,
                                conversation_id=conversation_id,
                                operation="upsert_memory",
                                revision=entry.embedding_revision,
                            )
                        )
                    created.append(entry)
        return created

    @staticmethod
    def _candidate_outcome(
        decision: str, replacement_found: bool
    ) -> tuple[str, str | None]:
        if decision == "coexist":
            return "active", None
        if decision == "state_change" and replacement_found:
            return "active", "historical"
        if decision == "replace_explicit" and replacement_found:
            return "active", "superseded"
        return "pending_confirmation", None

    async def set_validity(
        self, entry_id: uuid.UUID, user_id: uuid.UUID, validity: str
    ) -> MemoryEntry | None:
        if validity not in {"active", "invalid"}:
            raise ValueError("Unsupported memory validity")
        async with self.session_factory() as session:
            async with session.begin():
                entry = await session.scalar(
                    select(MemoryEntry).where(
                        MemoryEntry.id == entry_id, MemoryEntry.user_id == user_id
                    )
                )
                if entry is None or (validity == "active" and entry.superseded_by_id):
                    return None
                entry.validity = validity
                operation = "upsert_memory" if validity == "active" else "delete_memory"
                entry.embedding_status = "pending" if validity == "active" else "skipped"
                session.add(
                    VectorOutbox(
                        memory_id=entry.id,
                        user_id=entry.user_id,
                        conversation_id=entry.conversation_id,
                        operation=operation,
                        revision=entry.embedding_revision,
                    )
                )
            await session.refresh(entry)
            return entry

    async def confirm_candidate(
        self,
        entry_id: uuid.UUID,
        user_id: uuid.UUID,
        replace_memory_id: uuid.UUID | None = None,
    ) -> MemoryEntry | None:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            async with session.begin():
                entry = await session.scalar(
                    select(MemoryEntry).where(
                        MemoryEntry.id == entry_id,
                        MemoryEntry.user_id == user_id,
                        MemoryEntry.validity == "pending_confirmation",
                    )
                )
                if entry is None:
                    return None
                if replace_memory_id is not None:
                    replaced = await session.scalar(
                        select(MemoryEntry).where(
                            MemoryEntry.id == replace_memory_id,
                            MemoryEntry.user_id == user_id,
                            MemoryEntry.conversation_id == entry.conversation_id,
                            MemoryEntry.scope == entry.scope,
                            MemoryEntry.character_id == entry.character_id,
                            MemoryEntry.validity == "active",
                        )
                    )
                    if replaced is None:
                        return None
                    replaced.validity = "superseded"
                    replaced.effective_to = now
                    replaced.superseded_by_id = entry.id
                entry.validity = "active"
                entry.effective_from = now
                entry.embedding_status = "pending"
                session.add(
                    VectorOutbox(
                        memory_id=entry.id,
                        user_id=entry.user_id,
                        conversation_id=entry.conversation_id,
                        operation="upsert_memory",
                        revision=entry.embedding_revision,
                    )
                )
            await session.refresh(entry)
            return entry

    async def search(
        self,
        query: str,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        character_id: uuid.UUID | None = None,
    ) -> list[dict[str, object]]:
        if not query.strip():
            return []
        vector = await self.embedding_service.embed(query)
        hits = await self.vector_store.search(
            vector,
            user_id=user_id,
            conversation_id=conversation_id,
            limit=self.result_limit,
            score_threshold=self.relevance_threshold,
            character_id=character_id,
        )
        if not hits:
            return []
        score_by_id = dict(hits)
        async with self.session_factory() as session:
            result = await session.execute(
                select(MemoryEntry).where(
                    MemoryEntry.id.in_(score_by_id),
                    MemoryEntry.user_id == user_id,
                    MemoryEntry.conversation_id == conversation_id,
                    MemoryEntry.embedding_status == "ready",
                    MemoryEntry.validity == "active",
                    or_(
                        MemoryEntry.scope == "conversation_shared",
                        (
                            (MemoryEntry.scope == "character_private")
                            & (MemoryEntry.character_id == character_id)
                        ),
                    ),
                )
            )
            entries = list(result.scalars())
        entries.sort(key=lambda item: score_by_id[item.id], reverse=True)
        return [
            {
                "memory_id": str(entry.id),
                "content": entry.content,
                "similarity": score_by_id[entry.id],
                "metadata": entry.metadata_json,
            }
            for entry in entries
        ]

    async def list_entries(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID | None = None
    ) -> list[MemoryEntry]:
        async with self.session_factory() as session:
            statement = select(MemoryEntry).where(MemoryEntry.user_id == user_id)
            if conversation_id is not None:
                statement = statement.where(MemoryEntry.conversation_id == conversation_id)
            result = await session.execute(
                statement.order_by(MemoryEntry.created_at.desc())
            )
            return list(result.scalars())

    async def delete_entry(self, entry_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        async with self.session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(MemoryEntry).where(
                        MemoryEntry.id == entry_id,
                        MemoryEntry.user_id == user_id,
                    )
                )
                entry = result.scalar_one_or_none()
                if entry is None:
                    return False
                session.add(
                    VectorOutbox(
                        memory_id=entry.id,
                        user_id=entry.user_id,
                        conversation_id=entry.conversation_id,
                        operation="delete_memory",
                        revision=entry.embedding_revision,
                    )
                )
                await session.delete(entry)
        return True

    @staticmethod
    def enqueue_conversation_delete(
        session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> None:
        session.add(
            VectorOutbox(
                memory_id=None,
                user_id=user_id,
                conversation_id=conversation_id,
                operation="delete_conversation",
                revision=1,
            )
        )
