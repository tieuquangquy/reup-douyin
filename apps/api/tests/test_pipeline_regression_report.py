from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.services.pipeline_regression_report import build_regression_report


class PipelineRegressionReportTests(unittest.TestCase):
    def test_operator_gate_is_not_counted_as_execution_failure(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = workspace / "run"
            case_root = run / "case"
            case_root.mkdir(parents=True)
            corpus = {
                "corpus_sha256": "c" * 64,
                "real_video_gaps": {"orientation": ["portrait"]},
                "cases": [
                    {
                        "case_id": "case",
                        "probe": {"duration_seconds": 30.0},
                    }
                ],
            }
            (workspace / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
            state = {
                "run_sha256": "r" * 64,
                "failed_count": 0,
                "corpus_ref": {"path": "corpus.json"},
                "cases": [
                    {
                        "case_id": "case",
                        "source_video_external_id": "123",
                        "status": "WAITING_OCR_OPERATOR_REVIEW",
                        "artifact_root": "run/case",
                    }
                ],
            }
            (run / "batch_regression_state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )
            (case_root / "phase1_meta.json").write_text(
                json.dumps({"frame_count": 900, "elapsed_s": 90}), encoding="utf-8"
            )
            (case_root / "phase1_score.json").write_text(
                json.dumps({"PASS": True, "tracks": 20, "hardsubs": 10}),
                encoding="utf-8",
            )
            (case_root / "phase2_meta.json").write_text(
                json.dumps(
                    {
                        "tracks": 20,
                        "ocr_ok": 18,
                        "review_required": 5,
                        "ready_for_phase3": False,
                        "elapsed_s": 10,
                        "model_version": "ppocrv6-medium-det-rec",
                    }
                ),
                encoding="utf-8",
            )

            report = build_regression_report(
                run_root=run,
                workspace_root=workspace,
            )

            self.assertEqual(report["status"], "PASS_TO_OPERATOR_GATES")
            self.assertEqual(report["phase1_pass_count"], 1)
            self.assertEqual(report["phase1_accepted_count"], 1)
            self.assertEqual(report["operator_review_object_count"], 5)
            self.assertEqual(report["ocr_coverage_ratio"], 0.9)
            self.assertIn("exact OCR operator review", report["conclusion"])

    def test_ready_for_phase3_conclusion_does_not_claim_ocr_review_is_open(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = workspace / "run"
            case_root = run / "case"
            case_root.mkdir(parents=True)
            corpus = {
                "corpus_sha256": "c" * 64,
                "real_video_gaps": {"orientation": ["portrait"]},
                "cases": [{"case_id": "case", "probe": {"duration_seconds": 30.0}}],
            }
            (workspace / "corpus.json").write_text(
                json.dumps(corpus), encoding="utf-8"
            )
            state = {
                "run_sha256": "r" * 64,
                "failed_count": 0,
                "corpus_ref": {"path": "corpus.json"},
                "cases": [
                    {
                        "case_id": "case",
                        "source_video_external_id": "123",
                        "status": "READY_FOR_PHASE3",
                        "artifact_root": "run/case",
                    }
                ],
            }
            (run / "batch_regression_state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )
            (case_root / "phase1_meta.json").write_text(
                json.dumps({"frame_count": 900, "elapsed_s": 90}), encoding="utf-8"
            )
            (case_root / "phase1_score.json").write_text(
                json.dumps({"PASS": True, "tracks": 20, "hardsubs": 10}),
                encoding="utf-8",
            )
            (case_root / "phase2_meta.json").write_text(
                json.dumps(
                    {
                        "tracks": 20,
                        "ocr_ok": 18,
                        "review_required": 0,
                        "ready_for_phase3": True,
                        "elapsed_s": 10,
                    }
                ),
                encoding="utf-8",
            )

            report = build_regression_report(
                run_root=run,
                workspace_root=workspace,
            )

            self.assertIn("ready for Phase 3", report["conclusion"])
            self.assertNotIn("OCR operator review is still required", report["conclusion"])

    def test_pre_phase2_failure_is_reportable_without_phase2_meta(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = workspace / "run"
            case_root = run / "case"
            case_root.mkdir(parents=True)
            corpus = {
                "corpus_sha256": "c" * 64,
                "real_video_gaps": {},
                "cases": [
                    {"case_id": "case", "probe": {"duration_seconds": 5.0}}
                ],
            }
            (workspace / "corpus.json").write_text(
                json.dumps(corpus), encoding="utf-8"
            )
            state = {
                "run_sha256": "r" * 64,
                "failed_count": 1,
                "corpus_ref": {"path": "corpus.json"},
                "cases": [
                    {
                        "case_id": "case",
                        "source_video_external_id": "public_source",
                        "status": "FAILED",
                        "stages": [
                            {"stage": "phase1", "status": "PASS"},
                            {"stage": "phase1_score", "status": "FAIL"},
                        ],
                    }
                ],
            }
            (run / "batch_regression_state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )
            (case_root / "phase1_meta.json").write_text(
                json.dumps(
                    {
                        "frame_count": 5000,
                        "n_scanned_frames": 150,
                        "elapsed_s": 50,
                    }
                ),
                encoding="utf-8",
            )
            (case_root / "phase1_score.json").write_text(
                json.dumps(
                    {
                        "PASS": False,
                        "tracks": 0,
                        "hardsubs": 0,
                        "uncovered_dense_hardsub_spans": [],
                    }
                ),
                encoding="utf-8",
            )

            report = build_regression_report(
                run_root=run,
                workspace_root=workspace,
            )

            self.assertEqual(report["status"], "FAILED")
            self.assertEqual(report["phase1_execution_pass_count"], 1)
            self.assertEqual(report["phase1_pass_count"], 0)
            self.assertEqual(report["phase1_accepted_count"], 0)
            self.assertEqual(report["phase2_execution_pass_count"], 0)
            self.assertEqual(report["cases"][0]["frame_count"], 150)
            self.assertEqual(
                report["cases"][0]["phase1"]["container_frame_count"], 5000
            )
            self.assertEqual(
                report["cases"][0]["phase1"]["outcome"],
                "NO_CONFIRMED_TEXT_REVIEW_REQUIRED",
            )
            self.assertEqual(
                report["cases"][0]["phase2"]["skipped_reason"],
                "PHASE1_NOT_ACCEPTED",
            )


if __name__ == "__main__":
    unittest.main()
