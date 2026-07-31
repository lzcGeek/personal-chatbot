"""Local deterministic metrics exposed through DeepEval's reporting interface."""

from __future__ import annotations

from typing import Any

from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase, SingleTurnParams

from evals.evaluation_scoring import score_gold_contexts, score_numeric_answer


class _DeterministicMetric(BaseMetric):
    async_mode = False
    evaluation_model = "deterministic-local"
    include_reason = True

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self) -> bool:
        self.success = self.error is None and bool(
            self.score is not None and self.score >= self.threshold
        )
        return self.success


class GoldEvidenceRecallMetric(_DeterministicMetric):
    _required_params = [SingleTurnParams.RETRIEVAL_CONTEXT]

    def __init__(
        self,
        gold_evidence: list[dict[str, Any]],
        *,
        match_threshold: float = 0.6,
        threshold: float = 1.0,
    ) -> None:
        self.gold_evidence = gold_evidence
        self.match_threshold = match_threshold
        self.threshold = threshold

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        result = score_gold_contexts(
            self.gold_evidence,
            test_case.retrieval_context or [],
            match_threshold=self.match_threshold,
        )
        self.score = float(result["recall"])
        self.success = self.score >= self.threshold
        matched = sum(row["matched"] for row in result["evidence"])
        self.reason = (
            f"Matched {matched}/{len(result['evidence'])} annotated evidence "
            f"passages at shingle coverage >= {self.match_threshold:.2f}; "
            f"best coverage={result['best_coverage']:.3f}."
        )
        return self.score

    @property
    def __name__(self) -> str:
        return "Gold Evidence Recall"


class GoldEvidenceReciprocalRankMetric(_DeterministicMetric):
    _required_params = [SingleTurnParams.RETRIEVAL_CONTEXT]

    def __init__(
        self,
        gold_evidence: list[dict[str, Any]],
        *,
        match_threshold: float = 0.6,
        rank_pass_k: int = 3,
    ) -> None:
        self.gold_evidence = gold_evidence
        self.match_threshold = match_threshold
        self.rank_pass_k = max(1, rank_pass_k)
        self.threshold = 1 / self.rank_pass_k

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        result = score_gold_contexts(
            self.gold_evidence,
            test_case.retrieval_context or [],
            match_threshold=self.match_threshold,
        )
        self.score = float(result["reciprocal_rank"])
        self.success = self.score >= self.threshold
        rank = result["first_relevant_rank"]
        self.reason = (
            f"First annotated evidence rank={rank if rank is not None else 'none'}; "
            f"pass condition is rank <= {self.rank_pass_k}."
        )
        return self.score

    @property
    def __name__(self) -> str:
        return "Gold Evidence Reciprocal Rank"


class NumericAnswerCorrectnessMetric(_DeterministicMetric):
    _required_params = [SingleTurnParams.ACTUAL_OUTPUT]

    def __init__(self, numeric_spec: dict[str, Any]) -> None:
        self.numeric_spec = numeric_spec
        self.threshold = 1.0

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        result = score_numeric_answer(
            test_case.actual_output or "",
            self.numeric_spec,
        )
        self.score = float(result["score"])
        self.success = self.score >= self.threshold
        missing = [
            row["expected"] for row in result["values"] if not row["matched"]
        ]
        direction = ""
        if result["expected_direction"]:
            direction = (
                f"; expected direction={result['expected_direction']}, "
                f"detected={result['actual_direction']}"
            )
        self.reason = (
            f"Missing expected numeric values={missing or 'none'}"
            f"{direction}. Values use declared absolute/relative tolerances."
        )
        return self.score

    @property
    def __name__(self) -> str:
        return "Numeric Answer Correctness"
