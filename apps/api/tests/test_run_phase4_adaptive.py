from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_phase4_adaptive


class RunPhase4AdaptiveTests(unittest.TestCase):
    def test_records_frame_diagnostics_before_render_meta_exists(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            error = run_phase4_adaptive.AdaptiveVideoRenderError(
                "Adaptive frame blocked at index 5",
                diagnostics={"frame_index": 5, "track_id": "sub_04"},
            )

            path = run_phase4_adaptive._record_runner_failure(
                root,
                visual_preview=True,
                exc=error,
            )

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "VISUAL_PREVIEW_RENDER_FAILED")
            self.assertEqual(payload["failed_checks"], ["frame_render"])
            self.assertEqual(payload["error"]["diagnostics"]["frame_index"], 5)
            self.assertEqual(payload["error"]["type"], "AdaptiveVideoRenderError")

    def test_final_reuses_hash_bound_preview_and_skips_full_visual_qa(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"source")
            contract_path = root / "phase4_render_input.json"
            contract_path.write_text(
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
            (root / "phase1_meta.json").write_text(
                json.dumps({"video": str(source)}), encoding="utf-8"
            )
            preview = root / "phase4_adaptive_visual_preview.mp4"
            preview.write_bytes(b"preview")
            preview_qa_path = root / "qa" / "preview-output-qa.json"
            preview_qa_path.parent.mkdir(parents=True)
            preview_qa_path.write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "failed_checks": [],
                        "checks": {"residual_cjk": True},
                        "residual_cjk": {"complete": True, "detections": []},
                    }
                ),
                encoding="utf-8",
            )
            (root / "phase4_adaptive_render_meta.json").write_text(
                json.dumps(
                    {
                        "status": "VISUAL_PREVIEW_RENDERED",
                        "output_qa_status": "PASS",
                        "visual_preview": True,
                        "phase4_input_sha256": "c" * 64,
                        "visual_remediation_ref": {},
                        "output_video_sha256": "p" * 64,
                        "artifacts": {
                            "video": preview.name,
                            "output_qa": preview_qa_path.relative_to(root).as_posix(),
                        },
                    }
                ),
                encoding="utf-8",
            )
            final = root / "phase4_adaptive_final.mp4"
            render_qa = root / "qa" / "phase4_adaptive_final_qa.json"
            progress_events: list[tuple[str, int | None]] = []

            def hash_for(path):
                resolved = Path(path)
                if resolved == source:
                    return "s" * 64
                if resolved == contract_path:
                    return "c" * 64
                if resolved == preview:
                    return "p" * 64
                return "f" * 64

            def fake_remux(*_args, **_kwargs):
                final.write_bytes(b"final")
                render_qa.write_text("{}", encoding="utf-8")
                return SimpleNamespace(
                    output_path=final,
                    frame_count=30,
                    qa_path=render_qa,
                    visual_preview=False,
                    encoder_metadata={"visual_authority_reused": True},
                    audio_mix_metadata={"narration_complete": True},
                )

            with patch.object(
                run_phase4_adaptive, "_sha256_file", side_effect=hash_for
            ), patch.object(
                run_phase4_adaptive,
                "remux_adaptive_preview_as_final",
                side_effect=fake_remux,
            ) as remux, patch.object(
                run_phase4_adaptive,
                "collect_reused_visual_output_qa",
                return_value={"status": "PASS", "failed_checks": [], "audio": {"status": "PASS"}},
            ) as reused_qa, patch.object(
                run_phase4_adaptive, "render_adaptive_video"
            ) as full_render, patch.object(
                run_phase4_adaptive, "collect_adaptive_output_qa"
            ) as full_qa, patch.object(
                run_phase4_adaptive,
                "load_residual_cjk_false_positive_approval",
                return_value=None,
            ):
                result = run_phase4_adaptive.run(
                    root,
                    visual_preview=False,
                    narration_path=source,
                    on_progress=lambda phase, percent: progress_events.append(
                        (phase, percent)
                    ),
                )

            self.assertEqual(result, 0)
            remux.assert_called_once()
            reused_qa.assert_called_once()
            full_render.assert_not_called()
            full_qa.assert_not_called()
            self.assertEqual(
                [percent for _phase, percent in progress_events],
                [35, 78, 95, 100],
            )

    def test_final_reuses_preview_after_hash_bound_audio_only_rebind(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract_path = root / "phase4_render_input.json"
            contract_path.write_text('{"authorities":{"audio":{"status":"READY"}}}', encoding="utf-8")
            current_contract_sha = run_phase4_adaptive._sha256_file(contract_path)
            old_contract_sha = "a" * 64
            preview = root / "phase4_adaptive_visual_preview.mp4"
            preview.write_bytes(b"approved-preview")
            preview_sha = run_phase4_adaptive._sha256_file(preview)
            qa_path = root / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
            qa_path.parent.mkdir(parents=True)
            qa_path.write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "failed_checks": [],
                        "residual_cjk": {"complete": True, "detections": []},
                    }
                ),
                encoding="utf-8",
            )
            remediation = {
                "schema_version": "phase4_visual_remediation_v1",
                "status": "PHASE4_VISUAL_REMEDIATION_APPROVED",
                "operations": [],
                "non_goals": ["do_not_change_visual_operations"],
                "authority_refs": {
                    "encoded_output_qa": {
                        "path": qa_path.relative_to(root).as_posix(),
                        "sha256": run_phase4_adaptive._sha256_file(qa_path),
                    },
                    "audio_authority_rebind": {
                        "policy_version": "phase4_late_audio_authority_rebind_v1",
                        "old_phase4_input_sha256": old_contract_sha,
                        "new_phase4_input_sha256": current_contract_sha,
                    },
                },
            }
            remediation_path = root / "phase4_visual_remediation_audio_rebind.json"
            remediation_path.write_text(json.dumps(remediation), encoding="utf-8")
            remediation_ref = {
                "path": remediation_path.name,
                "sha256": run_phase4_adaptive._sha256_file(remediation_path),
            }
            (root / "phase4_adaptive_render_meta.json").write_text(
                json.dumps(
                    {
                        "status": "VISUAL_PREVIEW_RENDERED",
                        "output_qa_status": "PASS",
                        "visual_preview": True,
                        "phase4_input_sha256": old_contract_sha,
                        "visual_remediation_ref": None,
                        "output_video_sha256": preview_sha,
                        "artifacts": {
                            "video": preview.name,
                            "output_qa": qa_path.relative_to(root).as_posix(),
                        },
                    }
                ),
                encoding="utf-8",
            )

            authority = run_phase4_adaptive._approved_visual_preview_authority(
                root,
                contract_path=contract_path,
                visual_remediation_ref=remediation_ref,
            )

            self.assertIsNotNone(authority)
            assert authority is not None
            self.assertEqual(authority[0], preview)
            self.assertEqual(authority[1], preview_sha)

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
                    audio_mix_metadata={"narration_complete": True},
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
