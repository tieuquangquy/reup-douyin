"""Phase 2 OCR polish: dual-polarity, best-frame fallback, role filter, batch."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import cv2
import numpy as np

from src.media_pipeline.frame_sampling.master_phase1_extractor import (
    OcrRecognitionCache,
    accept_ocr_text_for_role,
    classify_ocr_box_role,
    is_wide_thin_ocr_crop,
    load_phase2_crop_bgr,
    ocr_timeline_keyframes,
    otsu_binarize_with_border,
    otsu_polarity_variants,
    phase2_ocr_prep_variants,
    phase2_ocr_fallback_variants,
    pick_best_ocr_text,
    timeline_to_ocr_payload,
    upscale_pad_ocr_crop,
)


class OcrRecognitionCacheTests(unittest.TestCase):
    def test_cache_persists_by_input_hash_and_namespace(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ocr_cache.json"
            first = OcrRecognitionCache(path, namespace="local:model-v1:prep-v2")
            self.assertIsNone(first.get(b"jpeg-a"))
            first.set(b"jpeg-a", "鸡蛋拌饭")
            first.set(b"jpeg-empty", None)
            first.flush()

            second = OcrRecognitionCache(path, namespace="local:model-v1:prep-v2")
            self.assertEqual(second.get(b"jpeg-a"), "鸡蛋拌饭")
            found, text = second.lookup(b"jpeg-empty")
            self.assertTrue(found)
            self.assertIsNone(text)
            isolated = OcrRecognitionCache(path, namespace="local:model-v2:prep-v2")
            self.assertIsNone(isolated.get(b"jpeg-a"))


class OtsuPrepTests(unittest.TestCase):
    def test_otsu_returns_bordered_binary_bgr(self) -> None:
        img = np.full((40, 80, 3), 200, dtype=np.uint8)
        img[10:30, 20:60] = 20
        out = otsu_binarize_with_border(img, border_px=10)
        self.assertEqual(out.ndim, 3)
        self.assertEqual(out.shape[0], 40 + 20)
        self.assertEqual(out.shape[1], 80 + 20)

    def test_dual_polarity_returns_two_variants(self) -> None:
        img = np.full((40, 80, 3), 200, dtype=np.uint8)
        img[10:30, 20:60] = 20
        variants = otsu_polarity_variants(img, border_px=10)
        self.assertEqual(len(variants), 2)
        names = {n for n, _ in variants}
        self.assertEqual(names, {"otsu", "otsu_inv"})
        a = variants[0][1]
        b = variants[1][1]
        # Inverted polarity should differ from normal on ink pixels.
        self.assertFalse(np.array_equal(a, b))


class WideThinHardsubPrepTests(unittest.TestCase):
    def test_detects_wide_thin_crop(self) -> None:
        wide = np.full((40, 1498, 3), 30, dtype=np.uint8)
        normal = np.full((40, 80, 3), 30, dtype=np.uint8)
        self.assertTrue(is_wide_thin_ocr_crop(wide))
        self.assertFalse(is_wide_thin_ocr_crop(normal))

    def test_upscale_pad_raises_min_height(self) -> None:
        crop = np.full((40, 1498, 3), 30, dtype=np.uint8)
        out = upscale_pad_ocr_crop(crop, target_h=64, vpad=24, hpad=16)
        self.assertEqual(out.shape[0], 64 + 48)
        self.assertGreater(out.shape[1], 1498)

    def test_wide_thin_prefers_raw_up_pad_not_otsu_only(self) -> None:
        crop = np.full((40, 1498, 3), 30, dtype=np.uint8)
        crop[8:32, 100:1400] = 220
        variants = phase2_ocr_prep_variants(crop, border_px=10)
        names = [n for n, _ in variants]
        self.assertIn("raw_up_vpad", names)
        self.assertIn("raw_up_wpad", names)
        # Otsu alone destroys mixed-bg hardsubs — must not be the only path.
        self.assertFalse(set(names) <= {"otsu", "otsu_inv"})
        vpad = next(img for n, img in variants if n == "raw_up_vpad")
        self.assertGreaterEqual(int(vpad.shape[0]), 64)

    def test_normal_crop_still_uses_otsu_polarity(self) -> None:
        crop = np.full((40, 80, 3), 200, dtype=np.uint8)
        crop[10:30, 20:60] = 20
        variants = phase2_ocr_prep_variants(crop, border_px=10)
        names = {n for n, _ in variants}
        self.assertEqual(names, {"otsu", "otsu_inv"})

    def test_failed_normal_crop_fallback_adds_raw_border_variants(self) -> None:
        crop = np.full((66, 618, 3), 30, dtype=np.uint8)
        crop[12:54, 40:578] = 220

        pass1_names = {
            name for name, _image in phase2_ocr_prep_variants(crop)
        }
        fallback_names = {
            name for name, _image in phase2_ocr_fallback_variants(crop)
        }

        self.assertEqual(pass1_names, {"otsu", "otsu_inv"})
        self.assertEqual(
            fallback_names,
            {"otsu", "otsu_inv", "raw_bpad", "raw_wpad"},
        )
        fallback = dict(phase2_ocr_fallback_variants(crop))
        self.assertEqual(fallback["raw_bpad"].shape[0], 64 + 2 * 24)
        self.assertEqual(fallback["raw_wpad"].shape[0], 64 + 2 * 24)

    def test_timeline_dumps_raw_up_pad_for_wide_thin_hardsub(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            crop = np.full((40, 1498, 3), 30, dtype=np.uint8)
            crop[8:32, 80:1400] = 220
            cv2.imwrite(str(root / "crops" / "sub_01.jpg"), crop)
            timeline = [
                {
                    "text_id": "sub_01",
                    "start_frame": 0,
                    "end_frame": 4,
                    "best_frame_index": 2,
                    "box_coords": [0.0, 977.0, 1498.0, 1018.0],
                    "crop_path": "crops/sub_01.jpg",
                }
            ]

            def _batch(items):  # noqa: ANN001
                return ["这一餐花菜搭配了一份西葫芦"] * len(items)

            with patch(
                "src.media_pipeline.frame_sampling.master_phase1_extractor."
                "_recognize_batch_sync",
                side_effect=_batch,
            ):
                out = ocr_timeline_keyframes(timeline, root_dir=root, video_path=None)

            self.assertEqual(out[0]["ocr_text"], "这一餐花菜搭配了一份西葫芦")
            dumps = {p.name for p in (root / "qa" / "ocr_inputs").glob("sub_01*.jpg")}
            self.assertTrue(any("raw_up_vpad" in n for n in dumps))
            self.assertTrue(any("raw_up_wpad" in n for n in dumps))


class RoleFilterTests(unittest.TestCase):
    def test_classify_hardsub_vs_mid(self) -> None:
        hard = classify_ocr_box_role(
            (80.0, 980.0, 900.0, 1040.0), frame_w=1920, frame_h=1080
        )
        mid = classify_ocr_box_role(
            (800.0, 480.0, 1000.0, 530.0), frame_w=1920, frame_h=1080
        )
        endcard_row = classify_ocr_box_role(
            (60.0, 840.0, 280.0, 880.0), frame_w=1920, frame_h=1080
        )
        self.assertEqual(hard, "hardsub")
        self.assertEqual(mid, "mid_label")
        self.assertEqual(endcard_row, "ui_chip")

    def test_mid_label_allows_short_cjk_rejects_latin_noise(self) -> None:
        self.assertEqual(
            accept_ocr_text_for_role("加盐", role="mid_label"), "加盐"
        )
        self.assertEqual(accept_ocr_text_for_role("盐", role="mid_label"), "盐")
        self.assertIsNone(accept_ocr_text_for_role("E", role="mid_label"))
        self.assertIsNone(accept_ocr_text_for_role("2", role="mid_label"))

    def test_pick_best_prefers_more_cjk(self) -> None:
        self.assertEqual(pick_best_ocr_text(["E", "加盐", "盐"]), "加盐")


class CropBypassTests(unittest.TestCase):
    def test_prefers_crop_path_over_keyframe(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            crop = np.zeros((20, 40, 3), dtype=np.uint8)
            crop[:] = (0, 0, 255)
            key = np.zeros((100, 200, 3), dtype=np.uint8)
            key[:] = (255, 0, 0)
            cv2.imwrite(str(root / "crops" / "sub_01.jpg"), crop)
            cv2.imwrite(str(root / "frames" / "sub_01.jpg"), key)
            entry = {
                "text_id": "sub_01",
                "crop_path": "crops/sub_01.jpg",
                "best_keyframe_path": "frames/sub_01.jpg",
                "box_coords": [10.0, 10.0, 50.0, 30.0],
            }
            loaded = load_phase2_crop_bgr(entry, root_dir=root)
            assert loaded is not None
            self.assertGreater(int(loaded[0, 0, 2]), 200)

    def test_hash_bound_probe_crop_precedes_wider_approved_cover_crop(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            cover_crop = np.zeros((40, 80, 3), dtype=np.uint8)
            cover_crop[:] = (0, 0, 255)
            key = np.zeros((100, 200, 3), dtype=np.uint8)
            key[:] = (255, 0, 0)
            key[40:60, 80:120] = (0, 255, 0)
            cv2.imwrite(str(root / "crops" / "wide.jpg"), cover_crop)
            cv2.imwrite(str(root / "frames" / "source.jpg"), key)
            entry = {
                "crop_path": "crops/wide.jpg",
                "best_keyframe_path": "frames/source.jpg",
                "box_coords": [20.0, 20.0, 160.0, 80.0],
                "ocr_probe_geometry": {
                    "x": 0.4,
                    "y": 0.4,
                    "width": 0.2,
                    "height": 0.2,
                },
            }

            loaded = load_phase2_crop_bgr(
                entry, root_dir=root, frame_width=200, frame_height=100
            )

            assert loaded is not None
            self.assertEqual(loaded.shape[:2], (20, 40))
            self.assertGreater(int(loaded[:, :, 1].mean()), 180)


class Phase2OcrMappingTests(unittest.TestCase):
    def test_success_sets_ocr_text_source_and_dumps_inputs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            img = np.full((30, 60, 3), 255, dtype=np.uint8)
            cv2.imwrite(str(root / "crops" / "sub_01.jpg"), img)
            timeline = [
                {
                    "text_id": "sub_01",
                    "start_frame": 10,
                    "end_frame": 20,
                    "best_frame_index": 14,
                    "box_coords": [100.0, 900.0, 400.0, 940.0],
                    "best_keyframe_path": "frames/sub_01.jpg",
                    "crop_path": "crops/sub_01.jpg",
                    "hit_count": 3,
                }
            ]
            box_before = list(timeline[0]["box_coords"])

            def _batch(items):  # noqa: ANN001
                return ["加盐"] * len(items)

            with patch(
                "src.media_pipeline.frame_sampling.master_phase1_extractor."
                "_recognize_batch_sync",
                side_effect=_batch,
            ):
                out = ocr_timeline_keyframes(timeline, root_dir=root, video_path=None)

            self.assertEqual(out[0]["ocr_text"], "加盐")
            self.assertEqual(out[0]["ocr_source"], "crop")
            self.assertEqual(out[0]["box_coords"], box_before)
            dumps = list((root / "qa" / "ocr_inputs").glob("sub_01*.jpg"))
            self.assertGreaterEqual(len(dumps), 2)

    def test_fallback_uses_best_frame_index_first(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            img = np.full((30, 60, 3), 255, dtype=np.uint8)
            cv2.imwrite(str(root / "crops" / "sub_02.jpg"), img)
            video = root / "clip.mp4"
            video.write_bytes(b"fake")
            timeline = [
                {
                    "text_id": "sub_02",
                    "start_frame": 10,
                    "end_frame": 20,
                    "best_frame_index": 12,
                    "box_coords": [800.0, 480.0, 1000.0, 530.0],
                    "best_keyframe_path": "frames/sub_02.jpg",
                    "crop_path": "crops/sub_02.jpg",
                }
            ]
            frame = np.full((1080, 1920, 3), 30, dtype=np.uint8)
            frame[480:530, 800:1000] = 220
            batch_calls = {"n": 0}

            def _batch(items):  # noqa: ANN001
                batch_calls["n"] += 1
                if batch_calls["n"] == 1:
                    return [None] * len(items)
                return ["加盐"] * len(items)

            with patch(
                "src.media_pipeline.frame_sampling.master_phase1_extractor."
                "_recognize_batch_sync",
                side_effect=_batch,
            ):
                with patch(
                    "src.media_pipeline.frame_sampling.master_phase1_extractor._read_frame",
                    return_value=frame,
                ) as rf:
                    out = ocr_timeline_keyframes(
                        timeline, root_dir=root, video_path=video
                    )
                    self.assertEqual(rf.call_args_list[0][0][1], 12)

            self.assertEqual(out[0]["ocr_text"], "加盐")
            self.assertEqual(out[0]["ocr_source"], "best_frame")
            self.assertEqual(out[0]["ocr_frame"], 12)

    def test_role_filter_drops_latin_noise_then_cover_only(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            img = np.full((30, 60, 3), 255, dtype=np.uint8)
            cv2.imwrite(str(root / "crops" / "sub_03.jpg"), img)
            timeline = [
                {
                    "text_id": "sub_03",
                    "start_frame": 0,
                    "end_frame": 4,
                    "box_coords": [800.0, 480.0, 1000.0, 530.0],
                    "crop_path": "crops/sub_03.jpg",
                    "best_keyframe_path": "frames/sub_03.jpg",
                }
            ]

            def _batch(items):  # noqa: ANN001
                return ["E"] * len(items)

            with patch(
                "src.media_pipeline.frame_sampling.master_phase1_extractor."
                "_recognize_batch_sync",
                side_effect=_batch,
            ):
                out = ocr_timeline_keyframes(timeline, root_dir=root, video_path=None)
            self.assertEqual(out[0].get("ocr_text", ""), "")
            payload = timeline_to_ocr_payload(
                out,
                fps=30.0,
                frame_count=10,
                frame_width=1920,
                frame_height=1080,
            )
            self.assertTrue(payload["frames"][0]["boxes"][0].get("cover_only"))


if __name__ == "__main__":
    unittest.main()
