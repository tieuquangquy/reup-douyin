from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.materialize_frontend_residual_remediation import materialize
from src.media_pipeline.video_renderer.visual_remediation import (
    apply_visual_remediation,
)


def test_materializes_hash_bound_add_track_without_mutating_contract() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract_path = root / "phase4_render_input.json"
        contract = {
            "status": "READY_FOR_PHASE4",
            "video": {"fps": 30.0, "frame_count": 100},
            "render_tracks": [],
        }
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        decisions_path = root / "decisions.json"
        decisions_path.write_text(
            json.dumps(
                [
                    {
                        "text_id": "residual_01",
                        "start_frame": 10,
                        "end_frame": 20,
                        "geometry": {
                            "x": 0.05,
                            "y": 0.70,
                            "width": 0.90,
                            "height": 0.04,
                        },
                        "text_vi": "Màu này hợp mọi kiểu makeup",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        ref = materialize(root, decisions_path)
        effective, applied_ref = apply_visual_remediation(
            root, contract, contract_path=contract_path
        )

        assert ref == applied_ref
        assert len(effective["render_tracks"]) == 1
        assert effective["render_tracks"][0]["text_id"] == "residual_01"
        assert contract["render_tracks"] == []
