"""Hybrid OCR: glyph-change keyframes and resumable OCR cache."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src.media_pipeline.ocr_filtering.hybrid_glyph_ocr import (
    GlyphSample,
    OcrResultCache,
    build_glyph_segments,
    glyph_mask_change_score,
    ocr_crop_cache_key,
    process_ocr_paths_with_cache,
    subtitle_glyph_mask,
    select_stable_glyph_keyframes,
)
from src.media_pipeline.ocr_filtering.types import DetectedTextBox, FrameOcrDetection


class HybridGlyphOcrTests(unittest.TestCase):
    def test_saturated_background_motion_does_not_change_caption_mask(self) -> None:
        a = np.zeros((180, 320, 3), dtype=np.uint8)
        b = np.zeros_like(a)
        a[145:180, :] = (0, 0, 180)
        b[145:180, :] = (0, 180, 0)
        for frame in (a, b):
            frame[158:166, 90:110] = 255
            frame[158:166, 125:145] = 255
            frame[158:166, 160:180] = 255

        mask_a = subtitle_glyph_mask(a, y0_norm=0.80)
        mask_b = subtitle_glyph_mask(b, y0_norm=0.80)

        self.assertLess(glyph_mask_change_score(mask_a, mask_b), 0.15)

    def test_selects_one_stable_keyframe_per_caption_change(self) -> None:
        a = np.zeros((24, 80), dtype=np.uint8)
        b = np.zeros_like(a)
        a[8:14, 10:35] = 255
        b[8:14, 42:70] = 255
        samples = [
            (0, 0, a),
            (1, 100, a),
            (2, 200, a),
            (3, 300, b),  # first changed frame: transition candidate
            (4, 400, b),  # stable confirmation
            (5, 500, b),
        ]

        keys = select_stable_glyph_keyframes(
            samples,
            change_threshold=0.4,
            stable_confirmations=2,
            min_gap_ms=100,
        )

        self.assertEqual([(k.frame_index, k.time_ms) for k in keys], [(1, 100), (4, 400)])

    def test_segment_first_ranks_best_candidates_inside_each_state(self) -> None:
        a = np.zeros((24, 80), dtype=np.uint8)
        b = np.zeros_like(a)
        a[8:14, 10:35] = 255
        b[8:14, 42:70] = 255
        samples = [
            GlyphSample(0, 0, a, 0.2),
            GlyphSample(1, 100, a, 0.9),
            GlyphSample(2, 200, a, 0.5),
            GlyphSample(3, 300, b, 0.1),
            GlyphSample(4, 400, b, 0.8),
            GlyphSample(5, 500, b, 0.6),
        ]

        segments = build_glyph_segments(
            samples,
            duration_ms=500,
            change_threshold=0.4,
            stable_confirmations=2,
            min_gap_ms=100,
            max_candidates=3,
        )

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].start_ms, 0)
        self.assertEqual(segments[0].candidate_times_ms[0], 100)
        self.assertEqual(segments[1].candidate_times_ms[0], 400)
        self.assertEqual(segments[-1].end_ms, 501)

    def test_cache_roundtrip_is_atomic_and_preserves_detection(self) -> None:
        detection = FrameOcrDetection(
            frame_width=320,
            frame_height=60,
            boxes=[
                DetectedTextBox(
                    x=0.1,
                    y=0.2,
                    width=0.7,
                    height=0.3,
                    text="测试字幕",
                    confidence=0.98,
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ocr-cache.json"
            cache = OcrResultCache(path)
            cache.put("abc", detection)
            cache.save()

            loaded = OcrResultCache(path)
            restored = loaded.get("abc")

        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.frame_width, 320)
        self.assertEqual(restored.boxes[0].text, "测试字幕")
        self.assertAlmostEqual(restored.boxes[0].confidence, 0.98)

    def test_cache_key_includes_authority_provider_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            crop = Path(tmp) / "crop.jpg"
            crop.write_bytes(b"same-image")
            first = ocr_crop_cache_key(crop, namespace="v3|provider=a|min=0.75")
            second = ocr_crop_cache_key(crop, namespace="v3|provider=b|min=0.75")
        self.assertNotEqual(first, second)

    def test_interrupted_batch_resumes_only_uncached_crop(self) -> None:
        detections = [
            FrameOcrDetection(
                frame_width=80,
                frame_height=24,
                boxes=(DetectedTextBox(0.1, 0.8, 0.5, 0.1, f"字幕{i}", 0.98),),
            )
            for i in range(3)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for i in range(3):
                path = root / f"{i}.jpg"
                path.write_bytes(f"crop-{i}".encode())
                paths.append(path)
            cache_path = root / "cache.json"
            with patch(
                "src.media_pipeline.ocr_filtering.hybrid_glyph_ocr.process_all_frames_sync",
                side_effect=[detections[:2], RuntimeError("interrupted")],
            ):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    process_ocr_paths_with_cache(
                        paths,
                        endpoint_url="https://provider.test/ocr",
                        cache_path=cache_path,
                        batch_size=2,
                    )

            with patch(
                "src.media_pipeline.ocr_filtering.hybrid_glyph_ocr.process_all_frames_sync",
                return_value=[detections[2]],
            ) as resumed:
                result = process_ocr_paths_with_cache(
                    paths,
                    endpoint_url="https://provider.test/ocr",
                    cache_path=cache_path,
                    batch_size=2,
                )

        self.assertEqual(
            [item.boxes[0].text for item in result],
            [item.boxes[0].text for item in detections],
        )
        self.assertEqual(len(resumed.call_args.args[0]), 1)


if __name__ == "__main__":
    unittest.main()
