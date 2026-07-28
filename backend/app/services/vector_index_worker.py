import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.memory_entry import MemoryEntry
from app.models.vector_outbox import VectorOutbox
from app.services.embedding_service import EmbeddingService
from app.services.qdrant_memory_store import QdrantMemoryStore


logger = logging.getLogger(__name__)


class VectorIndexWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedding_service: EmbeddingService,
        vector_store: QdrantMemoryStore,
        poll_seconds: float,
        max_attempts: int,
    ) -> None:
        self.session_factory = session_factory
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.poll_seconds = poll_seconds
        self.max_attempts = max_attempts
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="vector-index-worker")

    async def close(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                processed = await self._process_one()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Vector outbox worker iteration failed")
                processed = False
            if not processed:
                await asyncio.sleep(self.poll_seconds)

    async def _process_one(self) -> bool:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(VectorOutbox)
                    .where(
                        VectorOutbox.status == "pending",
                        VectorOutbox.next_retry_at <= now,
                    )
                    .order_by(VectorOutbox.id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                event = result.scalar_one_or_none()
                if event is None:
                    return False
                try:
                    await self._apply(session, event)
                except Exception as exc:
                    event.attempts += 1
                    event.last_error = (str(exc) or exc.__class__.__name__)[:4000]
                    if event.operation == "upsert_memory" and event.memory_id is not None:
                        memory = await session.get(MemoryEntry, event.memory_id)
                        if memory is not None and memory.embedding_revision == event.revision:
                            memory.last_embedding_error = event.last_error
                            memory.embedding_status = (
                                "failed" if event.attempts >= self.max_attempts else "pending"
                            )
                    if event.attempts >= self.max_attempts:
                        event.status = "failed"
                    else:
                        delay = min(300, 2 ** min(event.attempts, 8))
                        event.next_retry_at = now + timedelta(seconds=delay)
                    logger.warning("Vector event %s failed: %s", event.id, event.last_error)
                else:
                    event.status = "done"
                    event.completed_at = now
                    event.last_error = None
                return True

    async def _apply(self, session: AsyncSession, event: VectorOutbox) -> None:
        if event.operation == "upsert_memory":
            if event.memory_id is None:
                return
            memory = await session.get(MemoryEntry, event.memory_id)
            if memory is None or memory.embedding_revision != event.revision:
                return
            vector = await self.embedding_service.embed(memory.content)
            await self.vector_store.upsert(
                memory.id,
                memory.user_id,
                memory.conversation_id,
                memory.embedding_revision,
                vector,
                memory.scope,
                memory.character_id,
            )
            memory.embedding_status = "ready"
            memory.last_embedding_error = None
        elif event.operation == "delete_memory":
            if event.memory_id is not None:
                await self.vector_store.delete_memory(event.memory_id)
        elif event.operation == "delete_conversation":
            await self.vector_store.delete_conversation(event.user_id, event.conversation_id)
        else:
            raise ValueError(f"Unknown vector outbox operation: {event.operation}")
