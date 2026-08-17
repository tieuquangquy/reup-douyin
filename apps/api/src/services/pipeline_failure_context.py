"""Secret-safe structured failure metadata for durable localization stages."""

from __future__ import annotations

import re
from typing import Any

from src.services.pipeline_retry_policy import PipelineFailureClass, classify_pipeline_failure

_HTTP_STATUS_RE = re.compile(r"(?:http[_ ]|status[=: ]+)(\d{3})", re.IGNORECASE)
_PROVIDER_CODE_RE = re.compile(r"(?:error|provider)[ _-]*code\s*[:=]\s*([a-z0-9_-]+)", re.IGNORECASE)
_PROVIDER_HTTP_RE = re.compile(r"([a-z][a-z0-9_-]{1,80})_http_\d{3}", re.IGNORECASE)

_ERROR_DOMAIN_BY_STEP = {
    "download": "download",
    "analyze_audio": "audio_analysis",
    "translate": "translation",
    "tts": "tts",
    "ocr": "ocr",
    "render_preview": "render_preview",
    "render": "render",
}


def build_pipeline_failure_context(
    *,
    failed_step: str | None,
    error_code: str | None,
    error_message: str | None,
) -> dict[str, Any]:
    """Normalize a worker error without persisting credentials or raw provider payloads."""

    step = str(failed_step or "unknown").strip().lower() or "unknown"
    code = str(error_code or "PIPELINE_JOB_FAILED").strip()
    message = str(error_message or "").strip()
    blob = f"{code} {message}".casefold()
    failure_class = classify_pipeline_failure(code, message)
    context: dict[str, Any] = {
        "error_domain": _ERROR_DOMAIN_BY_STEP.get(step, "pipeline"),
        "failed_step": step,
        "retry_class": failure_class.value,
        "retryable": failure_class == PipelineFailureClass.TRANSIENT,
        "recovery_action": "REVIEW_PIPELINE_FAILURE",
    }

    http_match = _HTTP_STATUS_RE.search(blob)
    if http_match:
        context["http_status"] = int(http_match.group(1))
    provider_match = _PROVIDER_HTTP_RE.search(blob)
    if provider_match:
        context["provider"] = provider_match.group(1).lower()
    provider_code_match = _PROVIDER_CODE_RE.search(blob)
    if provider_code_match:
        context["provider_error_code"] = provider_code_match.group(1)

    is_translation_provider_failure = step == "translate" and (
        "translation_provider" in blob
        or "openai_compatible_http_" in blob
        or "gemini_http_" in blob
        or "google_cloud_http_" in blob
        or "ollama_http_" in blob
    )
    if is_translation_provider_failure:
        context["error_domain"] = "translation_provider"
        if any(
            marker in blob
            for marker in (
                "http_401",
                "http_402",
                "http_403",
                "api_key_missing",
                "missing key",
                "no llm client configured",
                "no completable primary client",
            )
        ):
            context["retry_class"] = "configuration"
            context["retryable"] = False
            context["recovery_action"] = "CHECK_TRANSLATION_AI_CONNECTION"
        else:
            context["recovery_action"] = "RETRY_TRANSLATION_PROVIDER"

    return context
