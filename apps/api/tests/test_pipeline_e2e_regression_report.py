from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.services.pipeline_e2e_regression_report import (
    build_e2e_regression_report,
)


def _self_hashed(payload: dict, field: str) -> dict:
    result = dict(payload)
    encoded = json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    result[field] = hashlib.sha256(encoded).hexdigest()
    return result


class PipelineE2eRegressionReportTests(unittest.TestCase):
    def _case(self, run: Path, name: str = "local_case") -> Path:
        root = run / name
        (root / "qa").mkdir(parents=True)
        final = root / "phase4_adaptive_final.mp4"
        final.write_bytes(b"final-video")
        final_hash = hashlib.sha256(final.read_bytes()).hexdigest()
        payloads = {
            "phase1_score.json": {"PASS": True},
            "phase2_meta.json": {"ready_for_phase3": True},
            "phase3_closeout.json": {"status": "PHASE3_CLOSED"},
            "phase4_visual_approval.json": {"status": "VISUAL_APPROVED"},
            "phase4_audio_approval.json": {"status": "AUDIO_APPROVED"},
            "phase4_adaptive_render_meta.json": {
                "status": "FINAL_RENDERED",
                "output_video_sha256": final_hash,
                "frames": 30,
                "encoder": {
                    "selected_encoder": "h264_nvenc",
                    "runtime_fallback_used": False,
                    "total_render_seconds": 2.0,
                },
                "audio_mix": {
                    "strategy": "replace_with_vietnamese_narration",
                    "normalization_mode": "two_pass_loudnorm",
                },
            },
            "phase5_export_handoff.json": {
                "status": "MANUAL_EXPORT_READY",
                "external_publish_triggered": False,
            },
            "phase5_db_handoff.json": {
                "status": "DB_EXPORT_PACKAGE_READY",
                "retry_safe": True,
                "asset_reused": True,
                "render_reused": True,
                "export_package_reused": True,
                "external_publish_triggered": False,
                "final_video_sha256": final_hash,
                "media_asset_id": "asset",
                "render_output_id": "render",
                "export_package_id": "package",
            },
        }
        for name, payload in payloads.items():
            (root / name).write_text(json.dumps(payload), encoding="utf-8")
        (root / "render_prep_manifest.json").write_text(
            json.dumps(
                {
                    "manifest_version": "RENDER_PREP_MANIFEST_V2",
                    "current_outputs": {
                        "tts_clips": [
                            {
                                "metadata": {
                                    "provider": {
                                        "provider": "omnivoice",
                                        "model_id": "k2-fsa/OmniVoice",
                                        "voice_id": "instruct:vi_female_north",
                                        "language": "vi",
                                        "speaking_rate": 1.0,
                                    }
                                }
                            }
                        ]
                    },
                    "provider_summary": {
                        "tts_provider": "omnivoice",
                        "voice_config": {
                            "voice_id": "instruct:vi_female_north",
                            "language_code": "vi",
                            "speaking_rate": 1.0,
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        (root / "qa" / "phase4_adaptive_final_output_qa.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "failed_checks": [],
                    "audio": {
                        "metrics": {"integrated_lufs": -14.0, "true_peak_db": -2.0}
                    },
                    "residual_cjk": {
                        "detections": [],
                        "source_intrinsic_exclusions": [],
                    },
                }
            ),
            encoding="utf-8",
        )
        approvals = {
            "phase5_final_approval.json": _self_hashed(
                {
                    "status": "FINAL_APPROVED",
                    "source_video": {"id": "source", "external_id": name},
                },
                "approval_sha256",
            ),
            "phase5_metadata_approval.json": _self_hashed(
                {"status": "METADATA_APPROVED"}, "approval_sha256"
            ),
            "phase5_rights_music_approval.json": _self_hashed(
                {"status": "SOURCE_RIGHTS_AND_MUSIC_APPROVED"},
                "approval_sha256",
            ),
            "phase5_manual_export_handoff.json": _self_hashed(
                {"status": "MANUAL_EXPORT_READY"}, "handoff_sha256"
            ),
        }
        for name, payload in approvals.items():
            (root / name).write_text(json.dumps(payload), encoding="utf-8")
        return root

    def test_reports_passing_retry_safe_cases_without_universal_claim(self) -> None:
        with TemporaryDirectory() as tmp:
            run = Path(tmp)
            self._case(run, "local_a")
            self._case(run, "local_b")
            self._case(run, "local_c")
            (run / "local_visual").mkdir()
            (run / "batch_regression_state.json").write_text(
                json.dumps(
                    {
                        "refreshed_at": "2026-08-01T00:00:00+00:00",
                        "cases": [
                            {"case_id": "local_a", "regression_scope": "FULL_E2E"},
                            {"case_id": "local_b", "regression_scope": "FULL_E2E"},
                            {"case_id": "local_c", "regression_scope": "FULL_E2E"},
                            {
                                "case_id": "local_visual",
                                "regression_scope": "VISUAL_LOCALIZATION_ONLY",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = build_e2e_regression_report(run)
            repeated = build_e2e_regression_report(run)

            self.assertEqual(report["status"], "PASS_CONTROLLED_E2E")
            self.assertEqual(report["passed_count"], 3)
            self.assertEqual(report["db_handoff_ready_count"], 3)
            self.assertFalse(report["claims"]["universal_video_support"])
            self.assertEqual(report["run_case_count"], 4)
            self.assertEqual(report["excluded_case_count"], 1)
            self.assertEqual(report["full_e2e_scope_case_count"], 3)
            self.assertEqual(report["visual_localization_excluded_count"], 1)
            self.assertTrue(report["claims"]["full_batch_end_to_end_pass"])
            self.assertEqual(report["created_at"], repeated["created_at"])
            self.assertEqual(
                report["tts_provenance"]["status"],
                "VERIFIED_SINGLE_RUNTIME_CONFIG",
            )
            self.assertEqual(report["tts_provenance"]["provider"], "omnivoice")
            self.assertEqual(
                report["tts_provenance"]["voice_id"],
                "instruct:vi_female_north",
            )

    def test_missing_full_e2e_db_handoff_keeps_full_batch_claim_false(self) -> None:
        with TemporaryDirectory() as tmp:
            run = Path(tmp)
            self._case(run, "local_complete")
            (run / "local_missing").mkdir()
            (run / "batch_regression_state.json").write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "case_id": "local_complete",
                                "regression_scope": "FULL_E2E",
                            },
                            {
                                "case_id": "local_missing",
                                "regression_scope": "FULL_E2E",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = build_e2e_regression_report(run)

            self.assertEqual(report["full_e2e_scope_case_count"], 2)
            self.assertEqual(report["full_e2e_excluded_count"], 1)
            self.assertFalse(report["claims"]["full_batch_end_to_end_pass"])

    def test_final_hash_mismatch_fails_the_batch(self) -> None:
        with TemporaryDirectory() as tmp:
            run = Path(tmp)
            root = self._case(run)
            (root / "phase4_adaptive_final.mp4").write_bytes(b"changed")

            report = build_e2e_regression_report(run)

            self.assertEqual(report["status"], "FAILED")
            self.assertIn("final_hash", report["cases"][0]["failed_checks"])

    def test_mixed_runtime_voices_fail_the_batch(self) -> None:
        with TemporaryDirectory() as tmp:
            run = Path(tmp)
            self._case(run, "local_a")
            changed = self._case(run, "local_b")
            manifest_path = changed / "render_prep_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            provider = manifest["current_outputs"]["tts_clips"][0]["metadata"][
                "provider"
            ]
            provider["voice_id"] = "instruct:vi_male_north"
            manifest["provider_summary"]["voice_config"][
                "voice_id"
            ] = "instruct:vi_male_north"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = build_e2e_regression_report(run)

            self.assertEqual(report["status"], "FAILED")
            self.assertEqual(
                report["tts_provenance"]["status"], "RUNTIME_CONFIG_MISMATCH"
            )
            self.assertIn("tts_provenance", report["cases"][0]["failed_checks"])

    def test_missing_manifest_for_narration_fails_the_case(self) -> None:
        with TemporaryDirectory() as tmp:
            run = Path(tmp)
            root = self._case(run)
            (root / "render_prep_manifest.json").unlink()

            report = build_e2e_regression_report(run)

            self.assertEqual(report["status"], "FAILED")
            self.assertEqual(report["cases"][0]["tts"]["status"], "INVALID")
            self.assertIn("tts_provenance", report["cases"][0]["failed_checks"])

    def test_accepts_clean_operator_geometry_approval_for_phase1(self) -> None:
        with TemporaryDirectory() as tmp:
            run = Path(tmp)
            root = self._case(run)
            score_path = root / "phase1_score.json"
            score_path.write_text(json.dumps({"PASS": False}), encoding="utf-8")
            review = _self_hashed(
                {
                    "status": "PHASE1_GEOMETRY_OPERATOR_REVIEW_REQUIRED",
                    "phase1_refs": {
                        "phase1_score": {
                            "path": "phase1_score.json",
                            "sha256": hashlib.sha256(score_path.read_bytes()).hexdigest(),
                        }
                    },
                    "issues": [{"issue_id": "geometry-1"}],
                },
                "review_sha256",
            )
            review_path = root / "phase1_geometry_review.json"
            review_path.write_text(json.dumps(review), encoding="utf-8")
            approval = _self_hashed(
                {
                    "status": "PHASE1_GEOMETRY_OPERATOR_APPROVED",
                    "review_ref": {
                        "path": review_path.name,
                        "sha256": review["review_sha256"],
                    },
                    "decisions": [
                        {"issue_id": "geometry-1", "decision": "EXPLAIN_SHADOW"}
                    ],
                },
                "approval_sha256",
            )
            (root / "phase1_geometry_approval.json").write_text(
                json.dumps(approval), encoding="utf-8"
            )

            report = build_e2e_regression_report(run)

            self.assertEqual(report["status"], "PASS_CONTROLLED_E2E")
            self.assertTrue(report["cases"][0]["checks"]["phase1"])

    def test_accepts_hash_bound_operator_no_text_approval_for_phase1(self) -> None:
        with TemporaryDirectory() as tmp:
            run = Path(tmp)
            root = self._case(run)
            (root / "phase1_score.json").write_text(
                json.dumps({"PASS": False, "tracks": 0}), encoding="utf-8"
            )
            source = run / "source.webm"
            source.write_bytes(b"source")
            review = _self_hashed(
                {
                    "status": "NO_TEXT_OPERATOR_REVIEW_REQUIRED",
                    "source_video": {
                        "path": str(source),
                        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        "size_bytes": source.stat().st_size,
                    },
                },
                "review_sha256",
            )
            (root / "phase1_no_text_review.json").write_text(
                json.dumps(review), encoding="utf-8"
            )
            approval = _self_hashed(
                {
                    "status": "NO_TEXT_OPERATOR_APPROVED",
                    "decision": "NO_TEXT_CONFIRMED",
                    "review_ref": {
                        "path": "phase1_no_text_review.json",
                        "sha256": review["review_sha256"],
                    },
                },
                "approval_sha256",
            )
            (root / "phase1_no_text_approval.json").write_text(
                json.dumps(approval), encoding="utf-8"
            )

            report = build_e2e_regression_report(run)

            self.assertEqual(report["status"], "PASS_CONTROLLED_E2E")
            self.assertTrue(report["cases"][0]["checks"]["phase1"])


if __name__ == "__main__":
    unittest.main()
