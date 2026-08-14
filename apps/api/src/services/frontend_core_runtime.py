"""Server-authoritative runtime binding for frontend core reup stages.

The browser selects a product action, but it must never select an implementation.
Every durable core job is stamped with the exact installed runtime before it is
persisted. Workers verify that immutable stamp again before doing any work, so a
queued job cannot silently execute a different recipe after a deploy/restart.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from src.audio_pipeline.translation_v3 import TRANSLATION_V3_RECIPE_VERSION
from src.audio_pipeline.types import (
    AUDIO_ANALYSIS_RECIPE_VERSION,
    AUDIO_ANALYSIS_VERSION,
)
from src.downloaders.download_quality_policy import DOWNLOAD_POLICY_VERSION
from src.downloaders.post_download_qa import POST_DOWNLOAD_QA_VERSION
from src.enums import JobType
from src.media_pipeline.frame_sampling.event_candidate_scheduler import (
    EVENT_SCAN_ENGINE_VERSION,
    EVENT_SCAN_POLICY_VERSION,
)
from src.media_pipeline.video_renderer.render_policy import RENDER_POLICY_VERSION
from src.render_pipeline.types import RENDER_PIPELINE_VERSION
from src.services.analyze_ocr_recipe import ANALYZE_OCR_RELEASE_LABEL
from src.services.pipeline_recipe_runtime import (
    DEFAULT_RELEASE_LABEL,
    QUALITY_WORKFLOW_VERSION,
)
from src.tts_pipeline.services.director import TTS_DIRECTOR_VERSION
from src.tts_pipeline.services.gemini_whole_video import GEMINI_WHOLE_VIDEO_VERSION
from src.tts_pipeline.services.whole_video_alignment import WHOLE_VIDEO_ALIGNMENT_VERSION
from src.tts_pipeline.types import TTS_PIPELINE_VERSION


FRONTEND_STAGE_RUNTIME_SCHEMA = "frontend_stage_runtime_v1"
FRONTEND_STAGE_RUNTIME_KEY = "frontend_stage_runtime"

DOWNLOAD_STAGE_VERSION = "DOWNLOAD_V2"
TRANSLATION_STAGE_VERSION = "TRANSLATION_V5"


class FrontendCoreRuntimeError(RuntimeError):
    """Raised when a frontend expectation or persisted runtime binding is stale."""


def _job_type_value(job_type: object) -> str:
    return str(job_type.value if hasattr(job_type, "value") else job_type)


def _sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _runtime_specs() -> dict[str, dict[str, Any]]:
    return {
        JobType.DOWNLOAD_VIDEO.value: {
            "stage_version": DOWNLOAD_STAGE_VERSION,
            "recipe_version": DOWNLOAD_POLICY_VERSION,
            "components": {
                "download_quality_policy": DOWNLOAD_POLICY_VERSION,
                "post_download_qa": POST_DOWNLOAD_QA_VERSION,
            },
        },
        JobType.ANALYZE_AUDIO.value: {
            "stage_version": AUDIO_ANALYSIS_VERSION,
            "recipe_version": AUDIO_ANALYSIS_RECIPE_VERSION,
            "components": {
                "analysis_version": AUDIO_ANALYSIS_VERSION,
                "analysis_recipe": AUDIO_ANALYSIS_RECIPE_VERSION,
            },
        },
        JobType.BUILD_TRANSLATION_DRAFT.value: {
            "stage_version": TRANSLATION_STAGE_VERSION,
            "recipe_version": TRANSLATION_V3_RECIPE_VERSION,
            "components": {
                "translation_recipe": TRANSLATION_V3_RECIPE_VERSION,
            },
        },
        JobType.SYNTHESIZE_TTS.value: {
            "stage_version": TTS_PIPELINE_VERSION,
            "recipe_version": TTS_DIRECTOR_VERSION,
            "components": {
                "temporal_pipeline": TTS_PIPELINE_VERSION,
                "director": TTS_DIRECTOR_VERSION,
                "gemini_whole_video": GEMINI_WHOLE_VIDEO_VERSION,
                "whole_video_alignment": WHOLE_VIDEO_ALIGNMENT_VERSION,
            },
        },
        JobType.ANALYZE_OCR.value: {
            "stage_version": ANALYZE_OCR_RELEASE_LABEL,
            "recipe_version": EVENT_SCAN_POLICY_VERSION,
            "components": {
                "analysis_engine": EVENT_SCAN_ENGINE_VERSION,
                "analysis_policy": EVENT_SCAN_POLICY_VERSION,
                "network_calls_allowed": 0,
            },
        },
        JobType.RENDER_PREVIEW.value: {
            "stage_version": QUALITY_WORKFLOW_VERSION,
            "recipe_version": DEFAULT_RELEASE_LABEL,
            "components": {
                "quality_workflow": QUALITY_WORKFLOW_VERSION,
                "pipeline_recipe_release": DEFAULT_RELEASE_LABEL,
                "render_policy": RENDER_POLICY_VERSION,
            },
        },
        JobType.RENDER_FINAL.value: {
            "stage_version": RENDER_PIPELINE_VERSION,
            "recipe_version": DEFAULT_RELEASE_LABEL,
            "components": {
                "render_pipeline": RENDER_PIPELINE_VERSION,
                "quality_workflow": QUALITY_WORKFLOW_VERSION,
                "pipeline_recipe_release": DEFAULT_RELEASE_LABEL,
                "render_policy": RENDER_POLICY_VERSION,
            },
        },
    }


def frontend_stage_runtime(job_type: object) -> dict[str, Any] | None:
    """Return the exact installed contract for one frontend core stage."""

    job_type_value = _job_type_value(job_type)
    spec = _runtime_specs().get(job_type_value)
    if spec is None:
        return None
    contract: dict[str, Any] = {
        "schema_version": FRONTEND_STAGE_RUNTIME_SCHEMA,
        "job_type": job_type_value,
        **spec,
    }
    contract["runtime_sha256"] = _sha256_json(contract)
    return contract


def frontend_stage_versions() -> dict[str, str]:
    """Compact browser handshake for the seven core frontend actions."""

    return {
        job_type: str(spec["stage_version"])
        for job_type, spec in _runtime_specs().items()
    }


def assert_expected_stage_version(job_type: object, expected: str | None) -> str:
    contract = frontend_stage_runtime(job_type)
    if contract is None:
        raise FrontendCoreRuntimeError(
            f"{_job_type_value(job_type)} is not a frontend core stage"
        )
    installed = str(contract["stage_version"])
    normalized = str(expected or "").strip()
    if normalized and normalized != installed:
        raise FrontendCoreRuntimeError(
            f"Frontend expects {_job_type_value(job_type)} {normalized}, "
            f"but the API has {installed}. Refresh/rebuild the frontend before retrying."
        )
    return installed


def assert_expected_stage_versions(expected: Mapping[str, Any] | None) -> None:
    if not expected:
        return
    for job_type, version in expected.items():
        assert_expected_stage_version(job_type, str(version or ""))


def bind_job_to_frontend_runtime(job: Any) -> dict[str, Any] | None:
    """Stamp a newly-created core job before its first persistence boundary."""

    contract = frontend_stage_runtime(getattr(job, "job_type", ""))
    if contract is None:
        return None
    payload = dict(getattr(job, "payload_json", None) or {})
    expected = payload.get("expected_stage_version")
    assert_expected_stage_version(getattr(job, "job_type", ""), expected)
    context = dict(getattr(job, "context_json", None) or {})
    metadata = dict(getattr(job, "metadata_json", None) or {})
    payload[FRONTEND_STAGE_RUNTIME_KEY] = dict(contract)
    context[FRONTEND_STAGE_RUNTIME_KEY] = dict(contract)
    metadata[FRONTEND_STAGE_RUNTIME_KEY] = dict(contract)
    metadata["runtime_version"] = contract["stage_version"]
    job.payload_json = payload
    job.context_json = context
    job.metadata_json = metadata
    return contract


def assert_job_frontend_runtime(job: Any) -> dict[str, Any] | None:
    """Fail closed if a persisted job would run a different installed recipe."""

    installed = frontend_stage_runtime(getattr(job, "job_type", ""))
    if installed is None:
        return None
    payload = dict(getattr(job, "payload_json", None) or {})
    context = dict(getattr(job, "context_json", None) or {})
    bound = payload.get(FRONTEND_STAGE_RUNTIME_KEY) or context.get(
        FRONTEND_STAGE_RUNTIME_KEY
    )
    if not isinstance(bound, dict) or not bound:
        raise FrontendCoreRuntimeError(
            f"{installed['job_type']} job has no frontend runtime binding"
        )
    if bound != installed:
        raise FrontendCoreRuntimeError(
            f"{installed['job_type']} job is bound to a stale runtime; "
            f"expected {installed['stage_version']} ({installed['runtime_sha256'][:12]})."
        )
    return installed


def ensure_job_frontend_runtime(job: Any) -> dict[str, Any] | None:
    """Bind legacy unversioned queued jobs once; never upgrade a stale binding."""

    installed = frontend_stage_runtime(getattr(job, "job_type", ""))
    if installed is None:
        return None
    payload = dict(getattr(job, "payload_json", None) or {})
    context = dict(getattr(job, "context_json", None) or {})
    if not payload.get(FRONTEND_STAGE_RUNTIME_KEY) and not context.get(
        FRONTEND_STAGE_RUNTIME_KEY
    ):
        step_statuses = {
            _job_type_value(getattr(step, "status", "")).upper()
            for step in list(getattr(job, "steps", None) or [])
        }
        if step_statuses.intersection(
            {"RUNNING", "COMPLETED", "SKIPPED", "WAITING_FOR_INPUT"}
        ):
            raise FrontendCoreRuntimeError(
                f"{installed['job_type']} legacy job already started without a runtime "
                "binding; restart it as a new frontend command."
            )
        return bind_job_to_frontend_runtime(job)
    return assert_job_frontend_runtime(job)
