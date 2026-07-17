"""Paddle OCR result parser accepts classic ocr() and predict() page payloads."""

from __future__ import annotations

import unittest

from src.ocr_pipeline.providers import _parse_paddle_ocr_result


class ParsePaddleOcrResultTests(unittest.TestCase):
    def test_parse_classic_ocr_lines(self) -> None:
        raw = [
            [
                [[[10, 100], [200, 100], [200, 140], [10, 140]], ("字幕", 0.97)],
            ]
        ]
        boxes = _parse_paddle_ocr_result(raw, width=1000, height=1000)
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0].text, "字幕")
        self.assertAlmostEqual(boxes[0].x, 0.01, places=3)
        self.assertAlmostEqual(boxes[0].y, 0.1, places=3)

    def test_parse_predict_page_dict(self) -> None:
        raw = [
            {
                "dt_polys": [
                    [[10, 800], [400, 800], [400, 860], [10, 860]],
                    [[20, 200], [100, 200], [100, 230], [20, 230]],
                ],
                "rec_texts": ["硬字幕", "标题"],
                "rec_scores": [0.95, 0.88],
            }
        ]
        boxes = _parse_paddle_ocr_result(raw, width=1000, height=1000)
        self.assertEqual(len(boxes), 2)
        self.assertEqual(boxes[0].text, "硬字幕")
        self.assertAlmostEqual(boxes[0].y, 0.8, places=2)
        self.assertEqual(boxes[1].text, "标题")


if __name__ == "__main__":
    unittest.main()
