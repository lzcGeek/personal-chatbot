from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings


settings = get_settings()
qdrant_client = AsyncQdrantClient(
    url=settings.qdrant_url,
    api_key=settings.qdrant_api_key or None,
)


async def init_vector_database() -> None:
    if not await qdrant_client.collection_exists(settings.qdrant_collection):
        await qdrant_client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=models.VectorParams(
                size=settings.embedding_dimension,
                distance=models.Distance.COSINE,
            ),
        )
    for field_name in ("user_id", "conversation_id", "memory_id", "kind"):
        try:
            await qdrant_client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        except Exception:
            # Qdrant returns an error when the index already exists.
            pass

    if not await qdrant_client.collection_exists(settings.qdrant_document_collection):
        await qdrant_client.create_collection(
            collection_name=settings.qdrant_document_collection,
            vectors_config=models.VectorParams(
                size=settings.embedding_dimension,
                distance=models.Distance.COSINE,
            ),
        )
    for field_name in ("user_id", "document_id", "chunk_id"):
        try:
            await qdrant_client.create_payload_index(
                collection_name=settings.qdrant_document_collection,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass


async def close_vector_database() -> None:
    await qdrant_client.close()
