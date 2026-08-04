from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.media_pipeline.frame_sampling.phase1_geometry_review import (
    prepare_phase1_geometry_review,
)
from src.services.pipeline_operator_review_pack import write_operator_review_pack


class PipelineOperatorReviewPackTests(unittest.TestCase):
    def test_reports_no_review_required_when_no_case_is_waiting(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = workspace / "run"
            (workspace / "docs").mkdir(parents=True)
            run.mkdir()
            (workspace / "docs" / "corpus.json").write_text(
                json.dumps({"cases": []}), encoding="utf-8"
            )
            (run / "batch_regression_state.json").write_text(
                json.dumps(
                    {
                        "run_sha256": "a" * 64,
                        "corpus_ref": {"path": "docs/corpus.json"},
                        "cases": [],
                    }
                ),
                encoding="utf-8",
            )

            pack = write_operator_review_pack(
                run_root=run,
                workspace_root=workspace,
            )

            self.assertEqual(pack["status"], "NO_OPERATOR_REVIEW_REQUIRED")
            self.assertEqual(pack["counts"]["selected_cases"], 0)
            self.assertEqual(pack["cases"], [])
            markdown = (run / "OPERATOR_REVIEW_PACK.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("No case is currently waiting", markdown)
            self.assertNotIn("Automation has not written", markdown)

    def test_includes_hash_verified_phase1_geometry_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = workspace / "run"
            case = run / "geometry"
            (case / "qa" / "boundaries").mkdir(parents=True)
            (case / "crops").mkdir()
            (case / "frames").mkdir()
            (workspace / "docs").mkdir()
            source = workspace / "source.mp4"
            source.write_bytes(b"source")
            (case / "crops" / "sub_01.jpg").write_bytes(b"crop")
            (case / "frames" / "sub_01.jpg").write_bytes(b"frame")
            (case / "qa" / "boundaries" / "sub_01.jpg").write_bytes(b"boundary")
            track = {
                "text_id": "sub_01",
                "start_frame": 1,
                "end_frame": 5,
                "box_coords": [1.0, 90.0, 220.0, 116.0],
                "best_frame_index": 3,
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
            prepare_phase1_geometry_review(case)
            corpus = workspace / "docs" / "corpus.json"
            corpus.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "case_id": "geometry",
                                "video_path": "source.mp4",
                                "probe": {"duration_seconds": 2.0},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (run / "batch_regression_state.json").write_text(
                json.dumps(
                    {
                        "run_sha256": "a" * 64,
                        "corpus_ref": {"path": "docs/corpus.json"},
                        "cases": [
                            {
                                "case_id": "geometry",
                                "status": "WAITING_PHASE1_GEOMETRY_OPERATOR_REVIEW",
                                "artifact_root": "run/geometry",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            pack = write_operator_review_pack(
                run_root=run,
                workspace_root=workspace,
            )

            self.assertEqual(pack["counts"]["phase1_geometry_issues"], 1)
            self.assertEqual(pack["cases"][0]["review_type"], "PHASE1_GEOMETRY")
            self.assertEqual(
                pack["cases"][0]["issues"][0]["text_id"], "sub_01"
            )
            self.assertFalse((case / "phase1_geometry_approval.json").exists())

    def test_builds_read_only_pack_for_no_text_and_exact_ocr(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run = workspace / "apps" / "api" / "regression_runs" / "run-v1"
            no_text_root = run / "local_no_text"
            ocr_root = run / "local_ocr"
            (no_text_root / "qa").mkdir(parents=True)
            (ocr_root / "crops").mkdir(parents=True)
            (workspace / "docs").mkdir()
            no_text_source = workspace / "no_text.webm"
            ocr_source = workspace / "ocr.webm"
            no_text_source.write_bytes(b"no-text-source")
            ocr_source.write_bytes(b"ocr-source")
            (no_text_root / "master_timeline.json").write_text("[]", encoding="utf-8")
            (no_text_root / "phase1_score.json").write_text(
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
            (no_text_root / "text_frame_coverage.json").write_text(
                json.dumps({"n_frames_with_text": 0, "n_hits": 0}),
                encoding="utf-8",
            )
            (no_text_root / "qa" / "quality_report.json").write_text(
                json.dumps({"uncertain_tracks": 0}), encoding="utf-8"
            )
            (no_text_root / "qa" / "no_text_review_contact_sheet.jpg").write_bytes(
                b"contact-sheet"
            )
            (no_text_root / "phase1_meta.json").write_text(
                json.dumps({"video": "no_text.webm", "n_scanned_frames": 10}),
                encoding="utf-8",
            )
            crop = ocr_root / "crops" / "sub_01.jpg"
            crop.write_bytes(b"jpeg")
            review_hash = "a" * 64
            (ocr_root / "phase2_review_queue.json").write_text(
                json.dumps(
                    {
                        "phase1_ref": {"path": "master_timeline.json", "sha256": "b" * 64},
                        "review_summary": {"unresolved": 1},
                        "content_objects": [
                            {
                                "content_id": "ocr_content_001",
                                "ocr_text_candidate": "example",
                                "ocr_text_llm_suggested": None,
                                "roles": ["generic"],
                                "geometry_refs": ["sub_01"],
                                "review_input_sha256": review_hash,
                                "review_assets": [
                                    {
                                        "text_id": "sub_01",
                                        "crop_path": "crops/sub_01.jpg",
                                        "start_frame": 1,
                                        "end_frame": 2,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            approvals = {"sentinel": True}
            approvals_path = ocr_root / "phase2_approvals.json"
            approvals_path.write_text(json.dumps(approvals), encoding="utf-8")
            proposal = {
                "review_queue_ref": {
                    "sha256": hashlib.sha256(
                        (ocr_root / "phase2_review_queue.json").read_bytes()
                    ).hexdigest()
                },
                "proposals": [
                    {
                        "content_id": "ocr_content_001",
                        "ocr_text_suggested": "corrected",
                        "proposed_decision": "EDIT",
                        "proposal_status": "OPERATOR_REVIEW_REQUIRED",
                    }
                ],
                "transition_merge_groups": [],
            }
            encoded_proposal = json.dumps(
                proposal,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            proposal["proposal_sha256"] = hashlib.sha256(
                encoded_proposal
            ).hexdigest()
            (ocr_root / "phase2_review_proposal.json").write_text(
                json.dumps(proposal), encoding="utf-8"
            )
            corpus_path = workspace / "docs" / "corpus.json"
            corpus_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "case_id": "local_no_text",
                                "video_path": "no_text.webm",
                                "probe": {"duration_seconds": 2.5},
                            },
                            {
                                "case_id": "local_ocr",
                                "video_path": "ocr.webm",
                                "probe": {"duration_seconds": 3.0},
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            state = {
                "run_sha256": "c" * 64,
                "corpus_ref": {"path": "docs/corpus.json"},
                "cases": [
                    {
                        "case_id": "local_no_text",
                        "status": "WAITING_NO_TEXT_OPERATOR_REVIEW",
                        "artifact_root": "apps/api/regression_runs/run-v1/local_no_text",
                    },
                    {
                        "case_id": "local_ocr",
                        "status": "WAITING_OCR_OPERATOR_REVIEW",
                        "artifact_root": "apps/api/regression_runs/run-v1/local_ocr",
                    },
                ],
            }
            (run / "batch_regression_state.json").write_text(
                json.dumps(state), encoding="utf-8"
            )

            pack = write_operator_review_pack(
                run_root=run,
                workspace_root=workspace,
                selected_case_ids=["local_no_text", "local_ocr"],
            )

            self.assertEqual(pack["counts"], {
                "selected_cases": 2,
                "no_text_reviews": 1,
                "phase1_geometry_issues": 0,
                "ocr_objects": 1,
            })
            unsigned = dict(pack)
            claimed = unsigned.pop("review_pack_sha256")
            encoded = json.dumps(
                unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            self.assertEqual(claimed, hashlib.sha256(encoded).hexdigest())
            self.assertTrue((run / "OPERATOR_REVIEW_PACK.md").is_file())
            self.assertIn("contact_sheet", pack["cases"][0])
            self.assertEqual(
                pack["cases"][1]["content_objects"][0]["ocr_text_suggested"],
                "corrected",
            )
            self.assertFalse(
                (no_text_root / "phase1_no_text_approval.json").exists()
            )
            self.assertEqual(
                json.loads(approvals_path.read_text(encoding="utf-8")), approvals
            )


if __name__ == "__main__":
    unittest.main()
