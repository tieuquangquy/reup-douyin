"""Aggregate a batch regression run without treating operator gates as failures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Any

from src.media_pipeline.frame_sampling.phase1_geometry_review import (
    Phase1GeometryReviewError,
    evaluate_phase1_geometry_operator_gate_safe,
)
from src.services.no_text_passthrough import (
    NoTextPassthroughError,
    load_no_text_authority,
)


class PipelineRegressionReportError(RuntimeError):
    pass


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


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineRegressionReportError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise PipelineRegressionReportError(f"{path.name} must contain an object")
    return payload


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


def _phase1_outcome(
    score: dict[str, Any],
    *,
    geometry_status: str | None = None,
) -> str:
    if bool(score.get("PASS")):
        return "PASS"
    if geometry_status == "PHASE1_GEOMETRY_OPERATOR_APPROVED":
        return "OPERATOR_GEOMETRY_APPROVED"
    if geometry_status == "WAITING_PHASE1_GEOMETRY_OPERATOR_REVIEW":
        return "GEOMETRY_REVIEW_REQUIRED"
    tracks = int(score.get("tracks") or 0)
    uncovered = list(score.get("uncovered_dense_hardsub_spans") or [])
    if tracks == 0 and uncovered:
        return "TEXT_RECALL_FAILURE"
    if tracks == 0:
        return "NO_CONFIRMED_TEXT_REVIEW_REQUIRED"
    return "PHASE1_QUALITY_FAILURE"


def build_regression_report(
    *,
    run_root: str | Path,
    workspace_root: str | Path,
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    workspace = Path(workspace_root).resolve()
    state = _load_object(run / "batch_regression_state.json")
    corpus_path = workspace / str(dict(state.get("corpus_ref") or {}).get("path") or "")
    corpus = _load_object(corpus_path)
    case_rows: list[dict[str, Any]] = []
    phase1_times: list[float] = []
    phase2_times: list[float] = []
    total_reviews = 0
    total_tracks = 0
    total_ocr_ok = 0
    phase1_execution_pass_count = 0
    total_phase1_geometry_issues = 0
    for row in list(state.get("cases") or []):
        case = dict(row)
        artifact_raw = str(case.get("artifact_root") or "").strip()
        artifact_root = (
            workspace / artifact_raw
            if artifact_raw
            else run / str(case.get("case_id") or "")
        )
        phase1_meta = _load_object(artifact_root / "phase1_meta.json")
        phase1_score = _load_object(artifact_root / "phase1_score.json")
        phase2_meta_path = artifact_root / "phase2_meta.json"
        phase2_meta = (
            _load_object(phase2_meta_path) if phase2_meta_path.is_file() else None
        )
        no_text_operator_approved = False
        if not bool(phase1_score.get("PASS")):
            try:
                load_no_text_authority(artifact_root)
            except NoTextPassthroughError:
                pass
            else:
                no_text_operator_approved = True
        geometry_status: str | None = None
        geometry_issue_count = 0
        geometry_review_path = artifact_root / "phase1_geometry_review.json"
        if not bool(phase1_score.get("PASS")) and geometry_review_path.is_file():
            geometry_review = _load_object(geometry_review_path)
            geometry_issue_count = len(list(geometry_review.get("issues") or []))
            try:
                geometry_status = str(
                    evaluate_phase1_geometry_operator_gate_safe(artifact_root).get(
                        "status"
                    )
                    or ""
                )
            except Phase1GeometryReviewError:
                geometry_status = "PHASE1_GEOMETRY_REVIEW_INVALID"
            if geometry_status != "WAITING_PHASE1_GEOMETRY_OPERATOR_REVIEW":
                geometry_issue_count = 0
        total_phase1_geometry_issues += geometry_issue_count
        stages = list(case.get("stages") or [])
        phase1_execution_pass = any(
            str(stage.get("stage") or "") == "phase1"
            and str(stage.get("status") or "") in {"PASS", "RESUMED", "REUSED_ACCEPTED_BASELINE"}
            for stage in stages
            if isinstance(stage, dict)
        )
        phase1_execution_pass_count += int(phase1_execution_pass)
        p1_elapsed = float(phase1_meta.get("elapsed_s") or 0.0)
        p2_elapsed = float((phase2_meta or {}).get("elapsed_s") or 0.0)
        review_required = int((phase2_meta or {}).get("review_required") or 0)
        tracks = int(
            (phase2_meta or {}).get("tracks") or phase1_score.get("tracks") or 0
        )
        ocr_ok = int((phase2_meta or {}).get("ocr_ok") or 0)
        decoded_frame_count = int(
            phase1_meta.get("n_scanned_frames")
            or phase1_meta.get("frame_count")
            or 0
        )
        container_frame_count = int(phase1_meta.get("frame_count") or 0)
        phase1_times.append(p1_elapsed)
        phase2_times.append(p2_elapsed)
        total_reviews += review_required
        total_tracks += tracks
        total_ocr_ok += ocr_ok
        case_rows.append(
            {
                "case_id": case.get("case_id"),
                "source_video_external_id": case.get("source_video_external_id"),
                "status": case.get("status"),
                "regression_scope": str(
                    case.get("regression_scope") or "FULL_E2E"
                ),
                "frame_count": decoded_frame_count,
                "duration_seconds": next(
                    (
                        float(dict(item.get("probe") or {}).get("duration_seconds") or 0.0)
                        for item in list(corpus.get("cases") or [])
                        if item.get("case_id") == case.get("case_id")
                    ),
                    0.0,
                ),
                "phase1": {
                    "execution_pass": phase1_execution_pass,
                    "pass": bool(phase1_score.get("PASS")),
                    "no_text_operator_approved": no_text_operator_approved,
                    "outcome": _phase1_outcome(
                        phase1_score, geometry_status=geometry_status
                    ),
                    "geometry_review_status": geometry_status,
                    "geometry_review_issue_count": geometry_issue_count,
                    "container_frame_count": container_frame_count,
                    "tracks": int(phase1_score.get("tracks") or 0),
                    "hardsubs": int(phase1_score.get("hardsubs") or 0),
                    "elapsed_seconds": p1_elapsed,
                    "frames_per_second": round(
                        decoded_frame_count / p1_elapsed, 3
                    )
                    if p1_elapsed > 0
                    else None,
                },
                "phase2": {
                    "execution_pass": phase2_meta is not None,
                    "skipped_reason": (
                        None
                        if phase2_meta is not None
                        else "PHASE1_GEOMETRY_REVIEW_REQUIRED"
                        if geometry_status
                        == "WAITING_PHASE1_GEOMETRY_OPERATOR_REVIEW"
                        else "PHASE1_NOT_ACCEPTED"
                    ),
                    "ocr_ok": ocr_ok,
                    "tracks": tracks,
                    "ocr_coverage_ratio": round(ocr_ok / max(1, tracks), 4),
                    "review_required": review_required,
                    "ready_for_phase3": bool(
                        (phase2_meta or {}).get("ready_for_phase3")
                    ),
                    "elapsed_seconds": p2_elapsed,
                    "model_version": (phase2_meta or {}).get("model_version"),
                },
            }
        )
    incidents_path = run / "regression_incidents.json"
    incidents = (
        list(_load_object(incidents_path).get("incidents") or [])
        if incidents_path.is_file()
        else []
    )
    no_text_review_case_count = sum(
        str(row.get("status") or "") == "WAITING_NO_TEXT_OPERATOR_REVIEW"
        for row in case_rows
    )
    no_text_approved_case_count = sum(
        bool(dict(row.get("phase1") or {}).get("no_text_operator_approved"))
        for row in case_rows
    )
    geometry_review_case_count = sum(
        row["phase1"]["geometry_review_status"]
        == "WAITING_PHASE1_GEOMETRY_OPERATOR_REVIEW"
        for row in case_rows
    )
    geometry_approved_case_count = sum(
        row["phase1"]["geometry_review_status"]
        == "PHASE1_GEOMETRY_OPERATOR_APPROVED"
        for row in case_rows
    )
    case_count = len(case_rows)
    phase3_ready_count = sum(
        row["phase2"]["ready_for_phase3"] for row in case_rows
    )
    operator_review_object_count = total_reviews + total_phase1_geometry_issues
    scope_manifest_ref = None
    scope_manifest_path = run / "regression_scope_manifest.json"
    if scope_manifest_path.is_file():
        scope_manifest = _load_object(scope_manifest_path)
        claimed_scope_hash = str(
            scope_manifest.get("scope_manifest_sha256") or ""
        )
        unsigned_scope = dict(scope_manifest)
        unsigned_scope.pop("scope_manifest_sha256", None)
        if len(claimed_scope_hash) != 64 or _sha256_json(unsigned_scope) != claimed_scope_hash:
            raise PipelineRegressionReportError(
                "Regression scope manifest self-hash is invalid"
            )
        scope_manifest_ref = {
            "path": scope_manifest_path.relative_to(run).as_posix(),
            "file_sha256": _sha256_file(scope_manifest_path),
            "scope_manifest_sha256": claimed_scope_hash,
        }
    report = {
        "schema_version": "pipeline_regression_report_v1",
        "status": (
            "PASS_TO_OPERATOR_GATES"
            if int(state.get("failed_count") or 0) == 0
            else "FAILED"
        ),
        "run_sha256": state.get("run_sha256"),
        "corpus_sha256": corpus.get("corpus_sha256"),
        "case_count": case_count,
        "operator_touch_count": int(state.get("operator_touch_count") or 0),
        "full_e2e_scope_case_count": sum(
            row["regression_scope"] == "FULL_E2E" for row in case_rows
        ),
        "visual_localization_scope_case_count": sum(
            row["regression_scope"] == "VISUAL_LOCALIZATION_ONLY"
            for row in case_rows
        ),
        "scope_manifest_ref": scope_manifest_ref,
        "phase1_execution_pass_count": phase1_execution_pass_count,
        "phase1_pass_count": sum(row["phase1"]["pass"] for row in case_rows),
        "phase1_accepted_count": sum(
            bool(row["phase1"]["pass"])
            or bool(row["phase1"].get("no_text_operator_approved"))
            or row["phase1"]["geometry_review_status"]
            == "PHASE1_GEOMETRY_OPERATOR_APPROVED"
            for row in case_rows
        ),
        "phase2_execution_pass_count": sum(
            row["phase2"]["execution_pass"] for row in case_rows
        ),
        "phase3_ready_count": phase3_ready_count,
        "operator_gate_case_count": sum(
            row["phase2"]["review_required"] > 0 for row in case_rows
        ),
        "operator_review_object_count": operator_review_object_count,
        "phase1_geometry_review_issue_count": total_phase1_geometry_issues,
        "phase1_geometry_review_case_count": geometry_review_case_count,
        "phase1_geometry_approved_case_count": geometry_approved_case_count,
        "no_text_review_case_count": no_text_review_case_count,
        "no_text_approved_case_count": no_text_approved_case_count,
        "ocr_coverage_ratio": round(total_ocr_ok / max(1, total_tracks), 4),
        "timing": {
            "phase1_total_seconds": round(sum(phase1_times), 3),
            "phase1_median_seconds": round(median(phase1_times), 3),
            "phase1_max_seconds": round(max(phase1_times, default=0.0), 3),
            "phase2_total_seconds": round(sum(phase2_times), 3),
            "phase2_median_seconds": round(median(phase2_times), 3),
            "phase2_max_seconds": round(max(phase2_times, default=0.0), 3),
        },
        "corpus_gaps": corpus.get("real_video_gaps"),
        "incidents": incidents,
        "open_incident_count": sum(
            str(item.get("status") or "").upper() != "RESOLVED"
            for item in incidents
            if isinstance(item, dict)
        ),
        "open_incidents": [
            item
            for item in incidents
            if isinstance(item, dict)
            and str(item.get("status") or "").upper() != "RESOLVED"
        ],
        "resolved_incidents": [
            item
            for item in incidents
            if isinstance(item, dict)
            and str(item.get("status") or "").upper() == "RESOLVED"
        ],
        "cases": case_rows,
        "conclusion": (
            "Automation stopped at the Phase 1 quality gate for one or more cases; "
            "Phase 2 was not executed for those cases and no corpus closure is claimed."
            if int(state.get("failed_count") or 0) > 0
            else "Phase 1 geometry candidates are waiting for hash-bound operator "
            "review. This is a correctness checkpoint, not an execution failure, "
            "and Phase 2 remains blocked for those cases."
            if geometry_review_case_count > 0
            else "Phase 1 no-text candidates are waiting for exact operator review. "
            "Phase 2 is intentionally not applicable until that review is resolved, "
            "and no corpus closure is claimed."
            if no_text_review_case_count > 0
            else "Phase 2 OCR review is approved and every selected case is ready "
            "for Phase 3. Full end-to-end closure is not claimed yet because "
            "translation, TTS, render, output QA, and declared corpus gaps remain."
            if (
                phase3_ready_count == case_count
                and operator_review_object_count == 0
                and geometry_review_case_count == 0
            )
            else "Operator-approved no-text controls bypass OCR by contract; text-bearing "
            "cases continue through local OCR. Full corpus closure still depends on all "
            "declared gaps and operator gates."
            if no_text_approved_case_count > 0
            else "Automation is healthy through local OCR. Full end-to-end closure is "
            "not claimed because exact OCR operator review or another declared "
            "operator/corpus gate is still open."
        ),
    }
    report["report_sha256"] = _sha256_json(report)
    return report


def write_regression_report(
    *,
    run_root: str | Path,
    workspace_root: str | Path,
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    report = build_regression_report(run_root=run, workspace_root=workspace_root)
    _write_json_atomic(run / "pipeline_regression_report.json", report)
    lines = [
        "# Pipeline Regression Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Cases: `{report['case_count']}`",
        f"- Phase 1 execution PASS: `{report['phase1_execution_pass_count']}/{report['case_count']}`",
        f"- Phase 1 PASS: `{report['phase1_pass_count']}/{report['case_count']}`",
        f"- Phase 1 accepted (including operator-approved NO_TEXT): `{report['phase1_accepted_count']}/{report['case_count']}`",
        f"- Phase 2 execution PASS: `{report['phase2_execution_pass_count']}/{report['case_count']}`",
        f"- Ready for Phase 3: `{report['phase3_ready_count']}/{report['case_count']}`",
        f"- OCR objects requiring operator review: `{report['operator_review_object_count']}`",
        f"- Phase 1 geometry issues requiring review: `{report['phase1_geometry_review_issue_count']}`",
        f"- OCR non-empty coverage: `{report['ocr_coverage_ratio']}`",
        f"- Report SHA-256: `{report['report_sha256']}`",
        "",
        "## Cases",
        "",
        "| Case | Scope | Frames | P1 outcome | P1 tracks | P1 sec | P2 OCR | Review | State |",
        "|---|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for case in report["cases"]:
        lines.append(
            "| {case} | `{scope}` | {frames} | `{outcome}` | {tracks} | {p1:.2f} | {ocr}/{total} | {review} | `{status}` |".format(
                case=case["source_video_external_id"],
                scope=case["regression_scope"],
                frames=case["frame_count"],
                outcome=case["phase1"]["outcome"],
                tracks=case["phase1"]["tracks"],
                p1=case["phase1"]["elapsed_seconds"],
                ocr=case["phase2"]["ocr_ok"],
                total=case["phase2"]["tracks"],
                review=case["phase2"]["review_required"],
                status=case["status"],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            report["conclusion"],
            "",
            "Operator review is a required correctness gate, not an execution failure.",
        ]
    )
    _write_text_atomic(run / "PIPELINE_REGRESSION_REPORT.md", "\n".join(lines) + "\n")
    return report
