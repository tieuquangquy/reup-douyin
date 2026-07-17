"""Extract per-clip TTS timing-fit fields for tts-summary / Editor badges."""

from __future__ import annotations

from collections import Counter
from typing import Any

from src.enums import MediaAssetType
from src.tts_pipeline.types import TimingFitStatus

_FIT_STATUSES = {status.value for status in TimingFitStatus}


def normalize_fit_status(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, TimingFitStatus):
        return raw.value
    text = str(raw).strip()
    if not text:
        return None
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    key = text.lower()
    return key if key in _FIT_STATUSES else None


def _as_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def extract_tts_clip_fits(assets: list[Any]) -> list[dict[str, Any]]:
    """Return structured fit rows for current TTS_AUDIO_CLIP assets only."""
    clips: list[dict[str, Any]] = []
    for asset in assets:
        asset_type = getattr(asset, "asset_type", None)
        if asset_type != MediaAssetType.TTS_AUDIO_CLIP and str(asset_type) != MediaAssetType.TTS_AUDIO_CLIP.value:
            continue
        if getattr(asset, "is_current", True) is False:
            continue
        meta = getattr(asset, "metadata_json", None) or {}
        if not isinstance(meta, dict):
            meta = {}
        translation_segment_id = meta.get("translation_segment_id")
        warnings_raw = meta.get("warnings") or []
        warnings = [str(item) for item in warnings_raw] if isinstance(warnings_raw, list) else []
        clips.append(
            {
                "asset_id": str(getattr(asset, "id", "")),
                "translation_segment_id": str(translation_segment_id) if translation_segment_id else None,
                "fit_status": normalize_fit_status(meta.get("fit_status")),
                "fit_ratio": _as_float(meta.get("fit_ratio")),
                "duration_seconds": _as_float(meta.get("duration_seconds")),
                "warnings": warnings,
            }
        )
    return clips


def build_timing_fit_summary(clips: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(clip.get("fit_status") for clip in clips if clip.get("fit_status"))
    return {
        "fits_well": int(counts.get("fits_well", 0)),
        "slightly_long": int(counts.get("slightly_long", 0)),
        "too_long": int(counts.get("too_long", 0)),
        "too_short": int(counts.get("too_short", 0)),
    }
