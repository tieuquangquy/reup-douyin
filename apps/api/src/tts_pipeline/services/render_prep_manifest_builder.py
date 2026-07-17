from __future__ import annotations

from collections import Counter

from src.models.media import MediaAsset
from src.tts_pipeline.types import SynthesizedSegment, TTS_PIPELINE_VERSION


def build_render_prep_manifest(
    *,
    source_video_id: str,
    source_video_external_id: str,
    assets: list[MediaAsset],
    synthesized_segments: list[SynthesizedSegment],
    subtitle_version: str,
    provider_summary: dict,
    warnings: list[str],
) -> dict:
    by_type = {}
    for asset in assets:
        if asset.is_current:
            by_type.setdefault(str(asset.asset_type), []).append(
                {
                    "id": str(asset.id),
                    "storage_key": asset.storage_key,
                    "logical_key": asset.logical_key,
                    "mime_type": asset.mime_type,
                    "version": asset.version,
                    "metadata_json": asset.metadata_json,
                }
            )
    fit_summary = Counter(str(segment.fit_status) for segment in synthesized_segments)
    return {
        "manifest_version": "RENDER_PREP_MANIFEST_V1",
        "pipeline_version": TTS_PIPELINE_VERSION,
        "source_video": {
            "id": source_video_id,
            "external_id": source_video_external_id,
        },
        "current_outputs": {
            "tts_clips": by_type.get("TTS_AUDIO_CLIP", []),
            "joined_narration": by_type.get("TTS_AUDIO_JOINED", []),
            "subtitle_json": by_type.get("SUBTITLE_JSON", []),
            "subtitle_srt": by_type.get("SUBTITLE_SRT", []),
            "cleaned_video": by_type.get("CLEANED_VIDEO", []),
            "ocr_events": by_type.get("OCR_EVENTS", []),
        },
        "subtitle_version": subtitle_version,
        "timing_fit_summary": dict(fit_summary),
        "provider_summary": provider_summary,
        "warnings": warnings,
        "render_contract": {
            "source_video_asset_type": (
                "CLEANED_VIDEO" if by_type.get("CLEANED_VIDEO") else "SOURCE_VIDEO_RAW"
            ),
            "narration_asset_type": "TTS_AUDIO_JOINED",
            "subtitle_asset_type": "SUBTITLE_JSON",
            "subtitle_track_kind": "vietnamese_hard_burn",
        },
    }
