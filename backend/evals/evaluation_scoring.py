"""Deterministic scoring helpers shared by local and DeepEval RAG evaluations."""

from __future__ import annotations

import re
from typing import Any, Iterable


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]")
_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])[-+]?\$?\s*\(?(\d[\d,]*(?:\.\d+)?)\)?\s*(?:%|times?)?",
    re.IGNORECASE,
)
_DIRECTION_TERMS = {
    "improved": (
        "improv", "increase", "increased", "jump", "rose", "risen", "higher",
        "改善", "上升", "增加", "提高",
    ),
    "declined": (
        "declin", "decrease", "decreased", "drop", "dropped", "fell", "fallen",
        "lower", "下降", "减少", "降低",
    ),
}


def normalized_tokens(value: str) -> list[str]:
    return _TOKEN_PATTERN.findall(value.casefold())


def token_shingles(value: str, size: int = 3) -> set[tuple[str, ...]]:
    tokens = normalized_tokens(value)
    if len(tokens) < size:
        return {(token,) for token in tokens}
    return {
        tuple(tokens[index : index + size])
        for index in range(len(tokens) - size + 1)
    }


def gold_evidence_coverage(gold_excerpt: str, retrieved_context: str) -> float:
    """Return the fraction of ordered gold token shingles present in a context."""
    gold = token_shingles(gold_excerpt)
    if not gold:
        return 0.0
    retrieved = token_shingles(retrieved_context)
    return len(gold & retrieved) / len(gold)


def score_gold_contexts(
    gold_evidence: Iterable[dict[str, Any]],
    retrieval_context: Iterable[str],
    *,
    match_threshold: float = 0.6,
) -> dict[str, Any]:
    """Score evidence coverage and first relevant rank without an LLM judge."""
    contexts = [str(item) for item in retrieval_context]
    evidence_rows: list[dict[str, Any]] = []
    for evidence in gold_evidence:
        excerpt = str(evidence.get("excerpt") or "")
        coverages = [
            gold_evidence_coverage(excerpt, context) for context in contexts
        ]
        best_coverage = max(coverages, default=0.0)
        best_rank = (
            coverages.index(best_coverage) + 1
            if best_coverage >= match_threshold
            else None
        )
        evidence_rows.append(
            {
                "matched": best_rank is not None,
                "best_rank": best_rank,
                "best_coverage": best_coverage,
            }
        )

    matched = [row for row in evidence_rows if row["matched"]]
    first_rank = min(
        (int(row["best_rank"]) for row in matched),
        default=None,
    )
    return {
        "recall": len(matched) / len(evidence_rows) if evidence_rows else 0.0,
        "first_relevant_rank": first_rank,
        "reciprocal_rank": 1 / first_rank if first_rank else 0.0,
        "best_coverage": max(
            (float(row["best_coverage"]) for row in evidence_rows),
            default=0.0,
        ),
        "evidence": evidence_rows,
    }


def extract_answer_numbers(value: str) -> list[float]:
    """Extract answer values while ignoring four-digit calendar/fiscal years."""
    numbers: list[float] = []
    for match in _NUMBER_PATTERN.finditer(value):
        raw = match.group(1).replace(",", "")
        number = float(raw)
        matched_text = match.group(0).strip()
        if matched_text.startswith("-") or (
            "(" in matched_text and ")" in matched_text
        ):
            number = -number
        if raw.isdigit() and len(raw) == 4 and 1900 <= number <= 2100:
            continue
        numbers.append(number)
    return numbers


def infer_direction(value: str) -> str | None:
    lowered = value.casefold()
    matches: list[tuple[int, str]] = []
    for direction, markers in _DIRECTION_TERMS.items():
        for marker in markers:
            index = lowered.find(marker)
            if index >= 0:
                matches.append((index, direction))
    return min(matches)[1] if matches else None


def infer_evaluation_spec(
    expected_output: str,
    question_reasoning: str | None,
) -> dict[str, Any]:
    """Create a transparent default spec; dataset overrides may refine it."""
    reasoning = str(question_reasoning or "").casefold()
    numerical = "numerical reasoning" in reasoning
    spec: dict[str, Any] = {
        "task_type": "calculation" if numerical else "direct",
        "gold_match_threshold": 0.6,
        "rank_pass_k": 3,
    }
    if not numerical:
        return spec

    expected_values = extract_answer_numbers(expected_output)
    direction = infer_direction(expected_output)
    if expected_values or direction:
        spec["numeric_answer"] = {
            "expected_values": expected_values,
            "absolute_tolerance": 0.05,
            "relative_tolerance": 0.01,
            "direction": direction,
        }
    return spec


def score_numeric_answer(
    actual_output: str,
    numeric_spec: dict[str, Any],
) -> dict[str, Any]:
    """Compare declared numeric expectations with the answer deterministically."""
    expected_values = [
        float(value) for value in numeric_spec.get("expected_values") or []
    ]
    actual_values = extract_answer_numbers(actual_output)
    absolute_tolerance = float(numeric_spec.get("absolute_tolerance", 0.05))
    relative_tolerance = float(numeric_spec.get("relative_tolerance", 0.01))

    remaining = list(enumerate(actual_values))
    value_rows: list[dict[str, Any]] = []
    for expected in expected_values:
        tolerance = max(absolute_tolerance, abs(expected) * relative_tolerance)
        candidates = [
            (abs(actual - expected), index, actual)
            for index, actual in remaining
            if abs(actual - expected) <= tolerance
        ]
        if candidates:
            _, matched_index, matched_value = min(candidates)
            remaining = [
                row for row in remaining if row[0] != matched_index
            ]
        else:
            matched_value = None
        value_rows.append(
            {
                "expected": expected,
                "matched": matched_value is not None,
                "actual": matched_value,
                "tolerance": tolerance,
            }
        )

    expected_direction = numeric_spec.get("direction")
    actual_direction = infer_direction(actual_output)
    direction_checked = expected_direction in _DIRECTION_TERMS
    direction_matched = (
        actual_direction == expected_direction if direction_checked else None
    )

    checks = [row["matched"] for row in value_rows]
    if direction_checked:
        checks.append(bool(direction_matched))
    score = sum(checks) / len(checks) if checks else 1.0
    return {
        "score": score,
        "expected_values": expected_values,
        "actual_values": actual_values,
        "values": value_rows,
        "expected_direction": expected_direction,
        "actual_direction": actual_direction,
        "direction_matched": direction_matched,
    }
