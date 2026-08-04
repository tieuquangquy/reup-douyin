from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.build_phase4_batch_preflight_index import (
    build_batch_preflight_index,
    render_markdown,
)


def _hash_json(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _case(run: Path, case_id: str, *, proposal: bool) -> None:
    root = run / case_id
    (root / "qa").mkdir(parents=True)
    handoff = root / "phase3_render_handoff.json"
    handoff.write_text("{}", encoding="utf-8")
    meta = {
        "status": "PHASE4_PREFLIGHT_BLOCKED",
        "final_render_gate": "BLOCKED_VISUAL_RESIDUAL_CJK",
        "phase3_render_handoff_sha256": hashlib.sha256(
            handoff.read_bytes()
        ).hexdigest(),
        "counts": {"render_tracks": 2},
        "typography": {"text_overflow": 0, "collision_events": 0},
        "residual_cjk": {
            "complete": True,
            "detections": [{"text": "午餐"}],
            "raw_detections": [{"text": "午餐"}],
            "temporal_false_positives": [],
        },
    }
    meta_path = root / "phase4_preflight_meta.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    (root / "qa" / "phase4_preflight_report.json").write_text(
        json.dumps({"blocked_reasons": ["residual_cjk:1"]}), encoding="utf-8"
    )
    if proposal:
        artifact = {
            "status": "PROPOSAL_READY_FOR_OPERATOR_REVIEW",
            "operator_approval_written": False,
            "counts": {"proposed_occurrences": 1},
        }
        artifact["proposal_sha256"] = _hash_json(artifact)
        (root / "phase2_residual_remediation_proposal.json").write_text(
            json.dumps(artifact), encoding="utf-8"
        )
    else:
        artifact = {
            "status": "PROPOSAL_BLOCKED_OPERATOR_TRIAGE_REQUIRED",
            "reason": "ambiguous source OCR",
            "phase4_preflight_meta_ref": {
                "sha256": hashlib.sha256(meta_path.read_bytes()).hexdigest()
            },
        }
        artifact["attempt_sha256"] = _hash_json(artifact)
        (root / "phase2_residual_remediation_proposal_attempt.json").write_text(
            json.dumps(artifact), encoding="utf-8"
        )


def test_builds_batch_index_for_proposal_and_triage_cases() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        _case(run, "proposal_case", proposal=True)
        _case(run, "triage_case", proposal=False)
        (run / "batch_regression_state.json").write_text(
            json.dumps(
                {
                    "run_sha256": "a" * 64,
                    "cases": [
                        {
                            "case_id": "proposal_case",
                            "status": "WAITING_RESIDUAL_REMEDIATION_OPERATOR_REVIEW",
                        },
                        {
                            "case_id": "triage_case",
                            "status": "WAITING_RESIDUAL_CJK_OPERATOR_TRIAGE",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        payload = build_batch_preflight_index(run_root=run)

        assert payload["status"] == "PHASE4_PREFLIGHT_OPERATOR_TRIAGE_REQUIRED"
        assert payload["counts"]["proposal_ready"] == 1
        assert payload["counts"]["triage_required"] == 1
        assert payload["counts"]["residual_detections"] == 2
        assert "proposal_case" in render_markdown(payload)
        assert "triage_case" in render_markdown(payload)


def test_ready_case_ignores_stale_residual_attempt() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        _case(run, "ready_case", proposal=False)
        root = run / "ready_case"
        meta_path = root / "phase4_preflight_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.update(
            {
                "status": "READY_FOR_PHASE4",
                "final_render_gate": "BLOCKED_AUDIO_AUTHORITY",
                "residual_cjk": {
                    "complete": True,
                    "detections": [],
                    "raw_detections": [],
                    "temporal_false_positives": [],
                },
            }
        )
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        (root / "qa" / "phase4_preflight_report.json").write_text(
            json.dumps({"blocked_reasons": []}), encoding="utf-8"
        )
        (run / "batch_regression_state.json").write_text(
            json.dumps(
                {
                    "run_sha256": "a" * 64,
                    "cases": [
                        {
                            "case_id": "ready_case",
                            "status": "READY_FOR_VISUAL_PREVIEW",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        payload = build_batch_preflight_index(run_root=run)

        assert payload["status"] == "READY_FOR_PHASE4"
        assert payload["counts"]["ready"] == 1
        assert payload["counts"]["triage_required"] == 0
        assert payload["cases"][0]["review_result"] == "READY"
        assert "triage_ref" not in payload["cases"][0]
