from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np

from scripts.build_phase2_batch_review_proposal import (
    build_batch_review_proposal,
    render_batch_markdown,
    render_review_index,
)


def test_builds_queue_bound_batch_without_recording_approval() -> None:
    with TemporaryDirectory() as tmp:
        run_root = Path(tmp)
        state_path = run_root / "batch_regression_state.json"
        state_path.write_text(json.dumps({"status": "RUNNING"}), encoding="utf-8")
        case_root = run_root / "local_case"
        (case_root / "crops").mkdir(parents=True)
        cv2.imwrite(
            str(case_root / "crops" / "sub_01.jpg"),
            np.full((40, 120, 3), 180, dtype=np.uint8),
        )
        (case_root / "phase2_ocr_timeline.json").write_text(
            json.dumps({"content_objects": []}), encoding="utf-8"
        )
        (case_root / "phase2_approvals.json").write_text(
            json.dumps({"approvals": []}), encoding="utf-8"
        )
        queue = {
            "phase1_ref": {"path": "master_timeline.json", "sha256": "a" * 64},
            "content_objects": [
                {
                    "content_id": "ocr_content_001",
                    "geometry_refs": ["sub_01"],
                    "ocr_text_candidate": "wr0ng",
                    "review_input_sha256": "b" * 64,
                    "review_assets": [
                        {"text_id": "sub_01", "crop_path": "crops/sub_01.jpg"}
                    ],
                }
            ],
        }
        queue_path = case_root / "phase2_review_queue.json"
        queue_path.write_text(json.dumps(queue), encoding="utf-8")
        manifest = {
            "schema_version": "phase2_batch_review_recommendations_v1",
            "batch_state_ref": {
                "path": state_path.name,
                "sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(),
            },
            "cases": {
                "local_case": {
                    "review_queue_sha256": hashlib.sha256(
                        queue_path.read_bytes()
                    ).hexdigest(),
                    "recommendations": {
                        "ocr_content_001": {
                            "decision": "EDIT",
                            "text": "wrong",
                            "confidence": "high",
                            "reason": "visible crop",
                        }
                    },
                }
            },
        }
        manifest_path = run_root / "recommendations.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = build_batch_review_proposal(
            run_root=run_root,
            recommendations_path=manifest_path,
            generated_at="2026-07-29T00:00:00+00:00",
        )

        assert result["status"] == "OPERATOR_APPROVAL_REQUIRED"
        assert result["counts"]["proposed_edit"] == 1
        assert result["non_authoritative"] is True
        assert not (case_root / "phase2_operator_review_audit.json").exists()
        assert "ocr_content_001" in render_batch_markdown(result)
        assert "local_case" in render_review_index(result)
