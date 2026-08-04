from __future__ import annotations

import unittest

from src.media_pipeline.video_renderer.render_policy import (
    RenderPolicyError,
    UNIFIED_EDITOR_COVER_MASK_MODE,
    UNIFIED_EDITOR_COVER_POLICY_VERSION,
    UNIFIED_EDITOR_COVER_STRATEGY,
    enrich_phase4_render_policies,
    plan_render_track,
    select_text_render_tracks,
)


def _track(**overrides: object) -> dict:
    row = {
        "text_id": "sub_01",
        "content_id": "ocr_content_001",
        "start_frame": 0,
        "end_frame": 24,
        "start_ms": 0,
        "end_ms": 1000,
        "geometry": {"x": 0.2, "y": 0.8, "width": 0.6, "height": 0.06},
        "roles": ["hardsub"],
        "kind": "hardsub",
        "text_vi": "Một câu phụ đề tiếng Việt",
        "cover_only": False,
    }
    row.update(overrides)
    return row


class RenderPolicyTests(unittest.TestCase):
    def test_selects_one_text_placement_for_overlapping_same_content(self) -> None:
        primary = _track(
            text_id="sub_primary",
            geometry={"x": 0.1, "y": 0.7, "width": 0.6, "height": 0.06},
        )
        duplicate = _track(
            text_id="sub_duplicate",
            geometry={"x": 0.2, "y": 0.71, "width": 0.2, "height": 0.04},
        )

        selected = select_text_render_tracks([duplicate, primary])

        self.assertEqual([row["text_id"] for row in selected], ["sub_primary"])

    def test_keeps_same_content_at_distinct_locations(self) -> None:
        left = _track(
            text_id="left",
            geometry={"x": 0.05, "y": 0.2, "width": 0.2, "height": 0.04},
        )
        right = _track(
            text_id="right",
            geometry={"x": 0.7, "y": 0.2, "width": 0.2, "height": 0.04},
        )

        selected = select_text_render_tracks([left, right])

        self.assertEqual(len(selected), 2)

    def test_selects_one_semantic_label_when_residual_tracks_use_new_content_ids(self) -> None:
        primary = _track(
            text_id="sub_05",
            content_id="ocr_content_005",
            text_vi="Khối lượng tịnh: 150 g",
            geometry={"x": 0.43, "y": 0.34, "width": 0.09, "height": 0.06},
        )
        residual = _track(
            text_id="p4out_duplicate",
            content_id="p4out_content_new",
            text_vi="  KHỐI LƯỢNG TỊNH: 150 g  ",
            geometry={"x": 0.435, "y": 0.335, "width": 0.09, "height": 0.06},
        )

        selected = select_text_render_tracks([primary, residual])

        self.assertEqual(len(selected), 1)

    def test_keeps_same_semantic_text_at_distinct_locations(self) -> None:
        left = _track(
            text_id="left_semantic",
            content_id="left_content",
            text_vi="150 g",
            geometry={"x": 0.05, "y": 0.2, "width": 0.15, "height": 0.04},
        )
        right = _track(
            text_id="right_semantic",
            content_id="right_content",
            text_vi="150 g",
            geometry={"x": 0.75, "y": 0.2, "width": 0.15, "height": 0.04},
        )

        selected = select_text_render_tracks([left, right])

        self.assertEqual(len(selected), 2)

    def test_canonical_transition_renders_once_across_split_geometries(self) -> None:
        first = _track(
            text_id="fragment_a",
            duplicate_transition_canonical=True,
            geometry={"x": 0.05, "y": 0.2, "width": 0.3, "height": 0.04},
        )
        second = _track(
            text_id="fragment_b",
            duplicate_transition_canonical=True,
            geometry={"x": 0.65, "y": 0.2, "width": 0.1, "height": 0.04},
        )

        selected = select_text_render_tracks([first, second])

        self.assertEqual([row["text_id"] for row in selected], ["fragment_a"])

    def test_cover_only_track_is_never_rendered_as_text(self) -> None:
        primary = _track(text_id="primary")
        cover = _track(
            text_id="cover_only",
            cover_only=True,
            geometry={"x": 0.75, "y": 0.90, "width": 0.1, "height": 0.08},
        )

        selected = select_text_render_tracks([primary, cover])

        self.assertEqual([row["text_id"] for row in selected], ["primary"])

    def test_hardsub_text_safe_area_matches_cover_roi(self) -> None:
        policy = plan_render_track(_track(), simultaneous_count=1)

        cover = policy["cover"]["roi"]
        safe = policy["layout"]["safe_area"]
        self.assertEqual(cover, safe)
        self.assertLessEqual(cover["width"], 0.7)
        self.assertEqual(policy["layout"]["mode"], "cover_aligned")
        self.assertEqual(policy["layout"]["max_lines"], 2)
        self.assertEqual(
            policy["cover"]["strategy"], UNIFIED_EDITOR_COVER_STRATEGY
        )
        self.assertEqual(
            policy["cover"]["mask_mode"], UNIFIED_EDITOR_COVER_MASK_MODE
        )
        self.assertTrue(policy["context"]["bounded_dense_ink_hardsub"])
        self.assertEqual(
            policy["damage_budget"]["max_ink_roi_fill_fraction"], 0.85
        )

    def test_concurrent_hardsub_layout_stays_bound_to_cover_geometry(self) -> None:
        policy = plan_render_track(_track(), simultaneous_count=2)

        self.assertEqual(policy["layout"]["mode"], "cover_aligned")
        self.assertEqual(policy["layout"]["safe_area"], policy["cover"]["roi"])

    def test_narrow_hardsub_retains_strict_80_percent_ink_limit(self) -> None:
        policy = plan_render_track(
            _track(
                geometry={"x": 0.2, "y": 0.8, "width": 0.3, "height": 0.06}
            ),
            simultaneous_count=1,
        )

        self.assertFalse(policy["context"]["bounded_dense_ink_hardsub"])
        self.assertEqual(
            policy["damage_budget"]["max_ink_roi_fill_fraction"], 0.80
        )

    def test_ui_uses_tight_cover_and_one_line_safe_layout(self) -> None:
        policy = plan_render_track(
            _track(
                geometry={"x": 0.01, "y": 0.25, "width": 0.12, "height": 0.04},
                roles=["mid_label"],
                kind="ui",
                text_vi="Nước tương 2 muỗng",
            ),
            simultaneous_count=4,
        )

        self.assertEqual(policy["layout"]["max_lines"], 1)
        self.assertEqual(policy["layout"]["mode"], "cover_aligned")
        self.assertGreaterEqual(policy["layout"]["safe_area"]["x"], 0.025)
        self.assertLess(policy["cover"]["roi"]["width"], 0.2)

    def test_regular_ui_safe_area_stays_centered_on_source_row(self) -> None:
        geometry = {"x": 0.2, "y": 0.25, "width": 0.2, "height": 0.08}
        policy = plan_render_track(
            _track(
                geometry=geometry,
                roles=["mid_label"],
                kind="ui",
            ),
            simultaneous_count=4,
        )

        safe = policy["layout"]["safe_area"]
        self.assertAlmostEqual(
            safe["y"] + safe["height"] * 0.5,
            geometry["y"] + geometry["height"] * 0.5,
            places=6,
        )
        self.assertEqual(policy["cover"]["mask_dilate_radius_fraction"], 0.04)

    def test_explicit_ui_chip_keeps_compact_typography_when_detector_box_is_tall(self) -> None:
        policy = plan_render_track(
            _track(
                geometry={"x": 0.22, "y": 0.87, "width": 0.18, "height": 0.056},
                roles=["ui_chip", "hardsub"],
                kind="ui",
            ),
            simultaneous_count=2,
        )

        self.assertTrue(policy["context"]["micro_ui"])
        self.assertEqual(policy["context"]["typography_kind"], "micro_ui")

    def test_dense_tracks_share_cover_geometry_and_unified_cover_style(self) -> None:
        policy = plan_render_track(
            _track(roles=["ui_chip"], kind="ui"),
            simultaneous_count=10,
        )

        self.assertEqual(
            policy["cover"]["strategy"], UNIFIED_EDITOR_COVER_STRATEGY
        )
        self.assertEqual(policy["layout"]["mode"], "cover_aligned")
        safe = policy["layout"]["safe_area"]
        cover = policy["cover"]["roi"]
        self.assertAlmostEqual(
            safe["x"] + safe["width"] * 0.5,
            cover["x"] + cover["width"] * 0.5,
            places=6,
        )
        self.assertEqual(policy["cover"]["mask_dilate_radius_fraction"], 0.08)
        self.assertEqual(
            policy["damage_budget"]["max_ink_roi_fill_fraction"],
            0.82,
        )

    def test_very_dense_ui_uses_bounded_full_row_plate(self) -> None:
        policy = plan_render_track(
            _track(roles=["ui_chip"], kind="ui"), simultaneous_count=15
        )

        self.assertEqual(policy["cover"]["mask_mode"], "full_roi_plate")
        self.assertTrue(policy["context"]["output_residual_bounded_dense_mask"])

    def test_large_centered_sparse_ui_is_promoted_to_visual_title_policy(self) -> None:
        policy = plan_render_track(
            _track(
                geometry={"x": 0.35, "y": 0.35, "width": 0.30, "height": 0.10},
                roles=["mid_label"],
                kind="ui",
            ),
            simultaneous_count=2,
        )
        self.assertEqual(policy["context"]["effective_kind"], "title")
        self.assertEqual(policy["cover"]["mask_mode"], "full_roi_plate")
        self.assertEqual(policy["layout"]["max_lines"], 2)

    def test_short_intro_title_uses_spatial_title_policy_when_ocr_height_is_truncated(self) -> None:
        policy = plan_render_track(
            _track(
                start_frame=0,
                end_frame=2,
                geometry={"x": 0.11, "y": 0.66, "width": 0.78, "height": 0.043},
                roles=["generic"],
                kind="ui",
            ),
            simultaneous_count=2,
        )

        self.assertFalse(policy["context"]["caption_row"])
        self.assertEqual(policy["context"]["effective_kind"], "title")
        self.assertEqual(policy["cover"]["mask_mode"], "full_roi_plate")
        self.assertEqual(policy["layout"]["max_lines"], 2)

    def test_oversized_sparse_detector_box_fails_closed(self) -> None:
        with self.assertRaises(RenderPolicyError):
            plan_render_track(
                _track(
                    geometry={"x": 0.05, "y": 0.1, "width": 0.9, "height": 0.5},
                    roles=["mid_label"],
                    kind="ui",
                ),
                simultaneous_count=1,
            )

    def test_wide_low_caption_row_keeps_source_row_layout(self) -> None:
        policy = plan_render_track(
            _track(
                geometry={"x": 0.08, "y": 0.58, "width": 0.78, "height": 0.03},
                roles=["generic"],
                kind="ui",
                text_vi="một hàng phụ đề khoa học",
            ),
            simultaneous_count=2,
        )

        self.assertTrue(policy["context"]["caption_row"])
        self.assertEqual(policy["context"]["effective_kind"], "ui")
        self.assertEqual(policy["context"]["typography_kind"], "caption_row")
        self.assertEqual(policy["layout"]["max_lines"], 1)
        self.assertEqual(policy["layout"]["mode"], "cover_aligned")
        self.assertEqual(policy["layout"]["safe_area"], policy["cover"]["roi"])
        self.assertEqual(policy["cover"]["mask_mode"], "full_roi_plate")
        self.assertEqual(policy["cover"]["strategy"], "spatial_telea_r9")

    def test_all_editor_overlay_roles_share_one_cover_policy(self) -> None:
        tracks = [
            _track(kind="hardsub", roles=["hardsub"]),
            _track(
                kind="ui",
                roles=["ui_chip"],
                geometry={"x": 0.22, "y": 0.70, "width": 0.18, "height": 0.04},
            ),
            _track(
                kind="title",
                roles=["title"],
                geometry={"x": 0.30, "y": 0.25, "width": 0.40, "height": 0.12},
            ),
        ]

        policies = [plan_render_track(track, simultaneous_count=1) for track in tracks]

        self.assertEqual(
            {policy["cover"]["strategy"] for policy in policies},
            {UNIFIED_EDITOR_COVER_STRATEGY},
        )
        self.assertEqual(
            {policy["cover"]["mask_mode"] for policy in policies},
            {UNIFIED_EDITOR_COVER_MASK_MODE},
        )
        self.assertEqual(
            {policy["cover"]["consistency_policy"] for policy in policies},
            {UNIFIED_EDITOR_COVER_POLICY_VERSION},
        )

    def test_wide_caption_row_near_individual_limits_is_still_safe(self) -> None:
        policy = plan_render_track(
            _track(
                geometry={"x": 0.09, "y": 0.82, "width": 0.83, "height": 0.098},
                roles=["generic"],
                kind="ui",
            ),
            simultaneous_count=2,
        )

        self.assertTrue(policy["context"]["caption_row"])

    def test_wide_shallow_caption_row_can_appear_above_midline(self) -> None:
        policy = plan_render_track(
            _track(
                geometry={"x": 0.20, "y": 0.23, "width": 0.60, "height": 0.025},
                roles=["generic"],
                kind="ui",
            ),
            simultaneous_count=3,
        )

        self.assertTrue(policy["context"]["caption_row"])

    def test_half_width_shallow_row_closes_ui_classification_gap(self) -> None:
        policy = plan_render_track(
            _track(
                geometry={"x": 0.24, "y": 0.19, "width": 0.518, "height": 0.019},
                roles=["generic"],
                kind="ui",
            ),
            simultaneous_count=3,
        )

        self.assertTrue(policy["context"]["caption_row"])
        self.assertEqual(policy["context"]["typography_kind"], "caption_row")

    def test_compact_ui_does_not_claim_tall_layout_band(self) -> None:
        policy = plan_render_track(
            _track(
                geometry={"x": 0.38, "y": 0.17, "width": 0.22, "height": 0.02},
                roles=["semantic_scene_label"],
                kind="ui",
            ),
            simultaneous_count=4,
        )

        self.assertLessEqual(policy["layout"]["safe_area"]["height"], 0.065)
        self.assertTrue(policy["context"]["micro_ui"])
        self.assertEqual(policy["context"]["effective_kind"], "ui")
        self.assertEqual(policy["context"]["typography_kind"], "micro_ui")
        safe = policy["layout"]["safe_area"]
        source_center = 0.17 + 0.02 * 0.5
        safe_center = safe["y"] + safe["height"] * 0.5
        self.assertAlmostEqual(safe_center, source_center, places=6)

    def test_enriches_without_video_specific_ids_or_coordinates(self) -> None:
        contract = {
            "render_tracks": [
                _track(text_id="any_a", start_ms=0, end_ms=1000),
                _track(text_id="any_b", start_ms=500, end_ms=1500),
            ]
        }
        enriched = enrich_phase4_render_policies(contract)

        self.assertEqual(enriched["render_tracks"][0]["render_policy"]["context"]["simultaneous_count"], 2)
        self.assertEqual(enriched["render_tracks"][1]["render_policy"]["context"]["simultaneous_count"], 2)

    def test_side_by_side_hardsubs_keep_independent_cover_aligned_lanes(self) -> None:
        contract = {
            "render_tracks": [
                _track(
                    text_id="left_label",
                    content_id="left_content",
                    start_ms=867,
                    end_ms=3300,
                    geometry={
                        "x": 0.018,
                        "y": 0.868,
                        "width": 0.194,
                        "height": 0.046,
                    },
                    text_vi="Giáº£m cÃ¢n kiá»ƒu Trung",
                ),
                _track(
                    text_id="right_label",
                    content_id="right_content",
                    start_ms=733,
                    end_ms=3300,
                    geometry={
                        "x": 0.223,
                        "y": 0.866,
                        "width": 0.368,
                        "height": 0.055,
                    },
                    text_vi="GÃ  háº¥p náº¥m 582 kcal",
                ),
            ]
        }

        enriched = enrich_phase4_render_policies(contract)
        left_policy = enriched["render_tracks"][0]["render_policy"]
        right_policy = enriched["render_tracks"][1]["render_policy"]
        left_safe = left_policy["layout"]["safe_area"]
        right_safe = right_policy["layout"]["safe_area"]

        self.assertEqual(left_safe, left_policy["cover"]["roi"])
        self.assertEqual(right_safe, right_policy["cover"]["roi"])
        self.assertEqual(left_policy["layout"]["mode"], "cover_aligned")
        self.assertEqual(right_policy["layout"]["mode"], "cover_aligned")

    def test_nearby_title_companion_inherits_reference_cover_only(self) -> None:
        contract = {
            "render_tracks": [
                _track(
                    text_id="title",
                    start_ms=0,
                    end_ms=200,
                    geometry={"x": 0.35, "y": 0.35, "width": 0.30, "height": 0.10},
                    roles=["mid_label"],
                    kind="ui",
                ),
                _track(
                    text_id="value",
                    start_ms=0,
                    end_ms=200,
                    geometry={"x": 0.42, "y": 0.48, "width": 0.16, "height": 0.05},
                    roles=["ui_chip"],
                    kind="ui",
                    text_vi="510 kcal",
                ),
            ]
        }
        enriched = enrich_phase4_render_policies(contract)
        value_policy = enriched["render_tracks"][1]["render_policy"]
        self.assertEqual(value_policy["cover"]["mask_mode"], "full_roi_plate")
        self.assertEqual(value_policy["context"]["reference_group"], "title")
        self.assertEqual(value_policy["context"]["effective_kind"], "ui")


if __name__ == "__main__":
    unittest.main()
