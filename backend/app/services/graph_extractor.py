import json
from typing import Any

from app.services.llm_client import LlmClient


class GraphExtractor:
    def __init__(self, llm_client: LlmClient, max_facts_per_chunk: int = 20) -> None:
        self.llm_client = llm_client
        self.max_facts_per_chunk = max_facts_per_chunk

    async def extract(self, text: str) -> list[dict[str, Any]]:
        turn = await self.llm_client.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "Extract explicit factual relations from the supplied document excerpt. "
                        "Return only JSON with a `facts` array. Each fact must contain subject, "
                        "subject_type, predicate, object, object_type, source_text, and confidence "
                        "from 0 to 1. Do not infer facts not stated by the excerpt."
                    ),
                },
                {"role": "user", "content": text[:12000]},
            ],
            temperature=0,
        )
        payload = self._parse_json(turn.content)
        facts = payload.get("facts", []) if isinstance(payload, dict) else []
        if not isinstance(facts, list):
            return []
        result: list[dict[str, Any]] = []
        for item in facts[: self.max_facts_per_chunk]:
            if not isinstance(item, dict):
                continue
            subject = self._text(item.get("subject"), 300)
            predicate = self._text(item.get("predicate"), 200)
            obj = self._text(item.get("object"), 500)
            if not subject or not predicate or not obj:
                continue
            try:
                confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
            except (TypeError, ValueError):
                confidence = 0.5
            result.append(
                {
                    "subject": subject,
                    "subject_type": self._text(item.get("subject_type"), 100) or "Entity",
                    "predicate": predicate,
                    "object": obj,
                    "object_type": self._text(item.get("object_type"), 100) or "Entity",
                    "source_text": self._text(item.get("source_text"), 1000) or text[:1000],
                    "confidence": confidence,
                }
            )
        return result

    @staticmethod
    def _parse_json(content: str) -> Any:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            start, end = stripped.find("{"), stripped.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(stripped[start : end + 1])
                except json.JSONDecodeError:
                    pass
        return {}

    @staticmethod
    def _text(value: Any, limit: int) -> str:
        return str(value).strip()[:limit] if value is not None else ""
