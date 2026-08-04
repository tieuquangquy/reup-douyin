from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.apply_phase1_geometry_review_proposal import apply_proposal
from src.media_pipeline.frame_sampling.phase1_geometry_review import (
    evaluate_phase1_geometry_operator_gate,
    prepare_phase1_geometry_review,
)


def _sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def test_applies_explicit_geometry_proposal_once_without_ocr_authority() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        case = run / "case_1"
        (case / "qa").mkdir(parents=True)
        (case / "crops").mkdir()
        (case / "frames").mkdir()
        (case / "source.mp4").write_bytes(b"source")
        (case / "crops" / "sub_01.jpg").write_bytes(b"crop")
        (case / "frames" / "sub_01.jpg").write_bytes(b"frame")
        track = {
            "text_id": "sub_01",
            "start_frame": 1,
            "end_frame": 5,
            "box_coords": [1.0, 90.0, 220.0, 116.0],
            "best_frame_index": 3,
            "hit_count": 2,
            "crop_path": "crops/sub_01.jpg",
            "best_keyframe_path": "frames/sub_01.jpg",
        }
        (case / "master_timeline.json").write_text(
            json.dumps([track]), encoding="utf-8"
        )
        (case / "phase1_score.json").write_text(
            json.dumps(
                {
                    "PASS": False,
                    "tracks": 1,
                    "frame_size": [240, 120],
                    "checks": {
                        "has_tracks": True,
                        "has_quality_report": True,
                        "has_text_frame_coverage": True,
                        "no_uncertain_tracks": False,
                        "crops_complete": True,
                        "keyframes_complete": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        (case / "text_frame_coverage.json").write_text(
            json.dumps({"frame_width": 240, "frame_height": 120}),
            encoding="utf-8",
        )
        (case / "qa" / "quality_report.json").write_text(
            json.dumps(
                {
                    "uncertain_tracks": 1,
                    "review_queue": [
                        {
                            "text_id": "sub_01",
                            "boundary_evidence": {
                                "status": "uncertain",
                                "reasons": ["frame_edge_box_review"],
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (case / "phase1_meta.json").write_text(
            json.dumps({"video": "source.mp4"}), encoding="utf-8"
        )
        review = prepare_phase1_geometry_review(case)
        proposal = {
            "schema_version": "phase1_geometry_review_proposal_v1",
            "status": "PROPOSAL_READY_FOR_OPERATOR_REVIEW",
            "approval_token_required": "APPROVE_TEST",
            "ocr_approval_granted": False,
            "recipe_lock_granted": False,
            "cases": [
                {
                    "case_id": "case_1",
                    "review_ref": {"review_sha256": review["review_sha256"]},
                    "decisions": [
                        {
                            "issue_id": review["issues"][0]["issue_id"],
                            "decision": "APPROVE_GEOMETRY",
                        }
                    ],
                }
            ],
        }
        proposal["proposal_sha256"] = _sha(proposal)
        (run / "phase1_geometry_review_proposal.json").write_text(
            json.dumps(proposal), encoding="utf-8"
        )

        first = apply_proposal(
            run_root=run,
            approval_token="APPROVE_TEST",
            operator_id="operator-1",
        )
        second = apply_proposal(
            run_root=run,
            approval_token="APPROVE_TEST",
            operator_id="operator-1",
        )

        assert first == second
        assert first["authority"]["geometry_only"] is True
        assert first["authority"]["ocr_approval_granted"] is False
        assert (
            evaluate_phase1_geometry_operator_gate(case)["status"]
            == "PHASE1_GEOMETRY_OPERATOR_APPROVED"
        )

