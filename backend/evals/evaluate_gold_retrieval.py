"""Run a fast, deterministic gold-evidence evaluation without an LLM judge."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from dotenv import load_dotenv


EVALS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVALS_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
DEFAULT_DATASET = EVALS_DIR / "datasets" / "rag_goldens.json"
DEFAULT_OUTPUT_DIR = EVALS_DIR / "results"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from evals.evaluation_scoring import gold_evidence_coverage


load_dotenv(PROJECT_ROOT / ".env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("EVAL_CASE_LIMIT", "5")),
        help="Number of cases to run; use 0 for every case.",
    )
    parser.add_argument(
        "--match-threshold",
        type=float,
        default=0.60,
        help="Minimum gold-evidence token-shingle recall required for a hit.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Markdown output path; JSON is written beside it.",
    )
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    cwd_path = (Path.cwd() / path).resolve()
    if cwd_path.exists():
        return cwd_path
    return (BACKEND_DIR / path).resolve()


def load_goldens(path: Path, limit: int) -> list[dict[str, Any]]:
    if limit < 0:
        raise ValueError("--limit must be 0 or a positive integer")
    if not path.is_file():
        raise FileNotFoundError(f"Evaluation dataset does not exist: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("Evaluation dataset must be a non-empty JSON list")
    selected = data if limit == 0 else data[:limit]
    for index, item in enumerate(selected, start=1):
        evidence = item.get("metadata", {}).get("gold_evidence") or []
        if not evidence:
            raise ValueError(
                f"Dataset case {index} ({item.get('id', '-')}) has no metadata.gold_evidence"
            )
    return selected


def evaluate_case(
    golden: dict[str, Any],
    retrieved: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    gold_rows: list[dict[str, Any]] = []
    for gold in golden["metadata"]["gold_evidence"]:
        source_name = Path(str(gold.get("source") or "")).name.casefold()
        best_rank: int | None = None
        best_coverage = 0.0
        best_page: int | None = None
        for rank, item in enumerate(retrieved, start=1):
            filename = Path(str(item.get("filename") or "")).name.casefold()
            if filename != source_name:
                continue
            coverage = gold_evidence_coverage(
                str(gold.get("excerpt") or ""),
                str(item.get("context_text") or ""),
            )
            if coverage > best_coverage:
                best_coverage = coverage
                best_rank = rank
                best_page = item.get("page_number")
        matched = best_coverage >= threshold
        gold_rows.append(
            {
                "source": gold.get("source"),
                "gold_page_index": gold.get("page_index"),
                "matched": matched,
                "best_rank": best_rank,
                "best_page_number": best_page,
                "best_coverage": best_coverage,
            }
        )

    matched_rows = [row for row in gold_rows if row["matched"]]
    matched_ranks = [int(row["best_rank"]) for row in matched_rows]
    first_rank = min(matched_ranks) if matched_ranks else None
    return {
        "id": golden.get("id"),
        "input": golden.get("input"),
        "hit": bool(matched_rows),
        "gold_evidence_recall": len(matched_rows) / len(gold_rows),
        "first_relevant_rank": first_rank,
        "reciprocal_rank": 1 / first_rank if first_rank else 0.0,
        "best_coverage": max(row["best_coverage"] for row in gold_rows),
        "gold_evidence": gold_rows,
        "retrieved": [
            {
                "rank": rank,
                "filename": item.get("filename"),
                "page_number": item.get("page_number"),
                "section": item.get("section"),
                "chunk_id": item.get("chunk_id"),
                "score": item.get("score"),
            }
            for rank, item in enumerate(retrieved, start=1)
        ],
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# NewAgent 黄金证据检索快测",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 数据集：`{report['dataset']}`",
        f"- 用例数量：{report['case_count']}",
        f"- 最终 Top-K：{report['result_limit']}",
        f"- 黄金证据匹配阈值：{report['match_threshold']:.2f}",
        "- 图谱：关闭（仅测试文本向量检索）",
        "",
        "## 汇总",
        "",
        "| 指标 | 分数 |",
        "|---|---:|",
        f"| Gold Evidence Hit Rate@{report['result_limit']} | {report['hit_rate']:.3f} |",
        f"| Gold Evidence Recall@{report['result_limit']} | {report['evidence_recall']:.3f} |",
        f"| MRR | {report['mrr']:.3f} |",
        f"| 平均最佳证据覆盖率 | {report['mean_best_coverage']:.3f} |",
        "",
        "## 用例明细",
        "",
        "| 问题 | Hit | Recall | 首次排名 | MRR | 最佳覆盖率 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for case in report["cases"]:
        question = str(case["input"]).replace("|", "\\|").replace("\n", " ")
        rank = case["first_relevant_rank"] or "-"
        lines.append(
            f"| {question} | {int(case['hit'])} | "
            f"{case['gold_evidence_recall']:.3f} | {rank} | "
            f"{case['reciprocal_rank']:.3f} | {case['best_coverage']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 阅读说明",
            "",
            "- Hit/Recall 衡量是否找到了数据集标注的原始证据，不调用 LLM 裁判。",
            "- 首次排名越小越好；MRR 越接近 1，黄金证据越靠前。",
            "- 覆盖率按连续三个词项的有序片段计算，可容忍 PDF 空格和换行变化。",
            "- 本报告只评估检索，不评估模型是否正确计算或回答。",
            "",
        ]
    )
    return "\n".join(lines)


async def run_live(
    goldens: list[dict[str, Any]],
    threshold: float,
) -> tuple[list[dict[str, Any]], int]:
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.core.database import SessionLocal, close_database
    from app.core.vector_db import close_vector_database, qdrant_client
    from app.models.user import User
    from app.services.auth_service import normalize_username
    from app.services.document_knowledge_service import DocumentKnowledgeService
    from app.services.document_vector_store import DocumentVectorStore
    from app.services.embedding_service import EmbeddingService

    settings = get_settings()
    username = os.getenv("EVAL_USERNAME", "").strip()
    if not username:
        raise RuntimeError(f"Missing EVAL_USERNAME in {PROJECT_ROOT / '.env'}")

    embedding = EmbeddingService(
        base_url=settings.resolved_embedding_base_url,
        api_key=settings.resolved_embedding_api_key,
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
        request_timeout_seconds=settings.embedding_request_timeout_seconds,
        max_retries=settings.embedding_max_retries,
    )
    vector_store = DocumentVectorStore(
        client=qdrant_client,
        collection_name=settings.qdrant_document_collection,
    )
    service = DocumentKnowledgeService(
        embedding_service=embedding,
        vector_store=vector_store,
        graph_store=None,
        result_limit=settings.document_result_limit,
        relevance_threshold=settings.document_relevance_threshold,
        vector_candidate_limit=settings.document_vector_candidate_limit,
    )

    cases: list[dict[str, Any]] = []
    try:
        async with SessionLocal() as session:
            user_result = await session.execute(
                select(User).where(
                    User.normalized_username == normalize_username(username),
                    User.status == "active",
                )
            )
            user = user_result.scalar_one_or_none()
            if user is None:
                raise RuntimeError(f"Evaluation user does not exist or is inactive: {username}")

            for index, golden in enumerate(goldens, start=1):
                print(f"[{index}/{len(goldens)}] {golden['input']}", flush=True)
                retrieved = await service.search(
                    session,
                    str(golden["input"]),
                    user.id,
                    retrieval_mode="vector",
                )
                cases.append(evaluate_case(golden, retrieved, threshold))
    finally:
        await close_vector_database()
        await close_database()
    return cases, settings.document_result_limit


def output_paths(requested: Path | None) -> tuple[Path, Path]:
    if requested is None:
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        markdown = DEFAULT_OUTPUT_DIR / f"gold-retrieval-{stamp}.md"
    else:
        markdown = requested if requested.is_absolute() else (Path.cwd() / requested)
    return markdown.resolve(), markdown.with_suffix(".json").resolve()


def main() -> None:
    args = parse_args()
    if not 0 <= args.match_threshold <= 1:
        raise SystemExit("--match-threshold must be between 0 and 1")
    dataset_path = resolve_path(args.dataset)
    try:
        goldens = load_goldens(dataset_path, args.limit)
        cases, result_limit = asyncio.run(run_live(goldens, args.match_threshold))
    except Exception as exc:
        raise SystemExit(f"Gold retrieval evaluation failed: {exc}") from exc

    total_gold = sum(len(case["gold_evidence"]) for case in cases)
    matched_gold = sum(
        sum(bool(row["matched"]) for row in case["gold_evidence"])
        for case in cases
    )
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "dataset": str(dataset_path),
        "case_count": len(cases),
        "result_limit": result_limit,
        "match_threshold": args.match_threshold,
        "hit_rate": mean(float(case["hit"]) for case in cases),
        "evidence_recall": matched_gold / total_gold,
        "mrr": mean(case["reciprocal_rank"] for case in cases),
        "mean_best_coverage": mean(case["best_coverage"] for case in cases),
        "cases": cases,
    }
    markdown_path, json_path = output_paths(args.output)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown_report(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\nGold retrieval evaluation completed.")
    print(f"Hit Rate@{result_limit}: {report['hit_rate']:.3f}")
    print(f"Evidence Recall@{result_limit}: {report['evidence_recall']:.3f}")
    print(f"MRR: {report['mrr']:.3f}")
    print(f"Markdown: {markdown_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
