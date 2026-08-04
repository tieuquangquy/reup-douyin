from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_phase4_adaptive


class RunPhase4AdaptiveTests(unittest.TestCase):
    def test_source_path_uses_the_shared_phase1_resolver(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            (root / "phase1_meta.json").write_text(
                json.dumps({"video": "source.mp4"}), encoding="utf-8"
            )

            self.assertEqual(run_phase4_adaptive._source_path(root), source.resolve())

    def test_run_visual_preview_writes_meta(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            (root / "phase1_meta.json").write_text(
                json.dumps({"video": str(source)}), encoding="utf-8"
            )
            (root / "phase4_render_input.json").write_text(
                json.dumps(
                    {
                        "status": "READY_FOR_PHASE4",
                        "refs": {"source_video_ref": {"sha256": "s" * 64}},
                        "authorities": {
                            "timebase": {"status": "READY_WITH_PTS_MAP", "mode": "VFR"},
                            "audio": {
                                "status": "VISUAL_PREVIEW_ONLY",
                                "strategy": "source_passthrough",
                            },
                        },
                        "render_tracks": [],
                    }
                ),
                encoding="utf-8",
            )
            output = root / "phase4_adaptive_visual_preview.mp4"
            qa = root / "qa" / "phase4_adaptive_visual_preview_qa.json"
            output.write_bytes(b"rendered")
            qa.parent.mkdir(parents=True)
            qa.write_text("{}", encoding="utf-8")
            residual_approval = {"approval_sha256": "a" * 64}
            with patch.object(
                run_phase4_adaptive,
                "render_adaptive_video",
                return_value=SimpleNamespace(
                    output_path=output,
                    frame_count=10,
                    qa_path=qa,
                    visual_preview=True,
                    encoder_metadata={
                        "selected_encoder": "h264_nvenc",
                        "hardware": True,
                    },
                ),
            ), patch.object(
                run_phase4_adaptive,
                "_sha256_file",
                return_value="s" * 64,
            ), patch.object(
                run_phase4_adaptive,
                "build_local_residual_ocr_provider",
                return_value=SimpleNamespace(provider_name="local_test_ocr"),
            ), patch.object(
                run_phase4_adaptive,
                "load_residual_cjk_false_positive_approval",
                return_value=residual_approval,
            ), patch.object(
                run_phase4_adaptive,
                "collect_adaptive_output_qa",
                return_value={"status": "PASS", "failed_checks": []},
            ) as collect_qa:
                result = run_phase4_adaptive.run(root, visual_preview=True)
            self.assertEqual(result, 0)
            meta = json.loads(
                (root / "phase4_adaptive_render_meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(meta["status"], "VISUAL_PREVIEW_RENDERED")
            self.assertNotIn("source_path", meta)
            self.assertEqual(meta["output_qa_status"], "PASS")
            self.assertEqual(meta["encoder"]["selected_encoder"], "h264_nvenc")
            self.assertEqual(meta["output_video_sha256"], "s" * 64)
            self.assertEqual(
                meta["artifacts"]["output_qa"],
                "qa/phase4_adaptive_visual_preview_output_qa.json",
            )
            self.assertEqual(
                collect_qa.call_args.kwargs["residual_false_positive_approval"],
                residual_approval,
            )
            self.assertEqual(
                collect_qa.call_args.kwargs["artifact_dir"].name,
                "p4vp_qa",
            )

    def test_final_handoff_is_blocked_when_encoded_output_qa_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            (root / "phase1_meta.json").write_text(
                json.dumps({"video": str(source)}), encoding="utf-8"
            )
            (root / "phase4_render_input.json").write_text(
                json.dumps(
                    {
                        "status": "READY_FOR_PHASE4",
                        "refs": {"source_video_ref": {"sha256": "s" * 64}},
                        "authorities": {
                            "timebase": {"status": "READY", "mode": "CFR"},
                            "audio": {"status": "READY"},
                        },
                        "render_tracks": [],
                    }
                ),
                encoding="utf-8",
            )
            output = root / "phase4_adaptive_final.mp4"
            qa = root / "qa" / "phase4_adaptive_final_qa.json"
            output.write_bytes(b"rendered")
            qa.parent.mkdir(parents=True)
            qa.write_text("{}", encoding="utf-8")
            with patch.object(
                run_phase4_adaptive,
                "render_adaptive_video",
                return_value=SimpleNamespace(
                    output_path=output,
                    frame_count=10,
                    qa_path=qa,
                    visual_preview=False,
                ),
            ), patch.object(
                run_phase4_adaptive,
                "_sha256_file",
                return_value="s" * 64,
            ), patch.object(
                run_phase4_adaptive,
                "build_local_residual_ocr_provider",
                return_value=SimpleNamespace(provider_name="local_test_ocr"),
            ), patch.object(
                run_phase4_adaptive,
                "collect_adaptive_output_qa",
                return_value={
                    "status": "FAIL",
                    "failed_checks": ["residual_cjk"],
                },
            ):
                with self.assertRaises(run_phase4_adaptive.Phase4AdaptiveRunnerError):
                    run_phase4_adaptive.run(
                        root,
                        visual_preview=False,
                        narration_path=source,
                    )
            meta = json.loads(
                (root / "phase4_adaptive_render_meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(meta["status"], "FINAL_OUTPUT_QA_FAILED")
            self.assertEqual(meta["output_qa_failed_checks"], ["residual_cjk"])

    def test_encoded_video_authority_survives_interrupted_output_qa(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            (root / "phase1_meta.json").write_text(
                json.dumps({"video": str(source)}), encoding="utf-8"
            )
            (root / "phase4_render_input.json").write_text(
                json.dumps(
                    {
                        "status": "READY_FOR_PHASE4",
                        "refs": {"source_video_ref": {"sha256": "s" * 64}},
                        "authorities": {
                            "timebase": {"status": "READY", "mode": "CFR"},
                            "audio": {"status": "VISUAL_PREVIEW_ONLY"},
                        },
                        "render_tracks": [],
                    }
                ),
                encoding="utf-8",
            )
            output = root / "phase4_adaptive_visual_preview.mp4"
            qa = root / "qa" / "phase4_adaptive_visual_preview_qa.json"
            output.write_bytes(b"rendered")
            qa.parent.mkdir(parents=True)
            qa.write_text("{}", encoding="utf-8")
            with patch.object(
                run_phase4_adaptive,
                "render_adaptive_video",
                return_value=SimpleNamespace(
                    output_path=output,
                    frame_count=10,
                    qa_path=qa,
                    visual_preview=True,
                ),
            ), patch.object(
                run_phase4_adaptive,
                "_sha256_file",
                return_value="s" * 64,
            ), patch.object(
                run_phase4_adaptive,
                "build_local_residual_ocr_provider",
                return_value=SimpleNamespace(provider_name="local_test_ocr"),
            ), patch.object(
                run_phase4_adaptive,
                "collect_adaptive_output_qa",
                side_effect=run_phase4_adaptive.AdaptiveOutputQaError("interrupted"),
            ):
                with self.assertRaises(run_phase4_adaptive.AdaptiveOutputQaError):
                    run_phase4_adaptive.run(root, visual_preview=True)

            meta = json.loads(
                (root / "phase4_adaptive_render_meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(meta["status"], "VISUAL_PREVIEW_OUTPUT_QA_PENDING")
            self.assertEqual(meta["output_qa_status"], "PENDING")
            self.assertEqual(
                meta["output_qa_error"]["type"], "AdaptiveOutputQaError"
            )
            self.assertEqual(
                meta["artifacts"]["video"], "phase4_adaptive_visual_preview.mp4"
            )

    def test_visual_operator_gate_is_blocked_when_output_qa_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            (root / "phase1_meta.json").write_text(
                json.dumps({"video": str(source)}), encoding="utf-8"
            )
            (root / "phase4_render_input.json").write_text(
                json.dumps(
                    {
                        "status": "READY_FOR_PHASE4",
                        "refs": {"source_video_ref": {"sha256": "s" * 64}},
                        "authorities": {
                            "timebase": {"status": "READY", "mode": "CFR"},
                            "audio": {"status": "VISUAL_PREVIEW_ONLY"},
                        },
                        "render_tracks": [],
                    }
                ),
                encoding="utf-8",
            )
            output = root / "phase4_adaptive_visual_preview.mp4"
            qa = root / "qa" / "phase4_adaptive_visual_preview_qa.json"
            output.write_bytes(b"rendered")
            qa.parent.mkdir(parents=True)
            qa.write_text("{}", encoding="utf-8")
            with patch.object(
                run_phase4_adaptive,
                "render_adaptive_video",
                return_value=SimpleNamespace(
                    output_path=output,
                    frame_count=10,
                    qa_path=qa,
                    visual_preview=True,
                ),
            ), patch.object(
                run_phase4_adaptive,
                "_sha256_file",
                return_value="s" * 64,
            ), patch.object(
                run_phase4_adaptive,
                "build_local_residual_ocr_provider",
                return_value=SimpleNamespace(provider_name="local_test_ocr"),
            ), patch.object(
                run_phase4_adaptive,
                "collect_adaptive_output_qa",
                return_value={"status": "FAIL", "failed_checks": ["residual_cjk"]},
            ):
                with self.assertRaises(run_phase4_adaptive.Phase4AdaptiveRunnerError):
                    run_phase4_adaptive.run(root, visual_preview=True)

            meta = json.loads(
                (root / "phase4_adaptive_render_meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(meta["status"], "VISUAL_PREVIEW_QA_FAILED")


if __name__ == "__main__":
    unittest.main()
