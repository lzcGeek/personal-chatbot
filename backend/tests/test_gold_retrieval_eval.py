from evals.evaluation_scoring import (
    infer_evaluation_spec,
    score_gold_contexts,
    score_numeric_answer,
)
from evals.evaluate_gold_retrieval import evaluate_case, gold_evidence_coverage


def test_gold_evidence_coverage_tolerates_surrounding_context() -> None:
    gold = "Total current assets 5,308 Total current liabilities 4,476"
    context = (
        "Consolidated Balance Sheets. Total current assets 5,308 "
        "Total current liabilities 4,476. See accompanying notes."
    )

    assert gold_evidence_coverage(gold, context) == 1.0


def test_evaluate_case_requires_matching_source_and_evidence() -> None:
    golden = {
        "id": "case-1",
        "input": "question",
        "metadata": {
            "gold_evidence": [
                {
                    "source": "report.pdf",
                    "page_index": 4,
                    "excerpt": "alpha beta gamma delta epsilon",
                }
            ]
        },
    }
    wrong_source = {
        "filename": "other.pdf",
        "page_number": 5,
        "context_text": "alpha beta gamma delta epsilon",
        "chunk_id": "1",
        "score": 0.9,
        "section": None,
    }
    matching = {
        **wrong_source,
        "filename": "report.pdf",
        "chunk_id": "2",
        "score": 0.8,
    }

    result = evaluate_case(golden, [wrong_source, matching], threshold=0.6)

    assert result["hit"] is True
    assert result["gold_evidence_recall"] == 1.0
    assert result["first_relevant_rank"] == 2
    assert result["reciprocal_rank"] == 0.5
    assert result["best_coverage"] == 1.0


def test_gold_context_scoring_separates_recall_from_rank() -> None:
    evidence = [{"excerpt": "alpha beta gamma delta epsilon"}]
    contexts = [
        "unrelated first context",
        "alpha beta gamma delta epsilon with surrounding text",
    ]

    result = score_gold_contexts(evidence, contexts, match_threshold=0.6)

    assert result["recall"] == 1.0
    assert result["first_relevant_rank"] == 2
    assert result["reciprocal_rank"] == 0.5


def test_numeric_answer_scoring_rejects_wrong_quick_ratio_definition() -> None:
    spec = {
        "expected_values": [0.67, 0.69],
        "absolute_tolerance": 0.02,
        "relative_tolerance": 0.01,
        "direction": "improved",
    }

    result = score_numeric_answer(
        "The quick ratio improved from 0.53 in FY2022 to 0.57 in FY2023.",
        spec,
    )

    assert result["score"] == 1 / 3
    assert result["direction_matched"] is True
    assert all(not row["matched"] for row in result["values"])


def test_numeric_answer_scoring_accepts_values_with_rounding_tolerance() -> None:
    spec = {
        "expected_values": [18.5, 19.4],
        "absolute_tolerance": 0.05,
        "relative_tolerance": 0.01,
        "direction": "declined",
    }

    result = score_numeric_answer(
        "Gross margin declined from 19.39% to 18.55% in FY2023.",
        spec,
    )

    assert result["score"] == 1.0


def test_numeric_direction_uses_primary_statement_before_later_noise() -> None:
    spec = {
        "expected_values": [18.5, 19.4],
        "absolute_tolerance": 0.05,
        "relative_tolerance": 0.01,
        "direction": "declined",
    }

    result = score_numeric_answer(
        "Gross margin declined from 19.4% to 18.5%. Sales later increased.",
        spec,
    )

    assert result["actual_direction"] == "declined"
    assert result["score"] == 1.0


def test_inferred_numeric_spec_ignores_fiscal_years() -> None:
    spec = infer_evaluation_spec(
        "The rate declined from 24.6% in FY2021 to 21.6% in FY2022.",
        "Numerical reasoning",
    )

    assert spec["task_type"] == "calculation"
    assert spec["numeric_answer"]["expected_values"] == [24.6, 21.6]
    assert spec["numeric_answer"]["direction"] == "declined"
