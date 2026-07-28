import uuid

from qdrant_client import AsyncQdrantClient, models


class DocumentVectorStore:
    def __init__(self, client: AsyncQdrantClient, collection_name: str) -> None:
        self.client = client
        self.collection_name = collection_name

    async def upsert(
        self,
        chunk_id: uuid.UUID,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        revision: int,
        vector: list[float],
        page_number: int | None,
        section: str | None,
    ) -> None:
        await self.client.upsert(
            collection_name=self.collection_name,
            wait=True,
            points=[
                models.PointStruct(
                    id=str(chunk_id),
                    vector=vector,
                    payload={
                        "chunk_id": str(chunk_id),
                        "document_id": str(document_id),
                        "user_id": str(user_id),
                        "revision": revision,
                        "page_number": page_number,
                        "section": section,
                    },
                )
            ],
        )

    async def delete_document(self, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        await self.client.delete(
            collection_name=self.collection_name,
            wait=True,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(key="user_id", match=models.MatchValue(value=str(user_id))),
                        models.FieldCondition(
                            key="document_id", match=models.MatchValue(value=str(document_id))
                        ),
                    ]
                )
            ),
        )

    async def search(
        self,
        vector: list[float],
        user_id: uuid.UUID,
        limit: int,
        score_threshold: float,
    ) -> list[tuple[uuid.UUID, float]]:
        result = await self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="user_id", match=models.MatchValue(value=str(user_id))
                    )
                ]
            ),
            limit=limit,
            score_threshold=score_threshold,
            with_payload=False,
        )
        return [(uuid.UUID(str(point.id)), float(point.score)) for point in result.points]
