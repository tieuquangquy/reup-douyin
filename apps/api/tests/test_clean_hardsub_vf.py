"""Timed per-event hard-sub cover VF contract (bbox + enable=between)."""

from __future__ import annotations

import unittest

from src.ocr_pipeline.clean_hardsub import build_timed_cover_vf
from src.ocr_pipeline.types import HardSubEvent


class TimedCoverVfTests(unittest.TestCase):
    def test_build_timed_cover_vf_uses_event_boxes_and_enable(self) -> None:
        events = [
            HardSubEvent(
                start_ms=0,
                end_ms=500,
                x=0.10,
                y=0.80,
                width=0.70,
                height=0.10,
                sample_count=2,
                avg_confidence=0.9,
                texts=["一"],
                unstable=False,
            ),
            HardSubEvent(
                start_ms=2000,
                end_ms=2500,
                x=0.20,
                y=0.82,
                width=0.55,
                height=0.08,
                sample_count=2,
                avg_confidence=0.9,
                texts=["二"],
                unstable=False,
            ),
        ]
        vf = build_timed_cover_vf(
            events, hold_ms=500, pad_x=0.0, pad_y=0.0, frame_width=1080, frame_height=1920
        )

        self.assertIn("delogo=", vf)
        self.assertIn("show=0", vf)
        self.assertIn("enable=between(t\\,", vf)
        self.assertEqual(vf.count("delogo="), 2)
        self.assertNotIn("drawbox=", vf)
        self.assertNotIn("iw*", vf)
        self.assertNotIn("ih*", vf)
        # Narrow OCR unions expand to min cover width (not left as crumbs).
        self.assertRegex(vf, r"delogo=x=\d+:y=\d+:w=\d+:h=\d+")
        self.assertNotIn("x=0:y=", vf)
        self.assertNotIn("w=iw:h=", vf)
        # Timed windows: [0, 1.0] and [2.0, 3.0] with hold_ms=500
        self.assertIn("between(t\\,0.000\\,1.000)", vf)
        self.assertIn("between(t\\,2.000\\,3.000)", vf)

    def test_hold_ms_extends_end_past_last_sample(self) -> None:
        events = [
            HardSubEvent(
                start_ms=1000,
                end_ms=1000,
                x=0.1,
                y=0.8,
                width=0.8,
                height=0.1,
                sample_count=1,
                avg_confidence=0.9,
                texts=["x"],
                unstable=True,
            )
        ]
        vf = build_timed_cover_vf(
            events, hold_ms=500, pad_x=0.0, pad_y=0.0, frame_width=1080, frame_height=1920
        )
        self.assertIn("between(t\\,1.000\\,1.500)", vf)


if __name__ == "__main__":
    unittest.main()
