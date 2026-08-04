from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from src.core.settings import get_settings


class MetricCollectionFailureClass(StrEnum):
    RATE_LIMITED = "rate_limited"
    TRANSIENT = "transient"
    TERMINAL = "terminal"


_RATE_LIMIT_CODES = {"metrics_rate_limited", "metrics_account_cooldown"}
_TERMINAL_CODE_MARKERS = (
    "not_found",
    "inactive",
    "on_hold",
    "not_published",
    "payload_invalid",
    "not_supported",
    "mock_",
    "sensitive_",
    "idempotency_conflict",
    "auth",
    "permission",
    "credentials",
    "identity_missing",
    "capability",
    "platform_invalid",
    "network_authorization",
    "configuration_invalid",
    "provider_request_invalid",
    "media_reference_missing",
    "live_preflight",
)


def classify_metric_collection_failure(error_code: str | None) -> MetricCollectionFailureClass:
    code = str(error_code or "").strip().lower()
    if code in _RATE_LIMIT_CODES:
        return MetricCollectionFailureClass.RATE_LIMITED
    if any(marker in code for marker in _TERMINAL_CODE_MARKERS):
        return MetricCollectionFailureClass.TERMINAL
    return MetricCollectionFailureClass.TRANSIENT


def next_metric_collection_retry_at(
    *,
    attempts: int,
    retry_after_seconds: int | None = None,
    now: datetime | None = None,
    settings: object | None = None,
) -> datetime:
    cfg = settings or get_settings()
    base = max(1, int(getattr(cfg, "metrics_collection_retry_backoff_base_seconds", 60)))
    cap = max(base, int(getattr(cfg, "metrics_collection_retry_backoff_max_seconds", 3600)))
    if retry_after_seconds is not None:
        # Provider/account cooldown is an explicit earliest-safe time, not a backoff
        # suggestion. Capping it would wake the job early and spend quota just to learn
        # that the same cooldown is still active.
        delay = max(1, int(retry_after_seconds))
    else:
        delay = min(cap, base * (2 ** max(0, int(attempts) - 1)))
    return (now or datetime.now(UTC)) + timedelta(seconds=delay)


def metric_collection_operator_message(
    *,
    failure_class: MetricCollectionFailureClass,
    error_message: str | None,
    will_retry: bool,
) -> str:
    base = (error_message or "Publication metric collection failed").strip()
    if failure_class == MetricCollectionFailureClass.TERMINAL:
        return f"{base} [terminal · operator/provider configuration check required]."
    if will_retry:
        return f"{base} [{failure_class.value} · automatic retry scheduled]."
    return f"{base} [{failure_class.value} · retries exhausted]."
