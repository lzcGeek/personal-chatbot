from openai import AsyncOpenAI


class EmbeddingService:
    def __init__(self, base_url: str, api_key: str, model: str, dimension: int) -> None:
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.dimension = dimension

    async def embed(self, text: str) -> list[float]:
        response = await self.client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimension,
        )
        vector = response.data[0].embedding
        if len(vector) != self.dimension:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.dimension}, got {len(vector)}"
            )
        return vector
