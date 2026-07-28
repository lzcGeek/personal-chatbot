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
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
)
from deepeval.models import GPTModel
from deepeval.test_case import LLMTestCase


EVALS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVALS_DIR.parents[1]
DATASET_PATH = EVALS_DIR / "datasets" / "rag_goldens.json"
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


def load_goldens() -> list[dict[str, Any]]:
    raw = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise RuntimeError(f"Evaluation dataset must be a non-empty list: {DATASET_PATH}")

    required = {"id", "input", "expected_output", "acceptable_sources"}
    for index, item in enumerate(raw, start=1):
        missing = required - set(item)
        if missing:
            raise RuntimeError(
                f"Dataset item {index} is missing fields: {', '.join(sorted(missing))}"
            )

    limit = int(os.getenv("EVAL_CASE_LIMIT", "5"))
    return raw if limit <= 0 else raw[:limit]


JUDGE_MODEL = GPTModel(
    model=os.getenv("EVAL_JUDGE_MODEL") or require_env("OPENAI_MODEL"),
    api_key=os.getenv("EVAL_JUDGE_API_KEY") or require_env("OPENAI_API_KEY"),
    base_url=os.getenv("EVAL_JUDGE_BASE_URL") or require_env("OPENAI_BASE_URL"),
    temperature=0,
)


def build_metrics():
    """Create fresh metric instances for each test case."""
    return [
        ContextualPrecisionMetric(threshold=0.7, model=JUDGE_MODEL, include_reason=True),
        ContextualRecallMetric(threshold=0.7, model=JUDGE_MODEL, include_reason=True),
        FaithfulnessMetric(threshold=0.8, model=JUDGE_MODEL, include_reason=True),
        AnswerRelevancyMetric(threshold=0.7, model=JUDGE_MODEL, include_reason=True),
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

    def ask(self, question: str) -> tuple[str, list[dict[str, Any]]]:
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
            },
        )
        message = response["message"]
        return str(message["content"]), list(message.get("citations") or [])

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
    actual_output, citations = newagent_client.ask(golden["input"])
    retrieval_context = [
        str(citation["excerpt"]).strip()
        for citation in citations
        if citation.get("excerpt") and str(citation["excerpt"]).strip()
    ]

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
    assert_test(test_case, build_metrics())
