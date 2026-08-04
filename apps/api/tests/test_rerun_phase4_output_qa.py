from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import rerun_phase4_output_qa


class RerunPhase4OutputQaTests(unittest.TestCase):
    def test_accepts_hash_bound_audio_only_rebind(self) -> None:
        ref = {"path": "audio-rebind.json", "sha256": "a" * 64}
        audit = {
            "status": "READY_FOR_FINAL_RENDER",
            "old_phase4_input_sha256": "b" * 64,
            "new_phase4_input_sha256": "c" * 64,
            "visual_remediation_ref": ref,
            "invariants": {
                "render_tracks_unchanged": True,
                "visual_remediation_operations_unchanged": True,
                "master_timeline_untouched": True,
            },
        }

        self.assertTrue(
            rerun_phase4_output_qa.is_valid_audio_only_rebind(
                audit,
                rendered_input_sha256="b" * 64,
                current_input_sha256="c" * 64,
                current_remediation_ref=ref,
            )
        )

    def test_reuses_hash_bound_preview_without_rendering_again(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            output = root / "phase4_adaptive_visual_preview.mp4"
            contract = root / "phase4_render_input.json"
            source.write_bytes(b"source")
            output.write_bytes(b"rendered")
            contract.write_text(json.dumps({"render_tracks": []}), encoding="utf-8")
            hashes = {
                contract: rerun_phase4_output_qa._sha256_file(contract),
                source: rerun_phase4_output_qa._sha256_file(source),
                output: rerun_phase4_output_qa._sha256_file(output),
            }
            (root / "phase4_adaptive_render_meta.json").write_text(
                json.dumps(
                    {
                        "status": "VISUAL_PREVIEW_QA_FAILED",
                        "visual_preview": True,
                        "phase4_input_sha256": hashes[contract],
                        "source_video_sha256": hashes[source],
                        "output_video_sha256": hashes[output],
                        "visual_remediation_ref": {
                            "path": "phase4_visual_remediation.json",
                            "sha256": "b" * 64,
                            "materialization_sha256": "c" * 64,
                        },
                        "artifacts": {"video": output.name},
                    }
                ),
                encoding="utf-8",
            )
            residual_approval = {"approval_sha256": "a" * 64}
            effective_contract = {
                "render_tracks": [{"text_id": "effective"}]
            }
            remediation_ref = {
                "path": "phase4_visual_remediation.json",
                "sha256": "b" * 64,
                "materialization_sha256": "c" * 64,
            }
            with (
                patch.object(rerun_phase4_output_qa, "_source_path", return_value=source),
                patch.object(
                    rerun_phase4_output_qa,
                    "apply_visual_remediation",
                    return_value=(effective_contract, remediation_ref),
                ),
                patch.object(
                    rerun_phase4_output_qa,
                    "build_local_residual_ocr_provider",
                    return_value=object(),
                ),
                patch.object(
                    rerun_phase4_output_qa,
                    "load_residual_cjk_false_positive_approval",
                    return_value=residual_approval,
                ),
                patch.object(
                    rerun_phase4_output_qa,
                    "collect_adaptive_output_qa",
                    return_value={"status": "PASS", "failed_checks": []},
                ) as collect_qa,
            ):
                meta = rerun_phase4_output_qa.rerun_output_qa(root)

            self.assertEqual(meta["status"], "VISUAL_PREVIEW_RENDERED")
            self.assertEqual(meta["output_qa_status"], "PASS")
            self.assertTrue(meta["qa_rerun"]["current_qa_sha256"])
            self.assertEqual(
                collect_qa.call_args.kwargs["residual_false_positive_approval"],
                residual_approval,
            )
            self.assertIs(
                collect_qa.call_args.kwargs["contract"], effective_contract
            )
            self.assertEqual(
                collect_qa.call_args.kwargs["artifact_dir"].name,
                "p4vp_qa",
            )


if __name__ == "__main__":
    unittest.main()
