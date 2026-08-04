from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.materialize_phase2_residual_remediation import verify_remediation
from scripts.recover_phase2_residual_remediation import reconstruct_remediation


def test_reconstructs_only_existing_phase2_operator_authority() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        master = root / "master_timeline.json"
        master.write_text("[]", encoding="utf-8")
        master_sha = hashlib.sha256(master.read_bytes()).hexdigest()
        legacy = root / "phase2_residual_remediation.json"
        legacy.write_text("overwritten", encoding="utf-8")
        timeline = {
            "phase1_ref": {
                "path": master.name,
                "sha256": master_sha,
            },
            "residual_remediation_ref": {
                "path": legacy.name,
                "sha256": "a" * 64,
                "remediation_sha256": "b" * 64,
            },
            "supplemental_occurrences": [
                {
                    "text_id": "p2r_old",
                    "start_frame": 0,
                    "end_frame": 3,
                    "box_coords": [1, 2, 3, 4],
                    "ocr_text": "old zh",
                    "ocr_source": "crop",
                    "ocr_frame": 0,
                }
            ],
            "track_enrichments": [
                {"text_id": "p2r_old", "content_id": "ocr_content_001"}
            ],
            "content_objects": [
                {
                    "content_id": "ocr_content_001",
                    "ocr_text_approved": "old zh",
                    "vi_text_approved": "old vi",
                    "review_status": "OCR_APPROVED",
                    "localization": {"mode": "llm_translate"},
                    "operator_review": {
                        "decision": "APPROVE",
                        "reviewer": "operator",
                        "reviewed_at": "2026-07-29T12:00:00+00:00",
                        "review_input_sha256": "c" * 64,
                        "stale": False,
                    },
                }
            ],
        }
        timeline_path = root / "phase2_ocr_timeline.json"
        timeline_path.write_text(json.dumps(timeline), encoding="utf-8")

        with patch(
            "scripts.recover_phase2_residual_remediation."
            "_capture_translation_authority",
            return_value={"source_refs": {}, "rows": [{"content_id": "old"}]},
        ):
            recovered = reconstruct_remediation(
                root_dir=root,
                phase2_timeline_path=timeline_path,
            )

        assert verify_remediation(recovered)
        assert recovered["generation"] == 1
        assert recovered["recovery"]["creates_new_operator_decisions"] is False
        row = recovered["approved_occurrences"][0]
        assert row["occurrence"]["text_id"] == "p2r_old"
        assert "ocr_text" not in row["occurrence"]
        assert row["operator_review"]["reviewer"] == "operator"
