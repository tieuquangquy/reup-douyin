"""OCR payload boxes must keep real geometry after best-box authority (w/h keys)."""

from __future__ import annotations

import unittest

from src.media_pipeline.video_renderer.overlays import overlays_from_ocr_payload
from src.ocr_pipeline.media_ocr_adapter import frame_results_from_ocr_payload


class OverlayBoxKeyTests(unittest.TestCase):
    def test_overlays_from_payload_accepts_w_h_keys(self) -> None:
        payload = {
            "frames": [
                {
                    "frame_id": "t4594",
                    "time_ms": 4594,
                    "boxes": [
                        {
                            "x": 0.12,
                            "y": 0.88,
                            "w": 0.72,
                            "h": 0.06,
                            "text": "这是个适合中国胃的减脂餐",
                            "confidence": 0.99,
                        }
                    ],
                }
            ]
        }
        vi = {"4594#0": "Bua an giam mo"}
        overlays = overlays_from_ocr_payload(payload, vi, hold_ms=500)
        self.assertEqual(len(overlays), 1)
        self.assertAlmostEqual(overlays[0].width, 0.72, places=3)
        self.assertAlmostEqual(overlays[0].height, 0.06, places=3)

    def test_frame_results_from_payload_accepts_w_h_keys(self) -> None:
        payload = {
            "frames": [
                {
                    "time_ms": 1000,
                    "frame_width": 1080,
                    "frame_height": 1920,
                    "boxes": [
                        {
                            "x": 0.1,
                            "y": 0.8,
                            "w": 0.65,
                            "h": 0.08,
                            "text": "测试",
                            "confidence": 0.95,
                        }
                    ],
                }
            ]
        }
        frames = frame_results_from_ocr_payload(payload)
        self.assertEqual(len(frames), 1)
        self.assertAlmostEqual(frames[0].boxes[0].width, 0.65, places=3)
        self.assertAlmostEqual(frames[0].boxes[0].height, 0.08, places=3)


if __name__ == "__main__":
    unittest.main()
