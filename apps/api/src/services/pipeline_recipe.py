"""Stable recipe fingerprint for finished reup products.

When an operator asks "why does today's batch sound quieter / look different?", the
answer must live on the clip itself — not in chat history or a forgotten .env change.
This module records the quality-affecting knobs that produced a render and hashes them
into a short fingerprint.

Stamp only at RENDER completion (orchestrator chokepoint). Intermediate jobs must not
rewrite the recipe: a half-finished clip has no product yet.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from src.media_pipeline.frame_sampling.phase1_policy import (
    FINAL_COVERAGE_FADE_TAIL_MAX_FRAMES,
)
from src.services.reup_pipeline_meta import PIPELINE_RECIPE_KEY, set_pipeline_meta

# Bump when the recipe field set changes shape (not when one setting value changes).
PIPELINE_RECIPE_SCHEMA = "pipeline_recipe_v3"

# The current product path is Master Phase 1 v58. Authority V3.6 full-duration is
# deliberately not part of this locked pilot.
OCR_AUTHORITY_VERSION = "phase1_v58_candidate_master_timeline"


def _settings_value(settings: object | None, name: str, default: Any) -> Any:
    if settings is None:
        return default
    return getattr(settings, name, default)


def build_recipe_dict(
    *,
    settings: object | None = None,
    pipeline_mode: str,
    skip_dubbing: bool,
) -> dict[str, Any]:
    """Quality-affecting knobs only — concurrency / disk guards do not belong here."""
    loudness_on = bool(_settings_value(settings, "render_loudness_normalization_enabled", True))
    target = float(_settings_value(settings, "render_loudness_target_lufs", -14.0))
    return {
        "ocr_authority": OCR_AUTHORITY_VERSION,
        "phase1": {
            "extractor_version": "v58_candidate",
            "step": 1,
            "pad": 1,
            "authority_artifact": "master_timeline.json",
            "authority_v3_6_full_duration": False,
            "final_coverage_fade_tail_max_frames": (
                FINAL_COVERAGE_FADE_TAIL_MAX_FRAMES
            ),
        },
        "phase2": {
            "provider": "local",
            "approval_policy": "exact_operator_review",
            "artifact_boundary": "phase2_ocr_timeline.json",
        },
        "pipeline_mode": str(pipeline_mode or "manual"),
        "skip_dubbing": bool(skip_dubbing),
        "loudness": {
            "enabled": loudness_on,
            "target_lufs": round(target, 3),
        },
        "tts": {
            "provider": str(_settings_value(settings, "audio_tts_provider", "auto") or "auto"),
            "voice_id": str(_settings_value(settings, "audio_tts_voice_id", "") or ""),
            "speaking_rate": round(float(_settings_value(settings, "audio_tts_speaking_rate", 1.0) or 1.0), 3),
            "model_id": str(_settings_value(settings, "audio_tts_model_id", "") or ""),
            "fallback_provider": str(_settings_value(settings, "audio_tts_fallback_provider", "none") or "none"),
        },
    }


def recipe_fingerprint(recipe: dict[str, Any]) -> str:
    payload = json.dumps(recipe, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_pipeline_recipe(
    *,
    settings: object | None = None,
    pipeline_mode: str,
    skip_dubbing: bool,
    stamped_at: datetime | None = None,
) -> dict[str, Any]:
    recipe = build_recipe_dict(
        settings=settings,
        pipeline_mode=pipeline_mode,
        skip_dubbing=skip_dubbing,
    )
    when = stamped_at or datetime.now(UTC)
    return {
        "schema": PIPELINE_RECIPE_SCHEMA,
        "fingerprint": recipe_fingerprint(recipe),
        "stamped_at": when.isoformat(),
        "recipe": recipe,
    }


def stamp_pipeline_recipe(
    item: Any,
    *,
    settings: object | None = None,
    pipeline_mode: str | None = None,
    skip_dubbing: bool | None = None,
) -> dict[str, Any]:
    from src.services.reup_pipeline_meta import get_pipeline_mode

    mode = pipeline_mode if pipeline_mode is not None else get_pipeline_mode(item)
    skip = bool(skip_dubbing) if skip_dubbing is not None else False
    if settings is None:
        from src.core.settings import get_settings

        settings = get_settings()
    payload = build_pipeline_recipe(
        settings=settings,
        pipeline_mode=mode,
        skip_dubbing=skip,
    )
    # Keep the runtime quality fingerprint and the immutable controlled-pilot
    # authority together.  The former describes effective knobs; the latter
    # proves which locked V24 artifact was selected for this queue item.
    from src.services.pipeline_recipe_runtime import RECIPE_LOCK_REF_KEY
    from src.services.reup_pipeline_meta import meta_dict

    lock_ref = meta_dict(item).get(RECIPE_LOCK_REF_KEY)
    if isinstance(lock_ref, dict) and lock_ref:
        payload["locked_recipe_ref"] = dict(lock_ref)
    set_pipeline_meta(item, extra={PIPELINE_RECIPE_KEY: payload})
    return payload
