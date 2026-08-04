from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from src.media_pipeline.video_renderer.adaptive_output_qa import (
    RESIDUAL_CJK_POLICY_VERSION,
)
from src.media_pipeline.video_renderer.render_policy import RENDER_POLICY_VERSION
from src.services.pipeline_recipe_lock import lock_pipeline_recipe
from src.services.pipeline_tts_provenance import (
    aggregate_tts_provenance,
    extract_case_tts_provenance,
)


def _self_hashed(payload: dict, field: str) -> dict:
    result = dict(payload)
    encoded = json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    result[field] = hashlib.sha256(encoded).hexdigest()
    return result


def _with_tts_provenance(root: Path, payload: dict) -> dict:
    case_root = root / "local_tts"
    case_root.mkdir(exist_ok=True)
    (case_root / "render_prep_manifest.json").write_text(
        json.dumps(
            {
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
    case = {
        "case_id": case_root.name,
        "render": {"audio_strategy": "replace_with_vietnamese_narration"},
        "tts": extract_case_tts_provenance(
            case_root=case_root,
            run_root=root,
            audio_strategy="replace_with_vietnamese_narration",
        ),
    }
    result = {**payload, "cases": [case]}
    result["tts_provenance"] = aggregate_tts_provenance(result["cases"])
    return result


def _runtime_tts(e2e: dict) -> dict:
    provenance = dict(e2e["tts_provenance"])
    return {
        "provider": provenance["provider"],
        "model_id": provenance["model_id"],
        "voice_id": provenance["voice_id"],
        "language_code": provenance["language_code"],
        "speaking_rate": provenance["speaking_rate"],
        "authority": "e2e_render_prep_manifests_v1",
        "runtime_config_sha256": provenance["runtime_config_sha256"],
        "verified_case_count": provenance["tts_case_count"],
    }


class PipelineRecipeLockTests(unittest.TestCase):
    def test_locks_v58_without_authority_v36_full_duration(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = _self_hashed(
                {
                    "schema_version": "pipeline_regression_corpus_v1",
                    "real_video_gaps": {"orientation": ["portrait"]},
                },
                "corpus_sha256",
            )
            report = _self_hashed(
                {
                    "status": "PASS_TO_OPERATOR_GATES",
                    "case_count": 1,
                    "phase1_pass_count": 1,
                    "phase2_execution_pass_count": 1,
                    "cases": [
                        {"phase2": {"model_version": "ppocrv6-medium-det-rec"}}
                    ],
                },
                "report_sha256",
            )
            corpus_path = root / "corpus.json"
            report_path = root / "report.json"
            corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
            report_path.write_text(json.dumps(report), encoding="utf-8")
            settings = SimpleNamespace(
                audio_tts_provider="edge",
                audio_tts_voice_id="vi-VN-HoaiMyNeural",
                audio_tts_speaking_rate=1.0,
                render_video_encoder="auto",
                render_hardware_encoder_smoke_probe=True,
                render_hardware_encoder_fallback_enabled=True,
                render_background_mix_gain=0.22,
                render_loudness_target_lufs=-14.0,
            )

            result = lock_pipeline_recipe(
                workspace_root=root,
                corpus_path=corpus_path,
                report_path=report_path,
                output_dir=root / "recipes",
                operator_id="operator",
                settings=settings,
            )

            recipe = result["recipe"]
            self.assertEqual(
                recipe["status"], "LOCKED_FOR_CONTROLLED_PILOT_WITH_GAPS"
            )
            self.assertEqual(recipe["phase1"]["extractor"], "v58_candidate")
            self.assertFalse(recipe["phase1"]["authority_v3_6_full_duration"])
            self.assertEqual(
                recipe["phase1"]["final_coverage_fade_tail_max_frames"], 5
            )
            guard = recipe["phase1"]["post_refinement_sparse_compact_guard"]
            self.assertEqual(
                guard["policy_version"],
                "post_refinement_sparse_compact_text_consensus_v1",
            )
            self.assertEqual(guard["max_height_frac"], 0.065)
            self.assertEqual(
                guard["recognizer_failure_policy"],
                "fail_soft_to_operator_review",
            )
            self.assertFalse(recipe["claims"]["universal_video_support"])
            self.assertTrue(result["versioned_path"].is_file())
            repeated = lock_pipeline_recipe(
                workspace_root=root,
                corpus_path=corpus_path,
                report_path=report_path,
                output_dir=root / "recipes",
                operator_id="operator",
                settings=settings,
            )
            self.assertEqual(
                recipe["recipe_sha256"], repeated["recipe"]["recipe_sha256"]
            )

    def test_operator_approved_no_text_case_counts_as_phase2_bypass(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = _self_hashed(
                {
                    "schema_version": "pipeline_regression_corpus_v1",
                    "real_video_gaps": {"lighting": ["light"]},
                },
                "corpus_sha256",
            )
            report = _self_hashed(
                {
                    "status": "PASS_TO_OPERATOR_GATES",
                    "case_count": 2,
                    "phase1_pass_count": 1,
                    "phase1_accepted_count": 2,
                    "phase2_execution_pass_count": 1,
                    "no_text_approved_case_count": 1,
                    "operator_review_object_count": 0,
                    "open_incident_count": 0,
                    "cases": [
                        {"phase2": {"model_version": "ppocrv6-medium-det-rec"}},
                        {"phase2": {"model_version": None}},
                    ],
                },
                "report_sha256",
            )
            corpus_path = root / "corpus.json"
            report_path = root / "report.json"
            corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
            report_path.write_text(json.dumps(report), encoding="utf-8")

            result = lock_pipeline_recipe(
                workspace_root=root,
                corpus_path=corpus_path,
                report_path=report_path,
                output_dir=root / "recipes",
                operator_id="operator",
                settings=SimpleNamespace(),
            )

            self.assertEqual(
                result["recipe"]["claims"]["approved_no_text_bypass_count"], 1
            )

    def test_binds_passing_e2e_evidence_and_new_audio_render_policies(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = _self_hashed(
                {
                    "schema_version": "pipeline_regression_corpus_v1",
                    "real_video_gaps": {"motion": ["high"]},
                },
                "corpus_sha256",
            )
            report = _self_hashed(
                {
                    "status": "PASS_TO_OPERATOR_GATES",
                    "case_count": 1,
                    "phase1_pass_count": 1,
                    "phase2_execution_pass_count": 1,
                    "operator_review_object_count": 0,
                    "open_incident_count": 0,
                    "cases": [{"phase2": {"model_version": "ppocr"}}],
                },
                "report_sha256",
            )
            e2e = _self_hashed(
                _with_tts_provenance(
                    root,
                    {
                    "status": "PASS_CONTROLLED_E2E",
                    "case_count": 3,
                    "passed_count": 3,
                    "db_handoff_ready_count": 3,
                    "external_publish_triggered_count": 0,
                    },
                ),
                "report_sha256",
            )
            corpus_path = root / "corpus.json"
            report_path = root / "report.json"
            e2e_path = root / "e2e.json"
            corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
            report_path.write_text(json.dumps(report), encoding="utf-8")
            e2e_path.write_text(json.dumps(e2e), encoding="utf-8")

            result = lock_pipeline_recipe(
                workspace_root=root,
                corpus_path=corpus_path,
                report_path=report_path,
                e2e_report_path=e2e_path,
                output_dir=root / "recipes",
                operator_id="operator",
                settings=SimpleNamespace(),
            )

            recipe = result["recipe"]
            self.assertTrue(recipe["claims"]["full_batch_end_to_end_pass"])
            self.assertEqual(recipe["claims"]["end_to_end_case_count"], 3)
            self.assertEqual(
                recipe["evidence"]["e2e_report"]["report_sha256"],
                e2e["report_sha256"],
            )
            self.assertEqual(
                recipe["render"]["residual_cjk_policy"]["policy_version"],
                RESIDUAL_CJK_POLICY_VERSION,
            )
            self.assertEqual(
                recipe["render"]["layout_policies"]["dense_group"],
                "source_relative_dense_group_v1",
            )
            self.assertEqual(
                recipe["render"]["layout_policies"]["semantic_dedup"],
                "semantic_render_dedup_v1",
            )
            self.assertEqual(
                recipe["audio_authority"]["no_dialogue_source_audio"][
                    "policy_version"
                ],
                "verified_silero_no_dialogue_source_audio_v1",
            )
            self.assertEqual(recipe["tts"]["provider"], "omnivoice")
            self.assertEqual(
                recipe["tts"]["voice_id"], "instruct:vi_female_north"
            )

    def test_binds_phase4_closeout_and_release_label_without_e2e_claim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            run.mkdir()
            corpus = _self_hashed(
                {
                    "schema_version": "pipeline_regression_corpus_v1",
                    "real_video_gaps": {"orientation": ["portrait"]},
                },
                "corpus_sha256",
            )
            report = _self_hashed(
                {
                    "status": "PASS_TO_OPERATOR_GATES",
                    "case_count": 1,
                    "phase1_pass_count": 1,
                    "phase2_execution_pass_count": 1,
                    "operator_review_object_count": 0,
                    "open_incident_count": 0,
                    "cases": [{"phase2": {"model_version": "ppocr"}}],
                },
                "report_sha256",
            )
            corpus_path = root / "corpus.json"
            report_path = run / "report.json"
            corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
            report_path.write_text(json.dumps(report), encoding="utf-8")
            state = _self_hashed(
                {"status": "PASS_TO_OPERATOR_GATES"}, "run_sha256"
            )
            state_path = run / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            preflight = _self_hashed(
                {"status": "READY_FOR_PHASE4"}, "batch_preflight_sha256"
            )
            preflight_path = run / "preflight.json"
            preflight_path.write_text(json.dumps(preflight), encoding="utf-8")
            closeout = _self_hashed(
                {
                    "status": "PASS_CONTROLLED_PHASE4_PREFLIGHT",
                    "case_count": 1,
                    "counts": {
                        "ready_for_phase4": 1,
                        "blocked": 0,
                        "operator_touch_required": 0,
                        "operator_review_objects": 0,
                        "open_incidents": 0,
                        "residual_cjk_detections": 0,
                        "collision_events": 0,
                    },
                    "evidence": {
                        "corpus": {
                            "path": corpus_path.relative_to(root).as_posix(),
                            "sha256": hashlib.sha256(
                                corpus_path.read_bytes()
                            ).hexdigest(),
                            "corpus_sha256": corpus["corpus_sha256"],
                        },
                        "batch_state": {
                            "path": state_path.relative_to(run).as_posix(),
                            "sha256": hashlib.sha256(
                                state_path.read_bytes()
                            ).hexdigest(),
                            "run_sha256": state["run_sha256"],
                        },
                        "regression_report": {
                            "path": report_path.relative_to(run).as_posix(),
                            "sha256": hashlib.sha256(
                                report_path.read_bytes()
                            ).hexdigest(),
                            "report_sha256": report["report_sha256"],
                        },
                        "phase4_batch_preflight": {
                            "path": preflight_path.relative_to(run).as_posix(),
                            "sha256": hashlib.sha256(
                                preflight_path.read_bytes()
                            ).hexdigest(),
                            "batch_preflight_sha256": preflight[
                                "batch_preflight_sha256"
                            ],
                        },
                    },
                    "claims": {
                        "controlled_pilot_ready_through_phase4_preflight": True,
                        "full_batch_end_to_end_pass": False,
                    },
                },
                "closeout_sha256",
            )
            closeout_path = run / "closeout.json"
            closeout_path.write_text(json.dumps(closeout), encoding="utf-8")

            result = lock_pipeline_recipe(
                workspace_root=root,
                corpus_path=corpus_path,
                report_path=report_path,
                closeout_path=closeout_path,
                output_dir=root / "recipes",
                operator_id="operator",
                release_label="V22.1",
                settings=SimpleNamespace(),
            )

            recipe = result["recipe"]
            self.assertEqual(recipe["schema_version"], "pipeline_recipe_lock_v3")
            self.assertEqual(recipe["release_label"], "V22.1")
            self.assertTrue(
                recipe["claims"][
                    "controlled_pilot_ready_through_phase4_preflight"
                ]
            )
            self.assertFalse(recipe["claims"]["full_batch_end_to_end_pass"])
            self.assertEqual(
                recipe["render"]["role_policy_version"],
                RENDER_POLICY_VERSION,
            )
            self.assertEqual(
                recipe["evidence"]["phase4_preflight_closeout"][
                    "closeout_sha256"
                ],
                closeout["closeout_sha256"],
            )

    def test_binds_validated_candidate_to_v23_lock(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = _self_hashed(
                {"real_video_gaps": {"orientation": ["portrait"]}},
                "corpus_sha256",
            )
            report = _self_hashed(
                {
                    "status": "PASS_TO_OPERATOR_GATES",
                    "case_count": 1,
                    "phase1_pass_count": 1,
                    "phase2_execution_pass_count": 1,
                    "operator_review_object_count": 0,
                    "open_incident_count": 0,
                    "cases": [{"phase2": {"model_version": "ppocr"}}],
                },
                "report_sha256",
            )
            e2e = _self_hashed(
                _with_tts_provenance(
                    root,
                    {
                    "status": "PASS_CONTROLLED_E2E",
                    "case_count": 3,
                    "passed_count": 3,
                    "db_handoff_ready_count": 3,
                    "external_publish_triggered_count": 0,
                    },
                ),
                "report_sha256",
            )
            runtime_tts = _runtime_tts(e2e)
            candidate = _self_hashed(
                {
                    "schema_version": "pipeline_recipe_candidate_v1",
                    "status": "VALIDATED_CANDIDATE_WITH_GAPS",
                    "release_label": "V23",
                    "blockers": [],
                    "claims": {"recipe_lock_recommended": True},
                    "tts": runtime_tts,
                    "render": {
                        "role_policy_version": RENDER_POLICY_VERSION,
                        "background_mix_gain": 1.0,
                        "layout_policies": {
                            "dense_group": "source_relative_dense_group_v1",
                            "semantic_dedup": "semantic_render_dedup_v1",
                        },
                        "source_text_provenance": {
                            "moving_object_region": (
                                "operator_hash_bound_moving_object_region_v1"
                            )
                        },
                    },
                    "evidence": {
                        "batch_report": {
                            "report_sha256": report["report_sha256"]
                        },
                        "e2e_report": {"report_sha256": e2e["report_sha256"]},
                    },
                },
                "candidate_sha256",
            )
            paths = {}
            for name, payload in {
                "corpus.json": corpus,
                "report.json": report,
                "e2e.json": e2e,
                "candidate.json": candidate,
            }.items():
                path = root / name
                path.write_text(json.dumps(payload), encoding="utf-8")
                paths[name] = path

            result = lock_pipeline_recipe(
                workspace_root=root,
                corpus_path=paths["corpus.json"],
                report_path=paths["report.json"],
                e2e_report_path=paths["e2e.json"],
                candidate_path=paths["candidate.json"],
                output_dir=root / "recipes",
                operator_id="operator",
                release_label="V23",
                settings=SimpleNamespace(render_background_mix_gain=1.0),
            )

            self.assertEqual(result["recipe"]["release_label"], "V23")
            self.assertEqual(
                result["recipe"]["evidence"]["recipe_candidate"][
                    "candidate_sha256"
                ],
                candidate["candidate_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
