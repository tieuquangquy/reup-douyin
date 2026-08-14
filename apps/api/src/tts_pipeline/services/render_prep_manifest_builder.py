from __future__ import annotations

from collections import Counter
from typing import Any

from src.models.media import MediaAsset
from src.tts_pipeline.types import SynthesizedSegment, TTS_PIPELINE_VERSION


_SAFE_METADATA_KEYS = {
    "duration_seconds",
    "audio_format",
    "timing_map",
    "assembly_strategy",
    "translation_segment_id",
    "translation_segment_ids",
    "member_segment_indices",
    "fit_status",
    "fit_ratio",
    "provider",
    "warnings",
    "subtitle_version",
    "speech_budget",
}


def _safe_asset(asset: MediaAsset) -> dict[str, Any]:
    raw_metadata = dict(asset.metadata_json or {})
    metadata = {
        key: value for key, value in raw_metadata.items() if key in _SAFE_METADATA_KEYS
    }
    payload = {
        "id": str(asset.id),
        "storage_key": asset.storage_key,
        "logical_key": asset.logical_key,
        "mime_type": asset.mime_type,
        "version": asset.version,
        "sha256": getattr(asset, "checksum_sha256", None),
        "size_bytes": getattr(asset, "size_bytes", None),
        "metadata": metadata,
    }
    if "duration_seconds" in metadata:
        payload["duration_seconds"] = metadata["duration_seconds"]
    if "audio_format" in metadata:
        payload["audio_format"] = metadata["audio_format"]
    return payload


def build_render_prep_manifest(
    *,
    source_video_id: str,
    source_video_external_id: str,
    assets: list[MediaAsset],
    synthesized_segments: list[SynthesizedSegment],
    subtitle_version: str,
    provider_summary: dict,
    warnings: list[str],
    timeline_duration_seconds: float | None = None,
    translation_input_sha256: str | None = None,
    background_stem_ref: dict[str, Any] | None = None,
    duration_gate_summary: dict[str, int] | None = None,
    temporal_summary: dict[str, Any] | None = None,
) -> dict:
    by_type: dict[str, list[dict[str, Any]]] = {}
    seen_asset_ids: set[str] = set()
    for asset in assets:
        asset_id = str(asset.id)
        if asset.is_current and asset_id not in seen_asset_ids:
            seen_asset_ids.add(asset_id)
            by_type.setdefault(str(asset.asset_type), []).append(_safe_asset(asset))
    fit_summary = Counter(str(segment.fit_status) for segment in synthesized_segments)
    return {
        "manifest_version": "RENDER_PREP_MANIFEST_V2",
        "pipeline_version": TTS_PIPELINE_VERSION,
        "source_video": {
            "id": source_video_id,
            "external_id": source_video_external_id,
            "duration_seconds": timeline_duration_seconds,
        },
        "input_authority": {
            "translation_input_sha256": translation_input_sha256,
        },
        "current_outputs": {
            "tts_clips": by_type.get("TTS_AUDIO_CLIP", []),
            "joined_narration": by_type.get("TTS_AUDIO_JOINED", []),
            "subtitle_json": by_type.get("SUBTITLE_JSON", []),
            "subtitle_srt": by_type.get("SUBTITLE_SRT", []),
            "cleaned_video": by_type.get("CLEANED_VIDEO", []),
            "ocr_events": by_type.get("OCR_EVENTS", []),
            "background_audio": (
                [dict(background_stem_ref)] if background_stem_ref else []
            ),
        },
        "subtitle_version": subtitle_version,
        "timing_fit_summary": dict(fit_summary),
        "duration_gate_summary": dict(duration_gate_summary or {}),
        "temporal": dict(temporal_summary or {}),
        "provider_summary": provider_summary,
        "warnings": warnings,
        "audio_review": {
            "status": "PENDING_AUDIO_REVIEW",
            "approved_at": None,
            "operator_id": None,
        },
        "render_contract": {
            "source_video_asset_type": (
                "CLEANED_VIDEO" if by_type.get("CLEANED_VIDEO") else "SOURCE_VIDEO_RAW"
            ),
            "narration_asset_type": "TTS_AUDIO_JOINED",
            "subtitle_asset_type": "SUBTITLE_JSON",
            "subtitle_track_kind": "vietnamese_hard_burn",
            "audio_strategy": (
                "mix_vietnamese_narration_with_background_stem"
                if background_stem_ref
                else "replace_with_timeline_aligned_vietnamese_narration"
            ),
            "timeline_authority": "phase3_tts_final_timeline.json",
            "subtitle_timing_authority": "synthesized_tts_timeline",
        },
    }
