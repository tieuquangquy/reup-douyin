from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.services.pipeline_batch_regression import (
    PipelineBatchRegressionError,
    PipelineBatchRegressionRunner,
    evaluate_case_gate,
    evaluate_operator_gate,
    refresh_batch_gate_state,
)
from src.media_pipeline.frame_sampling.phase1_no_text_contract import (
    record_no_text_decision,
)


class PipelineBatchRegressionTests(unittest.TestCase):
    def test_materialized_no_text_case_advances_to_downstream_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase2_meta.json").write_text("{}", encoding="utf-8")
            with patch(
                "src.services.pipeline_batch_regression.evaluate_no_text_operator_gate",
                return_value={"status": "NO_TEXT_OPERATOR_APPROVED"},
            ), patch(
                "src.services.pipeline_batch_regression.evaluate_operator_gate",
                return_value={"status": "WAITING_FINAL_OPERATOR_APPROVAL"},
            ) as downstream:
                gate = evaluate_case_gate(root, phase1_score={"PASS": False})

            self.assertEqual(gate["status"], "WAITING_FINAL_OPERATOR_APPROVAL")
            downstream.assert_called_once()

    def test_runner_applies_hash_bound_scope_manifest_before_case_execution(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            api_root = workspace / "apps" / "api"
            run = api_root / "run"
            api_root.mkdir(parents=True)
            cases = [
                {
                    "case_id": f"case_{index}",
                    "source_video_external_id": f"video_{index}",
                    "regression_scope": "FULL_E2E",
                }
                for index in range(5)
            ]
            corpus = {
                "corpus_sha256": "c" * 64,
                "cases": cases,
            }
            corpus_path = workspace / "corpus.json"
            corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
            run.mkdir(parents=True)
            manifest = {
                "schema_version": "pipeline_regression_scope_manifest_v1",
                "status": "ACTIVE",
                "corpus_sha256": corpus["corpus_sha256"],
                "scopes": {"case_0": "VISUAL_LOCALIZATION_ONLY"},
            }
            manifest["scope_manifest_sha256"] = hashlib.sha256(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            (run / "regression_scope_manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            runner = PipelineBatchRegressionRunner(
                workspace_root=workspace,
                api_root=api_root,
                corpus_path=corpus_path,
                run_root=run,
            )

            def fake_run_case(case: dict[str, object]) -> dict[str, object]:
                case_id = str(case["case_id"])
                return {
                    "case_id": case_id,
                    "status": "BATCH_REGRESSION_READY",
                    "operator_touch_required": False,
                    "regression_scope": runner.scope_overrides.get(case_id)
                    or str(case.get("regression_scope") or "FULL_E2E"),
                }

            with patch.object(runner, "_run_case", side_effect=fake_run_case):
                result = runner.run()

            self.assertEqual(
                result["cases"][0]["regression_scope"],
                "VISUAL_LOCALIZATION_ONLY",
            )
            self.assertEqual(result["cases"][1]["regression_scope"], "FULL_E2E")

    def test_refresh_applies_hash_bound_visual_scope_manifest(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = workspace / "run"
            case = run / "visual"
            case.mkdir(parents=True)
            (case / "phase1_score.json").write_text(
                json.dumps({"PASS": True}), encoding="utf-8"
            )
            (case / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            (case / "phase3_closeout.json").write_text("{}", encoding="utf-8")
            render_input = case / "phase4_render_input.json"
            render_input.write_text("{}", encoding="utf-8")
            (case / "phase4_adaptive_visual_preview.mp4").write_bytes(b"preview")
            (case / "phase4_adaptive_render_meta.json").write_text(
                json.dumps(
                    {
                        "visual_preview": True,
                        "output_qa_status": "PASS",
                        "phase4_input_sha256": hashlib.sha256(
                            render_input.read_bytes()
                        ).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
            (case / "phase4_visual_approval.json").write_text(
                json.dumps({"status": "VISUAL_APPROVED"}), encoding="utf-8"
            )
            corpus_sha = "c" * 64
            state = {
                "corpus_ref": {"corpus_sha256": corpus_sha},
                "cases": [
                    {
                        "case_id": "visual",
                        "artifact_root": "run/visual",
                    }
                ],
            }
            (run / "batch_regression_state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )
            manifest = {
                "schema_version": "pipeline_regression_scope_manifest_v1",
                "status": "ACTIVE",
                "corpus_sha256": corpus_sha,
                "scopes": {"visual": "VISUAL_LOCALIZATION_ONLY"},
            }
            manifest["scope_manifest_sha256"] = hashlib.sha256(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            manifest_path = run / "regression_scope_manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            refreshed = refresh_batch_gate_state(
                run_root=run,
                workspace_root=workspace,
            )

            self.assertEqual(
                refreshed["cases"][0]["status"],
                "VISUAL_LOCALIZATION_APPROVED",
            )
            manifest["scopes"]["visual"] = "FULL_E2E"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(PipelineBatchRegressionError):
                refresh_batch_gate_state(
                    run_root=run,
                    workspace_root=workspace,
                )

    def test_refreshes_gates_without_executing_downstream_stages(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = workspace / "run"
            ready = run / "ready"
            rejected = run / "rejected"
            (ready / "qa").mkdir(parents=True)
            (rejected / "qa").mkdir(parents=True)
            source = workspace / "source.webm"
            source.write_bytes(b"source")
            (ready / "phase1_score.json").write_text(
                json.dumps({"PASS": True, "tracks": 1}), encoding="utf-8"
            )
            (ready / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            (rejected / "master_timeline.json").write_text("[]", encoding="utf-8")
            (rejected / "phase1_score.json").write_text(
                json.dumps(
                    {
                        "PASS": False,
                        "tracks": 0,
                        "uncovered_dense_hardsub_spans": [],
                        "high_confidence_local_text_rejects": [],
                    }
                ),
                encoding="utf-8",
            )
            (rejected / "text_frame_coverage.json").write_text(
                json.dumps({"n_frames_with_text": 1, "n_hits": 1}),
                encoding="utf-8",
            )
            (rejected / "qa" / "quality_report.json").write_text(
                json.dumps({"uncertain_tracks": 0}), encoding="utf-8"
            )
            (rejected / "phase1_meta.json").write_text(
                json.dumps({"video": "source.webm", "n_scanned_frames": 1}),
                encoding="utf-8",
            )
            record_no_text_decision(
                rejected,
                operator_id="operator-1",
                decision="TEXT_PRESENT_REJECTED",
            )
            (run / "batch_regression_state.json").write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "case_id": "ready",
                                "artifact_root": "run/ready",
                            },
                            {
                                "case_id": "rejected",
                                "artifact_root": "run/rejected",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            state = refresh_batch_gate_state(
                run_root=run, workspace_root=workspace
            )

            self.assertEqual(state["status"], "FAILED")
            self.assertEqual(state["failed_count"], 1)
            self.assertEqual(state["cases"][0]["status"], "READY_FOR_PHASE3")
            self.assertEqual(
                state["cases"][1]["status"], "TEXT_PRESENT_PHASE1_REJECTED"
            )
            ready_case_state = json.loads(
                (ready / "regression_case_state.json").read_text(encoding="utf-8")
            )
            rejected_case_state = json.loads(
                (rejected / "regression_case_state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(ready_case_state["status"], "READY_FOR_PHASE3")
            self.assertEqual(
                rejected_case_state["status"], "TEXT_PRESENT_PHASE1_REJECTED"
            )
            self.assertFalse((ready / "phase3_meta.json").exists())

    def test_phase1_zero_track_case_waits_for_hash_bound_no_text_review(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source.mp4"
            source.write_bytes(b"source")
            run = workspace / "run"
            case_root = run / "local_case"
            (case_root / "qa").mkdir(parents=True)
            (case_root / "master_timeline.json").write_text("[]", encoding="utf-8")
            (case_root / "phase1_meta.json").write_text(
                json.dumps({"video": "source.mp4", "n_scanned_frames": 30}),
                encoding="utf-8",
            )
            (case_root / "text_frame_coverage.json").write_text(
                json.dumps({"n_frames_with_text": 0, "n_hits": 0}),
                encoding="utf-8",
            )
            (case_root / "qa" / "quality_report.json").write_text(
                json.dumps({"uncertain_tracks": 0}), encoding="utf-8"
            )
            runner = PipelineBatchRegressionRunner(
                workspace_root=workspace,
                api_root=workspace,
                corpus_path=workspace / "corpus.json",
                run_root=run,
            )
            score = {
                "PASS": False,
                "tracks": 0,
                "uncovered_dense_hardsub_spans": [],
                "high_confidence_local_text_rejects": [],
            }
            with patch(
                "src.services.pipeline_batch_regression.score_phase1_out",
                return_value=score,
            ):
                result = runner._run_case(
                    {
                        "case_id": "local_case",
                        "source_video_external_id": "source",
                        "video_path": "source.mp4",
                    }
                )

            self.assertEqual(result["status"], "WAITING_NO_TEXT_OPERATOR_REVIEW")
            self.assertTrue(result["operator_touch_required"])
            self.assertTrue((case_root / "phase1_no_text_review.json").is_file())

    def test_phase1_quality_failure_waits_at_geometry_review_not_failed(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source.mp4"
            source.write_bytes(b"source")
            run = workspace / "run"
            case_root = run / "local_case"
            (case_root / "qa").mkdir(parents=True)
            (case_root / "crops").mkdir()
            (case_root / "frames").mkdir()
            (case_root / "crops" / "sub_01.jpg").write_bytes(b"crop")
            (case_root / "frames" / "sub_01.jpg").write_bytes(b"frame")
            track = {
                "text_id": "sub_01",
                "start_frame": 1,
                "end_frame": 5,
                "box_coords": [1.0, 90.0, 220.0, 116.0],
                "best_frame_index": 3,
                "crop_path": "crops/sub_01.jpg",
                "best_keyframe_path": "frames/sub_01.jpg",
            }
            (case_root / "master_timeline.json").write_text(
                json.dumps([track]), encoding="utf-8"
            )
            (case_root / "phase1_meta.json").write_text(
                json.dumps({"video": "source.mp4", "frame_count": 30}),
                encoding="utf-8",
            )
            (case_root / "text_frame_coverage.json").write_text(
                json.dumps({"frame_width": 240, "frame_height": 120, "by_frame": {}}),
                encoding="utf-8",
            )
            (case_root / "qa" / "quality_report.json").write_text(
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
            score = {
                "PASS": False,
                "tracks": 1,
                "frame_size": [240, 120],
                "empty_left_wide_hardsubs": ["sub_01"],
                "checks": {
                    "has_tracks": True,
                    "has_quality_report": True,
                    "has_text_frame_coverage": True,
                    "no_uncertain_tracks": False,
                    "no_empty_left_wide_hardsub": False,
                    "crops_complete": True,
                    "keyframes_complete": True,
                },
            }
            runner = PipelineBatchRegressionRunner(
                workspace_root=workspace,
                api_root=workspace,
                corpus_path=workspace / "corpus.json",
                run_root=run,
            )
            with patch(
                "src.services.pipeline_batch_regression.score_phase1_out",
                return_value=score,
            ):
                result = runner._run_case(
                    {
                        "case_id": "local_case",
                        "source_video_external_id": "source",
                        "video_path": "source.mp4",
                    }
                )

            self.assertEqual(
                result["status"], "WAITING_PHASE1_GEOMETRY_OPERATOR_REVIEW"
            )
            self.assertTrue(result["operator_touch_required"])
            self.assertEqual(result["next_stage"], "phase1_geometry_review")
            self.assertTrue((case_root / "phase1_geometry_review.json").is_file())

    def test_phase1_stale_no_text_approval_returns_to_operator_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source.mp4"
            source.write_bytes(b"source")
            run = workspace / "run"
            case_root = run / "local_case"
            (case_root / "qa").mkdir(parents=True)
            (case_root / "master_timeline.json").write_text("[]", encoding="utf-8")
            (case_root / "phase1_meta.json").write_text(
                json.dumps({"video": "source.mp4", "n_scanned_frames": 30}),
                encoding="utf-8",
            )
            (case_root / "text_frame_coverage.json").write_text(
                json.dumps({"n_frames_with_text": 0, "n_hits": 0}),
                encoding="utf-8",
            )
            (case_root / "qa" / "quality_report.json").write_text(
                json.dumps({"uncertain_tracks": 0}), encoding="utf-8"
            )
            score = {
                "PASS": False,
                "tracks": 0,
                "uncovered_dense_hardsub_spans": [],
                "high_confidence_local_text_rejects": [],
            }
            (case_root / "phase1_score.json").write_text(
                json.dumps(score), encoding="utf-8"
            )
            record_no_text_decision(
                case_root,
                operator_id="operator-1",
                decision="NO_TEXT_CONFIRMED",
            )
            (case_root / "phase1_score.json").write_text(
                json.dumps({**score, "out": "new-run-root"}), encoding="utf-8"
            )
            runner = PipelineBatchRegressionRunner(
                workspace_root=workspace,
                api_root=workspace,
                corpus_path=workspace / "corpus.json",
                run_root=run,
            )
            with patch(
                "src.services.pipeline_batch_regression.score_phase1_out",
                return_value={**score, "out": "new-run-root"},
            ):
                result = runner._run_case(
                    {
                        "case_id": "local_case",
                        "source_video_external_id": "source",
                        "video_path": "source.mp4",
                    }
                )

            self.assertEqual(result["status"], "WAITING_NO_TEXT_OPERATOR_REVIEW")
            self.assertTrue(result["operator_touch_required"])
            self.assertEqual(result["review_required"], 1)

    def test_gate_waits_for_ocr_review(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": False, "review_required": 7}),
                encoding="utf-8",
            )
            gate = evaluate_operator_gate(root)
            self.assertEqual(gate["status"], "WAITING_OCR_OPERATOR_REVIEW")
            self.assertTrue(gate["operator_touch_required"])
            self.assertEqual(gate["review_required"], 7)

    def test_gate_surfaces_residual_remediation_proposal_review(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            (root / "phase3_closeout.json").write_text("{}", encoding="utf-8")
            (root / "phase2_residual_remediation_proposal.json").write_text(
                json.dumps(
                    {
                        "status": "PROPOSAL_READY_FOR_OPERATOR_REVIEW",
                        "operator_approval_written": False,
                        "proposal_sha256": "a" * 64,
                        "proposals": [{}, {}],
                    }
                ),
                encoding="utf-8",
            )

            gate = evaluate_operator_gate(root)

            self.assertEqual(
                gate["status"],
                "WAITING_RESIDUAL_REMEDIATION_OPERATOR_REVIEW",
            )
            self.assertEqual(gate["next_stage"], "phase2_residual_review")
            self.assertTrue(gate["operator_touch_required"])
            self.assertEqual(gate["review_required"], 2)

    def test_gate_surfaces_blocked_residual_when_proposal_cannot_be_built(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            (root / "phase3_closeout.json").write_text("{}", encoding="utf-8")
            (root / "phase4_preflight_meta.json").write_text(
                json.dumps(
                    {
                        "status": "PHASE4_PREFLIGHT_BLOCKED",
                        "final_render_gate": "BLOCKED_VISUAL_RESIDUAL_CJK",
                        "residual_cjk": {"detections": [{"text": "22.2å…ƒ"}]},
                    }
                ),
                encoding="utf-8",
            )

            gate = evaluate_operator_gate(root)

            self.assertEqual(
                gate["status"], "WAITING_RESIDUAL_CJK_OPERATOR_TRIAGE"
            )
            self.assertEqual(gate["next_stage"], "residual_cjk_triage")
            self.assertTrue(gate["operator_touch_required"])
            self.assertEqual(gate["review_required"], 1)

    def test_gate_resumes_phase2_after_residual_remediation_materializes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            (root / "phase3_closeout.json").write_text("{}", encoding="utf-8")
            (root / "phase2_residual_remediation.json").write_text(
                "{}", encoding="utf-8"
            )

            gate = evaluate_operator_gate(root)

            self.assertEqual(gate["status"], "READY_FOR_PHASE2_REMEDIATION")
            self.assertEqual(gate["next_stage"], "phase2")

    def test_gate_does_not_requeue_remediation_already_consumed_by_phase2(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            remediation = root / "phase2_residual_remediation.json"
            remediation.write_text("{}", encoding="utf-8")
            (root / "phase2_meta.json").write_text(
                json.dumps(
                    {
                        "ready_for_phase3": True,
                        "residual_remediation_ref": {
                            "path": remediation.name,
                            "sha256": hashlib.sha256(
                                remediation.read_bytes()
                            ).hexdigest(),
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "phase3_closeout.json").write_text("{}", encoding="utf-8")
            (root / "phase4_preflight_meta.json").write_text(
                json.dumps(
                    {
                        "status": "PHASE4_PREFLIGHT_BLOCKED",
                        "final_render_gate": "BLOCKED_VISUAL_RESIDUAL_CJK",
                        "residual_cjk": {"detections": [{"text": "åˆé¤"}]},
                    }
                ),
                encoding="utf-8",
            )

            gate = evaluate_operator_gate(root)

            self.assertEqual(
                gate["status"], "WAITING_RESIDUAL_CJK_OPERATOR_TRIAGE"
            )
            self.assertEqual(gate["review_required"], 1)

    def test_stop_after_phase2_never_executes_phase3(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source.mp4"
            source.write_bytes(b"source")
            run = workspace / "run"
            case_root = run / "local_case"
            case_root.mkdir(parents=True)
            (case_root / "master_timeline.json").write_text("[]", encoding="utf-8")
            (case_root / "phase1_meta.json").write_text(
                json.dumps({"video": "source.mp4"}), encoding="utf-8"
            )
            (case_root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            runner = PipelineBatchRegressionRunner(
                workspace_root=workspace,
                api_root=workspace,
                corpus_path=workspace / "corpus.json",
                run_root=run,
                stop_after_phase2=True,
            )
            with (
                patch(
                    "src.services.pipeline_batch_regression.score_phase1_out",
                    return_value={"PASS": True, "tracks": 1, "hardsubs": 0},
                ),
                patch.object(runner, "_execute") as execute,
            ):
                result = runner._run_case(
                    {
                        "case_id": "local_case",
                        "source_video_external_id": "source",
                        "video_path": "source.mp4",
                    }
                )

            self.assertEqual(result["status"], "READY_FOR_PHASE3")
            execute.assert_not_called()
            self.assertFalse((case_root / "phase3_meta.json").exists())

    def test_resume_does_not_mutate_phase1_meta(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source.mp4"
            source.write_bytes(b"source")
            run = workspace / "run"
            case_root = run / "local_case"
            case_root.mkdir(parents=True)
            (case_root / "master_timeline.json").write_text("[]", encoding="utf-8")
            meta_path = case_root / "phase1_meta.json"
            meta_path.write_text(
                json.dumps({"video": "../../source.mp4", "stable": True}),
                encoding="utf-8",
            )
            original_meta = meta_path.read_bytes()
            (case_root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            runner = PipelineBatchRegressionRunner(
                workspace_root=workspace,
                api_root=workspace,
                corpus_path=workspace / "corpus.json",
                run_root=run,
                stop_after_phase2=True,
            )
            with patch(
                "src.services.pipeline_batch_regression.score_phase1_out",
                return_value={"PASS": True, "tracks": 1, "hardsubs": 0},
            ):
                runner._run_case(
                    {
                        "case_id": "local_case",
                        "source_video_external_id": "source",
                        "video_path": "source.mp4",
                    }
                )

            self.assertEqual(meta_path.read_bytes(), original_meta)

    def test_resume_skips_completed_stages_and_executes_reachable_downstream_stages(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source.mp4"
            source.write_bytes(b"source")
            run = workspace / "run"
            case_root = run / "local_case"
            case_root.mkdir(parents=True)
            (case_root / "master_timeline.json").write_text("[]", encoding="utf-8")
            (case_root / "phase1_meta.json").write_text(
                json.dumps({"video": "source.mp4"}), encoding="utf-8"
            )
            (case_root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            (case_root / "phase3_closeout.json").write_text("{}", encoding="utf-8")
            runner = PipelineBatchRegressionRunner(
                workspace_root=workspace,
                api_root=workspace,
                corpus_path=workspace / "corpus.json",
                run_root=run,
            )

            def execute_stage(*, stage: str, args: list[str], logs_dir: Path) -> dict:
                del args, logs_dir
                if stage == "phase4_preflight":
                    (case_root / "phase4_render_input.json").write_text(
                        "{}", encoding="utf-8"
                    )
                elif stage == "phase4_visual":
                    (case_root / "phase4_adaptive_visual_preview.mp4").write_bytes(
                        b"preview"
                    )
                    (case_root / "phase4_adaptive_render_meta.json").write_text(
                        json.dumps(
                            {
                                "visual_preview": True,
                                "output_qa_status": "PASS",
                                "phase4_input_sha256": hashlib.sha256(
                                    (case_root / "phase4_render_input.json").read_bytes()
                                ).hexdigest(),
                            }
                        ),
                        encoding="utf-8",
                    )
                return {"stage": stage, "status": "PASS", "elapsed_seconds": 0.0}

            with (
                patch(
                    "src.services.pipeline_batch_regression.score_phase1_out",
                    return_value={"PASS": True, "tracks": 1, "hardsubs": 0},
                ),
                patch.object(runner, "_execute", side_effect=execute_stage) as execute,
            ):
                result = runner._run_case(
                    {
                        "case_id": "local_case",
                        "source_video_external_id": "source",
                        "video_path": "source.mp4",
                    }
                )

            self.assertEqual(result["status"], "WAITING_VISUAL_OPERATOR_REVIEW")
            self.assertEqual(
                [call.kwargs["stage"] for call in execute.call_args_list],
                ["phase4_preflight", "phase4_visual"],
            )

    def test_final_stage_refreshes_preflight_before_render(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source.mp4"
            source.write_bytes(b"source")
            run = workspace / "run"
            case_root = run / "local_case"
            case_root.mkdir(parents=True)
            (case_root / "master_timeline.json").write_text("[]", encoding="utf-8")
            (case_root / "phase1_meta.json").write_text(
                json.dumps({"video": "source.mp4"}), encoding="utf-8"
            )
            (case_root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            (case_root / "phase3_closeout.json").write_text("{}", encoding="utf-8")
            render_input = case_root / "phase4_render_input.json"
            render_input.write_text("{}", encoding="utf-8")
            (case_root / "phase4_adaptive_visual_preview.mp4").write_bytes(b"preview")
            (case_root / "phase4_adaptive_render_meta.json").write_text(
                json.dumps(
                    {
                        "status": "VISUAL_PREVIEW_RENDERED",
                        "visual_preview": True,
                        "output_qa_status": "PASS",
                        "phase4_input_sha256": hashlib.sha256(
                            render_input.read_bytes()
                        ).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
            (case_root / "phase4_visual_approval.json").write_text(
                json.dumps({"status": "VISUAL_APPROVED"}), encoding="utf-8"
            )
            (case_root / "phase4_audio_approval.json").write_text(
                json.dumps({"status": "AUDIO_APPROVED"}), encoding="utf-8"
            )
            runner = PipelineBatchRegressionRunner(
                workspace_root=workspace,
                api_root=workspace,
                corpus_path=workspace / "corpus.json",
                run_root=run,
            )

            def execute_stage(*, stage: str, args: list[str], logs_dir: Path) -> dict:
                del args, logs_dir
                if stage == "phase4_final":
                    (case_root / "phase4_adaptive_render_meta.json").write_text(
                        json.dumps(
                            {
                                "status": "FINAL_RENDERED",
                                "visual_preview": False,
                                "output_qa_status": "PASS",
                            }
                        ),
                        encoding="utf-8",
                    )
                return {"stage": stage, "status": "PASS", "elapsed_seconds": 0.0}

            with (
                patch(
                    "src.services.pipeline_batch_regression.score_phase1_out",
                    return_value={"PASS": True, "tracks": 1, "hardsubs": 0},
                ),
                patch.object(runner, "_execute", side_effect=execute_stage) as execute,
            ):
                result = runner._run_case(
                    {
                        "case_id": "local_case",
                        "source_video_external_id": "source",
                        "video_path": "source.mp4",
                    }
                )

            self.assertEqual(result["status"], "WAITING_FINAL_OPERATOR_APPROVAL")
            self.assertEqual(
                [call.kwargs["stage"] for call in execute.call_args_list],
                ["phase4_final_preflight", "phase4_final"],
            )

    def test_gate_never_skips_visual_or_audio_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            (root / "phase3_closeout.json").write_text("{}", encoding="utf-8")
            (root / "phase4_render_input.json").write_text("{}", encoding="utf-8")
            (root / "phase4_adaptive_visual_preview.mp4").write_bytes(b"preview")
            input_sha = hashlib.sha256(
                (root / "phase4_render_input.json").read_bytes()
            ).hexdigest()
            (root / "phase4_adaptive_render_meta.json").write_text(
                json.dumps(
                    {
                        "visual_preview": True,
                        "output_qa_status": "PASS",
                        "phase4_input_sha256": input_sha,
                    }
                ),
                encoding="utf-8",
            )
            visual_gate = evaluate_operator_gate(root)
            self.assertEqual(
                visual_gate["status"], "WAITING_VISUAL_OPERATOR_REVIEW"
            )
            (root / "phase4_visual_approval.json").write_text("{}", encoding="utf-8")
            audio_gate = evaluate_operator_gate(root)
            self.assertEqual(audio_gate["status"], "WAITING_AUDIO_OPERATOR_REVIEW")

    def test_gate_routes_known_dialogue_to_translation_review_before_audio(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            (root / "phase3_closeout.json").write_text("{}", encoding="utf-8")
            render_input = root / "phase4_render_input.json"
            render_input.write_text("{}", encoding="utf-8")
            (root / "phase4_adaptive_visual_preview.mp4").write_bytes(b"preview")
            input_sha = hashlib.sha256(render_input.read_bytes()).hexdigest()
            (root / "phase4_adaptive_render_meta.json").write_text(
                json.dumps(
                    {
                        "visual_preview": True,
                        "output_qa_status": "PASS",
                        "phase4_input_sha256": input_sha,
                    }
                ),
                encoding="utf-8",
            )
            (root / "phase4_visual_approval.json").write_text(
                json.dumps({"status": "VISUAL_APPROVED"}), encoding="utf-8"
            )
            (root / "phase4_dialogue_translation_review.json").write_text(
                json.dumps(
                    {
                        "status": "PENDING_OPERATOR_REVIEW",
                        "operator_approval_written": False,
                        "segments": [{"segment_index": 0}],
                        "artifact_sha256": "review-sha",
                    }
                ),
                encoding="utf-8",
            )

            gate = evaluate_operator_gate(root)

            self.assertEqual(
                gate["status"], "WAITING_DIALOGUE_TRANSLATION_OPERATOR_REVIEW"
            )
            self.assertEqual(gate["next_stage"], "dialogue_translation_review")
            self.assertEqual(gate["review_required"], 1)

    def test_gate_never_sends_failed_visual_output_qa_to_operator_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            (root / "phase3_closeout.json").write_text("{}", encoding="utf-8")
            (root / "phase4_render_input.json").write_text("{}", encoding="utf-8")
            (root / "phase4_adaptive_visual_preview.mp4").write_bytes(b"preview")
            (root / "phase4_adaptive_render_meta.json").write_text(
                json.dumps(
                    {
                        "visual_preview": True,
                        "status": "VISUAL_PREVIEW_QA_FAILED",
                        "output_qa_status": "FAIL",
                        "phase4_input_sha256": hashlib.sha256(
                            (root / "phase4_render_input.json").read_bytes()
                        ).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )

            gate = evaluate_operator_gate(root)

            self.assertEqual(gate["status"], "VISUAL_PREVIEW_QA_FAILED")
            self.assertIsNone(gate["next_stage"])

    def test_audio_approved_visual_preview_is_ready_for_final_render(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            (root / "phase3_closeout.json").write_text("{}", encoding="utf-8")
            render_input = root / "phase4_render_input.json"
            render_input.write_text("{}", encoding="utf-8")
            (root / "phase4_adaptive_visual_preview.mp4").write_bytes(b"preview")
            (root / "phase4_adaptive_render_meta.json").write_text(
                json.dumps(
                    {
                        "status": "VISUAL_PREVIEW_RENDERED",
                        "visual_preview": True,
                        "output_qa_status": "PASS",
                        "phase4_input_sha256": hashlib.sha256(
                            render_input.read_bytes()
                        ).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
            (root / "phase4_visual_approval.json").write_text(
                json.dumps({"status": "VISUAL_APPROVED"}), encoding="utf-8"
            )
            (root / "phase4_audio_approval.json").write_text(
                json.dumps({"status": "AUDIO_APPROVED"}), encoding="utf-8"
            )

            gate = evaluate_operator_gate(root)

            self.assertEqual(gate["status"], "READY_FOR_FINAL_RENDER")
            self.assertEqual(gate["next_stage"], "phase4_final")

    def test_stale_visual_preview_returns_to_render_instead_of_operator_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            (root / "phase3_closeout.json").write_text("{}", encoding="utf-8")
            (root / "phase4_render_input.json").write_text(
                '{"revision": 2}', encoding="utf-8"
            )
            (root / "phase4_adaptive_visual_preview.mp4").write_bytes(b"stale")
            (root / "phase4_adaptive_render_meta.json").write_text(
                json.dumps(
                    {
                        "visual_preview": True,
                        "output_qa_status": "PASS",
                        "phase4_input_sha256": "0" * 64,
                    }
                ),
                encoding="utf-8",
            )

            gate = evaluate_operator_gate(root)

            self.assertEqual(gate["status"], "READY_FOR_VISUAL_PREVIEW")
            self.assertEqual(gate["next_stage"], "phase4_visual")

    def test_gate_routes_pending_dialogue_conflict_before_audio_review(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            for name in (
                "phase3_closeout.json",
                "phase4_render_input.json",
                "phase4_visual_approval.json",
            ):
                (root / name).write_text("{}", encoding="utf-8")
            (root / "phase4_adaptive_visual_preview.mp4").write_bytes(b"preview")
            (root / "phase4_dialogue_detection_review.json").write_text(
                json.dumps(
                    {
                        "status": "PENDING_DIALOGUE_OPERATOR_REVIEW",
                        "operator_approval_written": False,
                        "artifact_sha256": "a" * 64,
                    }
                ),
                encoding="utf-8",
            )

            gate = evaluate_operator_gate(root)

            self.assertEqual(
                gate["status"], "WAITING_DIALOGUE_DETECTION_OPERATOR_REVIEW"
            )
            self.assertEqual(gate["next_stage"], "dialogue_detection_review")
            self.assertEqual(gate["review_required"], 1)

            (root / "phase4_dialogue_detection_approval.json").write_text(
                json.dumps({"status": "DIALOGUE_PRESENT_CONFIRMED"}),
                encoding="utf-8",
            )
            remediation_gate = evaluate_operator_gate(root)
            self.assertEqual(
                remediation_gate["status"], "READY_FOR_DIALOGUE_ASR_REMEDIATION"
            )
            self.assertEqual(remediation_gate["next_stage"], "audio_analysis")

    def test_gate_requires_final_approval_before_export(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (
                "phase3_closeout.json",
                "phase4_render_input.json",
                "phase4_visual_approval.json",
                "phase4_audio_approval.json",
            ):
                (root / name).write_text("{}", encoding="utf-8")
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            (root / "phase4_adaptive_visual_preview.mp4").write_bytes(b"preview")
            (root / "phase4_adaptive_render_meta.json").write_text(
                json.dumps({"status": "FINAL_RENDERED", "output_qa_status": "PASS"}),
                encoding="utf-8",
            )
            gate = evaluate_operator_gate(root)
            self.assertEqual(gate["status"], "WAITING_FINAL_OPERATOR_APPROVAL")

    def test_gate_routes_pending_background_mix_review(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            for name in (
                "phase3_closeout.json",
                "phase4_render_input.json",
                "phase4_visual_approval.json",
            ):
                (root / name).write_text("{}", encoding="utf-8")
            (root / "phase4_adaptive_visual_preview.mp4").write_bytes(b"preview")
            (root / "phase4_background_mix_review.json").write_text(
                json.dumps(
                    {
                        "status": "PENDING_AUDIO_MIX_REVIEW",
                        "artifact_sha256": "b" * 64,
                    }
                ),
                encoding="utf-8",
            )

            gate = evaluate_operator_gate(root)

            self.assertEqual(gate["status"], "WAITING_AUDIO_MIX_OPERATOR_REVIEW")
            self.assertEqual(gate["next_stage"], "audio_mix_review")
            self.assertEqual(gate["review_required"], 1)

    def test_visual_only_scope_stops_after_hash_bound_visual_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            (root / "phase3_closeout.json").write_text("{}", encoding="utf-8")
            render_input = root / "phase4_render_input.json"
            render_input.write_text("{}", encoding="utf-8")
            (root / "phase4_adaptive_visual_preview.mp4").write_bytes(b"preview")
            (root / "phase4_adaptive_render_meta.json").write_text(
                json.dumps(
                    {
                        "visual_preview": True,
                        "output_qa_status": "PASS",
                        "phase4_input_sha256": hashlib.sha256(
                            render_input.read_bytes()
                        ).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
            (root / "phase4_visual_approval.json").write_text(
                json.dumps({"status": "VISUAL_APPROVED"}), encoding="utf-8"
            )

            visual_gate = evaluate_operator_gate(
                root,
                regression_scope="VISUAL_LOCALIZATION_ONLY",
            )
            full_gate = evaluate_operator_gate(root)

            self.assertEqual(
                visual_gate["status"], "VISUAL_LOCALIZATION_APPROVED"
            )
            self.assertFalse(visual_gate["operator_touch_required"])
            self.assertIsNone(visual_gate["next_stage"])
            self.assertEqual(full_gate["status"], "WAITING_AUDIO_OPERATOR_REVIEW")

    def test_gate_does_not_regress_exact_legacy_mix_after_final_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            for name in (
                "phase3_closeout.json",
                "phase4_render_input.json",
                "phase4_visual_approval.json",
            ):
                (root / name).write_text("{}", encoding="utf-8")
            (root / "phase4_adaptive_visual_preview.mp4").write_bytes(b"preview")
            narration = root / "phase4_joined_narration.wav"
            background = root / "phase4_background.wav"
            mix_preview = root / "phase4_audio_mix_preview.wav"
            final_video = root / "phase4_adaptive_final.mp4"
            output_qa = root / "qa" / "phase4_adaptive_final_output_qa.json"
            narration.write_bytes(b"narration")
            background.write_bytes(b"background")
            mix_preview.write_bytes(b"mix")
            final_video.write_bytes(b"final")
            output_qa.parent.mkdir()
            output_qa.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
            review = {
                "status": "PENDING_AUDIO_MIX_REVIEW",
                "created_at": "2026-07-28T09:25:25+00:00",
                "artifact_sha256": "b" * 64,
                "narration_ref": {
                    "path": narration.name,
                    "sha256": hashlib.sha256(narration.read_bytes()).hexdigest(),
                },
                "background_ref": {
                    "path": background.name,
                    "sha256": hashlib.sha256(background.read_bytes()).hexdigest(),
                },
                "mix_preview_ref": {
                    "path": mix_preview.name,
                    "sha256": hashlib.sha256(mix_preview.read_bytes()).hexdigest(),
                },
                "mix_recipe": {"background_gain": 0.22},
            }
            (root / "phase4_background_mix_review.json").write_text(
                json.dumps(review), encoding="utf-8"
            )
            audio_approval = {
                "status": "AUDIO_APPROVED",
                "approved_at": "2026-07-28T09:28:10+00:00",
                "narration_ref": review["narration_ref"],
                "background_ref": review["background_ref"],
            }
            audio_path = root / "phase4_audio_approval.json"
            audio_path.write_text(json.dumps(audio_approval), encoding="utf-8")
            render_meta = {
                "status": "FINAL_RENDERED",
                "output_qa_status": "PASS",
                "output_video_sha256": hashlib.sha256(
                    final_video.read_bytes()
                ).hexdigest(),
                "audio_mix": {
                    "background_present": True,
                    "background_gain": 0.22,
                },
                "artifacts": {
                    "video": final_video.name,
                    "output_qa": output_qa.relative_to(root).as_posix(),
                },
            }
            render_meta_path = root / "phase4_adaptive_render_meta.json"
            render_meta_path.write_text(json.dumps(render_meta), encoding="utf-8")
            final_approval = {
                "status": "FINAL_APPROVED",
                "approved_at": "2026-07-28T09:42:39+00:00",
                "refs": {
                    "final_video": {
                        "path": final_video.name,
                        "sha256": render_meta["output_video_sha256"],
                    },
                    "output_qa": {
                        "path": output_qa.relative_to(root).as_posix(),
                        "sha256": hashlib.sha256(output_qa.read_bytes()).hexdigest(),
                    },
                    "audio_approval": {
                        "path": audio_path.name,
                        "sha256": hashlib.sha256(audio_path.read_bytes()).hexdigest(),
                    },
                    "render_meta": {
                        "path": render_meta_path.name,
                        "sha256": hashlib.sha256(
                            render_meta_path.read_bytes()
                        ).hexdigest(),
                    },
                },
            }
            (root / "phase5_final_approval.json").write_text(
                json.dumps(final_approval), encoding="utf-8"
            )

            gate = evaluate_operator_gate(root)

            self.assertEqual(gate["status"], "WAITING_FINAL_OPERATOR_APPROVAL")
            self.assertEqual(gate["next_stage"], "final_review")

            background.write_bytes(b"tampered")
            tampered_gate = evaluate_operator_gate(root)
            self.assertEqual(
                tampered_gate["status"], "WAITING_AUDIO_MIX_OPERATOR_REVIEW"
            )

    def test_gate_routes_completed_metadata_draft_for_operator_review(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "export_packages" / "case"
            package.mkdir(parents=True)
            (root / "phase2_meta.json").write_text(
                json.dumps({"ready_for_phase3": True}), encoding="utf-8"
            )
            for name in (
                "phase3_closeout.json",
                "phase4_render_input.json",
                "phase4_visual_approval.json",
                "phase4_audio_approval.json",
            ):
                (root / name).write_text("{}", encoding="utf-8")
            (root / "phase4_adaptive_visual_preview.mp4").write_bytes(b"preview")
            (root / "phase4_adaptive_render_meta.json").write_text(
                json.dumps({"status": "FINAL_RENDERED", "output_qa_status": "PASS"}),
                encoding="utf-8",
            )
            (root / "phase5_export_handoff.json").write_text(
                json.dumps({"package": {"path": "export_packages/case"}}),
                encoding="utf-8",
            )
            (package / "publish_draft.json").write_text(
                json.dumps({"status": "METADATA_DRAFT_COMPLETE_REVIEW_REQUIRED"}),
                encoding="utf-8",
            )

            gate = evaluate_operator_gate(root)

            self.assertEqual(gate["status"], "WAITING_METADATA_OPERATOR_REVIEW")
            self.assertEqual(gate["next_stage"], "metadata_review")
            self.assertEqual(gate["review_required"], 1)

    def test_execute_recreates_log_dir_removed_by_phase1_style_command(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = root / "case" / "logs"
            runner = PipelineBatchRegressionRunner(
                workspace_root=root,
                api_root=root,
                corpus_path=root / "corpus.json",
                run_root=root / "run",
            )
            command = (
                "import pathlib, shutil; "
                f"p=pathlib.Path({str(logs.parent)!r}); "
                "shutil.rmtree(p, ignore_errors=True); p.mkdir(parents=True)"
            )
            result = runner._execute(
                stage="phase1",
                args=["-c", command],
                logs_dir=logs,
            )
            self.assertEqual(result["status"], "PASS")
            self.assertTrue((logs / "phase1.log").is_file())


if __name__ == "__main__":
    unittest.main()
