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
    "a", "an", "the", "and", "or", "but", "if", "then", "else",
    "of", "to", "in", "on", "at", "for", "from", "by", "with", "about",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further",
    "this", "that", "these", "those", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "having", "do", "does", "did",
    "doing", "would", "should", "could", "can", "may", "might", "must",
    "will", "shall", "i", "me", "my", "we", "our", "you", "your", "he",
    "she", "it", "they", "them", "their", "what", "which", "who", "whom",
    "whose", "when", "where", "why", "how", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "only", "own", "same",
    "so", "than", "too", "very", "just", "now", "s", "t",
}
_TRAILING_ANSWER_INSTRUCTION = re.compile(
    r"^(?:"
    r"if\b[\s\S]*\b(?:then|please)\b|"
    r"please\b|answer\b|respond\b|state\b|explain\b|"
    r"when\s+(?:answering|responding)\b|"
    r"如果[\s\S]*(?:请|则|那么)|若[\s\S]*(?:请|则|那么)|请|回答时|作答时"
    r")",
    re.IGNORECASE,
)
_FAILURE_INTENT_TERMS = {
    "失败", "错误", "不可用", "超时", "重试",
    "failed", "failure", "error", "unavailable", "timeout", "retry",
}
_QUERY_NOISE_TERMS = {
    "calculate", "calculated", "compute", "computed", "determine",
    "done", "major", "show", "tell",
    "improve", "improved", "decline", "declined",
}
_QUERY_EXPANSIONS = (
    (
        re.compile(r"\bquick\s+ratio\b", re.IGNORECASE),
        "quick assets cash cash equivalents short-term investments "
        "marketable securities accounts receivable trade receivables "
        "current liabilities",
    ),
    (
        re.compile(r"\bcurrent\s+ratio\b", re.IGNORECASE),
        "current assets current liabilities",
    ),
    (
        re.compile(r"\bacquisition(?:s)?\b", re.IGNORECASE),
        "acquisitions and divestitures completed acquisition "
        "equity interest purchase consideration",
    ),
)
_FISCAL_YEAR_TERM = re.compile(r"^fy((?:19|20)\d{2})$")


class DocumentKnowledgeService:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: DocumentVectorStore,
        graph_store: GraphStore | None,
        result_limit: int,
        relevance_threshold: float,
        vector_candidate_limit: int | None = None,
    ) -> None:
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.result_limit = result_limit
        self.relevance_threshold = relevance_threshold
        self.vector_candidate_limit = max(
            result_limit,
            vector_candidate_limit if vector_candidate_limit is not None else result_limit,
        )

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
        retrieval_query = self._retrieval_query(normalized)
        vector_query = self._expand_retrieval_query(retrieval_query)

        evidence: list[dict[str, Any]] = []
        try:
            vector = await self.embedding_service.embed(vector_query)
            matches = await self.vector_store.search(
                vector=vector,
                user_id=user_id,
                limit=self.vector_candidate_limit,
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
                        "chunk_ordinal": chunk.ordinal,
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
            graph_limit, graph_weight = self._route_query(retrieval_query)
            try:
                graph_rows = await self.graph_store.search(
                    retrieval_query, user_id, graph_limit
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
            key=lambda item: self._ranking_score(vector_query, item),
            reverse=True,
        )
        deduplicated: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in ranked:
            key = (item["document_id"], item["chunk_id"])
            if key in seen:
                continue
            if self._is_near_duplicate(item, deduplicated):
                continue
            seen.add(key)
            deduplicated.append(item)
            if len(deduplicated) >= self.result_limit:
                break
        return deduplicated

    def _ranking_score(self, query: str, item: dict[str, Any]) -> float:
        """Restore Dense retrieval's deterministic lexical rerank signal."""
        score = float(item["score"])
        if item.get("evidence_type") == "text":
            score += 0.35 * self._lexical_relevance(query, item)
        return score

    @staticmethod
    def _retrieval_query(query: str) -> str:
        """Remove a trailing answer-format instruction from the retrieval query."""
        for index, character in enumerate(query):
            if character not in {"?", "？"}:
                continue
            suffix = query[index + 1 :].strip()
            if suffix and _TRAILING_ANSWER_INSTRUCTION.match(suffix):
                return query[: index + 1].strip()
        return query

    @staticmethod
    def _expand_retrieval_query(query: str) -> str:
        """Append domain concepts that commonly differ from source wording."""
        expansions: list[str] = []
        for pattern, concepts in _QUERY_EXPANSIONS:
            if pattern.search(query):
                expansions.append(concepts)
        if not expansions:
            return query
        return "\n".join([query, *expansions])

    @classmethod
    def _lexical_relevance(cls, query: str, item: dict[str, Any]) -> float:
        """Return normalized, field-aware coverage for deterministic reranking."""
        query_terms = cls._query_lexical_terms(query)
        if not query_terms:
            return 0.0

        body_text = "\n".join(
            str(item.get(field) or "")
            for field in ("content", "context_text")
        )
        section_text = str(item.get("section") or "")
        filename_text = str(item.get("filename") or "")
        body_terms = cls._lexical_terms(body_text)
        section_terms = cls._lexical_terms(section_text)
        filename_terms = cls._lexical_terms(filename_text)
        denominator = len(query_terms)
        body_coverage = len(query_terms & body_terms) / denominator
        section_coverage = len(query_terms & section_terms) / denominator
        filename_coverage = len(query_terms & filename_terms) / denominator
        coverage = body_coverage + 0.25 * section_coverage + 0.10 * filename_coverage

        lowered_query = query.lower()
        lowered_evidence = f"{section_text}\n{body_text}".lower()
        failure_terms = {
            term for term in _FAILURE_INTENT_TERMS if term in lowered_query
        }
        if failure_terms:
            matched = sum(term in lowered_evidence for term in failure_terms)
            coverage += 0.5 * matched / len(failure_terms)
        return min(1.0, coverage)

    @classmethod
    def _query_lexical_terms(cls, query: str) -> set[str]:
        return cls._lexical_terms(query) - _QUERY_NOISE_TERMS

    @classmethod
    def _is_near_duplicate(
        cls,
        candidate: dict[str, Any],
        accepted: list[dict[str, Any]],
    ) -> bool:
        """Suppress highly overlapping context windows from nearby chunks."""
        candidate_terms = cls._lexical_terms(str(candidate.get("context_text") or ""))
        if not candidate_terms:
            return False
        for existing in accepted:
            if candidate.get("document_id") != existing.get("document_id"):
                continue
            if not cls._locations_are_near(candidate, existing):
                continue
            existing_terms = cls._lexical_terms(str(existing.get("context_text") or ""))
            union = candidate_terms | existing_terms
            if union and len(candidate_terms & existing_terms) / len(union) >= 0.85:
                return True
        return False

    @staticmethod
    def _locations_are_near(left: dict[str, Any], right: dict[str, Any]) -> bool:
        left_ordinal = left.get("chunk_ordinal")
        right_ordinal = right.get("chunk_ordinal")
        if isinstance(left_ordinal, int) and isinstance(right_ordinal, int):
            return abs(left_ordinal - right_ordinal) <= 2
        left_page = left.get("page_number")
        right_page = right.get("page_number")
        if isinstance(left_page, int) and isinstance(right_page, int):
            return abs(left_page - right_page) <= 2
        return False

    @classmethod
    def _lexical_terms(cls, value: str) -> set[str]:
        terms: set[str] = set()
        for piece in _LEXICAL_PIECES.findall(value.lower().replace("_", " ")):
            if any("\u3400" <= char <= "\u9fff" for char in piece):
                if len(piece) == 1:
                    terms.add(piece)
                else:
                    terms.update(piece[index : index + 2] for index in range(len(piece) - 1))
            else:
                terms.add(cls._normalize_english_term(piece))
        return terms - _LEXICAL_STOP_TERMS

    @staticmethod
    def _normalize_english_term(term: str) -> str:
        fiscal_year = _FISCAL_YEAR_TERM.fullmatch(term)
        if fiscal_year:
            return fiscal_year.group(1)
        if len(term) > 4 and term.endswith("ies"):
            return f"{term[:-3]}y"
        if len(term) > 4 and term.endswith(("ches", "shes", "ses", "xes", "zes")):
            return term[:-2]
        if (
            len(term) > 3
            and term.endswith("s")
            and not term.endswith(("ss", "is", "us"))
        ):
            return term[:-1]
        return term

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
