from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.media_pipeline.frame_sampling.phase2_ocr_contract import (
    build_phase2_contract,
    parse_localization_policy,
    sha256_file,
    write_phase2_artifacts,
)


def _timeline() -> list[dict]:
    return [
        {
            "text_id": "sub_10",
            "start_frame": 126,
            "end_frame": 228,
            "box_coords": [74.0, 496.0, 250.0, 550.0],
            "crop_path": "crops/sub_10.jpg",
            "best_keyframe_path": "frames/sub_10.jpg",
            "ocr_text": "蒜末",
            "ocr_source": "crop",
        },
        {
            "text_id": "sub_13",
            "start_frame": 229,
            "end_frame": 230,
            "box_coords": [115.0, 380.0, 207.0, 435.0],
            "crop_path": "crops/sub_13.jpg",
            "best_keyframe_path": "frames/sub_13.jpg",
            "ocr_text": "蒜末",
            "ocr_source": "best_frame",
        },
        {
            "text_id": "sub_35",
            "start_frame": 677,
            "end_frame": 693,
            "box_coords": [1705.0, 551.0, 1874.0, 574.0],
            "ocr_text": "188千卡",
            "ocr_source": "crop",
        },
    ]


def _approve_all(contract: dict) -> dict[str, dict]:
    return {
        item["content_id"]: {
            "decision": "APPROVE",
            "ocr_text_approved": item["ocr_text_candidate"],
            "review_input_sha256": item["review_input_sha256"],
            "reviewer": "operator",
        }
        for item in contract["content_objects"]
    }


class LocalizationPolicyTests(unittest.TestCase):
    def test_numeric_unit_is_deterministic_and_preserves_value(self) -> None:
        policy = parse_localization_policy("188千卡")

        self.assertEqual(policy["mode"], "deterministic")
        self.assertEqual(policy["render_text_suggested"], "188 kcal")
        self.assertEqual(policy["protected_values"], ["188"])

    def test_mixed_label_protects_number_and_unit_for_llm(self) -> None:
        policy = parse_localization_policy("22.9克蛋白质")

        self.assertEqual(policy["mode"], "llm_with_protected_tokens")
        self.assertEqual(policy["protected_values"], ["22.9"])
        self.assertIn("{{VALUE_0}}", policy["translation_input"])
        self.assertIn("{{UNIT_0}}", policy["translation_input"])
        self.assertTrue(policy["translation_input"].endswith("蛋白质"))

    def test_ascii_gram_units_are_protected_inside_mixed_labels(self) -> None:
        for raw, value in (("锅中10g油", "10"), ("接着准备200g米饭", "200")):
            with self.subTest(raw=raw):
                policy = parse_localization_policy(raw)
                self.assertEqual(policy["mode"], "llm_with_protected_tokens")
                self.assertEqual(policy["protected_values"], [value])
                self.assertIn("{{VALUE_0}}", policy["translation_input"])
                self.assertIn("{{UNIT_0}}", policy["translation_input"])
                self.assertEqual(policy["unit_tokens"][0]["canonical"], "g")


class Phase2ContractTests(unittest.TestCase):
    def test_groups_same_content_across_multiple_geometry_refs(self) -> None:
        with TemporaryDirectory() as tmp:
            phase1 = Path(tmp) / "master_timeline.json"
            phase1.write_text(json.dumps(_timeline(), ensure_ascii=False), encoding="utf-8")

            contract = build_phase2_contract(
                _timeline(),
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
            )

            garlic = next(
                item
                for item in contract["content_objects"]
                if item["ocr_text_candidate"] == "蒜末"
            )
            self.assertEqual(garlic["geometry_refs"], ["sub_10", "sub_13"])
            self.assertEqual(len(garlic["review_assets"]), 2)
            self.assertEqual(
                garlic["review_assets"][0]["crop_path"], "crops/sub_10.jpg"
            )
            self.assertEqual(garlic["review_status"], "OCR_CANDIDATE")
            self.assertTrue(garlic["review_required"])
            self.assertEqual(contract["phase1_ref"]["sha256"], sha256_file(phase1))
            self.assertEqual(len(garlic["review_input_sha256"]), 64)

    def test_operator_corrected_transition_translates_once_for_both_geometries(self) -> None:
        with TemporaryDirectory() as tmp:
            phase1 = Path(tmp) / "master_timeline.json"
            timeline = [
                {
                    "text_id": "sub_08",
                    "start_frame": 341,
                    "end_frame": 354,
                    "box_coords": [500.0, 950.0, 800.0, 1030.0],
                    "ocr_text": "下入西",
                },
                {
                    "text_id": "sub_09",
                    "start_frame": 355,
                    "end_frame": 367,
                    "box_coords": [500.0, 950.0, 800.0, 1030.0],
                    "ocr_text": "下西",
                },
            ]
            phase1.write_text(
                json.dumps(timeline, ensure_ascii=False), encoding="utf-8"
            )
            pending = build_phase2_contract(
                timeline,
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
            )
            approvals = {
                item["content_id"]: {
                    "decision": "EDIT",
                    "ocr_text_approved": "下入西红柿",
                    "review_input_sha256": item["review_input_sha256"],
                    "reviewer": "operator",
                }
                for item in pending["content_objects"]
            }

            approved = build_phase2_contract(
                timeline,
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
                approvals=approvals,
            )

            self.assertEqual(len(approved["content_objects"]), 1)
            content = approved["content_objects"][0]
            self.assertEqual(content["geometry_refs"], ["sub_08", "sub_09"])
            self.assertEqual(
                content["source_content_ids"],
                ["ocr_content_001", "ocr_content_002"],
            )
            self.assertEqual(
                approved["duplicate_transition_summary"]["merged_content_objects"],
                1,
            )
            self.assertEqual(
                {row["content_id"] for row in approved["track_enrichments"]},
                {"ocr_content_001"},
            )

    def test_stale_or_missing_review_hash_cannot_approve_content(self) -> None:
        with TemporaryDirectory() as tmp:
            phase1 = Path(tmp) / "master_timeline.json"
            phase1.write_text(
                json.dumps(_timeline(), ensure_ascii=False), encoding="utf-8"
            )
            pending = build_phase2_contract(
                _timeline(),
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
            )
            content_id = pending["content_objects"][0]["content_id"]

            stale = build_phase2_contract(
                _timeline(),
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
                approvals={
                    content_id: {
                        "decision": "APPROVE",
                        "ocr_text_approved": "蒜末",
                        "review_input_sha256": "stale",
                    }
                },
            )
            reviewed = stale["content_objects"][0]

            self.assertEqual(reviewed["review_status"], "OCR_REVIEW_STALE")
            self.assertTrue(reviewed["review_required"])
            self.assertIsNone(reviewed["ocr_text_approved"])
            self.assertEqual(stale["review_summary"]["stale"], 1)
            self.assertEqual(stale["review_summary"]["status"], "OCR_REVIEW_STALE")

    def test_accept_llm_prefers_suggestion_over_prefilled_candidate(self) -> None:
        with TemporaryDirectory() as tmp:
            phase1 = Path(tmp) / "master_timeline.json"
            phase1.write_text(
                json.dumps(_timeline(), ensure_ascii=False), encoding="utf-8"
            )
            pending = build_phase2_contract(
                _timeline(),
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
            )
            garlic = next(
                item
                for item in pending["content_objects"]
                if item["ocr_text_candidate"] == "蒜末"
            )
            content_id = garlic["content_id"]

            suggested = build_phase2_contract(
                _timeline(),
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
                llm_suggestions={content_id: "蒜末末"},
            )
            suggested_garlic = next(
                item
                for item in suggested["content_objects"]
                if item["content_id"] == content_id
            )
            approved = build_phase2_contract(
                _timeline(),
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
                approvals={
                    content_id: {
                        "decision": "ACCEPT_LLM",
                        # The review template prefills this with the raw candidate.
                        "ocr_text_approved": "蒜末",
                        "review_input_sha256": suggested_garlic[
                            "review_input_sha256"
                        ],
                    }
                },
                llm_suggestions={content_id: "蒜末末"},
            )
            reviewed = next(
                item
                for item in approved["content_objects"]
                if item["content_id"] == content_id
            )

            self.assertEqual(reviewed["ocr_text_approved"], "蒜末末")
            self.assertEqual(reviewed["review_status"], "OCR_APPROVED")

    def test_accept_llm_recomputes_deterministic_render_text(self) -> None:
        with TemporaryDirectory() as tmp:
            phase1 = Path(tmp) / "master_timeline.json"
            phase1.write_text(
                json.dumps(_timeline(), ensure_ascii=False), encoding="utf-8"
            )
            pending = build_phase2_contract(
                _timeline(),
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
            )
            calories = next(
                item
                for item in pending["content_objects"]
                if item["ocr_text_candidate"] == "188千卡"
            )
            content_id = calories["content_id"]

            suggested = build_phase2_contract(
                _timeline(),
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
                llm_suggestions={content_id: "232千卡"},
            )
            suggested_calories = next(
                item
                for item in suggested["content_objects"]
                if item["content_id"] == content_id
            )
            approved = build_phase2_contract(
                _timeline(),
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
                approvals={
                    content_id: {
                        "decision": "ACCEPT_LLM",
                        "ocr_text_approved": "188千卡",
                        "vi_text_approved": "188 kcal",
                        "review_input_sha256": suggested_calories[
                            "review_input_sha256"
                        ],
                    }
                },
                llm_suggestions={content_id: "232千卡"},
            )
            reviewed = next(
                item
                for item in approved["content_objects"]
                if item["content_id"] == content_id
            )

            self.assertEqual(reviewed["ocr_text_approved"], "232千卡")
            self.assertEqual(reviewed["vi_text_approved"], "232 kcal")

    def test_operator_approval_is_required_before_final_payload(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            phase1 = root / "master_timeline.json"
            original = json.dumps(_timeline(), ensure_ascii=False, indent=2)
            phase1.write_text(original, encoding="utf-8")

            pending = build_phase2_contract(
                _timeline(),
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
            )
            paths = write_phase2_artifacts(
                root_dir=root,
                contract=pending,
                phase1_timeline=_timeline(),
                fps=30.0,
                frame_count=700,
                frame_width=1920,
                frame_height=1080,
            )

            self.assertEqual(phase1.read_text(encoding="utf-8"), original)
            self.assertTrue(paths["phase2_timeline"].is_file())
            self.assertTrue(paths["review_queue"].is_file())
            self.assertTrue(paths["preview_payload"].is_file())
            self.assertFalse((root / "ocr_payload.json").exists())
            approval_template = json.loads(
                paths["approvals"].read_text(encoding="utf-8")
            )
            self.assertEqual(
                len(approval_template["approvals"]),
                len(pending["content_objects"]),
            )
            self.assertEqual(
                approval_template["approvals"][0]["decision"], ""
            )
            self.assertEqual(
                approval_template["approvals"][0]["review_input_sha256"],
                pending["content_objects"][0]["review_input_sha256"],
            )
            self.assertTrue(paths["llm_suggestions"].is_file())

            approvals = _approve_all(pending)
            approved = build_phase2_contract(
                _timeline(),
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
                approvals=approvals,
            )
            paths = write_phase2_artifacts(
                root_dir=root,
                contract=approved,
                phase1_timeline=_timeline(),
                fps=30.0,
                frame_count=700,
                frame_width=1920,
                frame_height=1080,
            )

            self.assertEqual(approved["review_summary"]["unresolved"], 0)
            self.assertTrue(paths["final_payload"].is_file())
            self.assertEqual(phase1.read_text(encoding="utf-8"), original)
            payload = json.loads(
                paths["final_payload"].read_text(encoding="utf-8")
            )
            boxes = [
                box
                for frame in payload["frames"]
                for box in frame["boxes"]
                if box["text_id"] == "sub_35"
            ]
            self.assertTrue(boxes)
            self.assertEqual(boxes[0]["localization_mode"], "deterministic")
            self.assertEqual(boxes[0]["render_text_approved"], "188 kcal")
            self.assertNotIn("cover_only", boxes[0])
            self.assertTrue(paths["phase2_handoff"].is_file())
            handoff = json.loads(
                paths["phase2_handoff"].read_text(encoding="utf-8")
            )
            self.assertEqual(handoff["status"], "READY_FOR_PHASE3")
            self.assertEqual(handoff["counts"]["translate_items"], 1)
            self.assertEqual(handoff["counts"]["deterministic_items"], 1)
            self.assertEqual(handoff["counts"]["geometry_refs"], 3)
            self.assertFalse((root / "qa" / "translate_queue.json").exists())

    def test_pending_rerun_quarantines_stale_final_outputs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            phase1 = root / "master_timeline.json"
            phase1.write_text(
                json.dumps(_timeline(), ensure_ascii=False), encoding="utf-8"
            )
            pending = build_phase2_contract(
                _timeline(),
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
            )
            approved = build_phase2_contract(
                _timeline(),
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="ppocr-local-test",
                approvals=_approve_all(pending),
            )
            write_phase2_artifacts(
                root_dir=root,
                contract=approved,
                phase1_timeline=_timeline(),
                fps=30.0,
                frame_count=700,
                frame_width=1920,
                frame_height=1080,
            )
            self.assertTrue((root / "ocr_payload.json").is_file())
            self.assertTrue((root / "phase2_handoff.json").is_file())

            write_phase2_artifacts(
                root_dir=root,
                contract=pending,
                phase1_timeline=_timeline(),
                fps=30.0,
                frame_count=700,
                frame_width=1920,
                frame_height=1080,
            )

            self.assertFalse((root / "ocr_payload.json").exists())
            self.assertFalse((root / "phase2_handoff.json").exists())
            stale = list((root / "qa" / "stale").glob("*.json"))
            self.assertGreaterEqual(len(stale), 2)


class SemanticSceneRoleContractTests(unittest.TestCase):
    def test_preserves_semantic_scene_role_for_phase2_review(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            phase1 = root / "master_timeline.json"
            phase1.write_text("[]", encoding="utf-8")
            contract = build_phase2_contract(
                [
                    {
                        "text_id": "sub_01",
                        "start_frame": 0,
                        "end_frame": 19,
                        "box_coords": [450.0, 300.0, 700.0, 340.0],
                        "semantic_role": "semantic_scene_label",
                        "ocr_text": "Earth",
                    }
                ],
                phase1_timeline_path=phase1,
                provider_mode="local",
                model_version="test-model",
                frame_width=1920,
                frame_height=1080,
            )

            self.assertEqual(
                contract["content_objects"][0]["roles"],
                ["semantic_scene_label"],
            )
            self.assertEqual(
                contract["track_enrichments"][0]["ocr_role"],
                "semantic_scene_label",
            )


if __name__ == "__main__":
    unittest.main()
