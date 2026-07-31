"""End-to-end DeepEval tests for NewAgent's personal-document RAG."""

import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from dotenv import load_dotenv

from deepeval import assert_test
from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
)
from deepeval.models import GPTModel
from deepeval.test_case import LLMTestCase

from evals.deepeval_metrics import (
    GoldEvidenceRecallMetric,
    GoldEvidenceReciprocalRankMetric,
    NumericAnswerCorrectnessMetric,
)


EVALS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVALS_DIR.parents[1]
DEFAULT_DATASET_PATH = EVALS_DIR / "datasets" / "rag_goldens.json"
load_dotenv(PROJECT_ROOT / ".env")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise RuntimeError(
            f"Missing {name}. Add it to {PROJECT_ROOT / '.env'} before running evals."
        )
    return value.strip()


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def resolve_dataset_path() -> Path:
    configured = os.getenv("EVAL_DATASET_PATH", "").strip()
    if not configured:
        return DEFAULT_DATASET_PATH

    path = Path(configured)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_goldens() -> list[dict[str, Any]]:
    dataset_path = resolve_dataset_path()
    if not dataset_path.is_file():
        raise RuntimeError(f"Evaluation dataset does not exist: {dataset_path}")

    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise RuntimeError(
            f"Evaluation dataset must be a non-empty list: {dataset_path}"
        )

    required = {"id", "input", "expected_output", "acceptable_sources"}
    for index, item in enumerate(raw, start=1):
        missing = required - set(item)
        if missing:
            raise RuntimeError(
                f"Dataset item {index} is missing fields: {', '.join(sorted(missing))}"
            )

    limit = int(os.getenv("EVAL_CASE_LIMIT", "5"))
    if limit < 0:
        raise RuntimeError("EVAL_CASE_LIMIT must be 0 or a positive integer.")
    return raw if limit <= 0 else raw[:limit]


JUDGE_MODEL = GPTModel(
    model=os.getenv("EVAL_JUDGE_MODEL") or require_env("OPENAI_MODEL"),
    api_key=os.getenv("EVAL_JUDGE_API_KEY") or require_env("OPENAI_API_KEY"),
    base_url=os.getenv("EVAL_JUDGE_BASE_URL") or require_env("OPENAI_BASE_URL"),
    temperature=0,
)


def build_metrics(golden: dict[str, Any]):
    """Create fresh metric instances for each test case.

    ``fast`` is intended for frequent development feedback. ``full`` is the
    comparable release report and remains the default. Retrieval/generation
    profiles are useful when a failure has already been isolated to one stage.
    """
    profile = os.getenv("EVAL_METRIC_PROFILE", "full").strip().lower()
    profiles = {
        "fast": ("gold_recall", "numeric_correctness", "faithfulness"),
        "retrieval": ("gold_recall", "gold_reciprocal_rank"),
        "generation": (
            "numeric_correctness",
            "faithfulness",
            "answer_relevancy",
        ),
        "full": (
            "gold_recall",
            "gold_reciprocal_rank",
            "numeric_correctness",
            "faithfulness",
            "answer_relevancy",
        ),
    }
    if profile not in profiles:
        raise RuntimeError(
            "EVAL_METRIC_PROFILE must be one of: fast, retrieval, generation, full."
        )

    include_reason_raw = os.getenv("EVAL_INCLUDE_REASON", "").strip()
    include_reason = (
        profile == "full"
        if not include_reason_raw
        else include_reason_raw.lower() in {"1", "true", "yes", "on"}
    )
    evaluation = dict(golden.get("evaluation") or {})
    gold_evidence = list(golden.get("metadata", {}).get("gold_evidence") or [])
    match_threshold = float(evaluation.get("gold_match_threshold", 0.6))
    factories = {
        "gold_recall": lambda: GoldEvidenceRecallMetric(
            gold_evidence,
            match_threshold=match_threshold,
        ),
        "gold_reciprocal_rank": lambda: GoldEvidenceReciprocalRankMetric(
            gold_evidence,
            match_threshold=match_threshold,
            rank_pass_k=int(evaluation.get("rank_pass_k", 3)),
        ),
        "numeric_correctness": lambda: (
            NumericAnswerCorrectnessMetric(evaluation["numeric_answer"])
            if evaluation.get("numeric_answer")
            else None
        ),
        "faithfulness": lambda: FaithfulnessMetric(
            threshold=0.8, model=JUDGE_MODEL, include_reason=include_reason
        ),
        "answer_relevancy": lambda: AnswerRelevancyMetric(
            threshold=0.7, model=JUDGE_MODEL, include_reason=include_reason
        ),
    }
    return [
        metric
        for name in profiles[profile]
        if (metric := factories[name]()) is not None
    ]


class NewAgentEvalClient:
    """Small authenticated HTTP client used only by end-to-end evaluations."""

    def __init__(self) -> None:
        self.base_url = os.getenv("EVAL_BASE_URL", "http://127.0.0.1:8021").rstrip("/")
        self.csrf_cookie_name = os.getenv("CSRF_COOKIE_NAME", "newagent_csrf")
        timeout = float(os.getenv("EVAL_REQUEST_TIMEOUT_SECONDS", "180"))
        self.keep_conversations = env_flag("EVAL_KEEP_CONVERSATIONS")
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self.created_conversations: list[str] = []

    def login(self) -> None:
        self._request(
            "POST",
            "/api/auth/login",
            json={
                "username": require_env("EVAL_USERNAME"),
                "password": require_env("EVAL_PASSWORD"),
            },
            include_csrf=False,
        )

    def ask(
        self, question: str
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        conversation = self._request("POST", "/api/conversations")
        conversation_id = str(conversation["id"])
        self.created_conversations.append(conversation_id)

        response = self._request(
            "POST",
            "/api/chat/send",
            json={
                "message": question,
                "conversation_id": conversation_id,
                "allow_network": False,
                "client_request_id": str(uuid.uuid4()),
                "include_retrieval_context": True,
            },
        )
        message = response["message"]
        citations = list(message.get("citations") or [])
        retrieval_context = [
            str(item).strip()
            for item in message.get("retrieval_context") or []
            if str(item).strip()
        ]
        if not retrieval_context:
            # Compatibility with a backend that has not been restarted yet.
            retrieval_context = [
                str(citation["excerpt"]).strip()
                for citation in citations
                if citation.get("excerpt") and str(citation["excerpt"]).strip()
            ]
        return str(message["content"]), citations, retrieval_context

    def close(self) -> None:
        if not self.keep_conversations:
            for conversation_id in reversed(self.created_conversations):
                try:
                    self._request("DELETE", f"/api/conversations/{conversation_id}")
                except Exception:
                    # Cleanup must not hide the actual evaluation result.
                    pass
        self.client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        include_csrf: bool = True,
    ) -> Any:
        headers: dict[str, str] = {}
        if include_csrf and method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            csrf = self.client.cookies.get(self.csrf_cookie_name)
            if not csrf:
                raise RuntimeError("Login succeeded but the CSRF cookie is missing.")
            headers["X-CSRF-Token"] = csrf

        try:
            response = self.client.request(method, path, json=json, headers=headers)
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Cannot connect to NewAgent at {self.base_url}. Start the backend first."
            ) from exc

        if not response.is_success:
            raise RuntimeError(
                f"NewAgent API {method} {path} returned {response.status_code}: "
                f"{response.text[:500]}"
            )
        return response.json() if response.content else None


@pytest.fixture(scope="session")
def newagent_client():
    client = NewAgentEvalClient()
    client.login()
    try:
        yield client
    finally:
        client.close()


GOLDENS = load_goldens()


@pytest.mark.parametrize("golden", GOLDENS, ids=[item["id"] for item in GOLDENS])
def test_rag_quality(
    newagent_client: NewAgentEvalClient,
    golden: dict[str, Any],
) -> None:
    actual_output, citations, retrieval_context = newagent_client.ask(golden["input"])

    assert retrieval_context, (
        "NewAgent returned no document citations. Upload the evaluation documents, "
        "wait until they are ready, and confirm the question retrieves them."
    )

    returned_sources = {
        str(citation.get("filename"))
        for citation in citations
        if citation.get("filename")
    }
    acceptable_sources = set(golden["acceptable_sources"])
    assert returned_sources & acceptable_sources, (
        f"Expected at least one source from {sorted(acceptable_sources)}, "
        f"but NewAgent returned {sorted(returned_sources)}"
    )

    test_case = LLMTestCase(
        input=golden["input"],
        actual_output=actual_output,
        expected_output=golden["expected_output"],
        retrieval_context=retrieval_context,
    )
    assert_test(test_case, build_metrics(golden))
