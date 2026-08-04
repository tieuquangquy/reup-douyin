"""Hash-bound end-to-end evidence for completed controlled-pilot cases."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.services.no_text_passthrough import (
    NoTextPassthroughError,
    load_no_text_authority,
)
from src.services.pipeline_tts_provenance import (
    aggregate_tts_provenance,
    extract_case_tts_provenance,
)


E2E_REPORT_SCHEMA_VERSION = "pipeline_e2e_regression_report_v2"
E2E_REPORT_STATUS_PASS = "PASS_CONTROLLED_E2E"
ALLOWED_MANUAL_STATES = {
    "MANUAL_EXPORT_READY",
    "MANUAL_UPLOAD_DEFERRED",
    "MANUAL_UPLOAD_COMPLETED",
}


class PipelineE2eRegressionReportError(RuntimeError):
    pass


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
        raise PipelineE2eRegressionReportError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise PipelineE2eRegressionReportError(f"{path.name} must contain an object")
    return payload


def _verify_self_hash(payload: dict[str, Any], field: str, label: str) -> str:
    claimed = str(payload.get(field) or "")
    unsigned = dict(payload)
    unsigned.pop(field, None)
    if len(claimed) != 64 or _sha256_json(unsigned) != claimed:
        raise PipelineE2eRegressionReportError(f"{label} self-hash is invalid")
    return claimed


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _phase1_geometry_operator_approved(
    root: Path, phase1_score: dict[str, Any]
) -> bool:
    """Verify the explicit, hash-bound Phase-1 geometry acceptance path."""

    approval_path = root / "phase1_geometry_approval.json"
    if not approval_path.is_file():
        return False
    approval = _load_object(approval_path)
    _verify_self_hash(approval, "approval_sha256", "Phase 1 geometry approval")
    if str(approval.get("status") or "") != "PHASE1_GEOMETRY_OPERATOR_APPROVED":
        return False
    review_ref = dict(approval.get("review_ref") or {})
    review_path = (root / str(review_ref.get("path") or "")).resolve()
    if (
        not review_path.is_relative_to(root)
        or not review_path.is_file()
    ):
        return False
    review = _load_object(review_path)
    review_sha256 = _verify_self_hash(
        review, "review_sha256", "Phase 1 geometry review"
    )
    if review_sha256 != str(review_ref.get("sha256") or ""):
        return False
    score_ref = dict(dict(review.get("phase1_refs") or {}).get("phase1_score") or {})
    score_path = (root / str(score_ref.get("path") or "")).resolve()
    if (
        score_path != (root / "phase1_score.json").resolve()
        or _sha256_file(score_path) != str(score_ref.get("sha256") or "")
    ):
        return False
    issue_ids = {
        str(dict(row).get("issue_id") or "")
        for row in list(review.get("issues") or [])
        if str(dict(row).get("issue_id") or "")
    }
    decision_ids = {
        str(dict(row).get("issue_id") or "")
        for row in list(approval.get("decisions") or [])
        if str(dict(row).get("issue_id") or "")
    }
    return bool(issue_ids) and decision_ids == issue_ids and not bool(
        phase1_score.get("PASS")
    )


def _phase1_no_text_operator_approved(
    root: Path, phase1_score: dict[str, Any]
) -> bool:
    if bool(phase1_score.get("PASS")) or int(phase1_score.get("tracks") or 0) != 0:
        return False
    try:
        load_no_text_authority(root)
    except NoTextPassthroughError:
        return False
    return True


def _case_report(root: Path, run_root: Path) -> dict[str, Any]:
    phase1_score = _load_object(root / "phase1_score.json")
    phase2_meta = _load_object(root / "phase2_meta.json")
    phase3_closeout = _load_object(root / "phase3_closeout.json")
    render_meta = _load_object(root / "phase4_adaptive_render_meta.json")
    output_qa = _load_object(root / "qa" / "phase4_adaptive_final_output_qa.json")
    final_approval = _load_object(root / "phase5_final_approval.json")
    metadata_approval = _load_object(root / "phase5_metadata_approval.json")
    rights_approval = _load_object(root / "phase5_rights_music_approval.json")
    export_handoff = _load_object(root / "phase5_export_handoff.json")
    manual_handoff = _load_object(root / "phase5_manual_export_handoff.json")
    db_handoff = _load_object(root / "phase5_db_handoff.json")

    final_approval_hash = _verify_self_hash(
        final_approval, "approval_sha256", "Final approval"
    )
    metadata_approval_hash = _verify_self_hash(
        metadata_approval, "approval_sha256", "Metadata approval"
    )
    rights_approval_hash = _verify_self_hash(
        rights_approval, "approval_sha256", "Rights/music approval"
    )
    manual_handoff_hash = _verify_self_hash(
        manual_handoff, "handoff_sha256", "Manual export handoff"
    )
    source = dict(final_approval.get("source_video") or {})
    final_path = root / "phase4_adaptive_final.mp4"
    final_sha256 = _sha256_file(final_path)
    failures: list[str] = []
    phase1_operator_approved = _phase1_geometry_operator_approved(root, phase1_score)
    phase1_no_text_approved = _phase1_no_text_operator_approved(root, phase1_score)
    checks = {
        # A controlled pilot may accept a clean, hash-bound geometry review even
        # when the numeric scorer is intentionally conservative.  Treat that
        # explicit operator decision as Phase-1 acceptance; do not treat a
        # generic non-PASS score as sufficient.
        "phase1": (
            bool(phase1_score.get("PASS"))
            or phase1_operator_approved
            or phase1_no_text_approved
        ),
        "phase2": bool(phase2_meta.get("ready_for_phase3")),
        "phase3": str(phase3_closeout.get("status") or "") == "PHASE3_CLOSED",
        "visual": str(
            _load_object(root / "phase4_visual_approval.json").get("status") or ""
        )
        == "VISUAL_APPROVED",
        "audio": str(
            _load_object(root / "phase4_audio_approval.json").get("status") or ""
        )
        == "AUDIO_APPROVED",
        "render": str(render_meta.get("status") or "") == "FINAL_RENDERED",
        "output_qa": (
            str(output_qa.get("status") or "") == "PASS"
            and not list(output_qa.get("failed_checks") or [])
        ),
        "final": str(final_approval.get("status") or "") == "FINAL_APPROVED",
        "metadata": str(metadata_approval.get("status") or "")
        == "METADATA_APPROVED",
        "rights_music": str(rights_approval.get("status") or "")
        == "SOURCE_RIGHTS_AND_MUSIC_APPROVED",
        "manual_export": str(export_handoff.get("status") or "")
        in ALLOWED_MANUAL_STATES,
        "db_handoff": (
            str(db_handoff.get("status") or "") == "DB_EXPORT_PACKAGE_READY"
            and bool(db_handoff.get("retry_safe"))
            and bool(db_handoff.get("asset_reused"))
            and bool(db_handoff.get("render_reused"))
            and bool(db_handoff.get("export_package_reused"))
        ),
        "external_publish_disabled": not bool(
            export_handoff.get("external_publish_triggered")
            or db_handoff.get("external_publish_triggered")
        ),
        "final_hash": (
            final_sha256 == str(render_meta.get("output_video_sha256") or "")
            and final_sha256 == str(db_handoff.get("final_video_sha256") or "")
        ),
    }
    failures.extend(name for name, passed in checks.items() if not passed)
    audio = dict(output_qa.get("audio") or {})
    audio_metrics = dict(audio.get("metrics") or {})
    audio_mix = dict(render_meta.get("audio_mix") or {})
    encoder = dict(render_meta.get("encoder") or {})
    residual = dict(output_qa.get("residual_cjk") or {})
    tts_provenance = extract_case_tts_provenance(
        case_root=root,
        run_root=run_root,
        audio_strategy=str(audio_mix.get("strategy") or ""),
    )
    checkpoints = 7 + int((root / "phase4_dialogue_translation_approval.json").is_file())
    return {
        "case_id": root.name,
        "source_video_id": source.get("id"),
        "source_video_external_id": source.get("external_id"),
        "status": "PASS" if not failures else "FAIL",
        "failed_checks": failures,
        "checks": checks,
        "operator_checkpoint_count": checkpoints,
        "final_video_sha256": final_sha256,
        "approval_hashes": {
            "final": final_approval_hash,
            "metadata": metadata_approval_hash,
            "rights_music": rights_approval_hash,
            "manual_export_handoff": manual_handoff_hash,
        },
        "render": {
            "frames": int(render_meta.get("frames") or 0),
            "encoder": encoder.get("selected_encoder"),
            "hardware_fallback_used": bool(encoder.get("runtime_fallback_used")),
            "total_render_seconds": encoder.get("total_render_seconds"),
            "audio_strategy": audio_mix.get("strategy"),
            "normalization_mode": audio_mix.get("normalization_mode"),
        },
        "tts": tts_provenance,
        "output_qa": {
            "status": output_qa.get("status"),
            "residual_cjk_blocking": len(list(residual.get("detections") or [])),
            "source_intrinsic_exclusions": len(
                list(residual.get("source_intrinsic_exclusions") or [])
            ),
            "integrated_lufs": audio_metrics.get("integrated_lufs"),
            "true_peak_db": audio_metrics.get("true_peak_db"),
        },
        "manual_state": export_handoff.get("status"),
        "db_handoff": {
            "status": db_handoff.get("status"),
            "media_asset_id": db_handoff.get("media_asset_id"),
            "render_output_id": db_handoff.get("render_output_id"),
            "export_package_id": db_handoff.get("export_package_id"),
            "retry_reused_all": bool(
                db_handoff.get("asset_reused")
                and db_handoff.get("render_reused")
                and db_handoff.get("export_package_reused")
            ),
        },
    }


def build_e2e_regression_report(run_root: str | Path) -> dict[str, Any]:
    run = Path(run_root).resolve()
    report_created_at = _now()
    all_roots = sorted(
        path for path in run.iterdir() if path.is_dir() and path.name.startswith("local_")
    )
    excluded_cases: list[dict[str, Any]] = []
    state_path = run / "batch_regression_state.json"
    if state_path.is_file():
        state = _load_object(state_path)
        report_created_at = str(
            state.get("refreshed_at") or state.get("created_at") or report_created_at
        )
        rows = {
            str(row.get("case_id") or ""): dict(row)
            for row in list(state.get("cases") or [])
            if isinstance(row, dict) and str(row.get("case_id") or "")
        }
        roots = []
        for root in all_roots:
            row = rows.get(root.name, {})
            scope = str(row.get("regression_scope") or "FULL_E2E")
            if scope == "VISUAL_LOCALIZATION_ONLY":
                excluded_cases.append(
                    {
                        "case_id": root.name,
                        "regression_scope": scope,
                        "reason": "VISUAL_LOCALIZATION_SCOPE_NOT_FULL_E2E",
                    }
                )
            elif not (root / "phase5_db_handoff.json").is_file():
                excluded_cases.append(
                    {
                        "case_id": root.name,
                        "regression_scope": scope,
                        "reason": "RETRY_SAFE_DB_HANDOFF_NOT_AVAILABLE",
                    }
                )
            else:
                roots.append(root)
    else:
        roots = all_roots
    if not roots:
        raise PipelineE2eRegressionReportError(
            "No full end-to-end regression case roots were found"
        )
    cases = [_case_report(root, run) for root in roots]
    tts_provenance = aggregate_tts_provenance(cases)
    if tts_provenance.get("status") != "VERIFIED_SINGLE_RUNTIME_CONFIG":
        for case in cases:
            if case.get("tts", {}).get("status") != "NOT_APPLICABLE":
                case["failed_checks"].append("tts_provenance")
                case["checks"]["tts_provenance"] = False
            else:
                case["checks"]["tts_provenance"] = True
    else:
        for case in cases:
            case["checks"]["tts_provenance"] = case.get("tts", {}).get(
                "status"
            ) in {"VERIFIED", "NOT_APPLICABLE"}
            if not case["checks"]["tts_provenance"] and "tts_provenance" not in case[
                "failed_checks"
            ]:
                case["failed_checks"].append("tts_provenance")
    for case in cases:
        case["status"] = "PASS" if not case["failed_checks"] else "FAIL"
    # Recompute after adding the provenance gate to each case.
    passed = sum(case["status"] == "PASS" for case in cases)
    tts_provenance_pass = (
        tts_provenance.get("status") == "VERIFIED_SINGLE_RUNTIME_CONFIG"
    )
    full_e2e_excluded_count = sum(
        str(row.get("regression_scope") or "") != "VISUAL_LOCALIZATION_ONLY"
        for row in excluded_cases
    )
    visual_localization_excluded_count = sum(
        str(row.get("regression_scope") or "") == "VISUAL_LOCALIZATION_ONLY"
        for row in excluded_cases
    )
    report = {
        "schema_version": E2E_REPORT_SCHEMA_VERSION,
        "status": (
            E2E_REPORT_STATUS_PASS
            if passed == len(cases) and tts_provenance_pass
            else "FAILED"
        ),
        "created_at": report_created_at,
        "run_case_count": len(all_roots),
        "case_count": len(cases),
        "excluded_case_count": len(excluded_cases),
        "full_e2e_scope_case_count": len(cases) + full_e2e_excluded_count,
        "full_e2e_excluded_count": full_e2e_excluded_count,
        "visual_localization_excluded_count": visual_localization_excluded_count,
        "excluded_cases": excluded_cases,
        "passed_count": passed,
        "final_qa_pass_count": sum(
            case["checks"]["output_qa"] for case in cases
        ),
        "db_handoff_ready_count": sum(
            case["checks"]["db_handoff"] for case in cases
        ),
        "operator_checkpoint_count": sum(
            int(case["operator_checkpoint_count"]) for case in cases
        ),
        "external_publish_triggered_count": sum(
            not case["checks"]["external_publish_disabled"] for case in cases
        ),
        "cases": cases,
        "tts_provenance": tts_provenance,
        "claims": {
            "included_cases_end_to_end_pass": (
                passed == len(cases) and tts_provenance_pass
            ),
            "full_batch_end_to_end_pass": (
                passed == len(cases)
                and tts_provenance_pass
                and full_e2e_excluded_count == 0
                and len(cases) > 0
            ),
            "universal_video_support": False,
            "controlled_pilot_only": True,
        },
    }
    report["report_sha256"] = _sha256_json(report)
    return report


def write_e2e_regression_report(run_root: str | Path) -> dict[str, Any]:
    run = Path(run_root).resolve()
    report = build_e2e_regression_report(run)
    _write_json_atomic(run / "pipeline_e2e_regression_report.json", report)
    lines = [
        "# Pipeline End-to-End Regression Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Cases PASS: `{report['passed_count']}/{report['case_count']}`",
        f"- Run cases excluded by explicit scope/evidence boundary: `{report['excluded_case_count']}`",
        f"- Full-E2E cases: `{report['case_count']}/{report['full_e2e_scope_case_count']}`",
        f"- Full-E2E cases missing evidence: `{report['full_e2e_excluded_count']}`",
        f"- Visual-localization-only fixtures excluded: `{report['visual_localization_excluded_count']}`",
        f"- Final QA PASS: `{report['final_qa_pass_count']}/{report['case_count']}`",
        f"- DB handoff retry-safe: `{report['db_handoff_ready_count']}/{report['case_count']}`",
        f"- Operator checkpoints recorded: `{report['operator_checkpoint_count']}`",
        f"- External publish calls: `{report['external_publish_triggered_count']}`",
        "- TTS provenance: `{status}` (`{provider}` / `{model}` / `{voice}`; {cases} narration cases, {na} not applicable)".format(
            status=report["tts_provenance"].get("status"),
            provider=report["tts_provenance"].get("provider"),
            model=report["tts_provenance"].get("model_id"),
            voice=report["tts_provenance"].get("voice_id"),
            cases=report["tts_provenance"].get("tts_case_count"),
            na=report["tts_provenance"].get("not_applicable_case_count"),
        ),
        f"- Report SHA-256: `{report['report_sha256']}`",
        "",
        "| Case | State | Encoder | Audio strategy | LUFS | DB retry reuse |",
        "|---|---|---|---|---:|---|",
    ]
    for case in report["cases"]:
        lines.append(
            "| {external} | `{status}` | `{encoder}` | `{audio}` | {lufs} | `{reuse}` |".format(
                external=case["source_video_external_id"],
                status=case["status"],
                encoder=case["render"]["encoder"],
                audio=case["render"]["audio_strategy"],
                lufs=case["output_qa"]["integrated_lufs"],
                reuse=case["db_handoff"]["retry_reused_all"],
            )
        )
    lines.extend(
        [
            "",
            "This closes only the included controlled-pilot cases. Universal video support remains false.",
        ]
    )
    _write_text_atomic(run / "PIPELINE_E2E_REGRESSION_REPORT.md", "\n".join(lines) + "\n")
    return report
