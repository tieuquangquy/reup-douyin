"""OCR quality profile — best vs default runtime knobs."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

OCR_QUALITY_PROFILE_ENV = "OCR_QUALITY_PROFILE"
PROFILE_BEST = "best"
PROFILE_DEFAULT = "default"

# Applied when profile=best (client upload + Phase 2 crop).
BEST_PREPROCESS_MAX_EDGE = 1920
BEST_JPEG_QUALITY = 92
BEST_CROP_BAND = True


def resolve_ocr_quality_profile(override: str | None = None) -> str:
    raw = (override if override is not None else os.environ.get(OCR_QUALITY_PROFILE_ENV, "")).strip().lower()
    if raw in {PROFILE_BEST, "max", "high"}:
        return PROFILE_BEST
    return PROFILE_DEFAULT


def is_best_ocr_profile(override: str | None = None) -> bool:
    return resolve_ocr_quality_profile(override) == PROFILE_BEST


def effective_ocr_preprocess_max_edge(default: int, override: int | None = None) -> int:
    if override is not None:
        return max(64, int(override))
    if is_best_ocr_profile():
        return BEST_PREPROCESS_MAX_EDGE
    return default


def effective_ocr_jpeg_quality(default: int, override: int | None = None) -> int:
    if override is not None:
        return max(50, min(100, int(override)))
    if is_best_ocr_profile():
        return BEST_JPEG_QUALITY
    raw = os.environ.get("OCR_JPEG_QUALITY", "").strip()
    if raw:
        try:
            return max(50, min(100, int(raw)))
        except ValueError:
            logger.warning("invalid_OCR_JPEG_QUALITY raw=%s", raw[:20])
    return default


def effective_ocr_crop_band(default: bool, override: bool | None = None) -> bool:
    if override is not None:
        return bool(override)
    if is_best_ocr_profile():
        return BEST_CROP_BAND
    return default
