"""Runtime binding for the immutable controlled-pilot recipe.

The regression/lock scripts prove a recipe outside the request path.  This module
is the small runtime boundary that lets a Reup Queue item carry that same proof
through every durable stage without making the worker depend on the current pointer
remaining unchanged during a long run.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.core.settings import get_settings
from src.services.adaptive_final_db_handoff import (
    AdaptiveFinalDbHandoffError,
    LockedRecipeAuthority,
    load_locked_recipe_authority,
)

logger = logging.getLogger(__name__)

DEFAULT_RELEASE_LABEL = "V24.1"
RECIPE_LOCK_REF_KEY = "pipeline_recipe_lock"
RECIPE_LOCK_PATH_ENV = "PIPELINE_RECIPE_LOCK_PATH"
QUALITY_WORKFLOW_VERSION = "QUALITY_LOCALIZATION_V24_1"
_QUALITY_JOB_TYPES = frozenset({"ANALYZE_OCR", "RENDER_PREVIEW", "RENDER_FINAL"})


class RuntimeRecipeError(RuntimeError):
    """Raised when a queue item cannot be safely bound to the locked recipe."""


def repository_root() -> Path:
    # apps/api/src/services/pipeline_recipe_runtime.py -> repository root
    return Path(__file__).resolve().parents[4]


def current_recipe_path() -> Path:
    configured = str(getattr(get_settings(), "pipeline_recipe_lock_path", "") or "").strip()
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else (Path.cwd() / path).resolve()
    return repository_root() / "docs" / "pipeline-recipes" / "pipeline_recipe_current.json"


def versioned_recipe_path(reference: dict[str, Any]) -> Path:
    artifact_name = str(reference.get("artifact_name") or "").strip()
    if not artifact_name or Path(artifact_name).name != artifact_name:
        raise RuntimeRecipeError("Pipeline recipe artifact name is invalid")
    candidates = (
        current_recipe_path().parent / artifact_name,
        repository_root() / "docs" / "pipeline-recipes" / artifact_name,
    )
    for path in candidates:
        if path.is_file():
            return path.resolve()
    raise RuntimeRecipeError("The bound pipeline recipe artifact is missing")


def load_current_recipe_authority(*, release_label: str = DEFAULT_RELEASE_LABEL) -> LockedRecipeAuthority:
    path = current_recipe_path()
    try:
        current = load_locked_recipe_authority(path, expected_release_label=release_label)
        # Never persist the mutable current-pointer name. Resolve and verify the
        # content-addressed sibling now so a run survives a later recipe promotion.
        versioned = path.parent / f"pipeline_recipe_{current.recipe_sha256}.json"
        locked = load_locked_recipe_authority(
            versioned,
            expected_release_label=release_label,
        )
        if (
            locked.recipe_sha256 != current.recipe_sha256
            or locked.file_sha256 != current.file_sha256
        ):
            raise RuntimeRecipeError(
                "Current pipeline recipe and its versioned artifact do not match"
            )
        return locked
    except (AdaptiveFinalDbHandoffError, OSError, ValueError) as exc:
        raise RuntimeRecipeError(f"Current pipeline recipe is not runnable: {exc}") from exc


def load_bound_recipe_authority(reference: dict[str, Any]) -> LockedRecipeAuthority:
    """Verify the content-addressed recipe already selected by an item."""

    path = versioned_recipe_path(reference)
    try:
        authority = load_locked_recipe_authority(
            path,
            expected_release_label=str(reference.get("release_label") or DEFAULT_RELEASE_LABEL),
        )
    except (AdaptiveFinalDbHandoffError, OSError, ValueError) as exc:
        raise RuntimeRecipeError(f"Bound pipeline recipe is no longer valid: {exc}") from exc
    expected_sha = str(reference.get("recipe_sha256") or "").lower()
    expected_file_sha = str(reference.get("file_sha256") or "").lower()
    if expected_sha != authority.recipe_sha256 or expected_file_sha != authority.file_sha256:
        raise RuntimeRecipeError("Bound pipeline recipe hash does not match its artifact")
    return authority


def bind_item_to_current_recipe(item: Any, *, release_label: str = DEFAULT_RELEASE_LABEL) -> dict[str, Any]:
    """Bind an auto queue item once; subsequent retries must reuse this identity."""

    from src.services.reup_pipeline_meta import meta_dict, set_pipeline_meta

    existing = meta_dict(item).get(RECIPE_LOCK_REF_KEY)
    if isinstance(existing, dict) and existing:
        load_bound_recipe_authority(existing)
        return dict(existing)
    authority = load_current_recipe_authority(release_label=release_label)
    reference = authority.reference()
    set_pipeline_meta(item, extra={RECIPE_LOCK_REF_KEY: reference})
    logger.info(
        "reup_pipeline_recipe_bound",
        extra={
            "reup_queue_item_id": str(getattr(item, "id", "")),
            "release_label": authority.release_label,
            "recipe_sha256": authority.recipe_sha256,
        },
    )
    return reference


def ensure_item_recipe_binding(item: Any) -> dict[str, Any]:
    """Validate an item's immutable recipe reference, binding legacy auto items once."""

    from src.services.reup_pipeline_meta import meta_dict

    reference = meta_dict(item).get(RECIPE_LOCK_REF_KEY)
    if isinstance(reference, dict) and reference:
        load_bound_recipe_authority(reference)
        return dict(reference)
    return bind_item_to_current_recipe(item)


def bind_job_to_item_recipe(job: Any, item: Any) -> dict[str, Any]:
    """Copy the same recipe reference into each durable stage job."""

    reference = ensure_item_recipe_binding(item)
    context = dict(getattr(job, "context_json", None) or {})
    context[RECIPE_LOCK_REF_KEY] = reference
    job.context_json = context
    payload = dict(getattr(job, "payload_json", None) or {})
    payload[RECIPE_LOCK_REF_KEY] = reference
    job.payload_json = payload
    from src.services.analyze_ocr_recipe import (
        bind_job_to_official_analyze_ocr_recipe,
    )

    bind_job_to_official_analyze_ocr_recipe(job)
    assert_job_recipe_workflow_contract(job)
    return reference


def bind_job_to_recipe_reference(job: Any, reference: dict[str, Any]) -> dict[str, Any]:
    """Bind a later manual checkpoint job to the immutable recipe selected by OCR."""

    load_bound_recipe_authority(reference)
    context = dict(getattr(job, "context_json", None) or {})
    context[RECIPE_LOCK_REF_KEY] = dict(reference)
    job.context_json = context
    payload = dict(getattr(job, "payload_json", None) or {})
    payload[RECIPE_LOCK_REF_KEY] = dict(reference)
    job.payload_json = payload
    assert_job_recipe_workflow_contract(job)
    return dict(reference)


def assert_job_recipe_workflow_contract(job: Any) -> None:
    """Fail closed when a V24.1 quality job would execute a legacy implementation."""

    payload = dict(getattr(job, "payload_json", None) or {})
    context = dict(getattr(job, "context_json", None) or {})
    reference = payload.get(RECIPE_LOCK_REF_KEY) or context.get(RECIPE_LOCK_REF_KEY)
    if not isinstance(reference, dict) or not reference:
        return
    load_bound_recipe_authority(reference)
    release = str(reference.get("release_label") or "")
    job_type_raw = getattr(job, "job_type", "")
    job_type = job_type_raw.value if hasattr(job_type_raw, "value") else str(job_type_raw)
    if job_type == "ANALYZE_OCR":
        from src.services.analyze_ocr_recipe import (
            AnalyzeOcrRecipeError,
            assert_job_analyze_ocr_recipe,
        )

        try:
            assert_job_analyze_ocr_recipe(job)
        except AnalyzeOcrRecipeError as exc:
            raise RuntimeRecipeError(f"Official Analyze OCR recipe rejected job: {exc}") from exc
    if release == DEFAULT_RELEASE_LABEL and job_type in _QUALITY_JOB_TYPES:
        workflow = str(payload.get("workflow_version") or "")
        if workflow != QUALITY_WORKFLOW_VERSION:
            raise RuntimeRecipeError(
                f"{release} {job_type} requires workflow_version={QUALITY_WORKFLOW_VERSION}; "
                f"received {workflow or 'missing'}"
            )


def bind_job_to_current_recipe(
    job: Any, *, release_label: str = DEFAULT_RELEASE_LABEL
) -> dict[str, Any]:
    """Bind a frontend-created durable job when no queue item owns it."""

    authority = load_current_recipe_authority(release_label=release_label)
    reference = authority.reference()
    context = dict(getattr(job, "context_json", None) or {})
    context[RECIPE_LOCK_REF_KEY] = reference
    job.context_json = context
    payload = dict(getattr(job, "payload_json", None) or {})
    payload[RECIPE_LOCK_REF_KEY] = reference
    job.payload_json = payload
    from src.services.analyze_ocr_recipe import (
        bind_job_to_official_analyze_ocr_recipe,
    )

    bind_job_to_official_analyze_ocr_recipe(job)
    return reference
