from __future__ import annotations

from datetime import UTC, datetime

FETCH_STAGE_ACCOUNT_RESOLUTION = "account_resolution"
FETCH_STAGE_REQUEST_DISPATCH = "request_dispatch"
FETCH_STAGE_RESPONSE_CLASSIFICATION = "response_classification"
FETCH_STAGE_PARSE_PAYLOAD = "parse_payload"
FETCH_STAGE_NORMALIZE_PAYLOAD = "normalize_payload"
FETCH_STAGE_PERSIST_ENTITIES = "persist_entities"
FETCH_STAGE_CANDIDATE_FILTER = "candidate_filter"

FETCH_STAGE_RESULTS = {"ok", "warning", "blocked", "failed", "skipped"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def stage_event(
    *,
    result: str,
    code: str,
    message: str,
    metrics: dict | None = None,
) -> dict:
    safe_result = result if result in FETCH_STAGE_RESULTS else "failed"
    payload: dict = {
        "result": safe_result,
        "code": code,
        "message": message,
        "ts": now_iso(),
    }
    if isinstance(metrics, dict) and metrics:
        payload["metrics"] = metrics
    return payload


def blocked_reason_from_error(*, error_code: str | None, error_message: str | None) -> str | None:
    code = (error_code or "").lower()
    message = (error_message or "").lower()

    if "login" in code or "login" in message or "auth" in code:
        return "login_required"
    if "challenge" in code or "captcha" in code or "challenge" in message or "captcha" in message:
        return "challenge_required"
    if "unsupported" in code or "shape" in code or "normalize" in code:
        return "unsupported_shape"
    if "rate" in code or "throttle" in code or "429" in message or "empty" in message:
        return "throttled_or_empty"
    if "forbidden" in code or "403" in message or "network" in message:
        return "network_forbidden"
    return None
