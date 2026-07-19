"""Legacy endcard helpers (kept for API compat; pipeline is per-box layout)."""

from __future__ import annotations

import unittest

from src.media_pipeline.video_renderer.overlays import expand_endcard_panel, summarize_endcard_vi


class LegacyEndcardHelperTests(unittest.TestCase):
    def test_expand_endcard_panel_covers_most_of_frame(self) -> None:
        x, y, w, h = expand_endcard_panel(0.12, 0.20, 0.50, 0.40)
        self.assertGreaterEqual(w, 0.88)
        self.assertGreaterEqual(h, 0.70)
        self.assertGreaterEqual(x, 0.02)
        self.assertLessEqual(x + w, 0.98)

    def test_summarize_endcard_vi_truncates_laundry_list(self) -> None:
        long_vi = "Com, dau phong, tom, trung, rau cu, mon chinh va mon phu"
        got = summarize_endcard_vi(long_vi)
        self.assertLessEqual(len(got), 42)
        self.assertTrue(got.startswith("Com"))


if __name__ == "__main__":
    unittest.main()
