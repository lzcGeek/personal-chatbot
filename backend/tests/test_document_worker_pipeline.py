import asyncio
import uuid

import pytest

from app.models.document_chunk import DocumentChunk
from app.services.document_index_worker import ClaimedEvent, DocumentIndexWorker


class ConcurrentExtractor:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def extract(self, text: str):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return [{"subject": text}]


def make_worker(*, extractor=None, concurrency=2) -> DocumentIndexWorker:
    return DocumentIndexWorker(
        session_factory=None,  # type: ignore[arg-type]
        storage=None,  # type: ignore[arg-type]
        parser=None,  # type: ignore[arg-type]
        chunker=None,  # type: ignore[arg-type]
        embedding_service=None,  # type: ignore[arg-type]
        vector_store=None,  # type: ignore[arg-type]
        graph_store=None,
        graph_extractor=extractor,
        poll_seconds=1,
        max_attempts=3,
        graph_concurrency=concurrency,
    )


class ConcurrentBatchEmbedding:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.batch_sizes: list[int] = []
        self.texts: list[str] = []

    async def embed_batch(self, texts):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.batch_sizes.append(len(texts))
        self.texts.extend(texts)
        await asyncio.sleep(0.01)
        self.active -= 1
        return [[float(len(text))] for text in texts]


class BatchVectorStore:
    def __init__(self) -> None:
        self.items = []
        self.batch_sizes: list[int] = []

    async def upsert_batch(self, items):
        self.items.extend(items)
        self.batch_sizes.append(len(items))


@pytest.mark.asyncio
async def test_document_embeddings_are_batched_with_bounded_concurrency() -> None:
    embedding = ConcurrentBatchEmbedding()
    vector_store = BatchVectorStore()
    worker = DocumentIndexWorker(
        session_factory=None,  # type: ignore[arg-type]
        storage=None,  # type: ignore[arg-type]
        parser=None,  # type: ignore[arg-type]
        chunker=None,  # type: ignore[arg-type]
        embedding_service=embedding,  # type: ignore[arg-type]
        vector_store=vector_store,  # type: ignore[arg-type]
        graph_store=None,
        graph_extractor=None,
        poll_seconds=1,
        max_attempts=3,
        embedding_batch_size=3,
        embedding_concurrency=2,
    )
    document_id = uuid.uuid4()
    user_id = uuid.uuid4()
    event = ClaimedEvent(
        id=1,
        document_id=document_id,
        user_id=user_id,
        operation="process_document",
        revision=2,
    )
    chunks = [
        DocumentChunk(
            id=uuid.uuid4(),
            document_id=document_id,
            user_id=user_id,
            ordinal=index,
            content=f"chunk-{index}",
            context_text=f"context-{index}",
        )
        for index in range(10)
    ]

    await worker._embed_and_store_chunks(event, chunks)  # noqa: SLF001

    assert sorted(embedding.batch_sizes) == [1, 3, 3, 3]
    assert embedding.max_active == 2
    assert sorted(vector_store.batch_sizes) == [1, 3, 3, 3]
    assert {item.chunk_id for item in vector_store.items} == {chunk.id for chunk in chunks}
    assert set(embedding.texts) == {f"context-{index}" for index in range(10)}


class LimitedBatchEmbedding:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.batch_sizes: list[int] = []

    async def embed_batch(self, texts):
        self.batch_sizes.append(len(texts))
        if len(texts) > self.maximum:
            raise RuntimeError(
                "batch size is invalid, it should not be larger than "
                f"{self.maximum}"
            )
        return [[float(len(text))] for text in texts]


@pytest.mark.asyncio
async def test_embedding_batch_limit_error_is_split_and_retried() -> None:
    embedding = LimitedBatchEmbedding(maximum=2)
    vector_store = BatchVectorStore()
    worker = DocumentIndexWorker(
        session_factory=None,  # type: ignore[arg-type]
        storage=None,  # type: ignore[arg-type]
        parser=None,  # type: ignore[arg-type]
        chunker=None,  # type: ignore[arg-type]
        embedding_service=embedding,  # type: ignore[arg-type]
        vector_store=vector_store,  # type: ignore[arg-type]
        graph_store=None,
        graph_extractor=None,
        poll_seconds=1,
        max_attempts=3,
        embedding_batch_size=4,
        embedding_concurrency=1,
    )
    document_id = uuid.uuid4()
    user_id = uuid.uuid4()
    event = ClaimedEvent(1, document_id, user_id, "process_document", 1)
    chunks = [
        DocumentChunk(
            id=uuid.uuid4(),
            document_id=document_id,
            user_id=user_id,
            ordinal=index,
            content=f"chunk-{index}",
            context_text=f"chunk-{index}",
        )
        for index in range(4)
    ]

    await worker._embed_and_store_chunks(event, chunks)  # noqa: SLF001

    assert embedding.batch_sizes == [4, 2, 2]
    assert len(vector_store.items) == 4


class IdleWorker(DocumentIndexWorker):
    async def _run(self, operations, *, recover=True):
        await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_document_worker_starts_multiple_core_consumers() -> None:
    worker = IdleWorker(
        session_factory=None,  # type: ignore[arg-type]
        storage=None,  # type: ignore[arg-type]
        parser=None,  # type: ignore[arg-type]
        chunker=None,  # type: ignore[arg-type]
        embedding_service=None,  # type: ignore[arg-type]
        vector_store=None,  # type: ignore[arg-type]
        graph_store=None,
        graph_extractor=None,
        poll_seconds=1,
        max_attempts=3,
        core_concurrency=3,
    )

    worker.start()
    try:
        names = {task.get_name() for task in worker._tasks}  # noqa: SLF001
        assert names == {
            "document-core-worker-1",
            "document-core-worker-2",
            "document-core-worker-3",
            "document-graph-worker",
        }
    finally:
        await worker.close()


def test_graph_disposition_respects_document_mode_and_service_availability() -> None:
    disabled_worker = make_worker()
    assert disabled_worker._graph_disposition("disabled") == "skipped"  # noqa: SLF001
    assert disabled_worker._graph_disposition("inherit") == "disabled"  # noqa: SLF001
    assert disabled_worker._graph_disposition("enabled") == "unavailable"  # noqa: SLF001

    enabled_worker = make_worker(extractor=object())
    enabled_worker.graph_store = object()  # type: ignore[assignment]
    assert enabled_worker._graph_disposition("disabled") == "skipped"  # noqa: SLF001
    assert enabled_worker._graph_disposition("inherit") == "queued"  # noqa: SLF001
    assert enabled_worker._graph_disposition("enabled") == "queued"  # noqa: SLF001


@pytest.mark.asyncio
async def test_graph_extraction_uses_bounded_parallelism() -> None:
    extractor = ConcurrentExtractor()
    worker = make_worker(extractor=extractor, concurrency=2)
    chunks = [
        DocumentChunk(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            ordinal=index,
            content=f"chunk-{index}",
            context_text=f"chunk-{index}",
        )
        for index in range(6)
    ]

    facts = await worker._extract_graph_facts(chunks)  # noqa: SLF001

    assert set(facts) == {chunk.id for chunk in chunks}
    assert extractor.max_active == 2


class RoutingWorker(DocumentIndexWorker):
    def __init__(self, event: ClaimedEvent) -> None:
        super().__init__(
            session_factory=None,  # type: ignore[arg-type]
            storage=None,  # type: ignore[arg-type]
            parser=None,  # type: ignore[arg-type]
            chunker=None,  # type: ignore[arg-type]
            embedding_service=None,  # type: ignore[arg-type]
            vector_store=None,  # type: ignore[arg-type]
            graph_store=None,
            graph_extractor=None,
            poll_seconds=1,
            max_attempts=3,
        )
        self.event = event
        self.called: list[str] = []

    async def _claim_event(self, operations):
        self.called.append(f"claim:{','.join(operations)}")
        return self.event

    async def _delete_document(self, event):
        self.called.append("delete")

    async def _process_document(self, event):
        self.called.append("text")

    async def _index_graph(self, event):
        self.called.append("graph")

    async def _complete_event(self, event_id):
        self.called.append("complete")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("delete_document", "delete"),
        ("process_document", "text"),
        ("index_graph", "graph"),
    ],
)
async def test_claimed_operations_are_routed_independently(operation, expected) -> None:
    event = ClaimedEvent(
        id=1,
        document_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        operation=operation,
        revision=1,
    )
    worker = RoutingWorker(event)

    assert await worker._process_one((operation,)) is True  # noqa: SLF001
    assert expected in worker.called
    assert "complete" in worker.called
