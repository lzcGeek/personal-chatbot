import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient, models


@dataclass(frozen=True)
class DocumentVectorPoint:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    user_id: uuid.UUID
    revision: int
    vector: list[float]
    page_number: int | None
    section: str | None


class DocumentVectorStore:
    def __init__(
        self,
        client: AsyncQdrantClient,
        collection_name: str,
    ) -> None:
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
        await self.upsert_batch(
            [
                DocumentVectorPoint(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    user_id=user_id,
                    revision=revision,
                    vector=vector,
                    page_number=page_number,
                    section=section,
                )
            ]
        )

    async def upsert_batch(self, items: Sequence[DocumentVectorPoint]) -> None:
        if not items:
            return
        await self.client.upsert(
            collection_name=self.collection_name,
            wait=True,
            points=[
                models.PointStruct(
                    id=str(item.chunk_id),
                    vector=item.vector,
                    payload={
                        "chunk_id": str(item.chunk_id),
                        "document_id": str(item.document_id),
                        "user_id": str(item.user_id),
                        "revision": item.revision,
                        "page_number": item.page_number,
                        "section": item.section,
                    },
                ) for item in items
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
