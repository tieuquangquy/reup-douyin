"""Resumable local batch regression across the operator-gated Phase 1-5 flow."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.score_phase1_pass import score_phase1_out
from src.media_pipeline.frame_sampling.phase1_no_text_contract import (
    Phase1NoTextContractError,
    evaluate_no_text_operator_gate,
)
from src.media_pipeline.frame_sampling.phase1_geometry_review import (
    Phase1GeometryReviewError,
    evaluate_phase1_geometry_operator_gate_safe,
)
from src.services.residual_remediation_authority import (
    ResidualRemediationAuthorityError,
    resolve_active_residual_remediation,
)


class PipelineBatchRegressionError(RuntimeError):
    pass


REGRESSION_SCOPE_FULL_E2E = "FULL_E2E"
REGRESSION_SCOPE_VISUAL_LOCALIZATION_ONLY = "VISUAL_LOCALIZATION_ONLY"
ALLOWED_REGRESSION_SCOPES = {
    REGRESSION_SCOPE_FULL_E2E,
    REGRESSION_SCOPE_VISUAL_LOCALIZATION_ONLY,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineBatchRegressionError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise PipelineBatchRegressionError(f"{path.name} must contain an object")
    return payload


def _parse_authority_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _refs_match_current_file(
    root: Path,
    review_ref: dict[str, Any],
    approval_ref: dict[str, Any],
) -> bool:
    path = str(review_ref.get("path") or "")
    sha256 = str(review_ref.get("sha256") or "").lower()
    if (
        not path
        or len(sha256) != 64
        or path != str(approval_ref.get("path") or "")
        or sha256 != str(approval_ref.get("sha256") or "").lower()
    ):
        return False
    resolved = (root / path).resolve()
    return (
        resolved.is_relative_to(root)
        and resolved.is_file()
        and _sha256_file(resolved) == sha256
    )


def _residual_remediation_is_materialized(
    root: Path,
    phase2_meta: dict[str, Any],
    remediation_path: Path,
) -> bool:
    """Return true only when current Phase 2 authority consumed remediation."""

    ref = dict(phase2_meta.get("residual_remediation_ref") or {})
    return (
        remediation_path.is_file()
        and str(ref.get("path") or "")
        == remediation_path.resolve().relative_to(root.resolve()).as_posix()
        and str(ref.get("sha256") or "").lower()
        == _sha256_file(remediation_path)
    )


def _pending_mix_is_covered_by_downstream_authority(
    root: Path,
    mix_review: dict[str, Any],
) -> bool:
    """Accept a legacy pending mix only when later immutable authority proves it.

    Older controlled pilots wrote ``phase4_audio_approval.json`` after the mix
    review but did not materialize a separate background-mix approval.  Do not
    regress those completed cases to an operator gate when the exact inputs,
    recipe, final render, QA, and final approval still match current files.
    """

    required = {
        "audio": root / "phase4_audio_approval.json",
        "render_meta": root / "phase4_adaptive_render_meta.json",
        "final_approval": root / "phase5_final_approval.json",
    }
    if any(not path.is_file() for path in required.values()):
        return False
    try:
        audio = _load_object(required["audio"])
        render_meta = _load_object(required["render_meta"])
        final_approval = _load_object(required["final_approval"])
    except PipelineBatchRegressionError:
        return False
    if (
        str(audio.get("status") or "") != "AUDIO_APPROVED"
        or str(render_meta.get("status") or "") != "FINAL_RENDERED"
        or str(render_meta.get("output_qa_status") or "") != "PASS"
        or str(final_approval.get("status") or "") != "FINAL_APPROVED"
    ):
        return False
    review_created = _parse_authority_time(mix_review.get("created_at"))
    audio_approved = _parse_authority_time(audio.get("approved_at"))
    final_approved = _parse_authority_time(final_approval.get("approved_at"))
    if (
        review_created is None
        or audio_approved is None
        or final_approved is None
        or audio_approved < review_created
        or final_approved < audio_approved
    ):
        return False
    for role in ("narration", "background"):
        if not _refs_match_current_file(
            root,
            dict(mix_review.get(f"{role}_ref") or {}),
            dict(audio.get(f"{role}_ref") or {}),
        ):
            return False
    preview_ref = dict(mix_review.get("mix_preview_ref") or {})
    preview_path = (root / str(preview_ref.get("path") or "")).resolve()
    if (
        not preview_path.is_relative_to(root)
        or not preview_path.is_file()
        or _sha256_file(preview_path)
        != str(preview_ref.get("sha256") or "").lower()
    ):
        return False
    recipe = dict(mix_review.get("mix_recipe") or {})
    rendered_mix = dict(render_meta.get("audio_mix") or {})
    try:
        gain_matches = abs(
            float(rendered_mix.get("background_gain"))
            - float(recipe.get("background_gain"))
        ) <= 1e-9
    except (TypeError, ValueError):
        return False
    if not bool(rendered_mix.get("background_present")) or not gain_matches:
        return False
    final_refs = dict(final_approval.get("refs") or {})
    render_artifacts = dict(render_meta.get("artifacts") or {})
    final_video_ref = dict(final_refs.get("final_video") or {})
    final_video_path = (
        root / str(render_artifacts.get("video") or final_video_ref.get("path") or "")
    ).resolve()
    if (
        not final_video_path.is_relative_to(root)
        or not final_video_path.is_file()
        or str(final_video_ref.get("path") or "")
        != final_video_path.relative_to(root).as_posix()
        or str(final_video_ref.get("sha256") or "").lower()
        != str(render_meta.get("output_video_sha256") or "").lower()
        or _sha256_file(final_video_path)
        != str(render_meta.get("output_video_sha256") or "").lower()
    ):
        return False
    for role, current_path in (
        ("audio_approval", required["audio"]),
        ("render_meta", required["render_meta"]),
    ):
        ref = dict(final_refs.get(role) or {})
        if (
            str(ref.get("path") or "") != current_path.name
            or str(ref.get("sha256") or "").lower()
            != _sha256_file(current_path)
        ):
            return False
    output_qa_ref = dict(final_refs.get("output_qa") or {})
    output_qa_path = (root / str(output_qa_ref.get("path") or "")).resolve()
    return (
        output_qa_path.is_relative_to(root)
        and output_qa_path.is_file()
        and _sha256_file(output_qa_path)
        == str(output_qa_ref.get("sha256") or "").lower()
    )


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _scope_overrides_from_manifest(
    run: Path,
    state: dict[str, Any],
) -> dict[str, str]:
    path = run / "regression_scope_manifest.json"
    if not path.is_file():
        return {}
    manifest = _load_object(path)
    claimed = str(manifest.get("scope_manifest_sha256") or "")
    unsigned = dict(manifest)
    unsigned.pop("scope_manifest_sha256", None)
    if len(claimed) != 64 or _sha256_json(unsigned) != claimed:
        raise PipelineBatchRegressionError("Regression scope manifest hash mismatch")
    if str(manifest.get("status") or "") != "ACTIVE":
        raise PipelineBatchRegressionError("Regression scope manifest is not active")
    expected_corpus_sha = str(
        dict(state.get("corpus_ref") or {}).get("corpus_sha256") or ""
    )
    if (
        len(expected_corpus_sha) != 64
        or str(manifest.get("corpus_sha256") or "") != expected_corpus_sha
    ):
        raise PipelineBatchRegressionError(
            "Regression scope manifest targets another corpus"
        )
    raw_scopes = manifest.get("scopes") or {}
    if not isinstance(raw_scopes, dict) or not raw_scopes:
        raise PipelineBatchRegressionError("Regression scope manifest is empty")
    overrides = {
        str(case_id): str(scope)
        for case_id, scope in raw_scopes.items()
        if str(case_id)
    }
    if len(overrides) != len(raw_scopes) or any(
        scope not in ALLOWED_REGRESSION_SCOPES for scope in overrides.values()
    ):
        raise PipelineBatchRegressionError(
            "Regression scope manifest contains an invalid scope"
        )
    state_case_ids = {
        str(row.get("case_id") or "")
        for row in list(state.get("cases") or [])
        if isinstance(row, dict)
    }
    if not set(overrides).issubset(state_case_ids):
        raise PipelineBatchRegressionError(
            "Regression scope manifest contains an unknown case"
        )
    return overrides


def evaluate_operator_gate(
    root_dir: str | Path,
    *,
    regression_scope: str = REGRESSION_SCOPE_FULL_E2E,
) -> dict[str, Any]:
    root = Path(root_dir)
    scope = str(regression_scope or REGRESSION_SCOPE_FULL_E2E)
    if scope not in ALLOWED_REGRESSION_SCOPES:
        raise PipelineBatchRegressionError("Unsupported regression scope")
    phase2_meta_path = root / "phase2_meta.json"
    if not phase2_meta_path.is_file():
        return {"status": "READY_FOR_PHASE2", "next_stage": "phase2"}
    phase2_meta = _load_object(phase2_meta_path)
    if not bool(phase2_meta.get("ready_for_phase3")):
        return {
            "status": "WAITING_OCR_OPERATOR_REVIEW",
            "next_stage": "phase2_review",
            "operator_touch_required": True,
            "review_required": int(phase2_meta.get("review_required") or 0),
        }
    if not (root / "phase3_closeout.json").is_file():
        phase3_meta_path = root / "phase3_meta.json"
        if phase3_meta_path.is_file():
            phase3_meta = _load_object(phase3_meta_path)
            summary = dict(phase3_meta.get("review_summary") or {})
            if str(summary.get("status") or "") != "TRANSLATION_APPROVED":
                return {
                    "status": "WAITING_TRANSLATION_OPERATOR_REVIEW",
                    "next_stage": "phase3_review",
                    "operator_touch_required": True,
                    "review_required": int(summary.get("unresolved") or 0),
                }
        return {"status": "READY_FOR_PHASE3", "next_stage": "phase3"}
    render_input_path = root / "phase4_render_input.json"
    if not render_input_path.is_file():
        try:
            remediation_path = resolve_active_residual_remediation(root)
        except ResidualRemediationAuthorityError as exc:
            raise PipelineBatchRegressionError(str(exc)) from exc
        if remediation_path is not None and not _residual_remediation_is_materialized(
            root,
            phase2_meta,
            remediation_path,
        ):
            return {
                "status": "READY_FOR_PHASE2_REMEDIATION",
                "next_stage": "phase2",
            }
        proposal_path = root / "phase2_residual_remediation_proposal.json"
        if proposal_path.is_file():
            proposal = _load_object(proposal_path)
            if (
                str(proposal.get("status") or "")
                == "PROPOSAL_READY_FOR_OPERATOR_REVIEW"
                and not bool(proposal.get("operator_approval_written"))
            ):
                return {
                    "status": "WAITING_RESIDUAL_REMEDIATION_OPERATOR_REVIEW",
                    "next_stage": "phase2_residual_review",
                    "operator_touch_required": True,
                    "review_required": len(list(proposal.get("proposals") or [])),
                    "proposal_sha256": proposal.get("proposal_sha256"),
                }
        preflight_meta_path = root / "phase4_preflight_meta.json"
        if preflight_meta_path.is_file():
            preflight_meta = _load_object(preflight_meta_path)
            residual = dict(preflight_meta.get("residual_cjk") or {})
            if (
                str(preflight_meta.get("status") or "")
                == "PHASE4_PREFLIGHT_BLOCKED"
                and str(preflight_meta.get("final_render_gate") or "")
                == "BLOCKED_VISUAL_RESIDUAL_CJK"
            ):
                return {
                    "status": "WAITING_RESIDUAL_CJK_OPERATOR_TRIAGE",
                    "next_stage": "residual_cjk_triage",
                    "operator_touch_required": True,
                    "review_required": len(list(residual.get("detections") or [])),
                }
        return {"status": "READY_FOR_PHASE4_PREFLIGHT", "next_stage": "phase4_preflight"}
    if not (root / "phase4_adaptive_visual_preview.mp4").is_file():
        return {"status": "READY_FOR_VISUAL_PREVIEW", "next_stage": "phase4_visual"}
    visual_approval = root / "phase4_visual_approval.json"
    visual_meta_path = root / "phase4_adaptive_render_meta.json"
    if not visual_meta_path.is_file() and not visual_approval.is_file():
        return {"status": "READY_FOR_VISUAL_PREVIEW", "next_stage": "phase4_visual"}
    if visual_meta_path.is_file():
        visual_meta = _load_object(visual_meta_path)
    else:
        visual_meta = {}
    if bool(visual_meta.get("visual_preview")):
        if str(visual_meta.get("phase4_input_sha256") or "") != _sha256_file(
            render_input_path
        ):
            return {
                "status": "READY_FOR_VISUAL_PREVIEW",
                "next_stage": "phase4_visual",
            }
        if str(visual_meta.get("output_qa_status") or "") != "PASS":
            return {"status": "VISUAL_PREVIEW_QA_FAILED", "next_stage": None}
    if not visual_approval.is_file():
        return {
            "status": "WAITING_VISUAL_OPERATOR_REVIEW",
            "next_stage": "visual_review",
            "operator_touch_required": True,
        }
    if scope == REGRESSION_SCOPE_VISUAL_LOCALIZATION_ONLY:
        return {
            "status": "VISUAL_LOCALIZATION_APPROVED",
            "next_stage": None,
            "operator_touch_required": False,
            "review_required": 0,
            "regression_scope": scope,
        }
    dialogue_review_path = root / "phase4_dialogue_detection_review.json"
    if dialogue_review_path.is_file():
        dialogue_review = _load_object(dialogue_review_path)
        if (
            str(dialogue_review.get("status") or "")
            == "PENDING_DIALOGUE_OPERATOR_REVIEW"
            and not bool(dialogue_review.get("operator_approval_written"))
        ):
            dialogue_approval_path = root / "phase4_dialogue_detection_approval.json"
            if not dialogue_approval_path.is_file():
                return {
                    "status": "WAITING_DIALOGUE_DETECTION_OPERATOR_REVIEW",
                    "next_stage": "dialogue_detection_review",
                    "operator_touch_required": True,
                    "review_required": 1,
                    "review_sha256": dialogue_review.get("artifact_sha256"),
                }
            dialogue_approval = _load_object(dialogue_approval_path)
            decision = str(dialogue_approval.get("status") or "")
            if decision == "DIALOGUE_PRESENT_CONFIRMED":
                translation_approval_path = (
                    root / "phase4_dialogue_translation_approval.json"
                )
                if not translation_approval_path.is_file():
                    translation_review_path = (
                        root / "phase4_dialogue_translation_review.json"
                    )
                    if translation_review_path.is_file():
                        return {
                            "status": "WAITING_DIALOGUE_TRANSLATION_OPERATOR_REVIEW",
                            "next_stage": "dialogue_translation_review",
                            "operator_touch_required": True,
                            "review_required": len(
                                list(
                                    _load_object(translation_review_path).get(
                                        "segments"
                                    )
                                    or []
                                )
                            ),
                        }
                    return {
                        "status": "READY_FOR_DIALOGUE_ASR_REMEDIATION",
                        "next_stage": "audio_analysis",
                    }
            elif decision == "NO_DIALOGUE_CONFIRMED":
                if not (root / "phase4_no_dialogue_audio_review.json").is_file():
                    return {
                        "status": "READY_FOR_NO_DIALOGUE_AUDIO_STAGING",
                        "next_stage": "audio_staging",
                    }
            else:
                raise PipelineBatchRegressionError(
                    "Dialogue detection approval status is invalid"
                )
    translation_review_path = root / "phase4_dialogue_translation_review.json"
    if translation_review_path.is_file():
        translation_review = _load_object(translation_review_path)
        if (
            str(translation_review.get("status") or "")
            == "PENDING_OPERATOR_REVIEW"
            and not bool(translation_review.get("operator_approval_written"))
        ):
            translation_approval_path = (
                root / "phase4_dialogue_translation_approval.json"
            )
            if not translation_approval_path.is_file():
                return {
                    "status": "WAITING_DIALOGUE_TRANSLATION_OPERATOR_REVIEW",
                    "next_stage": "dialogue_translation_review",
                    "operator_touch_required": True,
                    "review_required": len(
                        list(translation_review.get("segments") or [])
                    ),
                    "review_sha256": translation_review.get("artifact_sha256"),
                }
    mix_review_path = root / "phase4_background_mix_review.json"
    if mix_review_path.is_file():
        mix_review = _load_object(mix_review_path)
        if str(mix_review.get("status") or "") == "PENDING_AUDIO_MIX_REVIEW":
            mix_approval_path = root / "phase4_background_mix_approval.json"
            if not mix_approval_path.is_file():
                if not _pending_mix_is_covered_by_downstream_authority(
                    root, mix_review
                ):
                    return {
                        "status": "WAITING_AUDIO_MIX_OPERATOR_REVIEW",
                        "next_stage": "audio_mix_review",
                        "operator_touch_required": True,
                        "review_required": 1,
                        "review_sha256": mix_review.get("artifact_sha256"),
                    }
            else:
                mix_approval = _load_object(mix_approval_path)
                if str(mix_approval.get("status") or "") != "AUDIO_MIX_APPROVED":
                    raise PipelineBatchRegressionError(
                        "Background mix approval status is invalid"
                    )
    audio_approval = root / "phase4_audio_approval.json"
    if not audio_approval.is_file():
        return {
            "status": "WAITING_AUDIO_OPERATOR_REVIEW",
            "next_stage": "audio_review",
            "operator_touch_required": True,
        }
    final_meta_path = root / "phase4_adaptive_render_meta.json"
    if not final_meta_path.is_file():
        return {"status": "READY_FOR_FINAL_RENDER", "next_stage": "phase4_final"}
    final_meta = _load_object(final_meta_path)
    if (
        str(final_meta.get("status") or "") == "VISUAL_PREVIEW_RENDERED"
        and bool(final_meta.get("visual_preview"))
        and str(final_meta.get("output_qa_status") or "") == "PASS"
    ):
        return {"status": "READY_FOR_FINAL_RENDER", "next_stage": "phase4_final"}
    if (
        str(final_meta.get("status") or "") != "FINAL_RENDERED"
        or str(final_meta.get("output_qa_status") or "") != "PASS"
    ):
        return {"status": "FINAL_RENDER_QA_FAILED", "next_stage": None}
    export_handoff = root / "phase5_export_handoff.json"
    if not export_handoff.is_file():
        return {
            "status": "WAITING_FINAL_OPERATOR_APPROVAL",
            "next_stage": "final_review",
            "operator_touch_required": True,
        }
    handoff = _load_object(export_handoff)
    if not (root / "phase5_metadata_approval.json").is_file():
        package_relative = str(dict(handoff.get("package") or {}).get("path") or "")
        package_root = (root / package_relative).resolve()
        draft_path = package_root / "publish_draft.json"
        draft_status = (
            str(_load_object(draft_path).get("status") or "")
            if package_root.is_relative_to(root) and draft_path.is_file()
            else ""
        )
        if draft_status == "METADATA_DRAFT_COMPLETE_REVIEW_REQUIRED":
            return {
                "status": "WAITING_METADATA_OPERATOR_REVIEW",
                "next_stage": "metadata_review",
                "operator_touch_required": True,
                "review_required": 1,
            }
        return {"status": "READY_FOR_METADATA_DRAFT", "next_stage": "metadata_draft"}
    if not (root / "phase5_rights_music_approval.json").is_file():
        return {
            "status": "WAITING_SOURCE_RIGHTS_AND_MUSIC_REVIEW",
            "next_stage": "rights_music_review",
            "operator_touch_required": True,
            "review_required": 1,
        }
    manual_decision_path = root / "phase5_manual_export_decision.json"
    if not manual_decision_path.is_file():
        return {
            "status": "WAITING_EXTERNAL_PUBLISH_AUTHORIZATION",
            "next_stage": "export_mode_review",
            "operator_touch_required": True,
            "review_required": 1,
        }
    manual_decision = _load_object(manual_decision_path)
    if str(manual_decision.get("status") or "") != "MANUAL_EXPORT_ONLY":
        return {"status": "EXTERNAL_PUBLISH_MODE_SELECTED", "next_stage": None}
    if not (root / "phase5_manual_export_handoff.json").is_file():
        return {"status": "READY_FOR_MANUAL_EXPORT", "next_stage": "manual_export"}
    if (root / "phase5_manual_upload_completion.json").is_file():
        return {"status": "MANUAL_UPLOAD_COMPLETED", "next_stage": None}
    if (root / "phase5_manual_upload_deferral.json").is_file():
        return {"status": "BATCH_REGRESSION_READY", "next_stage": None}
    return {
        "status": "WAITING_OPERATOR_MANUAL_UPLOAD",
        "next_stage": "manual_upload",
        "operator_touch_required": True,
        "review_required": 1,
    }


def evaluate_case_gate(
    root_dir: str | Path,
    *,
    phase1_score: dict[str, Any],
    regression_scope: str = REGRESSION_SCOPE_FULL_E2E,
) -> dict[str, Any]:
    """Route materialized NO_TEXT cases into the ordinary downstream gates."""

    root = Path(root_dir)
    if bool(phase1_score.get("PASS")):
        return evaluate_operator_gate(root, regression_scope=regression_scope)
    try:
        no_text_gate = evaluate_no_text_operator_gate(root)
    except Phase1NoTextContractError:
        try:
            geometry_gate = evaluate_phase1_geometry_operator_gate_safe(root)
        except Phase1GeometryReviewError:
            return {
                "status": "FAILED",
                "next_stage": None,
                "operator_touch_required": False,
                "review_required": 0,
            }
        return (
            evaluate_operator_gate(root, regression_scope=regression_scope)
            if geometry_gate.get("status")
            == "PHASE1_GEOMETRY_OPERATOR_APPROVED"
            else geometry_gate
        )
    if (
        str(no_text_gate.get("status") or "") == "NO_TEXT_OPERATOR_APPROVED"
        and (root / "phase2_meta.json").is_file()
    ):
        return evaluate_operator_gate(root, regression_scope=regression_scope)
    return no_text_gate


def refresh_batch_gate_state(
    *, run_root: str | Path, workspace_root: str | Path
) -> dict[str, Any]:
    """Refresh persisted gate states without executing any downstream stage."""
    run = Path(run_root).resolve()
    workspace = Path(workspace_root).resolve()
    state = _load_object(run / "batch_regression_state.json")
    corpus_scope_by_case: dict[str, str] = {}
    corpus_relative = str(dict(state.get("corpus_ref") or {}).get("path") or "")
    if corpus_relative:
        corpus_path = (workspace / corpus_relative).resolve()
        if corpus_path.is_relative_to(workspace) and corpus_path.is_file():
            corpus = _load_object(corpus_path)
            corpus_scope_by_case = {
                str(case.get("case_id") or ""): str(
                    case.get("regression_scope") or REGRESSION_SCOPE_FULL_E2E
                )
                for case in list(corpus.get("cases") or [])
                if isinstance(case, dict) and str(case.get("case_id") or "")
            }
    corpus_scope_by_case.update(_scope_overrides_from_manifest(run, state))
    rows: list[dict[str, Any]] = []
    artifact_rows: list[tuple[Path, dict[str, Any]]] = []
    for raw in list(state.get("cases") or []):
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        artifact = (workspace / str(row.get("artifact_root") or "")).resolve()
        if not artifact.is_relative_to(workspace) or not artifact.is_dir():
            raise PipelineBatchRegressionError(
                f"Invalid artifact root: {row.get('case_id')}"
            )
        score = _load_object(artifact / "phase1_score.json")
        case_id = str(row.get("case_id") or "")
        regression_scope = str(
            # The active, hash-bound scope manifest must be able to narrow a
            # previously persisted FULL_E2E row.  Persisted state is historical
            # output, not stronger authority than the manifest.
            corpus_scope_by_case.get(case_id)
            or row.get("regression_scope")
            or REGRESSION_SCOPE_FULL_E2E
        )
        if regression_scope not in ALLOWED_REGRESSION_SCOPES:
            raise PipelineBatchRegressionError(
                f"Unsupported regression scope: {case_id}"
            )
        gate = evaluate_case_gate(
            artifact,
            phase1_score=score,
            regression_scope=regression_scope,
        )
        row.update(
            {
                "status": str(gate.get("status") or "FAILED"),
                "operator_touch_required": bool(
                    gate.get("operator_touch_required")
                ),
                "review_required": int(gate.get("review_required") or 0),
                "next_stage": gate.get("next_stage"),
                "regression_scope": regression_scope,
            }
        )
        rows.append(row)
        artifact_rows.append((artifact, row))
    failed_statuses = {"FAILED", "TEXT_PRESENT_PHASE1_REJECTED"}
    state.update(
        {
            "status": (
                "FAILED"
                if any(str(row.get("status") or "") in failed_statuses for row in rows)
                else "PASS_TO_OPERATOR_GATES"
            ),
            "refreshed_at": _now(),
            "case_count": len(rows),
            "failed_count": sum(
                str(row.get("status") or "") in failed_statuses for row in rows
            ),
            "operator_touch_count": sum(
                bool(row.get("operator_touch_required")) for row in rows
            ),
            "cases": rows,
        }
    )
    state.pop("run_sha256", None)
    state["run_sha256"] = _sha256_json(state)
    _write_json_atomic(
        run / "attempts" / f"gate_refresh_{state['run_sha256']}.json", state
    )
    _write_json_atomic(run / "batch_regression_state.json", state)
    for artifact, row in artifact_rows:
        _write_json_atomic(artifact / "regression_case_state.json", row)
    return state


class PipelineBatchRegressionRunner:
    def __init__(
        self,
        *,
        workspace_root: str | Path,
        api_root: str | Path,
        corpus_path: str | Path,
        run_root: str | Path,
        phase2_provider: str = "local",
        stop_after_phase2: bool = False,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.api_root = Path(api_root).resolve()
        self.corpus_path = Path(corpus_path).resolve()
        self.run_root = Path(run_root).resolve()
        self.phase2_provider = str(phase2_provider or "local")
        self.stop_after_phase2 = bool(stop_after_phase2)
        self.scope_overrides: dict[str, str] = {}
        if self.phase2_provider not in {"local", "cloud", "mock"}:
            raise PipelineBatchRegressionError("Unsupported Phase 2 provider")

    def run(self) -> dict[str, Any]:
        corpus = _load_object(self.corpus_path)
        cases = list(corpus.get("cases") or [])
        if not 5 <= len(cases) <= 10:
            raise PipelineBatchRegressionError("Regression corpus must contain 5-10 cases")
        self.run_root.mkdir(parents=True, exist_ok=True)
        state_path = self.run_root / "batch_regression_state.json"
        scope_state = (
            _load_object(state_path)
            if state_path.is_file()
            else {
                "corpus_ref": {"corpus_sha256": corpus.get("corpus_sha256")},
                "cases": [
                    {"case_id": str(case.get("case_id") or "")}
                    for case in cases
                    if isinstance(case, dict)
                ],
            }
        )
        self.scope_overrides = _scope_overrides_from_manifest(
            self.run_root,
            scope_state,
        )
        rows = [self._run_case(dict(case)) for case in cases]
        summary = {
            "schema_version": "pipeline_batch_regression_v1",
            "status": (
                "PASS_TO_OPERATOR_GATES"
                if not any(row["status"] == "FAILED" for row in rows)
                else "FAILED"
            ),
            "created_at": _now(),
            "corpus_ref": {
                "path": self._relative_or_absolute(self.corpus_path),
                "sha256": _sha256_file(self.corpus_path),
                "corpus_sha256": corpus.get("corpus_sha256"),
            },
            "phase2_provider": self.phase2_provider,
            "case_count": len(rows),
            "failed_count": sum(row["status"] == "FAILED" for row in rows),
            "operator_touch_count": sum(
                bool(row.get("operator_touch_required")) for row in rows
            ),
            "cases": rows,
        }
        summary["run_sha256"] = _sha256_json(summary)
        _write_json_atomic(
            self.run_root / "attempts" / f"batch_{summary['run_sha256']}.json",
            summary,
        )
        _write_json_atomic(self.run_root / "batch_regression_state.json", summary)
        return summary

    def _run_case(self, case: dict[str, Any]) -> dict[str, Any]:
        case_id = str(case.get("case_id") or "").strip()
        video_id = str(case.get("source_video_external_id") or "").strip()
        if not case_id or not video_id:
            raise PipelineBatchRegressionError("Corpus case id and video id are required")
        regression_scope = str(
            self.scope_overrides.get(case_id)
            or case.get("regression_scope")
            or REGRESSION_SCOPE_FULL_E2E
        )
        if regression_scope not in ALLOWED_REGRESSION_SCOPES:
            raise PipelineBatchRegressionError(
                f"Unsupported regression scope: {case_id}"
            )

        def current_gate() -> dict[str, Any]:
            gate = evaluate_operator_gate(
                case_root, regression_scope=regression_scope
            )
            gate["regression_scope"] = regression_scope
            return gate

        source = (self.workspace_root / str(case.get("video_path") or "")).resolve()
        if not source.is_relative_to(self.workspace_root) or not source.is_file():
            raise PipelineBatchRegressionError(f"Invalid corpus video path: {case_id}")
        case_root = self.run_root / case_id
        logs_dir = case_root / "logs"
        stage_rows: list[dict[str, Any]] = []
        started = time.perf_counter()
        try:
            if not (case_root / "master_timeline.json").is_file():
                baseline_raw = case.get("phase1_artifact_root")
                baseline = (
                    (self.workspace_root / str(baseline_raw)).resolve()
                    if baseline_raw
                    else None
                )
                if baseline is not None and baseline.is_dir():
                    shutil.copytree(baseline, case_root, dirs_exist_ok=True)
                    stage_rows.append(
                        {
                            "stage": "phase1",
                            "status": "REUSED_ACCEPTED_BASELINE",
                            "elapsed_seconds": 0.0,
                        }
                    )
                else:
                    result = self._execute(
                        stage="phase1",
                        args=[
                            "-m",
                            "scripts.run_phase1_only",
                            str(source),
                            str(case_root),
                            "--step",
                            "1",
                        ],
                        logs_dir=logs_dir,
                    )
                    stage_rows.append(result)
                    if result["status"] != "PASS":
                        return self._failed_case(
                            case_id, video_id, stage_rows, started, case_root, source
                        )
            else:
                stage_rows.append(
                    {"stage": "phase1", "status": "RESUMED", "elapsed_seconds": 0.0}
                )

            phase1_score = score_phase1_out(case_root)
            _write_json_atomic(case_root / "phase1_score.json", phase1_score)
            phase1_geometry_approved = False
            if not bool(phase1_score.get("PASS")):
                try:
                    no_text_gate = evaluate_no_text_operator_gate(case_root)
                except Phase1NoTextContractError:
                    no_text_gate = None
                if no_text_gate is not None:
                    no_text_gate["regression_scope"] = regression_scope
                    no_text_status = str(no_text_gate.get("status") or "")
                    stage_rows.append(
                        {
                            "stage": "phase1_score",
                            "status": no_text_status,
                            "elapsed_seconds": 0.0,
                            "tracks": 0,
                            "review_required": int(
                                no_text_gate.get("review_required") or 0
                            ),
                        }
                    )
                    if no_text_status == "TEXT_PRESENT_PHASE1_REJECTED":
                        return self._failed_case(
                            case_id,
                            video_id,
                            stage_rows,
                            started,
                            case_root,
                            source,
                        )
                    return self._case_result(
                        case_id=case_id,
                        video_id=video_id,
                        status=no_text_status,
                        gate=no_text_gate,
                        stages=stage_rows,
                        started=started,
                        case_root=case_root,
                        source=source,
                    )
                try:
                    geometry_gate = evaluate_phase1_geometry_operator_gate_safe(
                        case_root
                    )
                except Phase1GeometryReviewError:
                    stage_rows.append(
                        {
                            "stage": "phase1_score",
                            "status": "FAIL",
                            "elapsed_seconds": 0.0,
                        }
                    )
                    return self._failed_case(
                        case_id, video_id, stage_rows, started, case_root, source
                    )
                geometry_gate["regression_scope"] = regression_scope
                geometry_status = str(geometry_gate.get("status") or "")
                stage_rows.append(
                    {
                        "stage": "phase1_geometry_review",
                        "status": geometry_status,
                        "elapsed_seconds": 0.0,
                        "tracks": phase1_score.get("tracks"),
                        "review_required": int(
                            geometry_gate.get("review_required") or 0
                        ),
                    }
                )
                if geometry_status != "PHASE1_GEOMETRY_OPERATOR_APPROVED":
                    return self._case_result(
                        case_id=case_id,
                        video_id=video_id,
                        status=geometry_status,
                        gate=geometry_gate,
                        stages=stage_rows,
                        started=started,
                        case_root=case_root,
                        source=source,
                    )
                phase1_geometry_approved = True
            stage_rows.append(
                {
                    "stage": "phase1_score",
                    "status": (
                        "OPERATOR_GEOMETRY_APPROVED"
                        if phase1_geometry_approved
                        else "PASS"
                    ),
                    "elapsed_seconds": 0.0,
                    "tracks": phase1_score.get("tracks"),
                    "hardsubs": phase1_score.get("hardsubs"),
                }
            )

            gate = current_gate()
            if gate["next_stage"] == "phase2":
                result = self._execute(
                    stage="phase2",
                    args=[
                        "-m",
                        "scripts.run_phase2_only",
                        "--provider",
                        self.phase2_provider,
                        str(case_root),
                        str(source),
                    ],
                    logs_dir=logs_dir,
                )
                stage_rows.append(result)
                if result["status"] != "PASS":
                    return self._failed_case(
                        case_id, video_id, stage_rows, started, case_root, source
                    )
                gate = current_gate()
            else:
                stage_rows.append(
                    {"stage": "phase2", "status": "RESUMED", "elapsed_seconds": 0.0}
                )

            if gate.get("operator_touch_required"):
                return self._case_result(
                    case_id=case_id,
                    video_id=video_id,
                    status=str(gate["status"]),
                    gate=gate,
                    stages=stage_rows,
                    started=started,
                    case_root=case_root,
                    source=source,
                )
            if self.stop_after_phase2:
                return self._case_result(
                    case_id=case_id,
                    video_id=video_id,
                    status=str(gate["status"]),
                    gate=gate,
                    stages=stage_rows,
                    started=started,
                    case_root=case_root,
                    source=source,
                )
            for stage_name, module_name in (
                ("phase3", "scripts.run_phase3_only"),
                ("phase4_preflight", "scripts.run_phase4_preflight"),
                ("phase4_visual", "scripts.run_phase4_adaptive"),
            ):
                gate = current_gate()
                if gate.get("operator_touch_required"):
                    break
                if gate.get("next_stage") != stage_name:
                    continue
                result = self._execute(
                    stage=stage_name,
                    args=["-m", module_name, str(case_root)],
                    logs_dir=logs_dir,
                )
                stage_rows.append(result)
                if result["status"] != "PASS":
                    return self._failed_case(
                        case_id, video_id, stage_rows, started, case_root, source
                    )
            gate = current_gate()
            if gate.get("next_stage") == "phase4_final":
                result = self._execute(
                    stage="phase4_final_preflight",
                    args=["-m", "scripts.run_phase4_preflight", str(case_root)],
                    logs_dir=logs_dir,
                )
                stage_rows.append(result)
                if result["status"] != "PASS":
                    return self._failed_case(
                        case_id, video_id, stage_rows, started, case_root, source
                    )
                result = self._execute(
                    stage="phase4_final",
                    args=[
                        "-m",
                        "scripts.run_phase4_adaptive",
                        str(case_root),
                        "--final",
                    ],
                    logs_dir=logs_dir,
                )
                stage_rows.append(result)
                if result["status"] != "PASS":
                    return self._failed_case(
                        case_id, video_id, stage_rows, started, case_root, source
                    )
                gate = current_gate()
            return self._case_result(
                case_id=case_id,
                video_id=video_id,
                status=str(gate["status"]),
                gate=gate,
                stages=stage_rows,
                started=started,
                case_root=case_root,
                source=source,
            )
        except Exception as exc:  # Persist the error type, never environment secrets.
            stage_rows.append(
                {"stage": "runner", "status": "FAIL", "error_type": type(exc).__name__}
            )
            return self._failed_case(
                case_id, video_id, stage_rows, started, case_root, source
            )

    def _execute(
        self, *, stage: str, args: list[str], logs_dir: Path
    ) -> dict[str, Any]:
        logs_dir.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, *args],
            cwd=self.api_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        elapsed = round(time.perf_counter() - started, 3)
        # Phase 1 intentionally recreates its output root, which can remove the
        # pre-created log directory while the subprocess is running.
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / f"{stage}.log"
        log_path.write_text(
            completed.stdout + "\n" + completed.stderr,
            encoding="utf-8",
        )
        return {
            "stage": stage,
            "status": "PASS" if completed.returncode == 0 else "FAIL",
            "return_code": completed.returncode,
            "elapsed_seconds": elapsed,
            "log_path": self._relative_or_absolute(log_path),
        }

    def _failed_case(
        self,
        case_id: str,
        video_id: str,
        stages: list[dict[str, Any]],
        started: float,
        case_root: Path,
        source: Path,
    ) -> dict[str, Any]:
        return {
            "case_id": case_id,
            "source_video_external_id": video_id,
            "status": "FAILED",
            "operator_touch_required": False,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "source_video_sha256": _sha256_file(source),
            "artifact_root": self._relative_or_absolute(case_root),
            "stages": stages,
        }

    def _case_result(
        self,
        *,
        case_id: str,
        video_id: str,
        status: str,
        gate: dict[str, Any],
        stages: list[dict[str, Any]],
        started: float,
        case_root: Path,
        source: Path,
    ) -> dict[str, Any]:
        result = {
            "case_id": case_id,
            "source_video_external_id": video_id,
            "status": status,
            "operator_touch_required": bool(gate.get("operator_touch_required")),
            "review_required": int(gate.get("review_required") or 0),
            "next_stage": gate.get("next_stage"),
            "regression_scope": gate.get(
                "regression_scope", REGRESSION_SCOPE_FULL_E2E
            ),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "source_video_sha256": _sha256_file(source),
            "artifact_root": self._relative_or_absolute(case_root),
            "stages": stages,
        }
        _write_json_atomic(case_root / "regression_case_state.json", result)
        return result

    def _relative_or_absolute(self, path: Path) -> str:
        resolved = path.resolve()
        return (
            resolved.relative_to(self.workspace_root).as_posix()
            if resolved.is_relative_to(self.workspace_root)
            else str(resolved)
        )
