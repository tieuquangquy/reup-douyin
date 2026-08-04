"""Metadata keys and helpers for Reup Queue auto pipeline lane."""

from __future__ import annotations

from typing import Any

PIPELINE_MODE_KEY = "pipeline_mode"
PIPELINE_HOLD_KEY = "pipeline_hold"
PIPELINE_STEP_KEY = "pipeline_step"
# Recorded for manual items too, so handing one to the auto lane resumes from real
# progress instead of guessing from the step that happens to be pinned in metadata.
PIPELINE_LAST_DONE_KEY = "pipeline_last_completed_step"
PIPELINE_MODE_MANUAL = "manual"
PIPELINE_MODE_AUTO_TO_TTS = "auto_to_tts"
PIPELINE_MODE_AUTO_TO_RENDER = "auto_to_render"

PIPELINE_STEP_DOWNLOAD = "download"
PIPELINE_STEP_ANALYZE_AUDIO = "analyze_audio"
PIPELINE_STEP_TRANSLATE = "translate"
PIPELINE_STEP_TRANSLATION_REVIEW = "translation_review"
PIPELINE_STEP_TTS = "tts"
PIPELINE_STEP_OCR = "ocr"
PIPELINE_STEP_QUALITY_REVIEW = "quality_review"
PIPELINE_STEP_RENDER = "render"
PIPELINE_STEP_READY_FINAL = "ready_final"
PIPELINE_STEP_NEEDS_ATTENTION = "needs_attention"

TRANSLATION_JOB_ID_KEY = "translation_job_id"
TTS_JOB_ID_KEY = "tts_job_id"
OCR_JOB_ID_KEY = "ocr_job_id"
RENDER_JOB_ID_KEY = "render_job_id"
ANALYZE_AUDIO_JOB_ID_KEY = "analyze_audio_job_id"
# Automated verdict written by the post-render QA gate; Output Review reads it for badges.
RENDER_QA_KEY = "render_qa"
QUALITY_WORKFLOW_STAGE_KEY = "quality_workflow_stage"
# Quality-knob fingerprint stamped when RENDER finishes; Output Review shows the short hash.
PIPELINE_RECIPE_KEY = "pipeline_recipe"

AUTO_PIPELINE_MODES = frozenset({PIPELINE_MODE_AUTO_TO_TTS, PIPELINE_MODE_AUTO_TO_RENDER})


def meta_dict(item: Any) -> dict[str, Any]:
    raw = getattr(item, "metadata_json", None) or {}
    return dict(raw) if isinstance(raw, dict) else {}


def get_pipeline_mode(item: Any) -> str:
    mode = meta_dict(item).get(PIPELINE_MODE_KEY)
    if isinstance(mode, str) and mode in AUTO_PIPELINE_MODES | {PIPELINE_MODE_MANUAL}:
        return mode
    return PIPELINE_MODE_MANUAL


def is_auto_pipeline(item: Any) -> bool:
    return get_pipeline_mode(item) in AUTO_PIPELINE_MODES


def is_pipeline_held(item: Any) -> bool:
    if getattr(item, "held_at", None) is not None:
        return True
    return bool(meta_dict(item).get(PIPELINE_HOLD_KEY))


def get_pipeline_step(item: Any) -> str | None:
    step = meta_dict(item).get(PIPELINE_STEP_KEY)
    return str(step) if step else None


def get_last_completed_step(item: Any) -> str | None:
    step = meta_dict(item).get(PIPELINE_LAST_DONE_KEY)
    return str(step) if step else None


def set_pipeline_meta(
    item: Any,
    *,
    mode: str | None = None,
    hold: bool | None = None,
    step: str | None = None,
    last_completed_step: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = meta_dict(item)
    if mode is not None:
        meta[PIPELINE_MODE_KEY] = mode
    if hold is not None:
        meta[PIPELINE_HOLD_KEY] = bool(hold)
    if step is not None:
        meta[PIPELINE_STEP_KEY] = step
    if last_completed_step is not None:
        meta[PIPELINE_LAST_DONE_KEY] = last_completed_step
    if extra:
        meta.update(extra)
    item.metadata_json = meta
    return meta


def parse_automation_mode(raw: str | None) -> str | None:
    """Strict parse for operator-chosen automation level; None when unrecognised."""
    value = (raw or "").strip().lower()
    if value in AUTO_PIPELINE_MODES or value == PIPELINE_MODE_MANUAL:
        return value
    return None


def normalize_pipeline_mode(raw: str | None) -> str:
    value = (raw or PIPELINE_MODE_AUTO_TO_TTS).strip().lower()
    if value == PIPELINE_MODE_AUTO_TO_RENDER:
        return PIPELINE_MODE_AUTO_TO_RENDER
    if value in AUTO_PIPELINE_MODES:
        return value
    return PIPELINE_MODE_AUTO_TO_TTS
