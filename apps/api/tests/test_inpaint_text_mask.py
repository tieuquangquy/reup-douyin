"""OpenCV text-mask + inpaint contracts for Phase 3+4."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import (
    apply_solid_cover,
    build_cover_mask,
    build_text_mask,
    draw_vi_overlays,
    inpaint_frame,
    process_frame_bgr,
    resolve_render_backend,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment


def _gradient_frame(h: int = 240, w: int = 320) -> np.ndarray:
    """BGR gradient background."""
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        frame[y, :, 0] = int(40 + 80 * y / h)
        frame[y, :, 1] = int(60 + 100 * y / h)
        frame[y, :, 2] = int(90 + 120 * y / h)
    return frame


class ResolveBackendTests(unittest.TestCase):
    def test_default_is_opencv_inpaint(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "OCR_RENDER_BACKEND"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(resolve_render_backend(), "opencv_inpaint")

    def test_ffmpeg_delogo_opt_in(self) -> None:
        with mock.patch.dict(os.environ, {"OCR_RENDER_BACKEND": "ffmpeg_delogo"}):
            self.assertEqual(resolve_render_backend(), "ffmpeg_delogo")


class TextMaskTests(unittest.TestCase):
    def test_mask_covers_dark_glyphs_after_dilate(self) -> None:
        frame = _gradient_frame()
        frame[180:210, 40:280] = (20, 20, 20)
        frame[190:200, 60:260] = (30, 30, 30)
        boxes = [(0.10, 0.72, 0.80, 0.16)]
        mask = build_text_mask(frame, boxes)
        self.assertEqual(mask.shape, (240, 320))
        self.assertEqual(mask.dtype, np.uint8)
        roi = mask[180:210, 40:280]
        coverage = float(np.count_nonzero(roi)) / float(roi.size)
        self.assertGreater(coverage, 0.3)

    def test_empty_boxes_yield_empty_mask(self) -> None:
        frame = _gradient_frame()
        mask = build_text_mask(frame, [])
        self.assertEqual(int(mask.max()), 0)


class InpaintFrameTests(unittest.TestCase):
    def test_inpaint_reduces_dark_ink_in_roi(self) -> None:
        frame = _gradient_frame()
        frame[100:140, 80:240] = (15, 15, 15)
        before = frame[100:140, 80:240].astype(np.float32).mean()
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        mask[100:140, 80:240] = 255
        out = inpaint_frame(frame, mask, large_region=False)
        after = out[100:140, 80:240].astype(np.float32).mean()
        self.assertGreater(after, before + 10)


class WhiteHardsubCoverTests(unittest.TestCase):
    """Douyin hard-subs are light glyphs — Otsu-only mask must not be the cover path."""

    def _white_bar_frame(self, *, y0: int = 188, y1: int = 208) -> np.ndarray:
        frame = _gradient_frame()
        # White fill + dark outline (typical hard-sub look).
        frame[y0:y1, 50:270] = (255, 255, 255)
        frame[y0 - 2 : y1 + 2, 48:50] = (10, 10, 10)
        frame[y0 - 2 : y1 + 2, 270:272] = (10, 10, 10)
        frame[y0 - 2 : y0, 50:270] = (10, 10, 10)
        frame[y1 : y1 + 2, 50:270] = (10, 10, 10)
        return frame

    def test_hardsub_cover_mask_is_solid_rect_not_sparse_otsu(self) -> None:
        frame = self._white_bar_frame()
        seg = OverlaySegment(0, 1000, 0.10, 0.75, 0.80, 0.12, "", kind="hardsub")
        mask = build_cover_mask(frame, [seg])
        # Expanded hardsub strip should be near-full coverage in the OCR union band.
        roi = mask[186:210, 48:272]
        coverage = float(np.count_nonzero(roi)) / float(roi.size)
        self.assertGreater(coverage, 0.85)

    def test_process_frame_removes_white_hardsub_pixels(self) -> None:
        frame = self._white_bar_frame()
        before_white = float((frame[188:208, 50:270, 0] > 200).mean())
        self.assertGreater(before_white, 0.9)
        seg = OverlaySegment(0, 1000, 0.10, 0.75, 0.80, 0.12, "", kind="hardsub")
        font = Path(r"C:\Windows\Fonts\arial.ttf")
        if not font.is_file():
            font = Path(r"C:\Windows\Fonts\segoeui.ttf")
        out = process_frame_bgr(frame, [seg], fontfile=font)
        after_white = float((out[188:208, 50:270, 0] > 200).mean())
        self.assertLess(after_white, 0.05)

    def test_title_cover_mask_is_solid_not_otsu(self) -> None:
        # Mid-frame white stylized title (Douyin dish name) — must be solid cover.
        frame = self._white_bar_frame(y0=100, y1=130)
        seg = OverlaySegment(0, 1000, 0.12, 0.38, 0.76, 0.14, "", kind="title")
        mask = build_cover_mask(frame, [seg])
        roi = mask[100:130, 50:270]
        coverage = float(np.count_nonzero(roi)) / float(roi.size)
        self.assertGreater(coverage, 0.85)

    def test_process_frame_removes_white_mid_title_pixels(self) -> None:
        frame = self._white_bar_frame(y0=100, y1=130)
        before_white = float((frame[100:130, 50:270, 0] > 200).mean())
        self.assertGreater(before_white, 0.9)
        seg = OverlaySegment(0, 1000, 0.12, 0.38, 0.76, 0.14, "", kind="title")
        font = Path(r"C:\Windows\Fonts\arial.ttf")
        if not font.is_file():
            font = Path(r"C:\Windows\Fonts\segoeui.ttf")
        out = process_frame_bgr(frame, [seg], fontfile=font)
        after_white = float((out[100:130, 50:270, 0] > 200).mean())
        self.assertLess(after_white, 0.05)

    def test_title_solid_does_not_force_full_width_min_cover(self) -> None:
        frame = _gradient_frame()
        # Narrow title box — solid fill of expanded pad only, not min_width 0.88 strip.
        seg = OverlaySegment(0, 1000, 0.35, 0.40, 0.30, 0.08, "", kind="title")
        mask = build_cover_mask(frame, [seg])
        self.assertGreater(int(mask.max()), 0)
        self.assertLess(float(np.count_nonzero(mask)) / float(mask.size), 0.25)

    def test_apply_solid_cover_is_fast_enough_for_hd_batch(self) -> None:
        """NS inpaint on 720x1280 solid strips hangs jobs for 30+ min; blur-fill must be ms-class."""
        import time

        h, w = 1280, 720
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:] = (40, 60, 80)
        frame[900:1100, 40:680] = (255, 255, 255)
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[880:1120, 20:700] = 255
        t0 = time.perf_counter()
        for _ in range(40):
            out = apply_solid_cover(frame, mask)
        elapsed = time.perf_counter() - t0
        self.assertLess(
            elapsed,
            4.0,
            f"apply_solid_cover too slow for production render: {elapsed:.2f}s / 40 frames",
        )
        after_white = float((out[900:1100, 40:680, 0] > 200).mean())
        self.assertLess(after_white, 0.05)


class DrawViTests(unittest.TestCase):
    def test_draw_vi_writes_non_background_pixels(self) -> None:
        frame = _gradient_frame()
        before = frame.copy()
        seg = OverlaySegment(0, 1000, 0.1, 0.7, 0.8, 0.15, "Xin chao", kind="hardsub")
        font = Path(r"C:\Windows\Fonts\arial.ttf")
        if not font.is_file():
            self.skipTest("arial.ttf missing")
        out = draw_vi_overlays(frame, [seg], fontfile=font)
        self.assertFalse(np.array_equal(out, before))


class BackendDispatchTests(unittest.TestCase):
    def test_render_dispatches_to_opencv_by_default(self) -> None:
        import tempfile

        from src.media_pipeline.video_renderer.renderer import render_video_single_pass

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.mp4"
            out = Path(tmp) / "out.mp4"
            src.write_bytes(b"fake")
            env = {k: v for k, v in os.environ.items() if k != "OCR_RENDER_BACKEND"}
            with mock.patch.dict(os.environ, env, clear=True):
                with mock.patch(
                    "src.media_pipeline.video_renderer.renderer.shutil.which",
                    return_value="ffmpeg",
                ):
                    with mock.patch(
                        "src.media_pipeline.video_renderer.inpaint_render.render_video_opencv_inpaint",
                        return_value=out,
                    ) as opencv:
                        result = render_video_single_pass(
                            src,
                            out,
                            [OverlaySegment(0, 500, 0.1, 0.8, 0.7, 0.1, "VI")],
                            frame_width=1080,
                            frame_height=1920,
                            progress=False,
                        )
        self.assertEqual(result, out)
        opencv.assert_called_once()

    def test_render_dispatches_to_ffmpeg_delogo_when_configured(self) -> None:
        import tempfile

        from src.media_pipeline.video_renderer.renderer import render_video_single_pass

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.mp4"
            out = Path(tmp) / "out.mp4"
            src.write_bytes(b"fake")
            with mock.patch.dict(os.environ, {"OCR_RENDER_BACKEND": "ffmpeg_delogo"}):
                with mock.patch(
                    "src.media_pipeline.video_renderer.renderer.shutil.which",
                    return_value="ffmpeg",
                ):
                    with mock.patch(
                        "src.media_pipeline.video_renderer.renderer._render_video_ffmpeg_delogo",
                        return_value=out,
                    ) as delogo:
                        result = render_video_single_pass(
                            src,
                            out,
                            [OverlaySegment(0, 500, 0.1, 0.8, 0.7, 0.1, "VI")],
                            frame_width=1080,
                            frame_height=1920,
                            progress=False,
                        )
        self.assertEqual(result, out)
        delogo.assert_called_once()


if __name__ == "__main__":
    unittest.main()
