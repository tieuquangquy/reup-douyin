"""Unit tests for SmartKeyframeExtractor (blur, centroid track, enhance)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from src.media_pipeline.frame_sampling.ensure_fsrcnn_model import (
    default_fsrcnn_model_path,
    ensure_fsrcnn_pb,
)
from src.media_pipeline.frame_sampling.smart_keyframe_extractor import (
    BoundingBoxXYXY,
    SmartKeyframeExtractor,
    centroids_from_boxes,
    filter_valid_text_boxes,
    has_new_centroid,
)


class FilterValidTextBoxesTests(unittest.TestCase):
    """Generalized chrome + geometry + zone filter (hardsub / mid / UI burn-in)."""

    def test_keeps_bottom_hardsub_landscape_and_portrait(self) -> None:
        for w, h in ((1920, 1080), (1080, 1920)):
            with self.subTest(w=w, h=h):
                # Long caption in bottom third (hardsub band).
                y0 = int(0.78 * h)
                y1 = int(0.84 * h)
                x0 = int(0.08 * w)
                x1 = int(0.72 * w)
                sub = BoundingBoxXYXY(x0, y0, x1, y1)
                kept = filter_valid_text_boxes([sub], w, h)
                self.assertEqual(len(kept), 1, f"expected hardsub kept on {w}x{h}")

    def test_keeps_mid_instruction_and_nutrition_ui_label(self) -> None:
        w, h = 1920, 1080
        # Mid-frame short instruction (like 加盐) — content_ui_label path.
        mid = BoundingBoxXYXY(312, 516, 414, 552)
        # Nutrition card label (like 鸡蛋).
        label = BoundingBoxXYXY(162, 492, 276, 522)
        kept = filter_valid_text_boxes([mid, label], w, h)
        self.assertEqual(len(kept), 2)

    def test_keeps_borderline_ui_label_width_0_04(self) -> None:
        """Fat-like label ~0.047W must keep after min-width 0.04 (was dropped at 0.05)."""
        w, h = 1920, 1080
        fat = BoundingBoxXYXY(246.0, 156.0, 336.0, 192.0)  # bw=90 → 0.0469W
        kept = filter_valid_text_boxes([fat], w, h)
        self.assertEqual(len(kept), 1)

    def test_keeps_large_mid_title(self) -> None:
        w, h = 1920, 1080
        # Wide mid-title: cy≈0.4, bw≥0.18, bh≥0.035
        title = BoundingBoxXYXY(400, 380, 1500, 460)
        kept = filter_valid_text_boxes([title], w, h)
        self.assertEqual(kept, [title])

    def test_drops_salt_texture_near_square_f075(self) -> None:
        """Real f075 salt blobs on yolks must not reach OCR."""
        w, h = 1920, 1080
        salt_a = BoundingBoxXYXY(744.0, 690.0, 858.0, 786.0)  # aspect ~1.19
        salt_b = BoundingBoxXYXY(954.0, 558.0, 1074.0, 684.0)  # near-square
        tiny = BoundingBoxXYXY(1020.0, 594.0, 1038.0, 612.0)
        kept = filter_valid_text_boxes([salt_a, salt_b, tiny], w, h)
        self.assertEqual(kept, [])

    def test_drops_rice_texture_false_positive_with_edge_gate(self) -> None:
        """Rice grains lack ink strokes → DROP; hardsub with ink → KEEP."""
        w, h = 1920, 1080
        frame = np.full((h, w, 3), 215, dtype=np.uint8)
        # Soft speckles (blurred) mimic rice without stroke ink.
        rng = np.random.default_rng(0)
        noise = rng.integers(200, 230, size=(105, 278, 3), dtype=np.uint8)
        frame[480:585, 761:1039] = noise
        frame[480:585, 761:1039] = cv2.GaussianBlur(frame[480:585, 761:1039], (7, 7), 0)
        rice_fp = BoundingBoxXYXY(761.0, 480.0, 1039.0, 585.0)
        caption = BoundingBoxXYXY(9.0, 929.0, 966.0, 976.0)
        # White glyphs on dark band → ink evidence.
        frame[929:976, 9:966] = (20, 20, 20)
        for x in range(20, 950, 28):
            frame[935:970, x : x + 10] = (240, 240, 240)
        kept = filter_valid_text_boxes([rice_fp, caption], w, h, frame_bgr=frame)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0], caption)

    def test_dense_overlay_keeps_right_calorie_and_short_eggs_label(self) -> None:
        """Full-card nutrition: right-side kcal + short 鸡蛋 must KEEP (not Douyin rail)."""
        w, h = 1920, 1080
        # Seed many horizontal labels to trigger dense burn-in layout.
        boxes = [
            BoundingBoxXYXY(230, 98, 379, 127),
            BoundingBoxXYXY(80, 148, 361, 185),
            BoundingBoxXYXY(228, 215, 447, 241),
            BoundingBoxXYXY(11, 404, 331, 430),
            BoundingBoxXYXY(145, 494, 305, 523),
            BoundingBoxXYXY(153, 546, 240, 567),
            BoundingBoxXYXY(148, 635, 224, 664),  # 鸡蛋-like ~76px
            BoundingBoxXYXY(147, 687, 237, 708),
            BoundingBoxXYXY(152, 776, 298, 805),
            BoundingBoxXYXY(143, 828, 241, 849),
            BoundingBoxXYXY(1697, 518, 1840, 544),  # right kcal cx~0.92
            BoundingBoxXYXY(1703, 656, 1843, 685),
        ]
        # Synthetic high-edge crops so edge gate does not block.
        frame = np.full((h, w, 3), 40, dtype=np.uint8)
        for b in boxes:
            x0, y0, x1, y1 = int(b.x0), int(b.y0), int(b.x1), int(b.y1)
            frame[y0:y1, x0:x1] = 40
            for x in range(x0 + 2, x1 - 2, 8):
                frame[y0 + 2 : y1 - 2, x : x + 3] = 240
        kept = filter_valid_text_boxes(boxes, w, h, frame_bgr=frame)
        self.assertGreaterEqual(len(kept), 10)
        self.assertTrue(any(abs(b.x0 - 148) < 1 for b in kept))
        self.assertTrue(any(b.x0 > 1600 for b in kept))

    def test_dense_drops_food_thumbnail_keeps_gray_label(self) -> None:
        """Nutrition card: saturated isotropic food photo DROP; gray UI label KEEP."""
        w, h = 1920, 1080
        seed = [
            BoundingBoxXYXY(230, 98, 379, 127),
            BoundingBoxXYXY(80, 148, 361, 185),
            BoundingBoxXYXY(228, 215, 447, 241),
            BoundingBoxXYXY(11, 404, 331, 430),
            BoundingBoxXYXY(145, 494, 305, 523),
            BoundingBoxXYXY(153, 546, 240, 567),
            BoundingBoxXYXY(148, 635, 224, 664),
            BoundingBoxXYXY(147, 687, 237, 708),
            BoundingBoxXYXY(152, 776, 298, 805),
            BoundingBoxXYXY(143, 828, 241, 849),
            BoundingBoxXYXY(1697, 518, 1840, 544),
            BoundingBoxXYXY(1703, 656, 1843, 685),
        ]
        # Real-ish shrimp-row: food thumb + grams label in hardsub band.
        food = BoundingBoxXYXY(50.0, 935.0, 100.0, 960.0)  # 50x25
        grams = BoundingBoxXYXY(144.0, 962.0, 220.0, 992.0)  # 76x30
        boxes = [*seed, food, grams]
        frame = np.full((h, w, 3), 245, dtype=np.uint8)
        for b in seed:
            x0, y0, x1, y1 = int(b.x0), int(b.y0), int(b.x1), int(b.y1)
            frame[y0:y1, x0:x1] = 40
            for x in range(x0 + 2, x1 - 2, 8):
                frame[y0 + 2 : y1 - 2, x : x + 3] = 240
        # Shrimp-like photo: low-chroma flesh (trips ink) + saturated isotropic texture.
        rng = np.random.default_rng(7)
        fy0, fy1, fx0, fx1 = 935, 960, 50, 100
        hh, ww = fy1 - fy0, fx1 - fx0
        yy, xx = np.mgrid[0:hh, 0:ww]
        # Soft radial blobs (isotropic edges), not axis-aligned glyph bars.
        base = np.full((hh, ww, 3), (170, 185, 200), dtype=np.float32)
        for _ in range(12):
            cy = float(rng.uniform(3, hh - 3))
            cx = float(rng.uniform(3, ww - 3))
            rad = float(rng.uniform(3.0, 8.0))
            dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
            mask = np.clip(1.0 - dist / rad, 0.0, 1.0)[..., None]
            color = np.array(
                [
                    float(rng.integers(30, 90)),
                    float(rng.integers(70, 150)),
                    float(rng.integers(150, 230)),
                ],
                dtype=np.float32,
            )
            base = base * (1.0 - mask) + color * mask
        # Low-chroma dark/bright patches for ink evidence.
        base[5:11, 10:18] = (45, 48, 50)
        base[15:21, 28:38] = (225, 228, 230)
        patch = np.clip(base, 0, 255).astype(np.uint8)
        frame[fy0:fy1, fx0:fx1] = cv2.GaussianBlur(patch, (7, 7), 0)
        # Low-sat gray digits for 52克-like label.
        frame[962:992, 144:220] = 250
        for x in range(148, 216, 10):
            frame[966:988, x : x + 4] = 40
        kept = filter_valid_text_boxes(boxes, w, h, frame_bgr=frame)
        self.assertFalse(any(abs(b.x0 - 50.0) < 1 and abs(b.y0 - 935.0) < 1 for b in kept))
        self.assertTrue(any(abs(b.x0 - 144.0) < 1 for b in kept))

    def test_dense_keeps_single_cjk_char_aspect(self) -> None:
        """Dense card: single-char box aspect ~0.73 (虾-like) with strokes must KEEP."""
        w, h = 1920, 1080
        seed = [
            BoundingBoxXYXY(230, 98, 379, 127),
            BoundingBoxXYXY(80, 148, 361, 185),
            BoundingBoxXYXY(228, 215, 447, 241),
            BoundingBoxXYXY(11, 404, 331, 430),
            BoundingBoxXYXY(145, 494, 305, 523),
            BoundingBoxXYXY(153, 546, 240, 567),
            BoundingBoxXYXY(148, 635, 224, 664),
            BoundingBoxXYXY(147, 687, 237, 708),
            BoundingBoxXYXY(152, 776, 298, 805),
            BoundingBoxXYXY(143, 828, 241, 849),
            BoundingBoxXYXY(1697, 518, 1840, 544),
            BoundingBoxXYXY(1703, 656, 1843, 685),
        ]
        # Aspect 48/66 ≈ 0.73; bw>=dense min_w so only aspect gate was blocking.
        single = BoundingBoxXYXY(160.0, 912.0, 208.0, 978.0)
        boxes = [*seed, single]
        frame = np.full((h, w, 3), 245, dtype=np.uint8)
        for b in seed:
            x0, y0, x1, y1 = int(b.x0), int(b.y0), int(b.x1), int(b.y1)
            frame[y0:y1, x0:x1] = 40
            for x in range(x0 + 2, x1 - 2, 8):
                frame[y0 + 2 : y1 - 2, x : x + 3] = 240
        frame[912:978, 160:208] = 250
        # Axis-aligned glyph strokes (not photo texture).
        frame[920:970, 172:176] = 30
        frame[930:934, 165:200] = 30
        frame[945:949, 165:200] = 30
        frame[920:970, 192:196] = 30
        kept = filter_valid_text_boxes(boxes, w, h, frame_bgr=frame)
        self.assertTrue(any(abs(b.x0 - 160.0) < 1 and abs(b.y0 - 912.0) < 1 for b in kept))

    def test_keeps_high_sat_axis_aligned_hardsub(self) -> None:
        """Colored hardsub (high sat + axis edges) must not trip photo gate."""
        w, h = 1920, 1080
        caption = BoundingBoxXYXY(200.0, 920.0, 900.0, 980.0)
        frame = np.full((h, w, 3), 30, dtype=np.uint8)
        # Orange-ish band with vertical stroke columns (axis-aligned).
        hsv = np.zeros((60, 700, 3), dtype=np.uint8)
        hsv[:, :, 0] = 12
        hsv[:, :, 1] = 160
        hsv[:, :, 2] = 220
        frame[920:980, 200:900] = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        for x in range(220, 880, 28):
            frame[928:972, x : x + 8] = (20, 20, 20)
        kept = filter_valid_text_boxes([caption], w, h, frame_bgr=frame)
        self.assertEqual(kept, [caption])

    def test_non_dense_still_drops_douyin_right_rail(self) -> None:
        w, h = 1920, 1080
        like_btn = BoundingBoxXYXY(1700, 700, 1850, 760)
        kept = filter_valid_text_boxes([like_btn], w, h)
        self.assertEqual(kept, [])

    def test_drops_icon_chip_music_status(self) -> None:
        w, h = 1920, 1080
        icon = BoundingBoxXYXY(66, 522, 84, 546)
        chip = BoundingBoxXYXY(180, 636, 198, 654)
        music = BoundingBoxXYXY(200, 1000, 900, 1050)
        status = BoundingBoxXYXY(100, 10, 400, 40)
        kept = filter_valid_text_boxes([icon, chip, music, status], w, h)
        self.assertEqual(kept, [])

    def test_drops_tall_aspect_and_tiny_height(self) -> None:
        w, h = 1920, 1080
        egg = BoundingBoxXYXY(400, 500, 460, 620)  # h > w*1.5
        noise = BoundingBoxXYXY(300, 700, 420, 712)  # height=12
        kept = filter_valid_text_boxes([egg, noise], w, h)
        self.assertEqual(kept, [])

    def test_f075_keeps_hardsub_drops_salt(self) -> None:
        w, h = 1920, 1080
        boxes = [
            BoundingBoxXYXY(486.0, 942.0, 1140.0, 984.0),  # hardsub
            BoundingBoxXYXY(54.0, 942.0, 378.0, 990.0),  # hardsub left
            BoundingBoxXYXY(744.0, 690.0, 858.0, 786.0),  # salt
            BoundingBoxXYXY(1020.0, 594.0, 1038.0, 612.0),  # tiny
            BoundingBoxXYXY(954.0, 558.0, 1074.0, 684.0),  # salt
            BoundingBoxXYXY(312.0, 516.0, 414.0, 552.0),  # 加盐-like
        ]
        kept = filter_valid_text_boxes(boxes, w, h)
        self.assertEqual(len(kept), 3)
        for box in kept:
            _cx, cy = box.centroid
            # Kept: two hardsubs (cy~0.89) + mid instruction (cy~0.49)
            self.assertTrue(cy > 0.45)

    def test_f820_keeps_labels_drops_icon_chips(self) -> None:
        w, h = 1920, 1080
        boxes = [
            BoundingBoxXYXY(180.0, 636.0, 198.0, 654.0),  # chip
            BoundingBoxXYXY(66.0, 522.0, 84.0, 546.0),  # icon
            BoundingBoxXYXY(162.0, 492.0, 276.0, 522.0),  # 鸡蛋
            BoundingBoxXYXY(42.0, 402.0, 90.0, 426.0),  # tiny crumb
            BoundingBoxXYXY(264.0, 210.0, 426.0, 240.0),  # 碳水化合
        ]
        kept = filter_valid_text_boxes(boxes, w, h)
        self.assertEqual(len(kept), 2)
        widths = sorted(b.x1 - b.x0 for b in kept)
        self.assertGreaterEqual(widths[0], 0.05 * w)

    def test_extract_filters_before_enhance(self) -> None:
        """Only boxes that pass ROI/geometry are cropped."""
        sharp = np.zeros((1080, 1920, 3), dtype=np.uint8)
        sharp[::2, ::2] = 255
        sharp[840:920, :] = (25, 25, 25)
        for x in range(80, 1600, 28):
            sharp[855:905, x : x + 12] = (240, 240, 240)
        frames = {0: sharp.copy(), 5: sharp.copy(), 10: sharp.copy()}

        class _FakeCap:
            def __init__(self) -> None:
                self.i = -1
                self.opened = True

            def isOpened(self) -> bool:
                return self.opened

            def read(self):
                self.i += 1
                if self.i > 15:
                    return False, None
                if self.i in frames:
                    return True, frames[self.i]
                return True, np.full((1080, 1920, 3), 128, dtype=np.uint8)

            def release(self) -> None:
                self.opened = False

        from src.media_pipeline.frame_sampling.local_text_detector import TextBox

        detector = MagicMock()
        # Normalized: one keepable subtitle + one right-margin junk.
        detector.detect.return_value = [
            TextBox(x=0.1, y=0.82, width=0.7, height=0.05),  # keep hardsub
            TextBox(x=0.9, y=0.5, width=0.08, height=0.04),  # drop right rail
        ]

        extractor = SmartKeyframeExtractor(
            dbnet_model_path=None,
            sample_stride=5,
            fade_in_wait_frames=2,
            _skip_detector_init=True,
        )
        extractor._detector = detector

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            dummy = Path(tmp.name)
        try:
            with patch("cv2.VideoCapture", return_value=_FakeCap()):
                with patch("builtins.print") as mocked_print:
                    results = extractor.extract(dummy)
        finally:
            dummy.unlink(missing_ok=True)

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(len(results[0].boxes), 1)
        self.assertEqual(len(results[0].enhanced_crops), 1)
        printed = " ".join(str(c.args[0]) for c in mocked_print.call_args_list if c.args)
        self.assertIn("Lọc ROI", printed)


class ContribOpenCvTests(unittest.TestCase):
    def test_dnn_superres_is_importable(self) -> None:
        """opencv-contrib-python-headless must expose dnn_superres."""
        from cv2 import dnn_superres  # noqa: F401

        self.assertTrue(hasattr(dnn_superres, "DnnSuperResImpl_create"))

    def test_default_fsrcnn_path_under_api_models(self) -> None:
        path = default_fsrcnn_model_path()
        self.assertEqual(path.name, "FSRCNN_x2.pb")
        self.assertEqual(path.parent.name, "models")
        self.assertTrue(str(path).replace("\\", "/").endswith("apps/api/models/FSRCNN_x2.pb") or path.parent.parent.name == "api")

    def test_ensure_fsrcnn_returns_existing_file(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "FSRCNN_x2.pb"
            dest.write_bytes(b"x" * 20_000)
            got = ensure_fsrcnn_pb(dest)
            self.assertEqual(got, dest)


class BlurDetectionTests(unittest.TestCase):
    def test_sharp_frame_is_not_blurry(self) -> None:
        # High-frequency checkerboard → large Laplacian variance.
        tile = np.array([[0, 255], [255, 0]], dtype=np.uint8)
        gray = np.tile(tile, (64, 64))
        frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        extractor = SmartKeyframeExtractor(dbnet_model_path=None, _skip_detector_init=True)
        self.assertFalse(extractor.is_blurry(frame, threshold=100.0))

    def test_uniform_frame_is_blurry(self) -> None:
        frame = np.full((128, 128, 3), 128, dtype=np.uint8)
        extractor = SmartKeyframeExtractor(dbnet_model_path=None, _skip_detector_init=True)
        self.assertTrue(extractor.is_blurry(frame, threshold=100.0))


class CentroidTrackingTests(unittest.TestCase):
    def test_centroids_from_boxes(self) -> None:
        boxes = [BoundingBoxXYXY(0, 0, 100, 50), BoundingBoxXYXY(10, 10, 30, 30)]
        cents = centroids_from_boxes(boxes)
        self.assertEqual(len(cents), 2)
        np.testing.assert_allclose(cents[0], (50.0, 25.0))
        np.testing.assert_allclose(cents[1], (20.0, 20.0))

    def test_same_position_is_not_new(self) -> None:
        prev = np.array([[100.0, 200.0]], dtype=np.float64)
        curr = np.array([[102.0, 201.0]], dtype=np.float64)  # within 50px
        self.assertFalse(has_new_centroid(curr, prev, threshold_px=50.0))

    def test_shifted_position_is_new(self) -> None:
        prev = np.array([[100.0, 200.0]], dtype=np.float64)
        curr = np.array([[200.0, 200.0]], dtype=np.float64)  # 100px away
        self.assertTrue(has_new_centroid(curr, prev, threshold_px=50.0))

    def test_empty_previous_means_all_new(self) -> None:
        curr = np.array([[10.0, 10.0]], dtype=np.float64)
        self.assertTrue(has_new_centroid(curr, np.zeros((0, 2)), threshold_px=50.0))

    def test_fade_in_commits_after_wait(self) -> None:
        extractor = SmartKeyframeExtractor(
            dbnet_model_path=None,
            fade_in_wait_frames=2,
            centroid_new_px=50.0,
            _skip_detector_init=True,
        )
        boxes_a = [BoundingBoxXYXY(0, 0, 40, 20)]
        # First sighting → pending, not committed
        committed = extractor._track_and_maybe_commit(boxes_a, frame_index=0)
        self.assertIsNone(committed)
        # Wait frame 1
        committed = extractor._track_and_maybe_commit(boxes_a, frame_index=5)
        self.assertIsNone(committed)
        # Wait frame 2 → commit
        committed = extractor._track_and_maybe_commit(boxes_a, frame_index=10)
        self.assertIsNotNone(committed)
        self.assertEqual(committed.frame_index, 10)


class EnhanceTextRegionsTests(unittest.TestCase):
    def test_enhance_returns_binary_crops(self) -> None:
        frame = np.full((200, 300, 3), 180, dtype=np.uint8)
        # Dark text-like rectangle
        frame[80:120, 40:200] = (20, 20, 20)
        boxes = [BoundingBoxXYXY(40, 80, 200, 120)]
        extractor = SmartKeyframeExtractor(dbnet_model_path=None, _skip_detector_init=True)
        crops = extractor.enhance_text_regions(frame, boxes)
        self.assertEqual(len(crops), 1)
        crop = crops[0]
        self.assertEqual(crop.ndim, 2)
        unique = set(np.unique(crop).tolist())
        self.assertTrue(unique.issubset({0, 255}), f"expected binary, got {unique}")

    def test_enhance_uses_cpu_bicubic_when_no_fsrcnn(self) -> None:
        frame = np.full((100, 100, 3), 100, dtype=np.uint8)
        frame[30:70, 20:80] = 30
        boxes = [BoundingBoxXYXY(20, 30, 80, 70)]
        extractor = SmartKeyframeExtractor(
            dbnet_model_path=None,
            fsrcnn_model_path=None,
            _skip_detector_init=True,
        )
        with patch("builtins.print") as mocked_print:
            crops = extractor.enhance_text_regions(frame, boxes)
        self.assertEqual(len(crops), 1)
        printed = " ".join(str(c.args[0]) for c in mocked_print.call_args_list if c.args)
        self.assertIn("CPU Bicubic", printed)


class ExtractPipelineTests(unittest.TestCase):
    def test_extract_skips_blurry_and_uses_detector(self) -> None:
        # Landscape frame: sharp content + ink-like subtitle band for text gate.
        sharp = np.zeros((1080, 1920, 3), dtype=np.uint8)
        sharp[::2, ::2] = 255
        sharp[1::2, 1::2] = 255
        # Hardsub strip: dark band + bright strokes (passes looks_like_text_region).
        sharp[840:920, :] = (25, 25, 25)
        for x in range(100, 1700, 30):
            sharp[855:905, x : x + 12] = (240, 240, 240)

        frames = {0: sharp.copy(), 5: sharp.copy(), 10: sharp.copy(), 15: sharp.copy()}

        class _FakeCap:
            def __init__(self) -> None:
                self.i = -1
                self.opened = True

            def isOpened(self) -> bool:
                return self.opened

            def read(self):
                self.i += 1
                if self.i > 20:
                    return False, None
                if self.i in frames:
                    return True, frames[self.i]
                return True, np.full((1080, 1920, 3), 128, dtype=np.uint8)

            def release(self) -> None:
                self.opened = False

        detector = MagicMock()
        # Normalized horizontal subtitle in lower-mid band (passes ROI filter).
        from src.media_pipeline.frame_sampling.local_text_detector import TextBox

        detector.detect.return_value = [
            TextBox(x=0.15, y=0.78, width=0.6, height=0.05),
        ]

        extractor = SmartKeyframeExtractor(
            dbnet_model_path=None,
            sample_stride=5,
            fade_in_wait_frames=2,
            _skip_detector_init=True,
        )
        extractor._detector = detector

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            dummy = Path(tmp.name)
        try:
            with patch("cv2.VideoCapture", return_value=_FakeCap()):
                results = extractor.extract(dummy)
        finally:
            dummy.unlink(missing_ok=True)

        self.assertGreaterEqual(len(results), 1)
        self.assertTrue(detector.detect.called)
        self.assertGreaterEqual(len(results[0].enhanced_crops), 1)


if __name__ == "__main__":
    unittest.main()
