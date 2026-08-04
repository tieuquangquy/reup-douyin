"""Build a non-locking recipe candidate from current runtime and regression evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.media_pipeline.video_renderer.adaptive_output_qa import (
    RESIDUAL_CJK_POLICY_VERSION,
)
from src.media_pipeline.video_renderer.adaptive_typography import (
    DENSE_GROUP_LAYOUT_POLICY_VERSION,
)
from src.media_pipeline.video_renderer.render_policy import (
    RENDER_POLICY_VERSION,
    SEMANTIC_RENDER_DEDUP_POLICY_VERSION,
)
from src.media_pipeline.video_renderer.source_text_provenance import (
    SOURCE_INTRINSIC_REGION_POLICY_VERSION,
)
from src.services.pipeline_tts_provenance import (
    PipelineTtsProvenanceError,
    verify_e2e_tts_provenance,
)


class PipelineRecipeCandidateError(RuntimeError):
    pass


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_verified(path: Path, hash_field: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineRecipeCandidateError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise PipelineRecipeCandidateError(f"{path.name} must contain an object")
    unsigned = dict(payload)
    claimed = str(unsigned.pop(hash_field, "") or "")
    if len(claimed) != 64 or _sha256_json(unsigned) != claimed:
        raise PipelineRecipeCandidateError(f"{path.name} self-hash is invalid")
    return payload


def _ref(workspace: Path, path: Path, payload: dict[str, Any], field: str) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_relative_to(workspace):
        raise PipelineRecipeCandidateError(f"{path.name} is outside the workspace")
    return {
        "path": resolved.relative_to(workspace).as_posix(),
        "file_sha256": _sha256_file(resolved),
        field: payload[field],
    }


def _immutable_base_recipe_path(
    base_path: Path, base: dict[str, Any]
) -> Path:
    if base_path.name != "pipeline_recipe_current.json":
        return base_path
    recipe_sha256 = str(base.get("recipe_sha256") or "")
    versioned = base_path.with_name(f"pipeline_recipe_{recipe_sha256}.json")
    if not versioned.is_file() or _sha256_file(versioned) != _sha256_file(base_path):
        raise PipelineRecipeCandidateError(
            "Current recipe does not have a matching immutable versioned artifact"
        )
    return versioned


def build_pipeline_recipe_candidate(
    *,
    workspace_root: str | Path,
    base_recipe_path: str | Path,
    report_path: str | Path,
    fixture_path: str | Path,
    fixture_report_path: str | Path,
    output_path: str | Path,
    release_label: str = "V24.1",
    e2e_report_path: str | Path | None = None,
) -> dict[str, Any]:
    workspace = Path(workspace_root).resolve()
    base_path = Path(base_recipe_path).resolve()
    batch_path = Path(report_path).resolve()
    fixture_file = Path(fixture_path).resolve()
    fixture_report_file = Path(fixture_report_path).resolve()
    target = Path(output_path).resolve()

    base = _load_verified(base_path, "recipe_sha256")
    base_evidence_path = _immutable_base_recipe_path(base_path, base)
    report = _load_verified(batch_path, "report_sha256")
    fixture = _load_verified(fixture_file, "fixture_sha256")
    fixture_report = _load_verified(fixture_report_file, "report_sha256")
    e2e_path = Path(e2e_report_path).resolve() if e2e_report_path else None
    e2e = _load_verified(e2e_path, "report_sha256") if e2e_path else None

    case_count = int(report.get("case_count") or 0)
    no_text_approved_count = int(
        report.get("no_text_approved_case_count")
        or report.get("no_text_approved_count")
        or 0
    )
    phase2_execution_count = int(report.get("phase2_execution_pass_count") or 0)
    phase2_coverage_complete = (
        phase2_execution_count == case_count
        or phase2_execution_count + no_text_approved_count == case_count
    )
    automated_batch_pass = (
        str(report.get("status") or "") == "PASS_TO_OPERATOR_GATES"
        and int(report.get("phase1_execution_pass_count") or 0) == case_count
        and int(report.get("phase1_accepted_count") or 0) == case_count
        and phase2_coverage_complete
        and int(report.get("operator_review_object_count") or 0) == 0
        and int(report.get("open_incident_count") or 0) == 0
    )
    fixture_pass = (
        str(fixture_report.get("status") or "") == "PASS"
        and int(fixture_report.get("case_count") or 0) > 0
        and int(fixture_report.get("passed_count") or 0)
        == int(fixture_report.get("case_count") or 0)
        and int(fixture_report.get("failed_count") or 0) == 0
        and str(dict(fixture_report.get("fixture_ref") or {}).get("fixture_sha256") or "")
        == str(fixture.get("fixture_sha256") or "")
    )
    if not automated_batch_pass or not fixture_pass:
        raise PipelineRecipeCandidateError(
            "Candidate requires a clean automated batch and passing final fixture"
        )
    if e2e is not None and str(e2e.get("status") or "") != "PASS_CONTROLLED_E2E":
        raise PipelineRecipeCandidateError("Provided E2E report is not passing")
    runtime_tts: dict[str, Any] | None = None
    if e2e is not None and e2e_path is not None:
        try:
            runtime_tts = verify_e2e_tts_provenance(
                e2e_report=e2e,
                e2e_report_path=e2e_path,
                workspace_root=workspace,
            )
        except PipelineTtsProvenanceError as exc:
            raise PipelineRecipeCandidateError(
                f"E2E TTS runtime provenance is invalid: {exc}"
            ) from exc

    pending_rights = sum(
        str(dict(row).get("status") or "")
        == "WAITING_SOURCE_RIGHTS_AND_MUSIC_REVIEW"
        for row in list(report.get("cases") or [])
        if isinstance(row, dict)
    )
    render = dict(base.get("render") or {})
    render.update(
        {
            "role_policy_version": RENDER_POLICY_VERSION,
            "background_mix_gain": 1.0,
            "layout_policies": {
                "dense_group": DENSE_GROUP_LAYOUT_POLICY_VERSION,
                "semantic_dedup": SEMANTIC_RENDER_DEDUP_POLICY_VERSION,
            },
            "source_text_provenance": {
                "moving_object_region": SOURCE_INTRINSIC_REGION_POLICY_VERSION,
                "operator_approval_required": True,
                "source_pixels_preserved": True,
            },
        }
    )
    residual = dict(render.get("residual_cjk_policy") or {})
    residual["policy_version"] = RESIDUAL_CJK_POLICY_VERSION
    render["residual_cjk_policy"] = residual

    blockers: list[str] = []
    if pending_rights:
        blockers.append("PENDING_SOURCE_RIGHTS_AND_MUSIC_REVIEW")
    if e2e is None:
        blockers.append("E2E_REPORT_NOT_AVAILABLE")
    elif not bool(dict(e2e.get("claims") or {}).get("full_batch_end_to_end_pass")):
        blockers.append("FULL_BATCH_END_TO_END_NOT_COMPLETE")
    if runtime_tts is None:
        blockers.append("TTS_RUNTIME_PROVENANCE_NOT_VERIFIED")
    limitations = (
        ["DECLARED_CORPUS_COVERAGE_GAPS"] if report.get("corpus_gaps") else []
    )
    recipe_lock_recommended = not blockers

    candidate: dict[str, Any] = {
        "schema_version": "pipeline_recipe_candidate_v1",
        "status": "VALIDATED_CANDIDATE_WITH_GAPS",
        "candidate_at": datetime.now(timezone.utc).isoformat(),
        "release_label": release_label,
        "base_recipe": _ref(
            workspace, base_evidence_path, base, "recipe_sha256"
        ),
        "phase1": dict(base.get("phase1") or {}),
        "phase2": dict(base.get("phase2") or {}),
        "phase3": dict(base.get("phase3") or {}),
        "tts": {
            **dict(base.get("tts") or {}),
            **(runtime_tts or {}),
            "authority": (
                "e2e_render_prep_manifests_v1"
                if runtime_tts is not None
                else "unverified_recipe_intent"
            ),
        },
        "render": render,
        "audio_authority": dict(base.get("audio_authority") or {}),
        "operator_gates": list(base.get("operator_gates") or []),
        "execution": dict(base.get("execution") or {}),
        "evidence": {
            "batch_report": _ref(workspace, batch_path, report, "report_sha256"),
            "final_fixture": _ref(workspace, fixture_file, fixture, "fixture_sha256"),
            "final_fixture_report": {
                **_ref(
                    workspace,
                    fixture_report_file,
                    fixture_report,
                    "report_sha256",
                ),
                "case_count": int(fixture_report.get("case_count") or 0),
                "passed_count": int(fixture_report.get("passed_count") or 0),
            },
            "e2e_report": (
                {
                    **_ref(workspace, e2e_path, e2e, "report_sha256"),
                    "case_count": int(e2e.get("case_count") or 0),
                    "passed_count": int(e2e.get("passed_count") or 0),
                    "excluded_case_count": int(e2e.get("excluded_case_count") or 0),
                }
                if e2e is not None and e2e_path is not None
                else None
            ),
            "tts_provenance": dict(e2e.get("tts_provenance") or {}) if e2e else None,
            "corpus_gaps": report.get("corpus_gaps"),
        },
        "claims": {
            "universal_video_support": False,
            "automated_batch_execution_pass": True,
            "final_fixture_pass": True,
            "included_cases_end_to_end_pass": bool(e2e)
            and bool(dict(e2e.get("claims") or {}).get("included_cases_end_to_end_pass")),
            "full_batch_end_to_end_pass": bool(e2e)
            and bool(dict(e2e.get("claims") or {}).get("full_batch_end_to_end_pass")),
            "candidate_case_count": case_count,
            "final_fixture_case_count": int(fixture_report.get("case_count") or 0),
            "pending_rights_review_count": pending_rights,
            "recipe_lock_recommended": recipe_lock_recommended,
        },
        "blockers": blockers,
        "limitations": limitations,
    }
    candidate["candidate_sha256"] = _sha256_json(candidate)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(target)
    return candidate
