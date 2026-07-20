"""Tests for production OCR box authority post-process."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.media_pipeline.ocr_filtering.ocr_box_authority import apply_best_box_authority


class OcrBoxAuthorityTests(unittest.TestCase):
    def test_apply_best_authority_refines_hardsub_geometry(self) -> None:
        h, w = 180, 320
        frame = np.full((h, w, 3), 25, dtype=np.uint8)
        frame[150:170, 40:280] = 245
        with tempfile.TemporaryDirectory() as tmp:
            jpeg = Path(tmp) / "f.jpg"
            cv2.imwrite(str(jpeg), frame)
            payload = {
                "frames": [
                    {
                        "time_ms": 0,
                        "path": str(jpeg),
                        "boxes": [
                            {
                                "x": 0.05,
                                "y": 0.82,
                                "w": 0.2,
                                "h": 0.06,
                                "text": "接着另起锅下入虾仁炒至变色",
                                "confidence": 0.99,
                            }
                        ],
                    }
                ]
            }
            out = apply_best_box_authority(payload, frame_paths=[jpeg])
            boxes = out["frames"][0]["boxes"]
            self.assertEqual(out.get("box_authority"), "best_v6_inkscan")
            self.assertEqual(len(boxes), 1)
            self.assertGreater(boxes[0]["w"], 0.4)
            self.assertGreater(boxes[0]["y"] + boxes[0]["h"] / 2.0, 0.85)


if __name__ == "__main__":
    unittest.main()
