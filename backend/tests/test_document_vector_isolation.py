import uuid
from types import SimpleNamespace

import pytest

from app.services.document_vector_store import DocumentVectorStore


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def query_points(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(points=[])


@pytest.mark.asyncio
async def test_document_search_always_filters_by_user() -> None:
    client = RecordingClient()
    store = DocumentVectorStore(client=client, collection_name="documents")  # type: ignore[arg-type]
    user_id = uuid.uuid4()

    await store.search([0.1, 0.2], user_id, limit=6, score_threshold=0.4)

    conditions = client.calls[0]["query_filter"].must
    assert {item.key: item.match.value for item in conditions} == {"user_id": str(user_id)}
