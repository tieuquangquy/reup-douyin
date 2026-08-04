"""Tests for SKE-run → CloudOCRAnalyzer crop bridge."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.media_pipeline.ocr_filtering.analyze_ocr import (
    export_analyze_result,
    load_crop_items_from_ske_dir,
)


class SkeBridgeTests(unittest.TestCase):
    def test_load_crops_from_ske_summary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            frame = np.full((100, 200, 3), 180, dtype=np.uint8)
            frame[20:50, 40:160] = (30, 30, 30)
            cv2.imwrite(str(root / "keyframe_000_f000010.jpg"), frame)
            summary = {
                "fps": 30.0,
                "keyframes": [
                    {
                        "frame_index": 10,
                        "approx_time_s": 0.333,
                        "frame_file": "keyframe_000_f000010.jpg",
                        "boxes": [
                            {"x0": 40, "y0": 20, "x1": 160, "y1": 50},
                            {"x0": 10, "y0": 10, "x1": 30, "y1": 25},
                        ],
                    }
                ],
            }
            (root / "summary.json").write_text(
                json.dumps(summary),
                encoding="utf-8",
            )
            items = load_crop_items_from_ske_dir(root)
            self.assertEqual(len(items), 2)
            self.assertAlmostEqual(float(items[0]["timestamp"]), 0.333, places=3)
            self.assertEqual(items[0]["original_box_coords"], [40.0, 20.0, 160.0, 50.0])
            crop = items[0]["image_crop"]
            self.assertEqual(crop.ndim, 3)
            # Recognition crop is padded vs tight box (30px tall → taller after pad).
            self.assertGreater(crop.shape[0], 30)
            self.assertGreater(crop.shape[1], 120)
            # Must not mutate summary box dicts.
            self.assertEqual(summary["keyframes"][0]["boxes"][0]["x0"], 40)

    def test_export_analyze_result_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            grouped = {
                "00:05.500": [
                    {"text": "减脂", "box": [1, 2, 3, 2, 3, 4, 1, 4]},
                ]
            }
            path = export_analyze_result(
                grouped,
                out,
                meta={"source": "test"},
            )
            self.assertTrue(path.is_file())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("00:05.500", payload["results"])
            self.assertEqual(payload["results"]["00:05.500"][0]["text"], "减脂")
            self.assertEqual(payload["meta"]["source"], "test")


if __name__ == "__main__":
    unittest.main()
