import hashlib
import uuid
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.models.document import Document
from app.models.document_chunk import DocumentChunk


class GraphStore:
    def __init__(self, uri: str, user: str, password: str) -> None:
        self.driver: AsyncDriver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def initialize(self) -> None:
        await self.driver.verify_connectivity()
        constraints = (
            "CREATE CONSTRAINT graph_user_id IF NOT EXISTS FOR (n:User) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT graph_document_id IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT graph_chunk_id IF NOT EXISTS FOR (n:Chunk) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT graph_entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT graph_fact_id IF NOT EXISTS FOR (n:Fact) REQUIRE n.id IS UNIQUE",
        )
        async with self.driver.session() as session:
            for statement in constraints:
                await session.run(statement)

    async def close(self) -> None:
        await self.driver.close()

    async def index_document(
        self,
        document: Document,
        chunks: list[DocumentChunk],
        facts_by_chunk: dict[uuid.UUID, list[dict[str, Any]]],
    ) -> None:
        user_id = str(document.user_id)
        document_id = str(document.id)
        chunk_rows = [
            {
                "id": str(chunk.id),
                "user_id": user_id,
                "document_id": document_id,
                "ordinal": chunk.ordinal,
                "page_number": chunk.page_number,
                "section": chunk.section,
                "content": chunk.content[:4000],
            }
            for chunk in chunks
        ]
        fact_rows: list[dict[str, Any]] = []
        for chunk in chunks:
            for fact in facts_by_chunk.get(chunk.id, []):
                subject_id = self._entity_id(document.user_id, fact["subject"])
                object_id = self._entity_id(document.user_id, fact["object"])
                fact_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{chunk.id}:{fact['subject']}:{fact['predicate']}:{fact['object']}",
                    )
                )
                fact_rows.append(
                    {
                        **fact,
                        "id": fact_id,
                        "user_id": user_id,
                        "document_id": document_id,
                        "chunk_id": str(chunk.id),
                        "filename": document.original_filename,
                        "page_number": chunk.page_number,
                        "section": chunk.section,
                        "subject_id": subject_id,
                        "object_id": object_id,
                    }
                )

        async with self.driver.session() as session:
            await session.execute_write(
                self._write_document,
                user_id,
                document_id,
                document.original_filename,
                chunk_rows,
                fact_rows,
            )

    @staticmethod
    async def _write_document(tx, user_id, document_id, filename, chunks, facts) -> None:
        await tx.run(
            """
            MERGE (u:User {id: $user_id})
            MERGE (d:Document {id: $document_id})
            SET d.user_id = $user_id, d.filename = $filename
            MERGE (u)-[:OWNS]->(d)
            """,
            user_id=user_id,
            document_id=document_id,
            filename=filename,
        )
        await tx.run(
            """
            MATCH (d:Document {id: $document_id})
            UNWIND $chunks AS row
            MERGE (c:Chunk {id: row.id})
            SET c += row
            MERGE (d)-[:HAS_CHUNK]->(c)
            """,
            document_id=document_id,
            chunks=chunks,
        )
        await tx.run(
            """
            UNWIND $facts AS row
            MATCH (c:Chunk {id: row.chunk_id})
            MERGE (s:Entity {id: row.subject_id})
            SET s.user_id = row.user_id, s.name = row.subject, s.type = row.subject_type
            MERGE (o:Entity {id: row.object_id})
            SET o.user_id = row.user_id, o.name = row.object, o.type = row.object_type
            MERGE (f:Fact {id: row.id})
            SET f.user_id = row.user_id, f.document_id = row.document_id,
                f.chunk_id = row.chunk_id, f.predicate = row.predicate,
                f.source_text = row.source_text, f.confidence = row.confidence,
                f.filename = row.filename, f.page_number = row.page_number,
                f.section = row.section
            MERGE (c)-[:SUPPORTS]->(f)
            MERGE (f)-[:SUBJECT]->(s)
            MERGE (f)-[:OBJECT]->(o)
            MERGE (c)-[:MENTIONS]->(s)
            MERGE (c)-[:MENTIONS]->(o)
            """,
            facts=facts,
        )

    async def delete_document(self, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        async with self.driver.session() as session:
            await session.execute_write(
                self._delete_document, str(user_id), str(document_id)
            )

    @staticmethod
    async def _delete_document(tx, user_id: str, document_id: str) -> None:
        await tx.run(
            """
            MATCH (d:Document {id: $document_id, user_id: $user_id})
            OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
            OPTIONAL MATCH (c)-[:SUPPORTS]->(f:Fact)
            DETACH DELETE f, c, d
            """,
            user_id=user_id,
            document_id=document_id,
        )
        await tx.run(
            """
            MATCH (e:Entity {user_id: $user_id})
            WHERE NOT (e)<-[:SUBJECT|OBJECT]-(:Fact)
            DETACH DELETE e
            """,
            user_id=user_id,
        )

    async def search(
        self, query: str, user_id: uuid.UUID, limit: int = 8
    ) -> list[dict[str, Any]]:
        normalized = query.strip().lower()
        if not normalized:
            return []
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (start:Entity {user_id: $user_id})
                WHERE toLower($query_text) CONTAINS toLower(start.name)
                   OR toLower(start.name) CONTAINS toLower($query_text)
                MATCH p=(start)-[:SUBJECT|OBJECT*1..4]-(node)
                WHERE ALL(n IN nodes(p) WHERE n.user_id = $user_id)
                UNWIND [n IN nodes(p) WHERE n:Fact] AS fact
                MATCH (fact)-[:SUBJECT]->(subject:Entity)
                MATCH (fact)-[:OBJECT]->(object:Entity)
                RETURN DISTINCT fact.id AS fact_id, subject.name AS subject,
                       fact.predicate AS predicate, object.name AS object,
                       fact.source_text AS source_text, fact.confidence AS confidence,
                       fact.document_id AS document_id, fact.chunk_id AS chunk_id,
                       fact.filename AS filename, properties(fact).page_number AS page_number,
                       fact.section AS section
                ORDER BY confidence DESC
                LIMIT $limit
                """,
                user_id=str(user_id),
                query_text=normalized,
                limit=limit,
            )
            return [dict(record) async for record in result]

    @staticmethod
    def _entity_id(user_id: uuid.UUID, name: str) -> str:
        normalized = " ".join(name.lower().split())
        digest = hashlib.sha256(f"{user_id}:{normalized}".encode("utf-8")).hexdigest()
        return digest
