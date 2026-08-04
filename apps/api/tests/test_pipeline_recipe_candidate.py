from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.services.pipeline_recipe_candidate import build_pipeline_recipe_candidate
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


class PipelineRecipeCandidateTests(unittest.TestCase):
    def test_builds_non_locking_v23_candidate_with_current_hardening(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _self_hashed(
                {
                    "schema_version": "pipeline_recipe_lock_v3",
                    "status": "LOCKED_FOR_CONTROLLED_PILOT_WITH_GAPS",
                    "phase1": {"extractor": "v58_candidate"},
                    "phase2": {"provider": "local"},
                    "phase3": {},
                    "tts": {},
                    "render": {"background_mix_gain": 0.22},
                    "audio_authority": {},
                    "operator_gates": ["SOURCE_RIGHTS_AND_MUSIC_APPROVED"],
                    "execution": {"external_publish": False},
                },
                "recipe_sha256",
            )
            report = _self_hashed(
                {
                    "status": "PASS_TO_OPERATOR_GATES",
                    "case_count": 1,
                    "phase1_execution_pass_count": 1,
                    "phase1_accepted_count": 1,
                    "phase2_execution_pass_count": 1,
                    "operator_review_object_count": 0,
                    "open_incident_count": 0,
                    "corpus_gaps": {"orientation": ["portrait"]},
                    "cases": [
                        {"status": "WAITING_SOURCE_RIGHTS_AND_MUSIC_REVIEW"}
                    ],
                },
                "report_sha256",
            )
            fixture = _self_hashed(
                {"status": "READY_FOR_VALIDATION", "cases": [{}]},
                "fixture_sha256",
            )
            fixture_report = _self_hashed(
                {
                    "status": "PASS",
                    "case_count": 1,
                    "passed_count": 1,
                    "failed_count": 0,
                    "fixture_ref": {
                        "fixture_sha256": fixture["fixture_sha256"]
                    },
                },
                "report_sha256",
            )
            e2e = _self_hashed(
                _with_tts_provenance(
                    root,
                    {
                    "status": "PASS_CONTROLLED_E2E",
                    "case_count": 1,
                    "passed_count": 1,
                    "excluded_case_count": 1,
                    "claims": {
                        "included_cases_end_to_end_pass": True,
                        "full_batch_end_to_end_pass": False,
                    },
                    },
                ),
                "report_sha256",
            )
            paths = {}
            for name, payload in {
                "pipeline_recipe_current.json": base,
                "report.json": report,
                "fixture.json": fixture,
                "fixture_report.json": fixture_report,
                "e2e.json": e2e,
            }.items():
                path = root / name
                path.write_text(json.dumps(payload), encoding="utf-8")
                paths[name] = path
            versioned_base = root / f"pipeline_recipe_{base['recipe_sha256']}.json"
            versioned_base.write_bytes(paths["pipeline_recipe_current.json"].read_bytes())

            candidate = build_pipeline_recipe_candidate(
                workspace_root=root,
                base_recipe_path=paths["pipeline_recipe_current.json"],
                report_path=paths["report.json"],
                fixture_path=paths["fixture.json"],
                fixture_report_path=paths["fixture_report.json"],
                e2e_report_path=paths["e2e.json"],
                output_path=root / "candidate.json",
            )

            self.assertEqual(candidate["status"], "VALIDATED_CANDIDATE_WITH_GAPS")
            self.assertEqual(candidate["render"]["background_mix_gain"], 1.0)
            self.assertEqual(
                candidate["render"]["layout_policies"]["dense_group"],
                "source_relative_dense_group_v1",
            )
            self.assertFalse(candidate["claims"]["recipe_lock_recommended"])
            self.assertIn(
                "PENDING_SOURCE_RIGHTS_AND_MUSIC_REVIEW", candidate["blockers"]
            )
            self.assertTrue((root / "candidate.json").is_file())
            self.assertEqual(candidate["tts"]["provider"], "omnivoice")
            self.assertEqual(
                candidate["tts"]["voice_id"], "instruct:vi_female_north"
            )
            self.assertEqual(
                candidate["tts"]["authority"], "e2e_render_prep_manifests_v1"
            )
            self.assertEqual(
                candidate["base_recipe"]["path"], versioned_base.name
            )

    def test_accepts_operator_approved_no_text_as_terminal_phase2_bypass(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _self_hashed(
                {
                    "schema_version": "pipeline_recipe_lock_v3",
                    "status": "LOCKED_FOR_CONTROLLED_PILOT_WITH_GAPS",
                    "phase1": {},
                    "phase2": {},
                    "phase3": {},
                    "tts": {},
                    "render": {},
                    "audio_authority": {},
                    "operator_gates": [],
                    "execution": {"external_publish": False},
                },
                "recipe_sha256",
            )
            report = _self_hashed(
                {
                    "status": "PASS_TO_OPERATOR_GATES",
                    "case_count": 2,
                    "phase1_execution_pass_count": 2,
                    "phase1_accepted_count": 2,
                    "phase2_execution_pass_count": 1,
                    "no_text_approved_case_count": 1,
                    "operator_review_object_count": 0,
                    "open_incident_count": 0,
                    "corpus_gaps": {},
                    "cases": [],
                },
                "report_sha256",
            )
            fixture = _self_hashed(
                {"status": "READY_FOR_VALIDATION", "cases": [{}]},
                "fixture_sha256",
            )
            fixture_report = _self_hashed(
                {
                    "status": "PASS",
                    "case_count": 1,
                    "passed_count": 1,
                    "failed_count": 0,
                    "fixture_ref": {"fixture_sha256": fixture["fixture_sha256"]},
                },
                "report_sha256",
            )
            paths = {}
            for name, payload in {
                "base.json": base,
                "report.json": report,
                "fixture.json": fixture,
                "fixture_report.json": fixture_report,
            }.items():
                path = root / name
                path.write_text(json.dumps(payload), encoding="utf-8")
                paths[name] = path

            candidate = build_pipeline_recipe_candidate(
                workspace_root=root,
                base_recipe_path=paths["base.json"],
                report_path=paths["report.json"],
                fixture_path=paths["fixture.json"],
                fixture_report_path=paths["fixture_report.json"],
                output_path=root / "candidate.json",
            )

            self.assertTrue(candidate["claims"]["automated_batch_execution_pass"])
            self.assertIn("E2E_REPORT_NOT_AVAILABLE", candidate["blockers"])


if __name__ == "__main__":
    unittest.main()
