"""Phase 2 OCR filtering: keep only bottom-1/3 subtitle-band boxes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.media_pipeline.ocr_filtering.errors import OcrFilteringError, OcrFilteringErrorCode
from src.media_pipeline.ocr_filtering.pipeline import run_ocr_filtering
from src.media_pipeline.ocr_filtering.providers import MockOcrProvider, RetryingOcrProvider
from src.media_pipeline.ocr_filtering.subtitle_band import (
    BOTTOM_BAND_RATIO,
    filter_subtitle_band_boxes,
    is_in_subtitle_band,
)
from src.media_pipeline.ocr_filtering.types import DetectedTextBox


class SubtitleBandFilterTests(unittest.TestCase):
    def test_keeps_only_bottom_third_boxes(self) -> None:
        # Frame 1000px tall → bottom 1/3 starts at y=666.67 (normalized 0.666...)
        boxes = [
            DetectedTextBox(x=0.1, y=0.10, width=0.3, height=0.05, text="logo", confidence=0.9),
            DetectedTextBox(x=0.2, y=0.40, width=0.4, height=0.08, text="mid", confidence=0.9),
            DetectedTextBox(x=0.1, y=0.78, width=0.8, height=0.10, text="硬字幕", confidence=0.95),
            DetectedTextBox(x=0.15, y=0.70, width=0.5, height=0.06, text="subtitle", confidence=0.92),
        ]
        kept = filter_subtitle_band_boxes(boxes, band_ratio=BOTTOM_BAND_RATIO)
        texts = [b.text for b in kept]
        self.assertEqual(texts, ["硬字幕", "subtitle"])
        self.assertTrue(all(is_in_subtitle_band(b, band_ratio=BOTTOM_BAND_RATIO) for b in kept))
        self.assertFalse(is_in_subtitle_band(boxes[0], band_ratio=BOTTOM_BAND_RATIO))
        self.assertFalse(is_in_subtitle_band(boxes[1], band_ratio=BOTTOM_BAND_RATIO))

    def test_exact_band_boundary_uses_center_y(self) -> None:
        # center_y == 2/3 → still in band (inclusive lower boundary of bottom third)
        height = 0.10
        y = (2.0 / 3.0) - (height / 2.0)
        box_on_boundary = DetectedTextBox(x=0.1, y=y, width=0.2, height=height, text="edge", confidence=0.8)
        self.assertAlmostEqual(box_on_boundary.center_y, 2.0 / 3.0, places=9)
        self.assertTrue(is_in_subtitle_band(box_on_boundary, band_ratio=BOTTOM_BAND_RATIO))


class OcrFilteringPipelineTests(unittest.TestCase):
    def test_run_ocr_filtering_links_timecode_and_filtered_boxes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame_a = root / "frame_000001.jpg"
            frame_b = root / "frame_000002.jpg"
            frame_a.write_bytes(b"fake-jpg-a")
            frame_b.write_bytes(b"fake-jpg-b")

            provider = MockOcrProvider(
                boxes_by_stem={
                    "frame_000001": [
                        DetectedTextBox(0.1, 0.2, 0.2, 0.05, "TOP", 0.9),
                        DetectedTextBox(0.1, 0.8, 0.7, 0.1, "BOTTOM_A", 0.95),
                    ],
                    "frame_000002": [
                        DetectedTextBox(0.1, 0.75, 0.6, 0.1, "BOTTOM_B", 0.93),
                    ],
                },
                frame_size=(1000, 1000),
            )
            result = run_ocr_filtering(
                [frame_a, frame_b],
                ocr_provider=provider,
                frame_time_ms=[0, 1000],
            )
            payload = result.to_dict()
            self.assertEqual(payload["frame_count"], 2)
            self.assertEqual(len(payload["frames"]), 2)
            self.assertEqual(payload["frames"][0]["frame_id"], "frame_000001")
            self.assertEqual(payload["frames"][0]["time_ms"], 0)
            self.assertEqual([b["text"] for b in payload["frames"][0]["boxes"]], ["BOTTOM_A"])
            self.assertEqual(payload["frames"][1]["time_ms"], 1000)
            self.assertEqual([b["text"] for b in payload["frames"][1]["boxes"]], ["BOTTOM_B"])
            # Normalized xywh present
            box0 = payload["frames"][0]["boxes"][0]
            self.assertIn("x", box0)
            self.assertIn("y", box0)
            self.assertIn("width", box0)
            self.assertIn("height", box0)

    def test_retrying_provider_retries_then_succeeds(self) -> None:
        primary = MagicMock()
        primary.provider_name = "flaky"
        primary.detect_image.side_effect = [
            OcrFilteringError(OcrFilteringErrorCode.OCR_PROVIDER_FAILED, "transient"),
            MagicMock(
                frame_width=100,
                frame_height=100,
                boxes=[DetectedTextBox(0.1, 0.8, 0.5, 0.1, "ok", 0.9)],
            ),
        ]
        provider = RetryingOcrProvider(primary, max_attempts=3, base_delay_seconds=0.0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame_000001.jpg"
            path.write_bytes(b"x")
            result = provider.detect_image(path)
        self.assertEqual(result.boxes[0].text, "ok")
        self.assertEqual(primary.detect_image.call_count, 2)


if __name__ == "__main__":
    unittest.main()
