"""Retry policy for localization pipeline stages after download.

Download has its own policy (`src.downloaders.download_error_policy`) because its failure
surface is Douyin/Playwright specific. Everything downstream — audio analysis, translation,
TTS, OCR, render — fails for two very different reasons: a flaky external call or busy file
handle (worth retrying), or a deterministic defect / missing input (retrying only wastes
minutes of GPU time). Classify once here so every stage behaves the same.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from src.core.settings import get_settings


class PipelineFailureClass(StrEnum):
    TRANSIENT = "transient"
    TERMINAL = "terminal"


# Python exception names that mean the code or its input is wrong, not the environment.
_TERMINAL_EXCEPTIONS = (
    "attributeerror",
    "keyerror",
    "typeerror",
    "valueerror",
    "importerror",
    "modulenotfounderror",
    "assertionerror",
    "nameerror",
    "indexerror",
    "notimplementederror",
    "zerodivisionerror",
)

_TERMINAL_MARKERS = (
    "no such file or directory",
    "has no downloaded asset",
    "asset content is empty",
    "not found",
    "missing ",
    "unsupported ",
    "invalid ",
    "no audio stream",
    "no transcript",
)

_TRANSIENT_MARKERS = (
    "timeout",
    "timed out",
    "connection",
    "network",
    "temporarily",
    "unavailable",
    "rate limit",
    "http 408",
    "http 429",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
    "out of memory",
    "being used by another process",
    "resource busy",
    "winerror 32",
    "try again",
)

_TRANSIENT_CODE_MARKERS = ("disk_space_low",)

_TERMINAL_CODE_MARKERS = (
    "missing_",
    "invalid_",
    "unsupported_",
    "not_found",
    "validation_failed",
    "recipe_workflow_mismatch",
    "quality_review_required",
    "quality_preflight_blocked",
    "quality_output_qa_failed",
    "blocked_visual_residual_cjk",
    "timing_fit_blocked",
    "translation_review_required",
)

_TERMINAL_PROVIDER_MARKERS = (
    "http_401",
    "http 401",
    "http_403",
    "http 403",
    "api key has expired",
    "api key expired",
    "api key đã hết hạn",
    "authentication failed",
    "authorization failed",
)


def classify_pipeline_failure(error_code: str | None, error_message: str | None) -> PipelineFailureClass:
    code = str(error_code or "").strip().lower()
    message = str(error_message or "").strip().lower()

    # A full volume is an environment condition, not a defect in the clip: wait for room.
    if any(marker in code for marker in _TRANSIENT_CODE_MARKERS):
        return PipelineFailureClass.TRANSIENT

    # Transient environment signals win over generic terminal wording such as "invalid",
    # because a timed-out provider often reports both.
    if any(marker in message for marker in _TRANSIENT_MARKERS):
        return PipelineFailureClass.TRANSIENT

    if any(marker in message for marker in _TERMINAL_PROVIDER_MARKERS):
        return PipelineFailureClass.TERMINAL

    if any(message.startswith(name) for name in _TERMINAL_EXCEPTIONS):
        return PipelineFailureClass.TERMINAL

    if any(marker in code for marker in _TERMINAL_CODE_MARKERS):
        return PipelineFailureClass.TERMINAL

    if any(marker in message for marker in _TERMINAL_MARKERS):
        return PipelineFailureClass.TERMINAL

    # Unknown failures get a bounded number of cheap retries; the cap stops runaway loops.
    return PipelineFailureClass.TRANSIENT


def pipeline_transient_max_attempts(settings: object | None = None) -> int:
    cfg = settings if settings is not None else get_settings()
    try:
        return max(1, int(getattr(cfg, "pipeline_transient_max_attempts", 3)))
    except (TypeError, ValueError):
        return 3


def should_auto_retry_pipeline_failure(
    *,
    failure_class: PipelineFailureClass,
    attempts: int,
    max_attempts: int | None = None,
) -> bool:
    if failure_class == PipelineFailureClass.TERMINAL:
        return False
    cap = max(1, int(max_attempts if max_attempts is not None else pipeline_transient_max_attempts()))
    return int(attempts) < cap


def next_pipeline_retry_at(
    *,
    attempts: int,
    now: datetime | None = None,
    base_seconds: int | None = None,
    max_seconds: int | None = None,
) -> datetime:
    settings = get_settings() if base_seconds is None or max_seconds is None else None
    base = max(
        1,
        int(base_seconds if base_seconds is not None else getattr(settings, "pipeline_retry_backoff_base_seconds", 15)),
    )
    cap = max(
        base,
        int(max_seconds if max_seconds is not None else getattr(settings, "pipeline_retry_backoff_max_seconds", 300)),
    )
    delay = min(cap, base * (2 ** max(0, int(attempts) - 1)))
    return (now or datetime.now(UTC)) + timedelta(seconds=delay)


def pipeline_failure_operator_message(
    *,
    failure_class: PipelineFailureClass,
    error_message: str | None,
    will_retry: bool,
) -> str:
    base = (error_message or "Pipeline step failed").strip()
    if failure_class == PipelineFailureClass.TERMINAL:
        return f"{base} [terminal · needs manual check]. Retrying will not help — inspect the item's inputs."
    if will_retry:
        return f"{base} [transient · auto-retry scheduled]."
    return f"{base} [transient · retries exhausted · needs manual check]."
