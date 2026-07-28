import uuid
from types import SimpleNamespace

import pytest

from app.services.qdrant_memory_store import QdrantMemoryStore


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def query_points(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(points=[])

    async def upsert(self, **kwargs):
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_search_always_filters_by_user_and_conversation() -> None:
    client = RecordingClient()
    store = QdrantMemoryStore(client=client, collection_name="memories")  # type: ignore[arg-type]
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()

    await store.search([0.1, 0.2], user_id, conversation_id, limit=5, score_threshold=0.5)

    conditions = client.calls[0]["query_filter"].must
    filters = {condition.key: condition.match.value for condition in conditions}
    assert filters == {
        "user_id": str(user_id),
        "conversation_id": str(conversation_id),
    }


@pytest.mark.asyncio
async def test_character_memory_search_and_payload_include_scope() -> None:
    client = RecordingClient()
    store = QdrantMemoryStore(client=client, collection_name="memories")  # type: ignore[arg-type]
    user_id, conversation_id, character_id, memory_id = (
        uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    )

    await store.upsert(
        memory_id, user_id, conversation_id, 1, [0.1], "character_private", character_id
    )
    payload = client.calls[-1]["points"][0].payload
    assert payload["scope"] == "character_private"
    assert payload["character_id"] == str(character_id)

    await store.search(
        [0.1], user_id, conversation_id, 5, 0.5, character_id=character_id
    )
    scope_filters = client.calls[-1]["query_filter"].should
    assert scope_filters[0].match.value == "conversation_shared"
    assert scope_filters[1].must[1].match.value == str(character_id)
