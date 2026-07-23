import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import chromadb
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.memory_entry import MemoryEntry


FactExtractor = Callable[[str, str], Awaitable[list[str]]]
logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(
        self,
        path: Path,
        session_factory: async_sessionmaker[AsyncSession],
        relevance_threshold: float,
        result_limit: int,
        embedding_function: Any | None = None,
    ) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(path))
        collection_kwargs: dict[str, Any] = {
            "name": "conversation_memories",
            "metadata": {"hnsw:space": "cosine"},
        }
        if embedding_function is not None:
            collection_kwargs["embedding_function"] = embedding_function
        self.collection = self.client.get_or_create_collection(**collection_kwargs)
        self.session_factory = session_factory
        self.relevance_threshold = relevance_threshold
        self.result_limit = result_limit

    async def store_facts(
        self,
        facts: list[str],
        source_message_ids: list[int],
        conversation_id: int | None = None,
    ) -> list[MemoryEntry]:
        normalized = list(dict.fromkeys(fact.strip() for fact in facts if fact.strip()))
        if not normalized:
            return []

        entries = [
            MemoryEntry(
                vector_id=str(uuid.uuid4()),
                content=fact,
                source_message_ids=source_message_ids,
                metadata_json={"kind": "conversation_fact"},
                conversation_id=conversation_id,
            )
            for fact in normalized
        ]
        ids = [entry.vector_id for entry in entries]
        metadatas = [
            {
                "kind": "conversation_fact",
                "source_message_ids": json.dumps(source_message_ids),
                "conversation_id": str(conversation_id) if conversation_id else "",
            }
            for _ in entries
        ]

        await asyncio.to_thread(
            self.collection.add,
            ids=ids,
            documents=normalized,
            metadatas=metadatas,
        )
        try:
            async with self.session_factory() as session:
                session.add_all(entries)
                await session.commit()
                for entry in entries:
                    await session.refresh(entry)
        except Exception:
            await asyncio.to_thread(self.collection.delete, ids=ids)
            raise
        return entries

    async def extract_and_store(
        self,
        user_content: str,
        assistant_content: str,
        source_message_ids: list[int],
        extractor: FactExtractor,
        conversation_id: int | None = None,
    ) -> list[MemoryEntry]:
        facts = await extractor(user_content, assistant_content)
        return await self.store_facts(facts, source_message_ids, conversation_id)

    async def search(self, query: str, conversation_id: int | None = None) -> list[dict[str, object]]:
        if not query.strip() or await asyncio.to_thread(self.collection.count) == 0:
            return []

        try:
            query_kwargs: dict = {
                "query_texts": [query],
                "n_results": min(
                    self.result_limit, await asyncio.to_thread(self.collection.count)
                ),
                "include": ["documents", "distances", "metadatas"],
            }
            if conversation_id is not None:
                query_kwargs["where"] = {"conversation_id": str(conversation_id)}
            result = await asyncio.to_thread(self.collection.query, **query_kwargs)
        except Exception:
            logger.exception("Semantic memory retrieval failed")
            return []
        documents = result.get("documents", [[]])[0]
        distances = result.get("distances", [[]])[0]
        ids = result.get("ids", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        memories: list[dict[str, object]] = []
        for vector_id, document, distance, metadata in zip(
            ids, documents, distances, metadatas, strict=False
        ):
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            if similarity >= self.relevance_threshold:
                memories.append(
                    {
                        "vector_id": vector_id,
                        "content": document,
                        "similarity": similarity,
                        "metadata": metadata or {},
                    }
                )
        return memories

    async def list_entries(self) -> list[MemoryEntry]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(MemoryEntry).order_by(MemoryEntry.created_at.desc())
            )
            return list(result.scalars())

    async def delete_entry(self, entry_id: int) -> bool:
        async with self.session_factory() as session:
            entry = await session.get(MemoryEntry, entry_id)
            if entry is None:
                return False
            vector_id = entry.vector_id
            await session.delete(entry)
            await session.commit()
        await asyncio.to_thread(self.collection.delete, ids=[vector_id])
        return True

    async def delete_by_conversation(self, conversation_id: int) -> None:
        """Delete all ChromaDB vectors for a conversation."""
        try:
            results = await asyncio.to_thread(
                self.collection.get,
                where={"conversation_id": str(conversation_id)},
                include=[],
            )
            ids = results.get("ids", [])
            if ids:
                await asyncio.to_thread(self.collection.delete, ids=ids)
        except Exception:
            logger.exception("Failed to delete ChromaDB vectors for conversation %s", conversation_id)
