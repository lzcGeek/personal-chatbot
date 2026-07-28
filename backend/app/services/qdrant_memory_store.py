import uuid

from qdrant_client import AsyncQdrantClient, models


class QdrantMemoryStore:
    def __init__(self, client: AsyncQdrantClient, collection_name: str) -> None:
        self.client = client
        self.collection_name = collection_name

    async def upsert(
        self,
        memory_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        revision: int,
        vector: list[float],
        scope: str = "conversation_shared",
        character_id: uuid.UUID | None = None,
    ) -> None:
        await self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=str(memory_id),
                    vector=vector,
                    payload={
                        "memory_id": str(memory_id),
                        "user_id": str(user_id),
                        "conversation_id": str(conversation_id),
                        "kind": "conversation_fact",
                        "revision": revision,
                        "scope": scope,
                        "character_id": str(character_id) if character_id else None,
                    },
                )
            ],
            wait=True,
        )

    async def search(
        self,
        vector: list[float],
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        limit: int,
        score_threshold: float,
        character_id: uuid.UUID | None = None,
    ) -> list[tuple[uuid.UUID, float]]:
        result = await self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="user_id", match=models.MatchValue(value=str(user_id))
                    ),
                    models.FieldCondition(
                        key="conversation_id", match=models.MatchValue(value=str(conversation_id))
                    ),
                ],
                should=[
                    models.FieldCondition(
                        key="scope", match=models.MatchValue(value="conversation_shared")
                    ),
                    models.Filter(
                        must=[
                            models.FieldCondition(
                                key="scope", match=models.MatchValue(value="character_private")
                            ),
                            models.FieldCondition(
                                key="character_id",
                                match=models.MatchValue(
                                    value=str(character_id) if character_id else ""
                                ),
                            ),
                        ]
                    ),
                ],
            ),
            limit=limit,
            score_threshold=score_threshold,
            with_payload=False,
        )
        return [(uuid.UUID(str(point.id)), float(point.score)) for point in result.points]

    async def delete_memory(self, memory_id: uuid.UUID) -> None:
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(points=[str(memory_id)]),
            wait=True,
        )

    async def delete_conversation(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id", match=models.MatchValue(value=str(user_id))
                        ),
                        models.FieldCondition(
                            key="conversation_id", match=models.MatchValue(value=str(conversation_id))
                        ),
                    ]
                )
            ),
            wait=True,
        )
