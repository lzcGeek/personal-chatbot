from collections.abc import Sequence

from openai import AsyncOpenAI


class EmbeddingService:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dimension: int,
        request_timeout_seconds: float = 60,
        max_retries: int = 2,
    ) -> None:
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=request_timeout_seconds,
            max_retries=max_retries,
        )
        self.model = model
        self.dimension = dimension

    async def embed(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self.client.embeddings.create(
            model=self.model,
            input=list(texts),
            dimensions=self.dimension,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        if len(ordered) != len(texts):
            raise ValueError(
                f"Embedding count mismatch: expected {len(texts)}, got {len(ordered)}"
            )
        vectors = [item.embedding for item in ordered]
        for vector in vectors:
            if len(vector) != self.dimension:
                raise ValueError(
                    "Embedding dimension mismatch: "
                    f"expected {self.dimension}, got {len(vector)}"
                )
        return vectors
