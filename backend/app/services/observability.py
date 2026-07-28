import logging
from collections import Counter
from contextvars import ContextVar
from threading import Lock


logger = logging.getLogger("app.chat.telemetry")
_lock = Lock()
_counters: Counter[str] = Counter()
_request_retry_count: ContextVar[int] = ContextVar("request_retry_count", default=0)


def record_metric(name: str, amount: int = 1) -> None:
    with _lock:
        _counters[name] += amount


def metrics_snapshot() -> dict[str, int]:
    with _lock:
        return dict(_counters)


def record_duration(name: str, duration_ms: int) -> None:
    with _lock:
        _counters[f"{name}.count"] += 1
        _counters[f"{name}.total_ms"] += max(duration_ms, 0)


def reset_request_metrics() -> None:
    _request_retry_count.set(0)


def record_llm_retry() -> None:
    _request_retry_count.set(_request_retry_count.get() + 1)
    record_metric("llm.retry")


def log_chat_outcome(
    *,
    request_id: str,
    outcome: str,
    duration_ms: int,
    error_code: str | None = None,
    degradations: list[str] | None = None,
) -> None:
    record_metric(f"chat.outcome.{outcome}")
    for degradation in degradations or []:
        record_metric(f"chat.degradation.{degradation}")
    if error_code:
        record_metric(f"chat.error.{error_code}")
    logger.info(
        "chat_request request_id=%s outcome=%s duration_ms=%d attempts=%d error_code=%s degradations=%s",
        request_id,
        outcome,
        duration_ms,
        _request_retry_count.get() + 1,
        error_code or "none",
        ",".join(degradations or []) or "none",
    )


def log_routing(plan_id: str, strategy: str, speaker_count: int, reason_code: str, duration_ms: int = 0) -> None:
    record_metric(f"routing.strategy.{strategy}")
    record_metric(f"routing.reason.{reason_code}")
    record_duration("routing.duration", duration_ms)
    logger.info(
        "npc_routing plan_id=%s strategy=%s speaker_count=%d reason_code=%s duration_ms=%d",
        plan_id, strategy, speaker_count, reason_code, duration_ms,
    )


def log_speaker_generation(plan_id: str, plan_index: int, outcome: str, duration_ms: int) -> None:
    record_metric(f"speaker.outcome.{outcome}")
    record_duration("speaker.duration", duration_ms)
    logger.info(
        "npc_speaker plan_id=%s plan_index=%d outcome=%s duration_ms=%d",
        plan_id, plan_index, outcome, duration_ms,
    )


def record_context_allocation(included: set[str], omitted: set[str], characters: int) -> None:
    record_metric("context.build")
    record_metric("context.characters", characters)
    for name in included:
        record_metric(f"context.included.{name}")
    for name in omitted:
        record_metric(f"context.omitted.{name}")


def log_background_job(kind: str, outcome: str) -> None:
    record_metric(f"background.{kind}.{outcome}")
    logger.info("background_job kind=%s outcome=%s", kind, outcome)
