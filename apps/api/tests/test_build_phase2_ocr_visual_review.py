from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np

from scripts.build_phase2_ocr_visual_review import build_visual_review


def _sha_json(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def test_builds_hash_bound_visual_review_with_empty_candidates_first() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "crops").mkdir()
        for text_id in ("sub_01", "sub_02"):
            cv2.imwrite(
                str(root / "crops" / f"{text_id}.jpg"),
                np.full((40, 120, 3), 180, dtype=np.uint8),
            )
        objects = [
            {
                "content_id": "ocr_content_001",
                "ocr_text_candidate": "正常文字",
                "roles": ["hardsub"],
                "geometry_refs": ["sub_01"],
                "review_input_sha256": "a" * 64,
                "review_assets": [
                    {"text_id": "sub_01", "crop_path": "crops/sub_01.jpg"}
                ],
            },
            {
                "content_id": "ocr_content_002",
                "ocr_text_candidate": "",
                "roles": ["ui_chip"],
                "geometry_refs": ["sub_02"],
                "review_input_sha256": "b" * 64,
                "review_assets": [
                    {"text_id": "sub_02", "crop_path": "crops/sub_02.jpg"}
                ],
            },
        ]
        queue_path = root / "phase2_review_queue.json"
        queue_path.write_text(
            json.dumps({"content_objects": objects}), encoding="utf-8"
        )
        proposal = {
            "review_queue_ref": {
                "sha256": hashlib.sha256(queue_path.read_bytes()).hexdigest()
            },
            "proposals": [
                {
                    "content_id": row["content_id"],
                    "ocr_text_suggested": row["ocr_text_candidate"],
                    "proposed_decision": (
                        "APPROVE" if row["ocr_text_candidate"] else None
                    ),
                    "proposal_status": "OPERATOR_REVIEW_REQUIRED",
                }
                for row in objects
            ],
        }
        proposal["proposal_sha256"] = _sha_json(proposal)
        (root / "phase2_review_proposal.json").write_text(
            json.dumps(proposal), encoding="utf-8"
        )

        result = build_visual_review(root)

        assert result["counts"] == {
            "objects": 2,
            "empty_candidates": 1,
            "exact_confirmation": 1,
            "proposed_edits": 0,
            "proposed_reject_ui": 0,
            "operator_input_required": 0,
            "sheets": 1,
        }
        assert result["objects"][0]["content_id"] == "ocr_content_002"
        assert (root / result["sheets"][0]["path"]).is_file()
        unsigned = dict(result)
        claimed = unsigned.pop("visual_review_sha256")
        assert claimed == _sha_json(unsigned)
