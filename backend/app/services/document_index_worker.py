import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import case, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_outbox import DocumentOutbox
from app.services.document_chunker import DocumentChunker
from app.services.document_parser import DocumentParser
from app.services.document_storage import DocumentStorage
from app.services.document_vector_store import DocumentVectorStore
from app.services.embedding_service import EmbeddingService
from app.services.graph_extractor import GraphExtractor
from app.services.graph_store import GraphStore


logger = logging.getLogger(__name__)

CORE_OPERATIONS = ("delete_document", "process_document")
GRAPH_OPERATIONS = ("index_graph",)


@dataclass(frozen=True)
class ClaimedEvent:
    id: int
    document_id: uuid.UUID
    user_id: uuid.UUID
    operation: str
    revision: int


class DocumentIndexWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: DocumentStorage,
        parser: DocumentParser,
        chunker: DocumentChunker,
        embedding_service: EmbeddingService,
        vector_store: DocumentVectorStore,
        graph_store: GraphStore | None,
        graph_extractor: GraphExtractor | None,
        poll_seconds: float,
        max_attempts: int,
        graph_concurrency: int = 4,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.parser = parser
        self.chunker = chunker
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.graph_extractor = graph_extractor
        self.poll_seconds = poll_seconds
        self.max_attempts = max_attempts
        self.graph_concurrency = graph_concurrency
        self._tasks: list[asyncio.Task[None]] = []
        self._document_locks: dict[uuid.UUID, asyncio.Lock] = {}

    def start(self) -> None:
        if any(not task.done() for task in self._tasks):
            return
        self._tasks = [
            asyncio.create_task(
                self._run(CORE_OPERATIONS), name="document-core-worker"
            ),
            asyncio.create_task(
                self._run(GRAPH_OPERATIONS), name="document-graph-worker"
            ),
        ]

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _run(self, operations: tuple[str, ...]) -> None:
        await self._recover_interrupted(operations)
        while True:
            try:
                processed = await self._process_one(operations)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Document worker iteration failed for %s", operations)
                processed = False
            if not processed:
                await asyncio.sleep(self.poll_seconds)

    async def _recover_interrupted(self, operations: tuple[str, ...]) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(DocumentOutbox)
                    .where(
                        DocumentOutbox.operation.in_(operations),
                        DocumentOutbox.status == "processing",
                    )
                    .values(status="pending", next_retry_at=datetime.now(timezone.utc))
                )

    async def _process_one(self, operations: tuple[str, ...]) -> bool:
        event = await self._claim_event(operations)
        if event is None:
            return False
        try:
            if event.operation == "process_document":
                await self._process_document(event)
            elif event.operation == "index_graph":
                await self._index_graph(event)
            elif event.operation == "delete_document":
                await self._delete_document(event)
            else:
                raise ValueError(f"Unknown document operation: {event.operation}")
        except asyncio.CancelledError:
            await self._release_event(event.id)
            raise
        except Exception as exc:
            await self._fail_event(event, exc)
        else:
            await self._complete_event(event.id)
        return True

    async def _claim_event(
        self, operations: tuple[str, ...]
    ) -> ClaimedEvent | None:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            async with session.begin():
                priority = case(
                    (DocumentOutbox.operation == "delete_document", 0),
                    (DocumentOutbox.operation == "process_document", 1),
                    else_=2,
                )
                event = (
                    await session.execute(
                        select(DocumentOutbox)
                        .where(
                            DocumentOutbox.operation.in_(operations),
                            DocumentOutbox.status == "pending",
                            DocumentOutbox.next_retry_at <= now,
                        )
                        .order_by(priority, DocumentOutbox.id)
                        .with_for_update(skip_locked=True)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if event is None:
                    return None
                event.status = "processing"
                return ClaimedEvent(
                    id=event.id,
                    document_id=event.document_id,
                    user_id=event.user_id,
                    operation=event.operation,
                    revision=event.revision,
                )

    async def _process_document(self, event: ClaimedEvent) -> None:
        async with self._lock_for(event.document_id):
            document = await self._get_current_document(event)
            if document is None or document.status in {"deleting", "deleted"}:
                return

            await self._set_text_phase(event, "processing", "parsing")
            extension = Path(document.storage_path).suffix.lower()
            units = await asyncio.to_thread(
                self.parser.parse, Path(document.storage_path), extension
            )
            prepared = self.chunker.chunk(units)
            if not prepared:
                raise ValueError("Document parser produced no indexable chunks")

            await self._set_text_phase(event, "processing", "chunking")
            await self.vector_store.delete_document(event.user_id, event.document_id)

            chunks = [
                DocumentChunk(
                    id=uuid.uuid4(),
                    document_id=event.document_id,
                    user_id=event.user_id,
                    ordinal=item.ordinal,
                    content=item.content,
                    context_text=item.context_text,
                    page_number=item.page_number,
                    section=item.section,
                    metadata_json=item.metadata,
                    embedding_revision=event.revision,
                )
                for item in prepared
            ]
            async with self.session_factory() as session:
                async with session.begin():
                    current = await self._locked_current_document(session, event)
                    if current is None or current.status in {"deleting", "deleted"}:
                        return
                    await session.execute(
                        delete(DocumentChunk).where(
                            DocumentChunk.document_id == event.document_id
                        )
                    )
                    session.add_all(chunks)
                    current.status = "processing"
                    current.processing_phase = "embedding"
                    current.error_message = None

            for chunk in chunks:
                vector = await self.embedding_service.embed(chunk.content)
                await self.vector_store.upsert(
                    chunk.id,
                    event.document_id,
                    event.user_id,
                    event.revision,
                    vector,
                    chunk.page_number,
                    chunk.section,
                )

            async with self.session_factory() as session:
                async with session.begin():
                    current = await self._locked_current_document(session, event)
                    if current is None or current.status in {"deleting", "deleted"}:
                        return
                    await session.execute(
                        update(DocumentChunk)
                        .where(
                            DocumentChunk.document_id == event.document_id,
                            DocumentChunk.embedding_revision == event.revision,
                        )
                        .values(embedding_status="ready")
                    )
                    current.status = "ready"
                    current.processing_phase = "ready"
                    current.error_message = None
                    graph_status = self._graph_disposition(current.graph_mode)
                    current.graph_status = graph_status
                    if graph_status == "queued":
                        active = await session.scalar(
                            select(DocumentOutbox.id).where(
                                DocumentOutbox.document_id == event.document_id,
                                DocumentOutbox.user_id == event.user_id,
                                DocumentOutbox.operation == "index_graph",
                                DocumentOutbox.revision == event.revision,
                                DocumentOutbox.status.in_(("pending", "processing")),
                            )
                        )
                        if active is None:
                            session.add(
                                DocumentOutbox(
                                    document_id=event.document_id,
                                    user_id=event.user_id,
                                    operation="index_graph",
                                    revision=event.revision,
                                )
                            )

    async def _index_graph(self, event: ClaimedEvent) -> None:
        if self.graph_store is None or self.graph_extractor is None:
            document = await self._get_current_document(event)
            status = (
                "unavailable"
                if document is not None and document.graph_mode == "enabled"
                else "disabled"
            )
            await self._set_graph_status(event, status, None)
            return

        async with self.session_factory() as session:
            document = await session.get(Document, event.document_id)
            if (
                not self._is_current(document, event)
                or document.status != "ready"
                or document.graph_mode == "disabled"
            ):
                if self._is_current(document, event) and document.graph_mode == "disabled":
                    document.graph_status = "skipped"
                    await session.commit()
                return
            result = await session.execute(
                select(DocumentChunk)
                .where(
                    DocumentChunk.document_id == event.document_id,
                    DocumentChunk.user_id == event.user_id,
                    DocumentChunk.embedding_revision == event.revision,
                    DocumentChunk.embedding_status == "ready",
                )
                .order_by(DocumentChunk.ordinal)
            )
            chunks = list(result.scalars())

        if not chunks:
            raise ValueError("No ready document chunks are available for graph indexing")
        await self._set_graph_status(event, "processing", None)

        facts_by_chunk = await self._extract_graph_facts(chunks)

        # Only serialize the final graph write with deletion. Expensive LLM extraction
        # remains outside this lock so delete requests can complete immediately.
        async with self._lock_for(event.document_id):
            document = await self._get_current_document(event)
            if document is None or document.status != "ready":
                return
            await self.graph_store.delete_document(event.user_id, event.document_id)
            await self.graph_store.index_document(document, chunks, facts_by_chunk)
            await self._set_graph_status(event, "ready", None)

    async def _extract_graph_facts(
        self, chunks: list[DocumentChunk]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        if self.graph_extractor is None:
            return {}
        semaphore = asyncio.Semaphore(self.graph_concurrency)

        async def extract(chunk: DocumentChunk) -> tuple[uuid.UUID, list[dict[str, Any]]]:
            async with semaphore:
                return chunk.id, await self.graph_extractor.extract(chunk.content)

        return dict(await asyncio.gather(*(extract(chunk) for chunk in chunks)))

    async def _delete_document(self, event: ClaimedEvent) -> None:
        async with self._lock_for(event.document_id):
            document = await self._get_owned_document(event)
            if document is None:
                return

            await self._set_delete_phase(event, "deleting_vectors")
            await self.vector_store.delete_document(event.user_id, event.document_id)

            await self._set_delete_phase(event, "deleting_graph")
            if self.graph_store is not None:
                await self.graph_store.delete_document(event.user_id, event.document_id)

            await self._set_delete_phase(event, "deleting_file")
            await asyncio.to_thread(self.storage.delete, event.user_id, event.document_id)

            async with self.session_factory() as session:
                async with session.begin():
                    document = await session.get(Document, event.document_id)
                    if document is None or document.user_id != event.user_id:
                        return
                    await session.execute(
                        delete(DocumentChunk).where(
                            DocumentChunk.document_id == event.document_id
                        )
                    )
                    document.status = "deleted"
                    document.processing_phase = "deleted"
                    document.graph_status = "deleted"
                    document.deleted_at = datetime.now(timezone.utc)
                    document.error_message = None

    async def _set_text_phase(
        self, event: ClaimedEvent, status: str, phase: str
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                document = await self._locked_current_document(session, event)
                if document is None or document.status in {"deleting", "deleted"}:
                    return
                document.status = status
                document.processing_phase = phase
                document.error_message = None

    async def _set_graph_status(
        self, event: ClaimedEvent, status: str, error: str | None
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                document = await self._locked_current_document(session, event)
                if document is None or document.status in {"deleting", "deleted"}:
                    return
                document.graph_status = status
                document.error_message = error

    async def _set_delete_phase(self, event: ClaimedEvent, phase: str) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                document = await session.get(Document, event.document_id, with_for_update=True)
                if document is None or document.user_id != event.user_id:
                    return
                document.status = "deleting"
                document.processing_phase = phase

    async def _get_current_document(self, event: ClaimedEvent) -> Document | None:
        async with self.session_factory() as session:
            document = await session.get(Document, event.document_id)
            return document if self._is_current(document, event) else None

    async def _get_owned_document(self, event: ClaimedEvent) -> Document | None:
        async with self.session_factory() as session:
            document = await session.get(Document, event.document_id)
            return document if document is not None and document.user_id == event.user_id else None

    async def _locked_current_document(
        self, session: AsyncSession, event: ClaimedEvent
    ) -> Document | None:
        document = await session.get(Document, event.document_id, with_for_update=True)
        return document if self._is_current(document, event) else None

    @staticmethod
    def _is_current(document: Document | None, event: ClaimedEvent) -> bool:
        return (
            document is not None
            and document.user_id == event.user_id
            and document.revision == event.revision
        )

    async def _complete_event(self, event_id: int) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                event = await session.get(DocumentOutbox, event_id, with_for_update=True)
                if event is not None and event.status == "processing":
                    event.status = "done"
                    event.completed_at = datetime.now(timezone.utc)
                    event.last_error = None

    async def _release_event(self, event_id: int) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                event = await session.get(DocumentOutbox, event_id, with_for_update=True)
                if event is not None and event.status == "processing":
                    event.status = "pending"
                    event.next_retry_at = datetime.now(timezone.utc)

    async def _fail_event(self, claimed: ClaimedEvent, exc: Exception) -> None:
        message = (str(exc) or exc.__class__.__name__)[:4000]
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            async with session.begin():
                event = await session.get(DocumentOutbox, claimed.id, with_for_update=True)
                if event is None:
                    return
                event.attempts += 1
                event.last_error = message
                exhausted = event.attempts >= self.max_attempts
                if exhausted:
                    event.status = "failed"
                else:
                    event.status = "pending"
                    event.next_retry_at = now + timedelta(
                        seconds=min(300, 2 ** min(event.attempts, 8))
                    )

                document = await session.get(Document, claimed.document_id)
                if not self._is_current(document, claimed):
                    return
                if claimed.operation == "index_graph" and document.status == "ready":
                    document.graph_status = "failed" if exhausted else "queued"
                    document.error_message = f"Knowledge graph indexing failed: {message}"
                elif claimed.operation == "delete_document":
                    document.error_message = f"Document deletion failed: {message}"
                    if exhausted:
                        document.status = "failed"
                        document.processing_phase = "delete_failed"
                elif document.status not in {"deleting", "deleted"}:
                    document.status = "failed" if exhausted else "processing"
                    document.error_message = message
        logger.warning("Document event %s failed: %s", claimed.id, message)

    def _lock_for(self, document_id: uuid.UUID) -> asyncio.Lock:
        return self._document_locks.setdefault(document_id, asyncio.Lock())

    def _graph_disposition(self, graph_mode: str) -> str:
        if graph_mode == "disabled":
            return "skipped"
        if self.graph_store is not None and self.graph_extractor is not None:
            return "queued"
        return "unavailable" if graph_mode == "enabled" else "disabled"
