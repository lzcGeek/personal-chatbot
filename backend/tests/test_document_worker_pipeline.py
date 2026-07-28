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
