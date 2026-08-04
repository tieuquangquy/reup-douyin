from __future__ import annotations

import unittest

import numpy as np

from src.media_pipeline.video_renderer.adaptive_quality import (
    TemporalInpaintState,
    assess_mask_quality,
    evaluate_damage_budget,
)


class MaskQualityTests(unittest.TestCase):
    def test_rejects_mask_that_consumes_too_much_of_frame(self) -> None:
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[10:90, 10:90] = 255
        verdict = assess_mask_quality(
            mask,
            cover_roi_px=(10, 10, 90, 90),
            max_frame_change_fraction=0.12,
        )
        self.assertEqual(verdict["status"], "BLOCKED")
        self.assertIn("mask_frame_fraction", verdict["blocked_reasons"])

    def test_rejects_empty_mask_in_nonempty_cover_roi(self) -> None:
        mask = np.zeros((100, 100), dtype=np.uint8)
        verdict = assess_mask_quality(
            mask,
            cover_roi_px=(20, 20, 80, 60),
            max_frame_change_fraction=0.12,
        )
        self.assertEqual(verdict["status"], "BLOCKED")
        self.assertIn("mask_empty", verdict["blocked_reasons"])

    def test_bounded_dense_ink_limit_accepts_82_percent_but_rejects_90(self) -> None:
        accepted = np.zeros((100, 100), dtype=np.uint8)
        accepted[10:90, 10:76] = 255
        accepted_verdict = assess_mask_quality(
            accepted,
            cover_roi_px=(10, 10, 90, 90),
            max_frame_change_fraction=0.70,
            max_roi_fill_fraction=0.85,
        )
        rejected = np.zeros((100, 100), dtype=np.uint8)
        rejected[10:90, 10:82] = 255
        rejected_verdict = assess_mask_quality(
            rejected,
            cover_roi_px=(10, 10, 90, 90),
            max_frame_change_fraction=0.70,
            max_roi_fill_fraction=0.85,
        )

        self.assertEqual(accepted_verdict["status"], "PASS")
        self.assertEqual(rejected_verdict["status"], "BLOCKED")
        self.assertIn(
            "mask_too_dense_for_ink", rejected_verdict["blocked_reasons"]
        )


class DamageBudgetTests(unittest.TestCase):
    def test_detects_changes_outside_allowed_mask(self) -> None:
        before = np.full((60, 80, 3), 120, dtype=np.uint8)
        after = before.copy()
        mask = np.zeros((60, 80), dtype=np.uint8)
        mask[20:40, 30:50] = 255
        after[0:10, 0:10] = 255
        verdict = evaluate_damage_budget(
            before,
            after,
            mask,
            {
                "max_frame_change_fraction": 0.12,
                "max_outside_mask_mean_abs_delta": 2.0,
                "min_outside_mask_ssim": 0.985,
            },
        )
        self.assertEqual(verdict["status"], "BLOCKED")
        self.assertIn("outside_mask_damage", verdict["blocked_reasons"])


class TemporalInpaintTests(unittest.TestCase):
    def test_clean_reference_can_seed_opening_title_plate(self) -> None:
        clean = np.full((80, 120, 3), 180, dtype=np.uint8)
        titled = clean.copy()
        titled[25:55, 30:90] = 15
        mask = np.zeros((80, 120), dtype=np.uint8)
        mask[25:55, 30:90] = 255
        state = TemporalInpaintState()
        state.seed("title", clean)

        output, meta = state.clean(titled, mask, key="title")

        self.assertEqual(meta["mode"], "static_plate")
        self.assertTrue(np.array_equal(output[mask > 0], clean[mask > 0]))

    def test_seeded_reference_aligns_without_blending_title_back_in(self) -> None:
        x = np.linspace(20, 230, 160, dtype=np.uint8)
        clean_reference = np.repeat(x[None, :, None], 100, axis=0)
        clean_reference = np.repeat(clean_reference, 3, axis=2)
        clean_current = np.roll(clean_reference, 3, axis=1)
        titled_current = clean_current.copy()
        titled_current[35:65, 50:110] = (10, 10, 220)
        mask = np.zeros((100, 160), dtype=np.uint8)
        mask[35:65, 50:110] = 255
        state = TemporalInpaintState()
        state.seed("moving_title", clean_reference)

        output, meta = state.clean(titled_current, mask, key="moving_title")

        self.assertIn(meta["mode"], {"affine_reference_plate", "flow_reference_plate"})
        mae = float(
            np.abs(
                output[mask > 0].astype(np.float32)
                - clean_current[mask > 0].astype(np.float32)
            ).mean()
        )
        self.assertLess(mae, 20.0)

    def test_static_background_reuses_stable_clean_plate(self) -> None:
        frame = np.full((80, 120, 3), 180, dtype=np.uint8)
        frame[30:50, 40:80] = 10
        mask = np.zeros((80, 120), dtype=np.uint8)
        mask[30:50, 40:80] = 255
        state = TemporalInpaintState()

        first, first_meta = state.clean(frame, mask, key="track")
        second, second_meta = state.clean(frame, mask, key="track")

        self.assertEqual(first_meta["mode"], "spatial_bootstrap")
        self.assertEqual(second_meta["mode"], "static_plate")
        self.assertTrue(np.array_equal(first, second))

    def test_motion_does_not_reuse_unwarped_stale_plate(self) -> None:
        x = np.linspace(20, 220, 120, dtype=np.uint8)
        base = np.repeat(x[None, :, None], 80, axis=0)
        frame1 = np.repeat(base, 3, axis=2)
        frame2 = np.roll(frame1, 4, axis=1)
        frame1[30:50, 45:75] = 0
        frame2[30:50, 49:79] = 0
        mask1 = np.zeros((80, 120), dtype=np.uint8)
        mask2 = np.zeros((80, 120), dtype=np.uint8)
        mask1[30:50, 45:75] = 255
        mask2[30:50, 49:79] = 255
        state = TemporalInpaintState()

        state.clean(frame1, mask1, key="moving")
        second, meta = state.clean(frame2, mask2, key="moving")

        self.assertNotEqual(meta["mode"], "static_plate")
        self.assertFalse(np.array_equal(second, frame1))


if __name__ == "__main__":
    unittest.main()
