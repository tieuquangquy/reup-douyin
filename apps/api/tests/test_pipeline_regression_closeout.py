from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.services.pipeline_regression_closeout import (
    PipelineRegressionCloseoutError,
    build_pipeline_regression_closeout,
    write_pipeline_regression_closeout,
)


def _sha_json(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _self_hashed(payload: dict, field: str) -> dict:
    result = dict(payload)
    result[field] = _sha_json(result)
    return result


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(workspace: Path) -> Path:
    run = workspace / "apps" / "api" / "regression_runs" / "run_v22_1"
    case = run / "case_01"
    case.mkdir(parents=True)
    corpus_path = workspace / "docs" / "corpus.json"
    corpus = _self_hashed(
        {
            "schema_version": "pipeline_regression_corpus_v1",
            "real_video_gaps": {"orientation": ["portrait"]},
        },
        "corpus_sha256",
    )
    _write(corpus_path, corpus)
    state = {
        "schema_version": "pipeline_batch_regression_v1",
        "status": "PASS_TO_OPERATOR_GATES",
        "failed_count": 0,
        "operator_touch_count": 0,
        "corpus_ref": {
            "path": "docs/corpus.json",
            "sha256": _sha_file(corpus_path),
            "corpus_sha256": corpus["corpus_sha256"],
        },
        "cases": [
            {
                "case_id": "case_01",
                "artifact_root": "apps/api/regression_runs/run_v22_1/case_01",
                "status": "READY_FOR_VISUAL_PREVIEW",
            }
        ],
    }
    state["run_sha256"] = _sha_json(state)
    state_path = run / "batch_regression_state.json"
    _write(state_path, state)
    report = _self_hashed(
        {
            "schema_version": "pipeline_regression_report_v1",
            "status": "PASS_TO_OPERATOR_GATES",
            "run_sha256": state["run_sha256"],
            "corpus_sha256": corpus["corpus_sha256"],
            "case_count": 1,
            "phase1_accepted_count": 1,
            "phase2_execution_pass_count": 1,
            "phase3_ready_count": 1,
            "operator_review_object_count": 0,
            "open_incident_count": 0,
            "ocr_coverage_ratio": 1.0,
            "timing": {"phase1_total_seconds": 1.0, "phase2_total_seconds": 2.0},
            "cases": [
                {
                    "case_id": "case_01",
                    "source_video_external_id": "video_01",
                    "regression_scope": "FULL_E2E",
                    "phase2": {
                        "status": "OCR_APPROVED",
                        "model_version": "ppocr",
                        "ocr_ok": 1,
                        "tracks": 1,
                        "review_required": 0,
                    },
                }
            ],
        },
        "report_sha256",
    )
    _write(run / "pipeline_regression_report.json", report)
    _write(
        case / "phase2_meta.json",
        {"status": "OCR_APPROVED", "ready_for_phase3": True},
    )
    _write(case / "phase3_closeout.json", {"status": "PHASE3_CLOSED"})
    preflight_meta = case / "phase4_preflight_meta.json"
    preflight_report = case / "qa" / "phase4_preflight_report.json"
    _write(preflight_meta, {"status": "READY_FOR_PHASE4"})
    _write(preflight_report, {"status": "READY_FOR_PHASE4"})
    index = {
        "schema_version": "phase4_batch_preflight_index_v1",
        "status": "READY_FOR_PHASE4",
        "counts": {
            "cases": 1,
            "ready": 1,
            "blocked": 0,
            "residual_detections": 0,
            "raw_residual_detections": 0,
            "temporal_false_positives": 0,
            "collision_events": 0,
            "proposal_ready": 0,
            "triage_required": 0,
        },
        "batch_state_ref": {
            "path": state_path.name,
            "sha256": _sha_file(state_path),
            "run_sha256": state["run_sha256"],
        },
        "cases": [
            {
                "case_id": "case_01",
                "preflight_status": "READY_FOR_PHASE4",
                "final_render_gate": "BLOCKED_AUDIO_AUTHORITY",
                "render_counts": {"render_tracks": 1, "content_objects": 1},
                "typography": {
                    "text_overflow": 0,
                    "clamp_required": 0,
                    "collision_events": 0,
                },
                "blocked_reasons": [],
                "residual_cjk": {
                    "complete": True,
                    "detections": 0,
                    "raw_detections": 0,
                    "temporal_false_positives": 0,
                },
                "review_result": "READY",
                "preflight_meta_ref": {
                    "path": preflight_meta.relative_to(run).as_posix(),
                    "sha256": _sha_file(preflight_meta),
                },
                "preflight_report_ref": {
                    "path": preflight_report.relative_to(run).as_posix(),
                    "sha256": _sha_file(preflight_report),
                },
            }
        ],
    }
    index["batch_preflight_sha256"] = _sha_json(index)
    _write(run / "phase4_batch_preflight_index.json", index)
    return run


def test_writes_idempotent_versioned_phase4_closeout() -> None:
    with TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        run = _fixture(workspace)

        first = write_pipeline_regression_closeout(
            run_root=run, workspace_root=workspace
        )
        second = write_pipeline_regression_closeout(
            run_root=run, workspace_root=workspace
        )

        assert first["status"] == "PASS_CONTROLLED_PHASE4_PREFLIGHT"
        assert first["case_count"] == 1
        assert first["claims"][
            "controlled_pilot_ready_through_phase4_preflight"
        ]
        assert not first["claims"]["full_batch_end_to_end_pass"]
        assert first["closeout_sha256"] == second["closeout_sha256"]
        assert (
            run / f"pipeline_regression_closeout_{first['closeout_sha256']}.json"
        ).is_file()
        assert (run / "PIPELINE_REGRESSION_CLOSEOUT.md").is_file()


def test_rejects_stale_case_preflight_evidence() -> None:
    with TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        run = _fixture(workspace)
        (run / "case_01" / "phase4_preflight_meta.json").write_text(
            '{"status":"tampered"}', encoding="utf-8"
        )

        with pytest.raises(
            PipelineRegressionCloseoutError, match="preflight meta reference is stale"
        ):
            build_pipeline_regression_closeout(
                run_root=run, workspace_root=workspace
            )
