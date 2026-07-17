"""OCR Phase 2 perf: band crop + remap, parallel detect, probe early-exit."""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.media_pipeline.ocr_filtering.pipeline import run_ocr_filtering
from src.media_pipeline.ocr_filtering.subtitle_band import (
    BOTTOM_BAND_RATIO,
    crop_bottom_band_jpeg,
    remap_box_from_band_crop,
    subtitle_band_top_normalized,
)
from src.media_pipeline.ocr_filtering.types import DetectedTextBox, FrameOcrDetection


def _write_solid_jpeg(path: Path, *, width: int = 100, height: int = 200) -> None:
    from PIL import Image

    Image.new("RGB", (width, height), color=(20, 40, 60)).save(path, format="JPEG", quality=85)


class BandCropGeometryTests(unittest.TestCase):
    def test_remap_box_from_band_crop_maps_into_full_frame(self) -> None:
        band = 0.28
        y0 = subtitle_band_top_normalized(band)
        crop_box = DetectedTextBox(x=0.1, y=0.25, width=0.5, height=0.2, text="硬", confidence=0.9)
        full = remap_box_from_band_crop(crop_box, band_ratio=band)
        self.assertAlmostEqual(full.x, 0.1)
        self.assertAlmostEqual(full.width, 0.5)
        self.assertAlmostEqual(full.y, y0 + 0.25 * band)
        self.assertAlmostEqual(full.height, 0.2 * band)
        self.assertEqual(full.text, "硬")

    def test_crop_bottom_band_jpeg_keeps_only_bottom_ratio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "frame.jpg"
            out = Path(tmp) / "band.jpg"
            _write_solid_jpeg(src, width=100, height=200)
            full_w, full_h, crop_h = crop_bottom_band_jpeg(src, out, band_ratio=0.25)
            self.assertEqual((full_w, full_h), (100, 200))
            self.assertEqual(crop_h, 50)
            self.assertTrue(out.is_file())
            from PIL import Image

            with Image.open(out) as img:
                self.assertEqual(img.size, (100, 50))


class OcrFilteringPerfPipelineTests(unittest.TestCase):
    def test_crop_before_ocr_remaps_provider_boxes_to_full_frame(self) -> None:
        """Provider sees crop image; boxes are crop-normalized then remapped."""
        band = 0.28
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame = root / "frame_000001.jpg"
            _write_solid_jpeg(frame, width=100, height=200)

            provider = MagicMock()
            provider.provider_name = "mock_crop"

            def _detect(path: Path) -> FrameOcrDetection:
                # Crop path must differ from full frame and be shorter.
                self.assertNotEqual(path.resolve(), frame.resolve())
                from PIL import Image

                with Image.open(path) as img:
                    self.assertEqual(img.size[1], 56)  # round(200 * 0.28)
                return FrameOcrDetection(
                    frame_width=100,
                    frame_height=56,
                    boxes=[
                        DetectedTextBox(0.1, 0.5, 0.8, 0.2, "BOTTOM", 0.95),
                    ],
                )

            provider.detect_image.side_effect = _detect
            result = run_ocr_filtering(
                [frame],
                ocr_provider=provider,
                frame_time_ms=[0],
                band_ratio=band,
                crop_band=True,
                concurrency=1,
                probe_stride=1,
            )
            self.assertEqual(result.frame_count, 1)
            box = result.frames[0].boxes[0]
            y0 = subtitle_band_top_normalized(band)
            self.assertAlmostEqual(box.y, y0 + 0.5 * band, places=5)
            self.assertAlmostEqual(box.height, 0.2 * band, places=5)
            self.assertEqual(result.frames[0].frame_width, 100)
            self.assertEqual(result.frames[0].frame_height, 200)

    def test_parallel_detect_runs_multiple_frames_concurrently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames = []
            for i in range(4):
                p = root / f"frame_{i:06d}.jpg"
                _write_solid_jpeg(p)
                frames.append(p)

            active = 0
            max_active = 0
            lock = threading.Lock()
            provider = MagicMock()
            provider.provider_name = "mock_parallel"

            def _detect(_path: Path) -> FrameOcrDetection:
                nonlocal active, max_active
                with lock:
                    active += 1
                    max_active = max(max_active, active)
                time.sleep(0.05)
                with lock:
                    active -= 1
                return FrameOcrDetection(
                    100,
                    200,
                    [DetectedTextBox(0.1, 0.5, 0.5, 0.2, "x", 0.9)],
                )

            provider.detect_image.side_effect = _detect
            run_ocr_filtering(
                frames,
                ocr_provider=provider,
                crop_band=True,
                concurrency=4,
                probe_stride=1,
            )
            self.assertGreaterEqual(max_active, 2)
            self.assertEqual(provider.detect_image.call_count, 4)

    def test_probe_early_exit_skips_unprobed_frames_when_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames = []
            for i in range(6):
                p = root / f"frame_{i:06d}.jpg"
                _write_solid_jpeg(p)
                frames.append(p)

            provider = MagicMock()
            provider.provider_name = "mock_probe"
            provider.detect_image.return_value = FrameOcrDetection(100, 200, boxes=[])

            result = run_ocr_filtering(
                frames,
                ocr_provider=provider,
                crop_band=True,
                concurrency=2,
                probe_stride=2,
                early_exit_empty_probe=True,
            )
            # Probe indices 0,2,4 → 3 OCR calls; 1,3,5 skipped
            self.assertEqual(provider.detect_image.call_count, 3)
            self.assertEqual(result.frame_count, 6)
            self.assertTrue(all(len(f.boxes) == 0 for f in result.frames))
            self.assertIn("ocr_probe_empty_early_exit", result.warnings)

    def test_probe_hit_triggers_ocr_on_remaining_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames = []
            for i in range(4):
                p = root / f"frame_{i:06d}.jpg"
                _write_solid_jpeg(p)
                frames.append(p)

            provider = MagicMock()
            provider.provider_name = "mock_probe_hit"

            def _detect(path: Path) -> FrameOcrDetection:
                # Any probe hit (crop-relative box in band)
                return FrameOcrDetection(
                    100,
                    56,
                    [DetectedTextBox(0.1, 0.4, 0.5, 0.2, "hit", 0.9)],
                )

            provider.detect_image.side_effect = _detect
            result = run_ocr_filtering(
                frames,
                ocr_provider=provider,
                crop_band=True,
                concurrency=2,
                probe_stride=2,
                early_exit_empty_probe=True,
            )
            self.assertEqual(provider.detect_image.call_count, 4)
            self.assertTrue(any(f.boxes for f in result.frames))
            self.assertNotIn("ocr_probe_empty_early_exit", result.warnings)


if __name__ == "__main__":
    unittest.main()
