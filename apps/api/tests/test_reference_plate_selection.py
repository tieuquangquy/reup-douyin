from __future__ import annotations

import math
import unittest

from src.media_pipeline.video_renderer.reference_plate import (
    is_text_reduced_reference_candidate,
    is_usable_reference_plate_candidate,
    reference_plate_candidate_score,
)


class ReferencePlateSelectionTests(unittest.TestCase):
    def test_rejects_neighbor_with_different_but_equally_dense_text(self) -> None:
        self.assertFalse(
            is_text_reduced_reference_candidate(
                current_textness_fraction=0.08,
                candidate_textness_fraction=0.075,
            )
        )

    def test_accepts_materially_cleaner_local_plate(self) -> None:
        self.assertTrue(
            is_text_reduced_reference_candidate(
                current_textness_fraction=0.08,
                candidate_textness_fraction=0.03,
            )
        )

    def test_rejects_candidate_that_still_contains_the_overlay(self) -> None:
        self.assertFalse(
            is_usable_reference_plate_candidate(
                outside_mad=2.38,
                inside_mad=1.53,
            )
        )

    def test_rejects_roi_change_that_only_matches_scene_motion(self) -> None:
        self.assertFalse(
            is_usable_reference_plate_candidate(
                outside_mad=5.72,
                inside_mad=6.22,
            )
        )

    def test_rejects_reference_from_another_scene(self) -> None:
        self.assertFalse(
            is_usable_reference_plate_candidate(
                outside_mad=38.01,
                inside_mad=35.45,
            )
        )

    def test_accepts_stable_clean_plate_with_material_roi_change(self) -> None:
        self.assertTrue(
            is_usable_reference_plate_candidate(
                outside_mad=3.0,
                inside_mad=18.0,
            )
        )

    def test_rejects_non_finite_metrics(self) -> None:
        self.assertFalse(
            is_usable_reference_plate_candidate(
                outside_mad=math.nan,
                inside_mad=18.0,
            )
        )

    def test_score_prefers_more_changed_roi_with_same_scene_distance(self) -> None:
        clean_score = reference_plate_candidate_score(
            outside_mad=3.0,
            inside_mad=24.0,
        )
        dirty_score = reference_plate_candidate_score(
            outside_mad=3.0,
            inside_mad=12.0,
        )

        self.assertLess(clean_score, dirty_score)


if __name__ == "__main__":
    unittest.main()
