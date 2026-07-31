"""Build a reproducible 30-case FinanceBench subset for NewAgent RAG evals."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


EVALS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVALS_DIR.parents[1]
FINANCEBENCH_ROOT = PROJECT_ROOT / "data" / "financebench-main"
SOURCE_PATH = FINANCEBENCH_ROOT / "data" / "financebench_open_source.jsonl"
PDF_DIR = FINANCEBENCH_ROOT / "pdfs"
OUTPUT_DIR = EVALS_DIR / "datasets"

# These are the five FinanceBench documents with the most open-source annotations.
# Together they provide exactly 30 original, human-annotated cases. The split is
# grouped by document so no filing appears in both development and test data.
DEV_DOCUMENTS = {
    "AMERICANEXPRESS_2022_10K",
    "BOEING_2022_10K",
    "AMCOR_2023_10K",
}

TEST_DOCUMENTS = {
    "AMD_2022_10K",
    "PEPSICO_2022_10K",
}

EXPECTED_COUNTS = {
    "all": 30,
    "dev": 18,
    "test": 12,
}

EXPECTED_TYPE_COUNTS = {
    "domain-relevant": 21,
    "metrics-generated": 2,
    "novel-generated": 7,
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSONL at {path}:{line_number}") from exc
    return rows


def compact_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(str(evidence.get("evidence_text") or "").split())
    return {
        "source": f"{evidence['doc_name']}.pdf",
        # FinanceBench documents this field as zero-indexed. Keep the original
        # value instead of silently converting it to a reader-facing page number.
        "page_index": evidence.get("evidence_page_num"),
        "excerpt": text,
    }


def normalize(row: dict[str, Any], split: str) -> dict[str, Any]:
    doc_name = str(row["doc_name"])
    return {
        "id": str(row["financebench_id"]),
        "input": str(row["question"]),
        "expected_output": str(row["answer"]),
        "acceptable_sources": [f"{doc_name}.pdf"],
        "metadata": {
            "benchmark": "FinanceBench OPEN_SOURCE",
            "split": split,
            "company": row.get("company"),
            "doc_name": doc_name,
            "question_type": row.get("question_type"),
            "question_reasoning": row.get("question_reasoning"),
            "domain_question_num": row.get("domain_question_num"),
            "justification": row.get("justification"),
            "gold_evidence": [compact_evidence(item) for item in row.get("evidence", [])],
        },
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate(rows: list[dict[str, Any]]) -> None:
    ids = [str(row["financebench_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("The selected FinanceBench cases contain duplicate IDs.")

    actual_types = Counter(str(row["question_type"]) for row in rows)
    if dict(actual_types) != EXPECTED_TYPE_COUNTS:
        raise RuntimeError(
            f"Unexpected question type distribution: {dict(actual_types)}; "
            f"expected {EXPECTED_TYPE_COUNTS}"
        )

    missing_pdfs = sorted(
        str(PDF_DIR / f"{row['doc_name']}.pdf")
        for row in rows
        if not (PDF_DIR / f"{row['doc_name']}.pdf").is_file()
    )
    if missing_pdfs:
        raise RuntimeError(f"Missing selected PDFs: {missing_pdfs}")

    overlap = DEV_DOCUMENTS & TEST_DOCUMENTS
    if overlap:
        raise RuntimeError(f"Dev/test document leakage detected: {sorted(overlap)}")


def main() -> None:
    if not SOURCE_PATH.is_file():
        raise RuntimeError(
            "FinanceBench source data was not found. Expected: "
            f"{SOURCE_PATH}"
        )

    selected_documents = DEV_DOCUMENTS | TEST_DOCUMENTS
    source_rows = read_jsonl(SOURCE_PATH)
    selected_rows = [
        row for row in source_rows if str(row.get("doc_name")) in selected_documents
    ]
    validate(selected_rows)

    dev_rows = [row for row in selected_rows if row["doc_name"] in DEV_DOCUMENTS]
    test_rows = [row for row in selected_rows if row["doc_name"] in TEST_DOCUMENTS]
    if len(selected_rows) != EXPECTED_COUNTS["all"]:
        raise RuntimeError(f"Expected 30 cases, found {len(selected_rows)}")
    if len(dev_rows) != EXPECTED_COUNTS["dev"]:
        raise RuntimeError(f"Expected 18 dev cases, found {len(dev_rows)}")
    if len(test_rows) != EXPECTED_COUNTS["test"]:
        raise RuntimeError(f"Expected 12 test cases, found {len(test_rows)}")

    normalized_dev = [normalize(row, "dev") for row in dev_rows]
    normalized_test = [normalize(row, "test") for row in test_rows]
    normalized_all = normalized_dev + normalized_test

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT_DIR / "financebench_goldens_dev.json", normalized_dev)
    write_json(OUTPUT_DIR / "financebench_goldens_test.json", normalized_test)
    write_json(OUTPUT_DIR / "financebench_goldens_30.json", normalized_all)

    manifest = {
        "benchmark": "FinanceBench",
        "upstream_repository": "https://github.com/patronus-ai/financebench",
        "upstream_paper": "https://arxiv.org/abs/2311.11944",
        "source_subset": "OPEN_SOURCE",
        "selection_policy": (
            "The five documents with the most open-source annotations, yielding "
            "30 original cases: 21 domain-relevant, 2 metrics-generated, and 7 "
            "novel-generated. Dev and test documents do not overlap."
        ),
        "counts": EXPECTED_COUNTS,
        "question_type_counts": EXPECTED_TYPE_COUNTS,
        "dev_documents": sorted(f"{name}.pdf" for name in DEV_DOCUMENTS),
        "test_documents": sorted(f"{name}.pdf" for name in TEST_DOCUMENTS),
        "upload_documents": sorted(
            f"data/financebench-main/pdfs/{name}.pdf"
            for name in DEV_DOCUMENTS | TEST_DOCUMENTS
        ),
        "notes": [
            "Questions, answers, justifications, and evidence are copied from the human-annotated open-source sample.",
            "FinanceBench evidence_page_num is retained as zero-indexed page_index.",
            "Consult the upstream repository for citation and usage information.",
        ],
    }
    write_json(OUTPUT_DIR / "financebench_manifest.json", manifest)

    print("Generated FinanceBench evaluation datasets:")
    print(f"  dev:  {len(normalized_dev)} cases")
    print(f"  test: {len(normalized_test)} cases")
    print(f"  all:  {len(normalized_all)} cases")
    print(f"  PDFs: {len(DEV_DOCUMENTS | TEST_DOCUMENTS)}")


if __name__ == "__main__":
    main()
