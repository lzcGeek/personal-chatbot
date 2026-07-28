import uuid
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.document_vector_store import DocumentVectorStore
from app.services.embedding_service import EmbeddingService
from app.services.graph_store import GraphStore


logger = logging.getLogger(__name__)

_LEXICAL_PIECES = re.compile(r"[a-z0-9_]+|[\u3400-\u9fff]+")
_LEXICAL_STOP_TERMS = {
    "用户", "文档", "知识", "识图", "图谱", "检索", "什么", "哪些", "如何",
    "是否", "为什么", "怎么", "可以", "能够", "newagent",
}
_FAILURE_INTENT_TERMS = {
    "失败", "错误", "不可用", "超时", "重试",
    "failed", "failure", "error", "unavailable", "timeout", "retry",
}


class DocumentKnowledgeService:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: DocumentVectorStore,
        graph_store: GraphStore | None,
        result_limit: int,
        relevance_threshold: float,
    ) -> None:
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.result_limit = result_limit
        self.relevance_threshold = relevance_threshold

    async def search(
        self,
        session: AsyncSession,
        query: str,
        user_id: uuid.UUID,
        retrieval_mode: str = "auto",
        degradations: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if retrieval_mode not in {"auto", "off", "vector", "hybrid"}:
            raise ValueError(f"Unsupported retrieval mode: {retrieval_mode}")
        normalized = query.strip()
        if not normalized or retrieval_mode == "off":
            return []

        evidence: list[dict[str, Any]] = []
        graph_limit, graph_weight = self._route_query(normalized)
        try:
            vector = await self.embedding_service.embed(normalized)
            matches = await self.vector_store.search(
                vector=vector,
                user_id=user_id,
                limit=self.result_limit,
                score_threshold=self.relevance_threshold,
            )
            score_by_id = dict(matches)
            if score_by_id:
                result = await session.execute(
                    select(DocumentChunk, Document)
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .where(
                        DocumentChunk.id.in_(score_by_id),
                        DocumentChunk.user_id == user_id,
                        Document.user_id == user_id,
                        Document.status == "ready",
                        Document.deleted_at.is_(None),
                    )
                )
                evidence.extend(
                    {
                        "evidence_type": "text",
                        "chunk_id": str(chunk.id),
                        "document_id": str(document.id),
                        "filename": document.original_filename,
                        "page_number": chunk.page_number,
                        "section": chunk.section,
                        "content": chunk.content,
                        "context_text": chunk.context_text,
                        "score": score_by_id[chunk.id],
                    }
                    for chunk, document in result.all()
                )
        except Exception:
            logger.exception("Vector document retrieval failed")
            if degradations is not None:
                degradations.append("document_vector_retrieval_failed")

        if retrieval_mode in {"auto", "hybrid"} and self.graph_store is not None:
            try:
                graph_rows = await self.graph_store.search(
                    normalized, user_id, graph_limit
                )
                evidence.extend(
                    {
                        "evidence_type": "graph",
                        "fact_id": row["fact_id"],
                        "chunk_id": row["chunk_id"],
                        "document_id": row["document_id"],
                        "filename": row["filename"],
                        "page_number": row["page_number"],
                        "section": row["section"],
                        "content": row["source_text"],
                        "context_text": (
                            f"{row['subject']} — {row['predicate']} → {row['object']}\n"
                            f"Source excerpt: {row['source_text']}"
                        ),
                        "score": min(
                            1.0,
                            (0.35 + 0.65 * float(row["confidence"] or 0))
                            * graph_weight,
                        ),
                    }
                    for row in graph_rows
                )
            except Exception:
                logger.exception("Knowledge graph retrieval failed")
                if degradations is not None:
                    degradations.append("document_graph_retrieval_failed")
        elif retrieval_mode == "hybrid" and self.graph_store is None:
            if degradations is not None:
                degradations.append("document_graph_unavailable")

        ranked = sorted(
            evidence,
            key=lambda item: (
                float(item["score"])
                + 0.35 * self._lexical_relevance(normalized, item),
                float(item["score"]),
            ),
            reverse=True,
        )
        deduplicated: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for item in ranked:
            key = (item["document_id"], item["chunk_id"], item["content"][:200])
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(item)
            if len(deduplicated) >= self.result_limit:
                break
        return deduplicated

    @classmethod
    def _lexical_relevance(cls, query: str, item: dict[str, Any]) -> float:
        """Return query-term coverage used only as a deterministic rerank signal."""
        query_terms = cls._lexical_terms(query)
        if not query_terms:
            return 0.0
        searchable = "\n".join(
            str(item.get(field) or "")
            for field in ("filename", "section", "content", "context_text")
        )
        evidence_terms = cls._lexical_terms(searchable)
        coverage = len(query_terms & evidence_terms) / len(query_terms)
        lowered_query = query.lower()
        lowered_evidence = searchable.lower()
        failure_terms = {
            term for term in _FAILURE_INTENT_TERMS if term in lowered_query
        }
        if failure_terms:
            matched = sum(term in lowered_evidence for term in failure_terms)
            coverage += 0.5 * matched / len(failure_terms)
        return min(1.0, coverage)

    @staticmethod
    def _lexical_terms(value: str) -> set[str]:
        terms: set[str] = set()
        for piece in _LEXICAL_PIECES.findall(value.lower()):
            if any("\u3400" <= char <= "\u9fff" for char in piece):
                if len(piece) == 1:
                    terms.add(piece)
                else:
                    terms.update(piece[index : index + 2] for index in range(len(piece) - 1))
            else:
                terms.add(piece)
        return terms - _LEXICAL_STOP_TERMS

    def _route_query(self, query: str) -> tuple[int, float]:
        lowered = query.lower()
        relation_markers = (
            "关系", "关联", "之间", "谁", "属于", "影响", "依赖",
            "relationship", "related", "between", "who", "depends", "works on",
        )
        relational = any(marker in lowered for marker in relation_markers)
        graph_limit = self.result_limit if relational else max(2, self.result_limit // 2)
        # Graph confidence is not directly comparable to vector cosine similarity.
        # Keep graph facts supplemental unless the query explicitly asks about a
        # relationship; otherwise generic high-confidence facts can outrank the
        # text passage that actually answers a procedural or explanatory query.
        graph_weight = 1.08 if relational else 0.45
        return graph_limit, graph_weight
