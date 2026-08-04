"""Phase 4 runtime opts: idle passthrough, caches, ROI merge, role font, clamp, timebase, samples."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import (
    draw_vi_overlays,
    inpaint_segments_roi,
    process_frame_bgr,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment
from src.media_pipeline.video_renderer.render_runtime import (
    FrameRenderState,
    ViGlyphCache,
    frame_index_to_ms,
    merge_pixel_rois,
    resolve_vi_font_size_for_kind,
    segment_is_active,
    write_render_sample_if_due,
)


def _font() -> Path:
    segoe = Path(r"C:\Windows\Fonts\segoeui.ttf")
    return segoe if segoe.is_file() else Path(r"C:\Windows\Fonts\arial.ttf")


class TimebaseTests(unittest.TestCase):
    def test_frame_index_to_ms_matches_half_open_active(self) -> None:
        # 30fps frame 30 → 1000ms; segment [1000, 2000) active at 1000, not at 2000.
        self.assertEqual(frame_index_to_ms(30, 30.0), 1000)
        seg = OverlaySegment(1000, 2000, 0.1, 0.8, 0.3, 0.08, "A", kind="hardsub")
        self.assertTrue(segment_is_active(seg, 1000))
        self.assertTrue(segment_is_active(seg, 1999))
        self.assertFalse(segment_is_active(seg, 2000))


class RoiMergeTests(unittest.TestCase):
    def test_merge_overlapping_rois(self) -> None:
        a = (10, 10, 40, 40)
        b = (30, 30, 60, 60)
        c = (200, 200, 220, 220)
        merged = merge_pixel_rois([a, b, c], pad_px=0)
        self.assertEqual(len(merged), 2)
        # First group covers union of a+b.
        self.assertEqual(merged[0][:2], (10, 10))
        self.assertEqual(merged[0][2:], (60, 60))


class RoleFontTests(unittest.TestCase):
    def test_ui_smaller_than_hardsub(self) -> None:
        hs = resolve_vi_font_size_for_kind(1000, "hardsub")
        ui = resolve_vi_font_size_for_kind(1000, "ui")
        self.assertGreater(hs, ui)


class GlyphCacheTests(unittest.TestCase):
    def test_glyph_cache_reuses_bitmap(self) -> None:
        cache = ViGlyphCache()
        a = cache.get_rgba("Muối", size=20, fontfile=_font())
        b = cache.get_rgba("Muối", size=20, fontfile=_font())
        self.assertIs(a, b)
        self.assertEqual(a.shape[2], 4)


class IdleAndCacheIntegrationTests(unittest.TestCase):
    def test_process_frame_empty_is_identity(self) -> None:
        frame = np.full((40, 40, 3), 77, dtype=np.uint8)
        out = process_frame_bgr(frame, [], fontfile=_font())
        self.assertTrue(np.array_equal(out, frame))

    def test_inpaint_cache_skips_recompute_on_static_roi(self) -> None:
        h, w = 120, 160
        frame = np.full((h, w, 3), 180, dtype=np.uint8)
        frame[40:70, 40:100] = (10, 10, 10)
        seg = OverlaySegment(0, 1000, 40 / w, 40 / h, 60 / w, 30 / h, "", kind="hardsub")
        state = FrameRenderState()
        out1 = inpaint_segments_roi(frame, [seg], state=state)
        calls_after_first = state.inpaint_cache.compute_count
        out2 = inpaint_segments_roi(frame, [seg], state=state)
        self.assertEqual(state.inpaint_cache.compute_count, calls_after_first)
        self.assertTrue(np.array_equal(out1[40:70, 40:100], out2[40:70, 40:100]))


class ClampCollisionTests(unittest.TestCase):
    def test_vi_clamped_inside_frame(self) -> None:
        h, w = 100, 120
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        # Box near bottom-right — text must not require reading off-array.
        seg = OverlaySegment(0, 1000, 0.85, 0.85, 0.12, 0.10, "Muối", kind="hardsub")
        out = draw_vi_overlays(frame, [seg], fontfile=_font())
        self.assertEqual(out.shape, frame.shape)


class SampleFossilTests(unittest.TestCase):
    def test_writes_sample_when_due(self) -> None:
        frame = np.full((32, 32, 3), 90, dtype=np.uint8)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_render_sample_if_due(
                root,
                frame_bgr=frame,
                frame_index=0,
                time_ms=0,
                active=[OverlaySegment(0, 1000, 0.1, 0.1, 0.2, 0.2, "A", kind="ui")],
                force=True,
            )
            self.assertIsNotNone(path)
            self.assertTrue(Path(path).is_file())


if __name__ == "__main__":
    unittest.main()
