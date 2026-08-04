"""Pre-Phase-3 OCR gate: translate_ready, split, purge, typo repair, dedupe."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.media_pipeline.frame_sampling.ocr_translate_gate import (
    dedupe_overlapping_translate_tracks,
    finalize_ocr_for_translate,
    repair_ocr_typos,
    split_caption_and_ui,
    evaluate_translate_gate,
)
from src.media_pipeline.frame_sampling.master_phase1_extractor import (
    timeline_to_ocr_payload,
)


class TypoRepairTests(unittest.TestCase):
    def test_common_cooking_typos(self) -> None:
        self.assertEqual(repair_ocr_typos("水开上锅蒸15分钢"), "水开上锅蒸15分钟")
        self.assertEqual(repair_ocr_typos("虾位豆腐蒸蛋"), "虾仁豆腐蒸蛋")


class SplitSuspectTests(unittest.TestCase):
    def test_splits_caption_from_kcal(self) -> None:
        cap, ui = split_caption_and_ui("虾仁豆腐蒸蛋634千卡")
        self.assertEqual(cap, "虾仁豆腐蒸蛋")
        self.assertEqual(ui, "634千卡")

    def test_no_split_when_pure_caption(self) -> None:
        cap, ui = split_caption_and_ui("加盐")
        self.assertEqual(cap, "加盐")
        self.assertIsNone(ui)


class TranslateGateTests(unittest.TestCase):
    def test_rejects_kcal_only_and_noise(self) -> None:
        ready, reason, text = evaluate_translate_gate(
            {
                "ocr_text": "614千卡",
                "box_coords": [100.0, 0.0, 300.0, 40.0],
            },
            frame_w=1920,
            frame_h=1080,
        )
        self.assertFalse(ready)
        self.assertIn(reason, {"ui_numeric", "ui_chip", "noise"})

        ready2, _r2, _t2 = evaluate_translate_gate(
            {
                "ocr_text": "产",
                "box_coords": [800.0, 480.0, 900.0, 530.0],
            },
            frame_w=1920,
            frame_h=1080,
        )
        self.assertFalse(ready2)

        ready3, _r3, text3 = evaluate_translate_gate(
            {
                "ocr_text": "加盐",
                "box_coords": [800.0, 480.0, 1000.0, 530.0],
            },
            frame_w=1920,
            frame_h=1080,
        )
        self.assertTrue(ready3)
        self.assertEqual(text3, "加盐")

    def test_suspect_split_keeps_caption_ready(self) -> None:
        ready, reason, text = evaluate_translate_gate(
            {
                "ocr_text": "虾仁豆腐蒸蛋634千卡",
                "ocr_suspect": True,
                "box_coords": [0.0, 900.0, 1200.0, 980.0],
            },
            frame_w=1920,
            frame_h=1080,
        )
        self.assertTrue(ready)
        self.assertEqual(text, "虾仁豆腐蒸蛋")
        self.assertEqual(reason, "split_ui")

    def test_preserves_pure_ui_unit_for_deterministic_localization(self) -> None:
        ready, reason, text = evaluate_translate_gate(
            {
                "ocr_text": "千卡",
                "box_coords": [1250.0, 389.0, 1297.0, 412.0],
            },
            frame_w=1920,
            frame_h=1080,
        )

        self.assertTrue(ready)
        self.assertEqual(reason, "ok")
        self.assertEqual(text, "千卡")


class DedupeTests(unittest.TestCase):
    def test_overlapping_similar_text_keeps_one_primary(self) -> None:
        tracks = [
            {
                "text_id": "sub_01",
                "start_frame": 10,
                "end_frame": 40,
                "box_coords": [100.0, 900.0, 500.0, 960.0],
                "ocr_text": "虾仁豆腐蒸蛋",
                "translate_ready": True,
            },
            {
                "text_id": "sub_02",
                "start_frame": 20,
                "end_frame": 50,
                "box_coords": [110.0, 905.0, 510.0, 965.0],
                "ocr_text": "虾仁豆腐蒸蛋",
                "translate_ready": True,
            },
        ]
        out = dedupe_overlapping_translate_tracks(tracks)
        ready = [t for t in out if t.get("translate_ready")]
        self.assertEqual(len(ready), 1)

    def test_adjacent_same_text_keeps_longer_primary(self) -> None:
        tracks = [
            {
                "text_id": "sub_10",
                "start_frame": 126,
                "end_frame": 228,
                "ocr_text": "蒜末",
                "translate_ready": True,
            },
            {
                "text_id": "sub_13",
                "start_frame": 229,
                "end_frame": 230,
                "ocr_text": "蒜末",
                "translate_ready": True,
            },
        ]

        out = dedupe_overlapping_translate_tracks(tracks)

        self.assertTrue(out[0]["translate_ready"])
        self.assertFalse(out[1]["translate_ready"])
        self.assertEqual(out[1]["translate_reject_reason"], "dedupe_secondary")
        self.assertEqual(out[1]["translate_primary_id"], "sub_10")


class FinalizePipelineTests(unittest.TestCase):
    def test_writes_queue_and_payload_skips_non_ready(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline = [
                {
                    "text_id": "sub_01",
                    "start_frame": 0,
                    "end_frame": 10,
                    "box_coords": [80.0, 900.0, 900.0, 960.0],
                    "ocr_text": "加盐",
                    "ocr_source": "crop",
                },
                {
                    "text_id": "sub_02",
                    "start_frame": 0,
                    "end_frame": 10,
                    "box_coords": [100.0, 50.0, 250.0, 90.0],
                    "ocr_text": "614千卡",
                    "ocr_source": "crop",
                },
                {
                    "text_id": "sub_03",
                    "start_frame": 0,
                    "end_frame": 10,
                    "box_coords": [80.0, 900.0, 900.0, 960.0],
                    "ocr_text": "水开上锅蒸15分钢",
                    "ocr_source": "crop",
                },
            ]
            out, audit = finalize_ocr_for_translate(
                timeline,
                qa_dir=root / "qa",
                frame_w=1920,
                frame_h=1080,
            )
            queue_path = root / "qa" / "translate_queue.json"
            self.assertTrue(queue_path.is_file())
            self.assertTrue(out[0]["translate_ready"])
            self.assertFalse(out[1]["translate_ready"])
            self.assertEqual(out[2]["ocr_text"], "水开上锅蒸15分钟")
            self.assertIn("ready", audit)

            payload = timeline_to_ocr_payload(
                out,
                fps=30.0,
                frame_count=20,
                frame_width=1920,
                frame_height=1080,
            )
            boxes = payload["frames"][0]["boxes"]
            by_id = {b["text_id"]: b for b in boxes}
            self.assertEqual(by_id["sub_01"]["text"], "加盐")
            self.assertTrue(by_id["sub_02"].get("cover_only"))
            self.assertEqual(by_id["sub_02"].get("text") or "", "")

    def test_failed_ocr_is_reviewable_but_numeric_reject_is_cover_only(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline = [
                {
                    "text_id": "sub_01",
                    "start_frame": 0,
                    "end_frame": 20,
                    "box_coords": [600.0, 980.0, 1300.0, 1040.0],
                    "ocr_text": "",
                    "ocr_source": "failed",
                },
                {
                    "text_id": "sub_02",
                    "start_frame": 21,
                    "end_frame": 30,
                    "box_coords": [100.0, 50.0, 300.0, 90.0],
                    "ocr_text": "188千卡",
                    "ocr_source": "crop",
                },
            ]

            out, audit = finalize_ocr_for_translate(
                timeline,
                qa_dir=root / "qa",
                frame_w=1920,
                frame_h=1080,
            )

            self.assertTrue(out[0]["ocr_review_required"])
            self.assertEqual(out[0]["translate_reject_reason"], "ocr_failed")
            self.assertFalse(out[1]["ocr_review_required"])
            self.assertEqual(audit["review_required"], 1)

            queue = (root / "qa" / "translate_queue.json").read_text(
                encoding="utf-8"
            )
            self.assertIn('"ocr_review_required": true', queue)


if __name__ == "__main__":
    unittest.main()
