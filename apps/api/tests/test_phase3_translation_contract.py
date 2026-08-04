from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from src.media_pipeline.translator.config import TranslatorSettings
from src.media_pipeline.translator.phase3_contract import (
    Phase3TranslationError,
    translate_phase3_handoff,
    write_phase3_artifacts,
)


def _handoff() -> dict:
    return {
        "schema_version": "phase2_handoff_v1",
        "phase1_ref": {"path": "master_timeline.json", "sha256": "1" * 64},
        "phase2_ref": {"path": "phase2_ocr_timeline.json", "sha256": "2" * 64},
        "status": "READY_FOR_PHASE3",
        "blocked_reasons": [],
        "counts": {
            "content_objects": 3,
            "translate_items": 2,
            "deterministic_items": 1,
            "cover_only_items": 0,
            "geometry_refs": 3,
        },
        "translate_items": [
            {
                "content_id": "ocr_content_001",
                "geometry_refs": ["sub_01"],
                "roles": ["hardsub"],
                "zh_approved": "锅中10g油",
                "translation_input": "锅中{{VALUE_0}} {{UNIT_0}}油",
                "protected_values": ["10"],
                "unit_tokens": [{"raw": "g", "canonical": "g"}],
            },
            {
                "content_id": "ocr_content_002",
                "geometry_refs": ["sub_02"],
                "roles": ["mid_label"],
                "zh_approved": "陈醋1勺",
                "translation_input": "陈醋{{VALUE_0}} {{UNIT_0}}",
                "protected_values": ["1"],
                "unit_tokens": [{"raw": "勺", "canonical": "thìa"}],
            },
        ],
        "deterministic_items": [
            {
                "content_id": "ocr_content_003",
                "geometry_refs": ["sub_03"],
                "roles": ["ui_chip"],
                "zh_approved": "510千卡",
                "render_text": "510 kcal",
                "protected_values": ["510"],
                "unit_tokens": [{"raw": "千卡", "canonical": "kcal"}],
            }
        ],
        "cover_only_items": [],
        "geometry_map": {
            "sub_01": {"content_id": "ocr_content_001"},
            "sub_02": {"content_id": "ocr_content_002"},
            "sub_03": {"content_id": "ocr_content_003"},
        },
    }


def _settings() -> TranslatorSettings:
    return TranslatorSettings(
        api_key="secret",
        base_url="https://example.test/v1",
        model_name="caption-test",
        system_prompt="Dịch ngắn gọn.",
        source="workspace_db",
    )


def _client(payload: dict[str, str]) -> MagicMock:
    response = MagicMock()
    response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps(payload, ensure_ascii=False)
            )
        )
    ]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def _client_raw(payload: object) -> MagicMock:
    response = MagicMock()
    response.choices = [
        MagicMock(
            message=MagicMock(content=json.dumps(payload, ensure_ascii=False))
        )
    ]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


class Phase3TranslationTests(unittest.TestCase):
    def test_normalizes_workspace_prompt_list_response_by_exact_content_id(self) -> None:
        client = _client_raw(
            [
                {
                    "id": "ocr_content_001",
                    "translated_text": "Cho {{VALUE_0}} {{UNIT_0}} dầu vào chảo",
                },
                {
                    "id": "ocr_content_002",
                    "translated_text": "Giấm đen {{VALUE_0}} {{UNIT_0}}",
                },
            ]
        )
        with TemporaryDirectory() as tmp:
            contract = translate_phase3_handoff(
                _handoff(),
                settings=_settings(),
                client=client,
                memory_path=Path(tmp) / "memory.json",
            )
        rows = {row["content_id"]: row for row in contract["content_objects"]}
        self.assertEqual(
            rows["ocr_content_002"]["vi_text_candidate"], "Giấm đen 1 muỗng"
        )

    def test_rejects_response_with_wrong_content_ids(self) -> None:
        client = _client_raw(
            [
                {"id": "ocr_content_001", "translated_text": "Một"},
                {"id": "wrong_id", "translated_text": "Hai"},
            ]
        )
        with TemporaryDirectory() as tmp:
            with self.assertRaises(Phase3TranslationError):
                translate_phase3_handoff(
                    _handoff(),
                    settings=_settings(),
                    client=client,
                    memory_path=Path(tmp) / "memory.json",
                )

    def test_batches_by_content_id_and_restores_protected_tokens(self) -> None:
        client = _client(
            {
                "ocr_content_001": "Cho {{VALUE_0}} {{UNIT_0}} dầu vào chảo",
                "ocr_content_002": "Giấm đen {{VALUE_0}} {{UNIT_0}}",
            }
        )
        with TemporaryDirectory() as tmp:
            contract = translate_phase3_handoff(
                _handoff(),
                settings=_settings(),
                client=client,
                memory_path=Path(tmp) / "memory.json",
            )

        self.assertEqual(client.chat.completions.create.call_count, 1)
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["temperature"], 0)
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        user_payload = json.loads(kwargs["messages"][1]["content"])
        self.assertEqual(user_payload["ocr_content_001"]["role"], "hardsub")
        self.assertEqual(
            user_payload["ocr_content_002"]["text"],
            "陈醋{{VALUE_0}} {{UNIT_0}}",
        )

        rows = {row["content_id"]: row for row in contract["content_objects"]}
        self.assertEqual(rows["ocr_content_001"]["vi_text_candidate"], "Cho 10 g dầu vào chảo")
        self.assertEqual(rows["ocr_content_002"]["vi_text_candidate"], "Giấm đen 1 muỗng")
        self.assertEqual(rows["ocr_content_002"]["review_status"], "TRANSLATION_CANDIDATE")
        self.assertIsNone(rows["ocr_content_002"]["vi_text_approved"])
        self.assertEqual(rows["ocr_content_003"]["review_status"], "TRANSLATION_DETERMINISTIC")
        self.assertEqual(rows["ocr_content_003"]["vi_text_approved"], "510 kcal")
        self.assertEqual(contract["review_summary"]["unresolved"], 2)

    def test_missing_placeholder_fails_closed(self) -> None:
        client = _client(
            {
                "ocr_content_001": "Cho dầu vào chảo",
                "ocr_content_002": "Giấm đen {{VALUE_0}} {{UNIT_0}}",
            }
        )
        with TemporaryDirectory() as tmp:
            contract = translate_phase3_handoff(
                _handoff(),
                settings=_settings(),
                client=client,
                memory_path=Path(tmp) / "memory.json",
            )
        row = next(
            item
            for item in contract["content_objects"]
            if item["content_id"] == "ocr_content_001"
        )
        self.assertEqual(row["review_status"], "TRANSLATION_FAILED")
        self.assertIn("protected_token_mismatch", row["quality_flags"])
        self.assertIsNone(row["vi_text_candidate"])

    def test_operator_edit_cannot_change_protected_value_or_unit(self) -> None:
        client = _client(
            {
                "ocr_content_001": "Cho {{VALUE_0}} {{UNIT_0}} dầu vào chảo",
                "ocr_content_002": "Giấm đen {{VALUE_0}} {{UNIT_0}}",
            }
        )
        with TemporaryDirectory() as tmp:
            memory_path = Path(tmp) / "memory.json"
            first = translate_phase3_handoff(
                _handoff(),
                settings=_settings(),
                client=client,
                memory_path=memory_path,
            )
            row = next(
                item
                for item in first["content_objects"]
                if item["content_id"] == "ocr_content_002"
            )
            second = translate_phase3_handoff(
                _handoff(),
                settings=_settings(),
                client=client,
                memory_path=memory_path,
                approvals={
                    "ocr_content_002": {
                        "decision": "EDIT",
                        "review_input_sha256": row["review_input_sha256"],
                        "vi_text_approved": "Giấm đen 2 muỗng",
                    }
                },
            )
        edited = next(
            item
            for item in second["content_objects"]
            if item["content_id"] == "ocr_content_002"
        )
        self.assertEqual(edited["review_status"], "TRANSLATION_REVIEW_INVALID")
        self.assertTrue(edited["review_required"])
        self.assertIsNone(edited["vi_text_approved"])
        self.assertIn("approval_protected_token_mismatch", edited["quality_flags"])

    def test_approved_proposal_fossil_prevents_candidate_memory_drift(self) -> None:
        first_client = _client(
            {
                "ocr_content_001": "Cho {{VALUE_0}} {{UNIT_0}} dầu vào chảo",
                "ocr_content_002": "Giấm đen {{VALUE_0}} {{UNIT_0}}",
            }
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_path = root / "phase2_handoff.json"
            handoff_path.write_text(
                json.dumps(_handoff(), ensure_ascii=False), encoding="utf-8"
            )
            first = translate_phase3_handoff(
                _handoff(),
                settings=_settings(),
                client=first_client,
                memory_path=root / "memory.json",
                phase2_handoff_path=handoff_path,
            )
            review_rows = {
                row["content_id"]: row
                for row in first["content_objects"]
                if row["review_required"]
            }
            approvals = {
                content_id: {
                    "decision": "APPROVE",
                    "review_input_sha256": row["review_input_sha256"],
                    "vi_text_approved": row["vi_text_candidate"],
                }
                for content_id, row in review_rows.items()
            }
            fossils = {
                content_id: {
                    "vi_text_candidate": row["vi_text_candidate"],
                    "quality_flags": row["quality_flags"],
                    "review_input_sha256": row["review_input_sha256"],
                }
                for content_id, row in review_rows.items()
            }
            unused_client = MagicMock()
            second = translate_phase3_handoff(
                _handoff(),
                settings=_settings(),
                client=unused_client,
                memory_path=root / "memory.json",
                approvals=approvals,
                review_fossils=fossils,
                phase2_handoff_path=handoff_path,
            )

        unused_client.chat.completions.create.assert_not_called()
        self.assertEqual(second["stats"]["review_fossil_hits"], 2)
        self.assertEqual(second["review_summary"]["unresolved"], 0)
        self.assertEqual(second["review_summary"]["status"], "TRANSLATION_APPROVED")

    def test_writes_review_artifacts_but_not_final_before_approval(self) -> None:
        client = _client(
            {
                "ocr_content_001": "Cho {{VALUE_0}} {{UNIT_0}} dầu vào chảo",
                "ocr_content_002": "Giấm đen {{VALUE_0}} {{UNIT_0}}",
            }
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_path = root / "phase2_handoff.json"
            handoff_path.write_text(
                json.dumps(_handoff(), ensure_ascii=False), encoding="utf-8"
            )
            contract = translate_phase3_handoff(
                _handoff(),
                settings=_settings(),
                client=client,
                memory_path=root / "qa" / "phase3_translation_memory.json",
                phase2_handoff_path=handoff_path,
            )
            paths = write_phase3_artifacts(root_dir=root, contract=contract)

            self.assertTrue(paths["timeline"].is_file())
            self.assertTrue(paths["review_queue"].is_file())
            self.assertTrue(paths["approvals"].is_file())
            self.assertTrue(paths["render_handoff_preview"].is_file())
            self.assertFalse(paths["render_handoff"].exists())
            approvals = json.loads(paths["approvals"].read_text(encoding="utf-8"))
            self.assertEqual(len(approvals["approvals"]), 2)
            self.assertEqual(approvals["approvals"][0]["decision"], "")

    def test_rejects_non_ready_phase2_handoff(self) -> None:
        handoff = _handoff()
        handoff["status"] = "HANDOFF_BLOCKED"
        with self.assertRaises(Phase3TranslationError):
            translate_phase3_handoff(
                handoff,
                settings=_settings(),
                client=_client({}),
            )


if __name__ == "__main__":
    unittest.main()
