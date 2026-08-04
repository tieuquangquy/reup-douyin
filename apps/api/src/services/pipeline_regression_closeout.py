"""Build an immutable closeout for a batch accepted through Phase 4 preflight."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


CLOSEOUT_SCHEMA_VERSION = "pipeline_regression_closeout_v1"
CLOSEOUT_PASS_STATUS = "PASS_CONTROLLED_PHASE4_PREFLIGHT"


class PipelineRegressionCloseoutError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
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
        raise PipelineRegressionCloseoutError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise PipelineRegressionCloseoutError(
            f"{path.name} must contain an object"
        )
    return payload


def _load_self_hashed(path: Path, field: str, label: str) -> dict[str, Any]:
    payload = _load_object(path)
    unsigned = dict(payload)
    claimed = str(unsigned.pop(field, "") or "")
    if len(claimed) != 64 or claimed != _sha256_json(unsigned):
        raise PipelineRegressionCloseoutError(f"{label} self-hash is invalid")
    return payload


def _verified_ref(root: Path, ref: Mapping[str, Any], label: str) -> Path:
    relative = str(ref.get("path") or "")
    path = (root / relative).resolve()
    if (
        not relative
        or not path.is_relative_to(root)
        or not path.is_file()
        or _sha256_file(path) != str(ref.get("sha256") or "")
    ):
        raise PipelineRegressionCloseoutError(f"{label} reference is stale")
    return path


def _artifact_root(
    *, workspace: Path, run: Path, state_case: Mapping[str, Any], case_id: str
) -> Path:
    relative = str(state_case.get("artifact_root") or "")
    root = (workspace / relative).resolve()
    if (
        not relative
        or not root.is_relative_to(workspace)
        or not root.is_dir()
        or root.name != case_id
        or root.parent != run
    ):
        raise PipelineRegressionCloseoutError(
            f"Invalid artifact root for {case_id}"
        )
    return root


def _optional_remediation_summary(root: Path) -> dict[str, Any]:
    meta_path = root / "phase2_meta.json"
    meta = _load_object(meta_path)
    ref = dict(meta.get("residual_remediation_ref") or {})
    if not ref:
        return {
            "phase2_meta_ref": {
                "path": meta_path.name,
                "sha256": _sha256_file(meta_path),
            },
            "remediation_ref": None,
            "approved_occurrences": 0,
            "approved_geometry_overrides": 0,
        }
    remediation_path = _verified_ref(root, ref, "Residual remediation")
    remediation = _load_object(remediation_path)
    unsigned = dict(remediation)
    claimed = str(unsigned.pop("remediation_sha256", "") or "")
    if (
        claimed != str(ref.get("remediation_sha256") or "")
        or len(claimed) != 64
        or claimed != _sha256_json(unsigned)
    ):
        raise PipelineRegressionCloseoutError(
            f"Residual remediation self-hash is invalid for {root.name}"
        )
    return {
        "phase2_meta_ref": {
            "path": meta_path.name,
            "sha256": _sha256_file(meta_path),
        },
        "remediation_ref": {
            "path": remediation_path.name,
            "sha256": _sha256_file(remediation_path),
            "remediation_sha256": claimed,
        },
        "approved_occurrences": len(
            list(remediation.get("approved_occurrences") or [])
        ),
        "approved_geometry_overrides": len(
            list(remediation.get("approved_geometry_overrides") or [])
        ),
    }


def build_pipeline_regression_closeout(
    *, run_root: str | Path, workspace_root: str | Path
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    workspace = Path(workspace_root).resolve()
    if not run.is_dir() or not run.is_relative_to(workspace):
        raise PipelineRegressionCloseoutError("Run root is outside the workspace")

    state_path = run / "batch_regression_state.json"
    report_path = run / "pipeline_regression_report.json"
    preflight_path = run / "phase4_batch_preflight_index.json"
    state = _load_self_hashed(state_path, "run_sha256", "Batch state")
    report = _load_self_hashed(report_path, "report_sha256", "Regression report")
    preflight = _load_self_hashed(
        preflight_path, "batch_preflight_sha256", "Phase 4 batch preflight"
    )

    state_sha = str(state.get("run_sha256") or "")
    report_sha = str(report.get("report_sha256") or "")
    case_count = int(report.get("case_count") or 0)
    preflight_counts = dict(preflight.get("counts") or {})
    preflight_state_ref = dict(preflight.get("batch_state_ref") or {})
    pending_operator_gates = [
        "{case}:{status}".format(
            case=str(dict(row).get("case_id") or "unknown"),
            status=str(dict(row).get("status") or "unknown"),
        )
        for row in list(state.get("cases") or [])
        if isinstance(row, Mapping) and bool(dict(row).get("operator_touch_required"))
    ]
    if pending_operator_gates:
        raise PipelineRegressionCloseoutError(
            "Batch still has pending operator gates: "
            + ", ".join(pending_operator_gates)
        )
    if (
        str(state.get("status") or "") != "PASS_TO_OPERATOR_GATES"
        or int(state.get("failed_count") or 0) != 0
        or int(state.get("operator_touch_count") or 0) != 0
        or str(report.get("status") or "") != "PASS_TO_OPERATOR_GATES"
        or str(report.get("run_sha256") or "") != state_sha
        or int(report.get("phase1_accepted_count") or 0) != case_count
        or int(report.get("phase2_execution_pass_count") or 0) != case_count
        or int(report.get("phase3_ready_count") or 0) != case_count
        or int(report.get("operator_review_object_count") or 0) != 0
        or int(report.get("open_incident_count") or 0) != 0
        or str(preflight.get("status") or "") != "READY_FOR_PHASE4"
        or int(preflight_counts.get("cases") or 0) != case_count
        or int(preflight_counts.get("ready") or 0) != case_count
        or int(preflight_counts.get("blocked") or 0) != 0
        or int(preflight_counts.get("residual_detections") or 0) != 0
        or int(preflight_counts.get("collision_events") or 0) != 0
        or int(preflight_counts.get("proposal_ready") or 0) != 0
        or int(preflight_counts.get("triage_required") or 0) != 0
        or str(preflight_state_ref.get("run_sha256") or "") != state_sha
        or str(preflight_state_ref.get("sha256") or "")
        != _sha256_file(state_path)
    ):
        raise PipelineRegressionCloseoutError(
            "Batch is not cleanly accepted through Phase 4 preflight"
        )

    corpus_ref = dict(state.get("corpus_ref") or {})
    corpus_path = (workspace / str(corpus_ref.get("path") or "")).resolve()
    if (
        not corpus_path.is_relative_to(workspace)
        or not corpus_path.is_file()
        or _sha256_file(corpus_path) != str(corpus_ref.get("sha256") or "")
    ):
        raise PipelineRegressionCloseoutError("Regression corpus reference is stale")
    corpus = _load_self_hashed(corpus_path, "corpus_sha256", "Regression corpus")
    if (
        str(corpus.get("corpus_sha256") or "")
        != str(corpus_ref.get("corpus_sha256") or "")
        or str(report.get("corpus_sha256") or "")
        != str(corpus_ref.get("corpus_sha256") or "")
    ):
        raise PipelineRegressionCloseoutError("Regression corpus identity drifted")

    state_cases = {
        str(row.get("case_id") or ""): dict(row)
        for row in list(state.get("cases") or [])
        if isinstance(row, Mapping) and str(row.get("case_id") or "")
    }
    report_cases = {
        str(row.get("case_id") or ""): dict(row)
        for row in list(report.get("cases") or [])
        if isinstance(row, Mapping) and str(row.get("case_id") or "")
    }
    preflight_cases = {
        str(row.get("case_id") or ""): dict(row)
        for row in list(preflight.get("cases") or [])
        if isinstance(row, Mapping) and str(row.get("case_id") or "")
    }
    expected_ids = set(state_cases)
    if (
        len(expected_ids) != case_count
        or set(report_cases) != expected_ids
        or set(preflight_cases) != expected_ids
    ):
        raise PipelineRegressionCloseoutError("Closeout case set drifted")

    case_rows: list[dict[str, Any]] = []
    total_occurrences = 0
    total_overrides = 0
    for case_id in sorted(expected_ids):
        state_case = state_cases[case_id]
        report_case = report_cases[case_id]
        preflight_case = preflight_cases[case_id]
        typography = dict(preflight_case.get("typography") or {})
        residual = dict(preflight_case.get("residual_cjk") or {})
        if (
            str(preflight_case.get("review_result") or "") != "READY"
            or str(preflight_case.get("preflight_status") or "")
            != "READY_FOR_PHASE4"
            or list(preflight_case.get("blocked_reasons") or [])
            or int(typography.get("text_overflow") or 0) != 0
            or int(typography.get("clamp_required") or 0) != 0
            or int(typography.get("collision_events") or 0) != 0
            or not bool(residual.get("complete"))
            or int(residual.get("detections") or 0) != 0
        ):
            raise PipelineRegressionCloseoutError(
                f"Phase 4 evidence is not clean for {case_id}"
            )
        _verified_ref(
            run,
            dict(preflight_case.get("preflight_meta_ref") or {}),
            f"{case_id} preflight meta",
        )
        _verified_ref(
            run,
            dict(preflight_case.get("preflight_report_ref") or {}),
            f"{case_id} preflight report",
        )
        artifact = _artifact_root(
            workspace=workspace,
            run=run,
            state_case=state_case,
            case_id=case_id,
        )
        phase3_path = artifact / "phase3_closeout.json"
        phase3 = _load_object(phase3_path)
        if str(phase3.get("status") or "") != "PHASE3_CLOSED":
            raise PipelineRegressionCloseoutError(
                f"Phase 3 closeout is not ready for {case_id}"
            )
        remediation = _optional_remediation_summary(artifact)
        total_occurrences += int(remediation["approved_occurrences"])
        total_overrides += int(remediation["approved_geometry_overrides"])
        case_rows.append(
            {
                "case_id": case_id,
                "source_video_external_id": report_case.get(
                    "source_video_external_id"
                ),
                "regression_scope": report_case.get("regression_scope"),
                "state_status": state_case.get("status"),
                "phase2": {
                    "status": dict(report_case.get("phase2") or {}).get(
                        "status"
                    ),
                    "model_version": dict(report_case.get("phase2") or {}).get(
                        "model_version"
                    ),
                    "ocr_ok": int(
                        dict(report_case.get("phase2") or {}).get("ocr_ok") or 0
                    ),
                    "tracks": int(
                        dict(report_case.get("phase2") or {}).get("tracks") or 0
                    ),
                    "review_required": int(
                        dict(report_case.get("phase2") or {}).get(
                            "review_required"
                        )
                        or 0
                    ),
                    **remediation,
                },
                "phase3_closeout_ref": {
                    "path": phase3_path.relative_to(run).as_posix(),
                    "sha256": _sha256_file(phase3_path),
                },
                "phase4": {
                    "status": preflight_case.get("preflight_status"),
                    "final_render_gate": preflight_case.get("final_render_gate"),
                    "render_counts": preflight_case.get("render_counts"),
                    "typography": typography,
                    "residual_cjk": residual,
                    "preflight_meta_ref": preflight_case.get(
                        "preflight_meta_ref"
                    ),
                    "preflight_report_ref": preflight_case.get(
                        "preflight_report_ref"
                    ),
                },
            }
        )

    closeout: dict[str, Any] = {
        "schema_version": CLOSEOUT_SCHEMA_VERSION,
        "status": CLOSEOUT_PASS_STATUS,
        "created_at": _now(),
        "run_id": run.name,
        "case_count": case_count,
        "counts": {
            "ready_for_phase4": case_count,
            "blocked": 0,
            "operator_touch_required": 0,
            "operator_review_objects": 0,
            "open_incidents": 0,
            "residual_cjk_detections": 0,
            "raw_residual_cjk_detections": int(
                preflight_counts.get("raw_residual_detections") or 0
            ),
            "temporal_false_positives": int(
                preflight_counts.get("temporal_false_positives") or 0
            ),
            "collision_events": 0,
            "approved_residual_occurrences": total_occurrences,
            "approved_geometry_overrides": total_overrides,
        },
        "timing": report.get("timing"),
        "ocr_coverage_ratio": report.get("ocr_coverage_ratio"),
        "recipe_inputs": {
            "phase1_extractor": "v58_candidate",
            "step": 1,
            "pad": 1,
            "authority_v3_6_full_duration": False,
            "phase2_provider": "local",
            "master_timeline_overwritten": False,
        },
        "evidence": {
            "corpus": {
                "path": corpus_path.relative_to(workspace).as_posix(),
                "sha256": _sha256_file(corpus_path),
                "corpus_sha256": corpus.get("corpus_sha256"),
            },
            "batch_state": {
                "path": state_path.relative_to(run).as_posix(),
                "sha256": _sha256_file(state_path),
                "run_sha256": state_sha,
            },
            "regression_report": {
                "path": report_path.relative_to(run).as_posix(),
                "sha256": _sha256_file(report_path),
                "report_sha256": report_sha,
            },
            "phase4_batch_preflight": {
                "path": preflight_path.relative_to(run).as_posix(),
                "sha256": _sha256_file(preflight_path),
                "batch_preflight_sha256": preflight.get(
                    "batch_preflight_sha256"
                ),
            },
        },
        "cases": case_rows,
        "claims": {
            "controlled_pilot_ready_through_phase4_preflight": True,
            "audio_authority_approved": False,
            "final_render_executed": False,
            "full_batch_end_to_end_pass": False,
            "universal_video_support": False,
            "controlled_pilot_only": True,
        },
        "next_boundary": "AUDIO_AUTHORITY_THEN_FINAL_RENDER_OUTPUT_QA",
    }
    closeout["closeout_sha256"] = _sha256_json(closeout)
    return closeout


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def write_pipeline_regression_closeout(
    *, run_root: str | Path, workspace_root: str | Path
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    current_path = run / "pipeline_regression_closeout.json"
    if current_path.is_file():
        current = _load_self_hashed(
            current_path, "closeout_sha256", "Current regression closeout"
        )
        evidence = dict(current.get("evidence") or {})
        state_ref = dict(evidence.get("batch_state") or {})
        report_ref = dict(evidence.get("regression_report") or {})
        preflight_ref = dict(evidence.get("phase4_batch_preflight") or {})
        if (
            str(state_ref.get("sha256") or "")
            == _sha256_file(run / "batch_regression_state.json")
            and str(report_ref.get("sha256") or "")
            == _sha256_file(run / "pipeline_regression_report.json")
            and str(preflight_ref.get("sha256") or "")
            == _sha256_file(run / "phase4_batch_preflight_index.json")
        ):
            refs_current = True
            for raw_case in list(current.get("cases") or []):
                case = dict(raw_case)
                phase4 = dict(case.get("phase4") or {})
                try:
                    _verified_ref(
                        run,
                        dict(phase4.get("preflight_meta_ref") or {}),
                        "Current preflight meta",
                    )
                    _verified_ref(
                        run,
                        dict(phase4.get("preflight_report_ref") or {}),
                        "Current preflight report",
                    )
                except PipelineRegressionCloseoutError:
                    refs_current = False
                    break
            if refs_current:
                return current
    closeout = build_pipeline_regression_closeout(
        run_root=run, workspace_root=workspace_root
    )
    versioned_path = run / (
        f"pipeline_regression_closeout_{closeout['closeout_sha256']}.json"
    )
    if versioned_path.is_file():
        existing = _load_self_hashed(
            versioned_path, "closeout_sha256", "Versioned regression closeout"
        )
        if existing != closeout:
            raise PipelineRegressionCloseoutError(
                "Versioned regression closeout conflicts with current evidence"
            )
    else:
        _write_json_atomic(versioned_path, closeout)
    _write_json_atomic(current_path, closeout)
    lines = [
        "# Pipeline Regression Closeout",
        "",
        f"- Status: `{closeout['status']}`",
        f"- Run: `{closeout['run_id']}`",
        f"- Cases READY_FOR_PHASE4: `{closeout['case_count']}/{closeout['case_count']}`",
        f"- Residual CJK: `{closeout['counts']['residual_cjk_detections']}`",
        f"- Collision events: `{closeout['counts']['collision_events']}`",
        f"- Closeout SHA-256: `{closeout['closeout_sha256']}`",
        "",
        "| Case | Phase 2 | OCR | Phase 4 | Residual | Collision | Audio gate |",
        "|---|---|---:|---|---:|---:|---|",
    ]
    for case in closeout["cases"]:
        phase2 = dict(case.get("phase2") or {})
        phase4 = dict(case.get("phase4") or {})
        residual = dict(phase4.get("residual_cjk") or {})
        typography = dict(phase4.get("typography") or {})
        lines.append(
            "| `{case}` | `{p2}` | {ocr}/{tracks} | `{p4}` | {residual} | "
            "{collision} | `{audio}` |".format(
                case=case.get("case_id"),
                p2=phase2.get("status"),
                ocr=phase2.get("ocr_ok"),
                tracks=phase2.get("tracks"),
                p4=phase4.get("status"),
                residual=residual.get("detections"),
                collision=typography.get("collision_events"),
                audio=phase4.get("final_render_gate"),
            )
        )
    lines.extend(
        [
            "",
            "Closeout này khóa boundary Phase 4 preflight. Nó không tuyên bố audio authority, final render, DB handoff, E2E hoặc universal support.",
            "",
        ]
    )
    _write_text_atomic(run / "PIPELINE_REGRESSION_CLOSEOUT.md", "\n".join(lines))
    return closeout
