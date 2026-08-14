from __future__ import annotations

from enum import StrEnum


class RenderPipelineErrorCode(StrEnum):
    MISSING_RENDER_PREP_MANIFEST = "missing_render_prep_manifest"
    MISSING_SOURCE_VIDEO_ASSET = "missing_source_video_asset"
    MISSING_NARRATION_ASSET = "missing_narration_asset"
    MISSING_SUBTITLE_ASSET = "missing_subtitle_asset"
    PROBE_FAILED = "probe_failed"
    AUDIO_PREPARE_FAILED = "audio_prepare_failed"
    SUBTITLE_BURN_PREPARE_FAILED = "subtitle_burn_prepare_failed"
    EXPORT_FAILED = "export_failed"
    OUTPUT_VALIDATION_FAILED = "output_validation_failed"
    PERSISTENCE_FAILED = "persistence_failed"
    QUALITY_REVIEW_REQUIRED = "quality_review_required"
    TTS_AUTHORITY_INVALID = "tts_authority_invalid"
    PIPELINE_RECIPE_WORKFLOW_MISMATCH = "pipeline_recipe_workflow_mismatch"


class RenderPipelineError(Exception):
    def __init__(self, code: RenderPipelineErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
