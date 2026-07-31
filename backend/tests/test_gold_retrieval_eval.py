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
