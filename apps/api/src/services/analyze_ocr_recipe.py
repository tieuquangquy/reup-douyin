"""Immutable runtime authority for the official local Analyze OCR recipe."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.settings import get_settings
from src.media_pipeline.frame_sampling.event_candidate_scheduler import (
    EVENT_SCAN_ENGINE_VERSION,
    EVENT_SCAN_POLICY_VERSION,
)


ANALYZE_OCR_RECIPE_SCHEMA = "analyze_ocr_recipe_lock_v1"
ANALYZE_OCR_RECIPE_STATUS = "LOCKED_AS_OFFICIAL_DEFAULT"
ANALYZE_OCR_RELEASE_LABEL = "OCR-V34"
ANALYZE_OCR_RECIPE_REF_KEY = "analyze_ocr_recipe_lock"


class AnalyzeOcrRecipeError(RuntimeError):
    """Raised when the official Analyze OCR authority is missing or stale."""


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def current_recipe_path() -> Path:
    configured = str(
        getattr(get_settings(), "analyze_ocr_recipe_lock_path", "") or ""
    ).strip()
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else (Path.cwd() / path).resolve()
    return (
        repository_root()
        / "docs"
        / "pipeline-recipes"
        / "analyze_ocr_recipe_current.json"
    )


@dataclass(frozen=True)
class AnalyzeOcrRecipeAuthority:
    source_path: Path
    release_label: str
    recipe_sha256: str
    file_sha256: str
    analysis_engine: str
    analysis_policy_version: str

    def reference(self) -> dict[str, str]:
        return {
            "schema_version": "analyze_ocr_recipe_lock_ref_v1",
            "artifact_name": self.source_path.name,
            "release_label": self.release_label,
            "recipe_sha256": self.recipe_sha256,
            "file_sha256": self.file_sha256,
            "status": ANALYZE_OCR_RECIPE_STATUS,
        }


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalyzeOcrRecipeError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise AnalyzeOcrRecipeError("Analyze OCR recipe must contain an object")
    claimed = str(payload.get("recipe_sha256") or "").lower()
    unsigned = dict(payload)
    unsigned.pop("recipe_sha256", None)
    if len(claimed) != 64 or _sha256_json(unsigned) != claimed:
        raise AnalyzeOcrRecipeError("Analyze OCR recipe self-hash is invalid")
    if payload.get("schema_version") != ANALYZE_OCR_RECIPE_SCHEMA:
        raise AnalyzeOcrRecipeError("Analyze OCR recipe schema is unsupported")
    if payload.get("status") != ANALYZE_OCR_RECIPE_STATUS:
        raise AnalyzeOcrRecipeError("Analyze OCR recipe is not the official default")
    if payload.get("release_label") != ANALYZE_OCR_RELEASE_LABEL:
        raise AnalyzeOcrRecipeError("Analyze OCR recipe release is not current")
    claims = dict(payload.get("claims") or {})
    if claims.get("official_frontend_default") is not True:
        raise AnalyzeOcrRecipeError("Analyze OCR recipe is not enabled for frontend use")
    if claims.get("network_calls_allowed") != 0:
        raise AnalyzeOcrRecipeError("Analyze OCR recipe must remain local-only")
    return payload


def _authority(path: Path, payload: dict[str, Any]) -> AnalyzeOcrRecipeAuthority:
    phase1 = dict(payload.get("phase1") or {})
    engine = str(phase1.get("analysis_engine") or "")
    policy = str(phase1.get("analysis_policy_version") or "")
    if engine != EVENT_SCAN_ENGINE_VERSION or policy != EVENT_SCAN_POLICY_VERSION:
        raise AnalyzeOcrRecipeError(
            "Analyze OCR recipe does not match the installed local engine policy"
        )
    phase2 = dict(payload.get("phase2") or {})
    if phase2.get("provider") != "local" or phase2.get("network_calls_allowed") != 0:
        raise AnalyzeOcrRecipeError("Analyze OCR Phase 2 must remain local-only")
    return AnalyzeOcrRecipeAuthority(
        source_path=path.resolve(),
        release_label=str(payload["release_label"]),
        recipe_sha256=str(payload["recipe_sha256"]),
        file_sha256=_sha256_file(path),
        analysis_engine=engine,
        analysis_policy_version=policy,
    )


def load_current_analyze_ocr_recipe() -> AnalyzeOcrRecipeAuthority:
    current = current_recipe_path()
    payload = _load_payload(current)
    versioned = current.with_name(
        f"analyze_ocr_recipe_{payload['recipe_sha256']}.json"
    )
    versioned_payload = _load_payload(versioned)
    if _sha256_file(current) != _sha256_file(versioned):
        raise AnalyzeOcrRecipeError(
            "Analyze OCR current pointer and immutable artifact do not match"
        )
    if versioned_payload["recipe_sha256"] != payload["recipe_sha256"]:
        raise AnalyzeOcrRecipeError("Analyze OCR immutable recipe identity changed")
    return _authority(versioned, versioned_payload)


def load_bound_analyze_ocr_recipe(
    reference: dict[str, Any],
) -> AnalyzeOcrRecipeAuthority:
    artifact_name = str(reference.get("artifact_name") or "")
    if not artifact_name or Path(artifact_name).name != artifact_name:
        raise AnalyzeOcrRecipeError("Analyze OCR recipe artifact name is invalid")
    path = current_recipe_path().parent / artifact_name
    payload = _load_payload(path)
    authority = _authority(path, payload)
    if (
        str(reference.get("release_label") or "") != authority.release_label
        or str(reference.get("recipe_sha256") or "").lower()
        != authority.recipe_sha256
        or str(reference.get("file_sha256") or "").lower() != authority.file_sha256
    ):
        raise AnalyzeOcrRecipeError("Bound Analyze OCR recipe hash is stale")
    return authority


def bind_job_to_official_analyze_ocr_recipe(job: Any) -> dict[str, str] | None:
    job_type_raw = getattr(job, "job_type", "")
    job_type = job_type_raw.value if hasattr(job_type_raw, "value") else str(job_type_raw)
    if job_type != "ANALYZE_OCR":
        return None
    authority = load_current_analyze_ocr_recipe()
    reference = authority.reference()
    payload = dict(getattr(job, "payload_json", None) or {})
    context = dict(getattr(job, "context_json", None) or {})
    payload[ANALYZE_OCR_RECIPE_REF_KEY] = reference
    context[ANALYZE_OCR_RECIPE_REF_KEY] = reference
    job.payload_json = payload
    job.context_json = context
    return reference


def assert_job_analyze_ocr_recipe(job: Any) -> None:
    job_type_raw = getattr(job, "job_type", "")
    job_type = job_type_raw.value if hasattr(job_type_raw, "value") else str(job_type_raw)
    if job_type != "ANALYZE_OCR":
        return
    payload = dict(getattr(job, "payload_json", None) or {})
    context = dict(getattr(job, "context_json", None) or {})
    reference = payload.get(ANALYZE_OCR_RECIPE_REF_KEY) or context.get(
        ANALYZE_OCR_RECIPE_REF_KEY
    )
    if not isinstance(reference, dict) or not reference:
        raise AnalyzeOcrRecipeError("Analyze OCR job has no official recipe binding")
    authority = load_bound_analyze_ocr_recipe(reference)
    if str(payload.get("analysis_engine") or "") != authority.analysis_engine:
        raise AnalyzeOcrRecipeError(
            "Analyze OCR job engine does not match its official recipe"
        )
    if payload.get("use_master_phase1") is not True:
        raise AnalyzeOcrRecipeError("Analyze OCR official recipe requires Master Phase 1")
