"""Tests for CJK/conf/zone filter, line merge, and temporal consensus."""

from __future__ import annotations

import unittest

from src.media_pipeline.ocr_filtering.box_timeline_tracker import OcrObservation, TimedBox
from src.media_pipeline.ocr_filtering.clean_box_authority import (
    apply_temporal_consensus,
    clean_observation_boxes,
    filter_authority_boxes,
    merge_horizontal_line_boxes,
)


class CleanBoxAuthorityTests(unittest.TestCase):
    def test_filter_drops_latin_and_low_conf(self) -> None:
        boxes = [
            TimedBox(0.2, 0.92, 0.5, 0.04, text="和木耳胡萝卜", confidence=0.9),
            TimedBox(0.2, 0.5, 0.3, 0.05, text="abc", confidence=0.99),
            TimedBox(0.2, 0.92, 0.2, 0.03, text="盐", confidence=0.9),  # 1 CJK
            TimedBox(0.2, 0.92, 0.4, 0.04, text="开大火爆炒", confidence=0.4),
        ]
        kept = filter_authority_boxes(boxes, min_confidence=0.75, min_cjk_chars=2)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].text, "和木耳胡萝卜")

    def test_merge_horizontal_line(self) -> None:
        boxes = [
            TimedBox(0.2, 0.92, 0.15, 0.04, text="和木", confidence=0.9),
            TimedBox(0.36, 0.93, 0.2, 0.035, text="耳胡萝卜", confidence=0.88),
            TimedBox(0.3, 0.5, 0.4, 0.06, text="什锦炒虾仁", confidence=0.95),
        ]
        merged = merge_horizontal_line_boxes(boxes, y_gap=0.04)
        self.assertEqual(len(merged), 2)
        hard = next(b for b in merged if "木" in b.text)
        self.assertIn("和木", hard.text)
        self.assertIn("耳胡萝卜", hard.text)
        self.assertLess(hard.x, 0.25)
        self.assertGreater(hard.w, 0.3)

    def test_repair_snaps_caption_with_y_near_zero(self) -> None:
        from src.media_pipeline.ocr_filtering.clean_box_authority import (
            repair_implausible_caption_geometry,
        )

        # Ultra-tall full-strip hardsub (not mid-title sized) may snap to bottom.
        bad = TimedBox(0.2, 0.0, 0.55, 0.35, text="接着另起锅下入虾仁炒至变色", confidence=0.96)
        fixed = repair_implausible_caption_geometry(bad)
        self.assertGreater(fixed.y, 0.85)
        self.assertLess(fixed.h, 0.1)
        kept = filter_authority_boxes([bad])
        self.assertEqual(len(kept), 1)
        self.assertGreater(kept[0].y, 0.85)

    def test_filter_rejects_short_band_top_noise(self) -> None:
        """Short / weak band-top hits stay rejected; long stuck hardsub snaps in."""
        boxes = [
            TimedBox(0.2, 0.667, 0.15, 0.04, text="盐啊", confidence=0.98),
            TimedBox(0.25, 0.92, 0.5, 0.04, text="开大火爆炒收汁就可以", confidence=0.98),
        ]
        kept = filter_authority_boxes(boxes)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].text, "开大火爆炒收汁就可以")

    def test_band_stuck_hardsub_snaps_to_bottom_strip(self) -> None:
        """Hard-band OCR often returns correct CJK at cy≈0.70 (band top) — keep + snap."""
        stuck = TimedBox(
            0.15,
            0.68,
            0.7,
            0.045,
            text="调味就加一勺盐白胡椒和淀粉水勾芡",
            confidence=0.98,
        )
        cleaned = clean_observation_boxes([stuck])
        self.assertEqual(len(cleaned), 1)
        cy = cleaned[0].y + cleaned[0].h / 2.0
        self.assertGreaterEqual(cy, 0.85)
        self.assertIn("调味", cleaned[0].text)

    def test_mid_title_geometry_not_snapped_to_bottom(self) -> None:
        """f0 failure: correct mid title must keep mid Y — never snap to hardsub strip."""
        mid = TimedBox(0.3, 0.42, 0.4, 0.08, text="什锦炒虾仁", confidence=0.99)
        cleaned = clean_observation_boxes([mid])
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0].text, "什锦炒虾仁")
        cy = cleaned[0].y + cleaned[0].h / 2.0
        self.assertLess(cy, 0.72)
        self.assertGreater(cy, 0.22)
        self.assertLess(cleaned[0].y, 0.7)

    def test_clean_keeps_mid_title(self) -> None:
        boxes = [
            TimedBox(0.3, 0.45, 0.4, 0.06, text="什锦炒虾仁", confidence=0.92),
            TimedBox(0.4, 0.55, 0.2, 0.04, text="525千卡", confidence=0.9),
        ]
        cleaned = clean_observation_boxes(boxes)
        texts = {b.text for b in cleaned}
        self.assertIn("什锦炒虾仁", texts)
        title = next(b for b in cleaned if b.text == "什锦炒虾仁")
        self.assertLess(title.y + title.h / 2.0, 0.72)

    def test_consensus_requires_neighbor_or_strong_title(self) -> None:
        obs = [
            OcrObservation(
                0,
                (TimedBox(0.3, 0.45, 0.4, 0.06, text="什锦炒虾仁", confidence=0.95),),
            ),
            OcrObservation(
                500,
                (
                    TimedBox(0.25, 0.92, 0.5, 0.04, text="和木耳胡萝卜一起", confidence=0.9),
                ),
            ),
            OcrObservation(
                1000,
                (
                    TimedBox(0.26, 0.91, 0.48, 0.045, text="和木耳胡萝卜一起", confidence=0.91),
                ),
            ),
            OcrObservation(
                5000,
                (TimedBox(0.2, 0.92, 0.15, 0.04, text="盐啊", confidence=0.95),),
            ),
        ]
        got = apply_temporal_consensus(obs, min_hits=2, max_gap_ms=1500)
        by_t = {o.time_ms: o for o in got}
        # Title single-hit allowed
        self.assertEqual(len(by_t[0].boxes), 1)
        # Hardsub confirmed across 500/1000
        self.assertEqual(len(by_t[500].boxes), 1)
        self.assertEqual(len(by_t[1000].boxes), 1)
        # Short one-shot hardsub dropped (needs neighbor or strong long line)
        self.assertEqual(len(by_t[5000].boxes), 0)

    def test_consensus_keeps_strong_single_hardsub_line(self) -> None:
        obs = [
            OcrObservation(
                8000,
                (
                    TimedBox(
                        0.25,
                        0.92,
                        0.5,
                        0.04,
                        text="和木耳胡萝卜一起下锅焯水断生",
                        confidence=0.95,
                    ),
                ),
            ),
        ]
        got = apply_temporal_consensus(obs, min_hits=2, max_gap_ms=1500)
        self.assertEqual(len(got[0].boxes), 1)

    def test_collapse_nearby_picks_best_hardsub_at_earliest_tick(self) -> None:
        from src.media_pipeline.ocr_filtering.clean_box_authority import (
            collapse_nearby_observations,
        )

        obs = [
            OcrObservation(
                12623,
                (
                    TimedBox(0.17, 0.91, 0.27, 0.05, text="虾仁炒至变色", confidence=0.99),
                    TimedBox(0.49, 0.91, 0.27, 0.05, text="接着另起锅下", confidence=0.97),
                ),
            ),
            OcrObservation(
                12971,
                (
                    TimedBox(
                        0.12,
                        0.91,
                        0.72,
                        0.05,
                        text="接着另起锅下入虾仁炒至变色",
                        confidence=0.99,
                    ),
                ),
            ),
        ]
        got = collapse_nearby_observations(obs, gap_ms=900)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].time_ms, 12623)
        self.assertEqual(len(got[0].boxes), 1)
        self.assertIn("接着另起锅", got[0].boxes[0].text)
        self.assertIn("虾仁", got[0].boxes[0].text)


if __name__ == "__main__":
    unittest.main()
