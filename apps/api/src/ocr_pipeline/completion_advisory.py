"""Advisory signals when ANALYZE_OCR completes without a new cleaned plate."""

from __future__ import annotations

OCR_NO_HARDSUB_OUTPUT = "OCR_NO_HARDSUB_OUTPUT"
OCR_NO_HARDSUB_MESSAGE = (
    "No hard-sub detected; clean skipped — no new cleaned MP4 (prior kept if any)"
)

_NO_OUTPUT_WARNINGS = frozenset({"clean_skipped_no_hardsub", "no_hardsub_detected"})


def ocr_completion_advisory(warnings: list[str] | None) -> tuple[str, str] | None:
    """Return (error_code, error_message) for Ops Jobs when clean produced nothing new."""
    for warning in warnings or []:
        if warning in _NO_OUTPUT_WARNINGS:
            return OCR_NO_HARDSUB_OUTPUT, OCR_NO_HARDSUB_MESSAGE
    return None


def ocr_run_produced_cleaned_video(
    warnings: list[str] | None,
    *,
    cleaned_asset_id: str | None,
) -> bool:
    """True only when this run wrote a fresh CLEANED_VIDEO (not a restored prior)."""
    if not cleaned_asset_id:
        return False
    if "clean_skipped_no_hardsub" in (warnings or []):
        return False
    return True
