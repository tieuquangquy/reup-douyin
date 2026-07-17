from __future__ import annotations

from src.render_pipeline.types import RENDER_PIPELINE_VERSION, RenderProfile, ResolvedRenderInput, VideoProbe


def build_render_manifest(
    *,
    source_video_id: str,
    render_output_id: str,
    render_version: str,
    resolved_input: ResolvedRenderInput,
    output_asset: dict,
    render_profile: RenderProfile,
    input_probe: VideoProbe,
    output_probe: VideoProbe,
    warnings: list[str],
    job_id: str | None,
) -> dict:
    return {
        "manifest_version": "RENDER_MANIFEST_V1",
        "pipeline_version": RENDER_PIPELINE_VERSION,
        "render_output_id": render_output_id,
        "source_video_id": source_video_id,
        "render_version": render_version,
        "inputs": {
            "render_prep_manifest_asset_id": str(resolved_input.render_prep_manifest_asset_id),
            "source_video_storage_key": resolved_input.source_video_storage_key,
            "narration_storage_key": resolved_input.narration_storage_key,
            "subtitle_storage_key": resolved_input.subtitle_storage_key,
        },
        "output": output_asset,
        "render_settings": {
            "output_format": render_profile.output_format,
            "video_codec": render_profile.video_codec,
            "audio_codec": render_profile.audio_codec,
            "subtitle_burned": render_profile.subtitle_burned,
            "audio_strategy": render_profile.audio_strategy,
            "keep_source_resolution": render_profile.keep_source_resolution,
            "keep_source_fps": render_profile.keep_source_fps,
        },
        "probe": {
            "input": input_probe.__dict__,
            "output": output_probe.__dict__,
        },
        "warnings": warnings,
        "job_id": job_id,
    }
