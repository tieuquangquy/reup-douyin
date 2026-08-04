"""Phase1 recall: higher DBNet long-edge + wider bottom-line merge + stroke prep."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import cv2
import numpy as np

from src.media_pipeline.frame_sampling.local_text_detector import (
    TextBox,
    merge_collinear_text_boxes,
)
from src.media_pipeline.frame_sampling.master_phase1_extractor import (
    PHASE1_DET_LONG_EDGE,
    ROI_Y0,
    ROI_Y1,
    MasterPhase1Extractor,
    overlay_stroke_enhance_bgr,
    roi_clahe_bgr,
    roi_phase1_detect_preps,
)


def _synthetic_burnin_on_bright_food(
    *,
    h: int = 120,
    w: int = 640,
) -> np.ndarray:
    """White thin burn-in glyphs on mottled bright food — CLAHE alone washes out."""
    rng = np.random.default_rng(7)
    base = np.full((h, w), 205, dtype=np.uint8)
    base = np.clip(
        base.astype(np.int16) + rng.integers(-25, 26, size=(h, w), dtype=np.int16),
        180,
        245,
    ).astype(np.uint8)
    # Thin white hardsub-like strokes (edited overlay), not solid blocks.
    y0, y1 = h - 28, h - 10
    for x0 in (40, 90, 140, 190, 250, 310, 370, 430, 490):
        base[y0:y1, x0 : x0 + 18] = 255
        base[y0 + 4 : y1 - 4, x0 + 6 : x0 + 12] = 30  # dark outline / hollow
    return cv2.cvtColor(base, cv2.COLOR_GRAY2BGR)


class Phase1DetectResolutionTests(unittest.TestCase):
    def test_phase1_roi_covers_full_frame(self) -> None:
        """Editor text can sit near the top; do not crop ROI away from y=0."""
        self.assertEqual(ROI_Y0, 0.0)
        self.assertEqual(ROI_Y1, 1.0)

    def test_phase1_uses_1280_long_edge(self) -> None:
        """1080p ROI still undersamples thin mid labels / hardsubs at 960."""
        self.assertGreaterEqual(PHASE1_DET_LONG_EDGE, 1280)

    def test_detect_frame_hits_passes_phase1_recall_knobs(self) -> None:
        from src.media_pipeline.frame_sampling.master_phase1_extractor import (
            PHASE1_DET_BIN_THRESH,
            PHASE1_EXPAND_PAD_H_BOTTOM_FRAC,
            PHASE1_EXPAND_PAD_H_TOP_FRAC,
            PHASE1_EXPAND_PAD_W_FRAC,
        )

        frame = np.full((1080, 1920, 3), 80, dtype=np.uint8)
        det = MagicMock()
        det.detect.return_value = []
        MasterPhase1Extractor()._detect_frame_hits(
            frame, frame_index=0, detector=det, frame_w=1920, frame_h=1080
        )
        self.assertGreaterEqual(det.detect.call_count, 2)
        self.assertLessEqual(PHASE1_DET_BIN_THRESH, 0.17)
        self.assertLessEqual(PHASE1_EXPAND_PAD_W_FRAC, 0.06)
        self.assertLessEqual(PHASE1_EXPAND_PAD_H_TOP_FRAC, 0.25)
        self.assertLessEqual(PHASE1_EXPAND_PAD_H_BOTTOM_FRAC, 0.18)
        for call in det.detect.call_args_list:
            kwargs = call.kwargs
            self.assertGreaterEqual(int(kwargs.get("long_edge") or 0), 1280)
            self.assertLessEqual(float(kwargs.get("bin_thresh") or 1.0), 0.17)
            self.assertTrue(bool(kwargs.get("rematch_after_expand")))
            self.assertLessEqual(float(kwargs.get("expand_pad_w_frac") or 1.0), 0.06)
            self.assertLessEqual(
                float(kwargs.get("expand_pad_h_top_frac") or 1.0), 0.25
            )


class OverlayStrokePrepTests(unittest.TestCase):
    def test_stroke_prep_boosts_burnin_ink_vs_clahe(self) -> None:
        """
        Edited-in white hardsub on bright food: stroke prep must raise glyph
        selectivity vs CLAHE (CLAHE amplifies food noise; stroke favors ink).
        """
        roi = _synthetic_burnin_on_bright_food()
        clahe_bgr, _ = roi_clahe_bgr(roi, y0_frac=0.0, y1_frac=1.0)
        stroke_bgr = overlay_stroke_enhance_bgr(roi)
        band = slice(roi.shape[0] - 28, roi.shape[0] - 10)
        clahe_g = cv2.cvtColor(clahe_bgr, cv2.COLOR_BGR2GRAY)[band].astype(np.float32)
        stroke_g = cv2.cvtColor(stroke_bgr, cv2.COLOR_BGR2GRAY)[band].astype(np.float32)
        # Glyph columns from the synthetic painter (centers ±9).
        glyph_mask = np.zeros(roi.shape[1], dtype=bool)
        for x0 in (40, 90, 140, 190, 250, 310, 370, 430, 490):
            glyph_mask[x0 : x0 + 18] = True
        bg_mask = ~glyph_mask

        def _selectivity(gray: np.ndarray) -> float:
            g = float(gray[:, glyph_mask].var())
            b = float(gray[:, bg_mask].var()) + 1e-6
            return g / b

        self.assertGreater(_selectivity(stroke_g), _selectivity(clahe_g) * 1.15)

    def test_phase1_preps_include_clahe_and_stroke(self) -> None:
        frame = np.full((1080, 1920, 3), 90, dtype=np.uint8)
        preps = roi_phase1_detect_preps(frame)
        names = [n for n, _img, _y in preps]
        self.assertEqual(names, ["clahe", "stroke"])
        self.assertEqual(preps[0][2], preps[1][2])

    def test_roi_includes_low_bottom_hardsub_band(self) -> None:
        """
        Burn-ins often sit at y≈1004–1046 on 1080p (cy≈0.95).

        ROI must include the full frame bottom — cropping at 0.95H leaves only
        ~half the glyph and DBNet drops the line (Video1 gap ~19–28s).
        """
        self.assertGreaterEqual(ROI_Y1, 0.99)
        frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
        # Product-class low hardsub (missed when ROI_Y1 was 0.95).
        cv2.rectangle(frame, (400, 1006), (1500, 1046), (255, 255, 255), -1)
        preps = roi_phase1_detect_preps(frame)
        y_off = int(preps[0][2])
        roi_h = int(preps[0][1].shape[0])
        self.assertEqual(y_off + roi_h, 1080)
        self.assertLessEqual(1006 - y_off, roi_h - 1)
        self.assertLessEqual(1046 - y_off, roi_h)

    def test_dual_prep_detect_unions_unique_boxes(self) -> None:
        """Stroke path can recover a second hardsub-shaped box CLAHE misses."""
        frame = np.full((1080, 1920, 3), 80, dtype=np.uint8)
        cv2.rectangle(frame, (100, 980), (900, 1020), (255, 255, 255), -1)
        cv2.rectangle(frame, (100, 980), (900, 1020), (0, 0, 0), 2)
        cv2.rectangle(frame, (200, 860), (700, 900), (255, 255, 255), -1)
        cv2.rectangle(frame, (200, 860), (700, 900), (0, 0, 0), 2)
        y0 = int(round(1080 * ROI_Y0))
        y1 = int(round(1080 * ROI_Y1))
        roi_h = max(1, y1 - y0)
        det = MagicMock()
        det.detect.side_effect = [
            [
                TextBox(
                    x=100 / 1920,
                    y=(980 - y0) / roi_h,
                    width=800 / 1920,
                    height=40 / roi_h,
                )
            ],
            [
                TextBox(
                    x=200 / 1920,
                    y=(860 - y0) / roi_h,
                    width=500 / 1920,
                    height=40 / roi_h,
                )
            ],
        ]
        hits, _rej = MasterPhase1Extractor()._detect_frame_hits(
            frame, frame_index=3, detector=det, frame_w=1920, frame_h=1080
        )
        self.assertEqual(det.detect.call_count, 2)
        self.assertEqual(len(hits), 2)


class HardsubFragmentMergeTests(unittest.TestCase):
    def test_title_body_gap_seventeen_percent_merges(self) -> None:
        """
        Orange title + white body across '|' often leave ~0.15–0.18 frame gap.

        Merge must union them before expand (all videos).
        """
        left = TextBox(x=0.03, y=0.86, width=0.50, height=0.04)
        right = TextBox(x=0.70, y=0.865, width=0.22, height=0.038)  # gap ≈ 0.17
        merged = merge_collinear_text_boxes([left, right])
        self.assertEqual(len(merged), 1)
        self.assertGreaterEqual(merged[0].width, 0.85)


if __name__ == "__main__":
    unittest.main()
