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
    def test_solid_editor_card_rows_share_one_panel_cover_and_timing(self) -> None:
        panel = {"x": 0.15, "y": 0.70, "width": 0.68, "height": 0.10}
        first = _track(
            text_id="card_left",
            kind="ui",
            roles=["ui_chip"],
            start_frame=100,
            end_frame=130,
            start_ms=3333,
            end_ms=4367,
            geometry={"x": 0.20, "y": 0.72, "width": 0.18, "height": 0.025},
            editor_card_panel_box=[108, 896, 598, 1024],
            editor_card_panel_geometry=panel,
            visual_provenance={"classification": "EDITOR_OVERLAY"},
        )
        second = _track(
            text_id="card_right",
            kind="ui",
            roles=["ui_chip"],
            start_frame=104,
            end_frame=142,
            start_ms=3467,
            end_ms=4767,
            geometry={"x": 0.53, "y": 0.735, "width": 0.16, "height": 0.025},
            editor_card_panel_box=[108, 896, 598, 1024],
            editor_card_panel_geometry=panel,
            visual_provenance={"classification": "EDITOR_OVERLAY"},
        )

        contract = enrich_phase4_render_policies(
            {
                "video": {"fps": 30.0},
                "render_tracks": [first, second],
            }
        )
        rows = {row["text_id"]: row for row in contract["render_tracks"]}

        self.assertEqual(contract["counts"]["editor_card_panel_groups"], 1)
        self.assertEqual(rows["card_left"]["cover_start_frame"], 100)
        self.assertEqual(rows["card_left"]["cover_end_frame"], 142)
        self.assertEqual(rows["card_right"]["cover_start_frame"], 100)
        self.assertEqual(rows["card_right"]["cover_end_frame"], 142)
        left_cover = rows["card_left"]["render_policy"]["cover"]
        right_cover = rows["card_right"]["render_policy"]["cover"]
        for key, value in panel.items():
            self.assertAlmostEqual(left_cover["roi"][key], value)
            self.assertAlmostEqual(right_cover["roi"][key], value)
        self.assertEqual(
            left_cover["caption_cover_group_id"],
            right_cover["caption_cover_group_id"],
        )

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
        self.assertGreater(safe["width"], cover["width"])
        self.assertGreater(safe["height"], cover["height"])
        self.assertAlmostEqual(
            safe["x"] + safe["width"] * 0.5,
            cover["x"] + cover["width"] * 0.5,
        )
        self.assertAlmostEqual(
            safe["y"] + safe["height"] * 0.5,
            cover["y"] + cover["height"] * 0.5,
        )
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
        safe = policy["layout"]["safe_area"]
        cover = policy["cover"]["roi"]
        self.assertGreater(safe["width"], cover["width"])
        self.assertAlmostEqual(
            safe["x"] + safe["width"] * 0.5,
            cover["x"] + cover["width"] * 0.5,
        )

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
                text_vi="510 kcal",
            ),
            simultaneous_count=2,
        )

        self.assertTrue(policy["context"]["micro_ui"])
        self.assertEqual(policy["context"]["typography_kind"], "micro_ui")

    def test_long_approved_ui_chip_promotes_typography_and_wraps(self) -> None:
        policy = plan_render_track(
            _track(
                geometry={"x": 0.165, "y": 0.557, "width": 0.173, "height": 0.047},
                roles=["ui_chip"],
                kind="ui",
                text_vi="Chị em mặt bẹt, không thích",
            ),
            simultaneous_count=3,
        )

        self.assertTrue(policy["context"]["micro_ui_source"])
        self.assertFalse(policy["context"]["micro_ui"])
        self.assertTrue(policy["context"]["micro_ui_overflow_promoted"])
        self.assertEqual(policy["context"]["typography_kind"], "ui")
        self.assertEqual(policy["layout"]["max_lines"], 2)

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
        self.assertFalse(policy["context"]["intro_stylized_title"])
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
        self.assertEqual(policy["cover"]["mask_mode"], "stylized_components")
        self.assertTrue(policy["context"]["intro_stylized_title"])
        self.assertGreaterEqual(
            policy["damage_budget"]["max_frame_change_fraction"], 0.10
        )
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
        self.assertEqual(policy["layout"]["max_lines"], 2)
        self.assertEqual(policy["layout"]["mode"], "cover_aligned")
        self.assertGreater(
            policy["layout"]["safe_area"]["width"],
            policy["cover"]["roi"]["width"],
        )
        self.assertAlmostEqual(
            policy["layout"]["safe_area"]["x"]
            + policy["layout"]["safe_area"]["width"] * 0.5,
            policy["cover"]["roi"]["x"]
            + policy["cover"]["roi"]["width"] * 0.5,
        )
        self.assertEqual(policy["cover"]["mask_mode"], "full_roi_plate")
        self.assertEqual(
            policy["cover"]["strategy"], UNIFIED_EDITOR_COVER_STRATEGY
        )
        self.assertEqual(
            policy["cover"]["geometry_mode"], "stable_caption_envelope"
        )
        self.assertLess(policy["cover"]["roi"]["width"], 0.90)
        self.assertLess(policy["cover"]["roi"]["height"], 0.08)

    def test_near_full_width_caption_row_is_safe(self) -> None:
        policy = plan_render_track(
            _track(
                geometry={"x": 0.02, "y": 0.787, "width": 0.963, "height": 0.026},
                roles=["generic"],
                kind="ui",
            ),
            simultaneous_count=2,
        )
        self.assertTrue(policy["context"]["caption_row"])

    def test_cover_only_caption_row_can_survive_dense_epoch_overlap(self) -> None:
        policy = plan_render_track(
            _track(
                geometry={"x": 0.02, "y": 0.787, "width": 0.963, "height": 0.026},
                roles=["generic"],
                kind="ui",
                cover_only=True,
                visual_provenance={"classification": "EDITOR_OVERLAY"},
            ),
            simultaneous_count=7,
        )
        self.assertTrue(policy["context"]["caption_row"])

    def test_adjacent_caption_content_shares_one_bounded_stable_cover(self) -> None:
        contract = {
            "render_tracks": [
                _track(
                    text_id="caption_a",
                    kind="ui",
                    roles=["generic"],
                    start_frame=10,
                    end_frame=20,
                    start_ms=333,
                    end_ms=700,
                    geometry={"x": 0.18, "y": 0.72, "width": 0.62, "height": 0.03},
                ),
                _track(
                    text_id="caption_b",
                    kind="ui",
                    roles=["generic"],
                    start_frame=25,
                    end_frame=40,
                    start_ms=833,
                    end_ms=1366,
                    geometry={"x": 0.20, "y": 0.721, "width": 0.58, "height": 0.03},
                ),
            ],
            "counts": {},
        }

        enriched = enrich_phase4_render_policies(contract)
        first, second = enriched["render_tracks"]
        first_cover = first["render_policy"]["cover"]
        second_cover = second["render_policy"]["cover"]

        self.assertEqual(enriched["counts"]["stable_caption_cover_groups"], 1)
        self.assertEqual(
            first_cover["geometry_mode"],
            "stable_caption_group_adaptive_horizontal",
        )
        # Vertical placement is shared, but horizontal coverage is derived
        # per caption so a short sibling does not inherit a long blur plate.
        self.assertAlmostEqual(first_cover["roi"]["y"], second_cover["roi"]["y"])
        self.assertAlmostEqual(
            first_cover["roi"]["height"], second_cover["roi"]["height"]
        )
        self.assertNotEqual(first_cover["roi"], second_cover["roi"])
        self.assertLess(first_cover["roi"]["width"], 0.90)
        self.assertEqual(first["cover_end_frame"] + 1, second["cover_start_frame"])
        first_epoch = first["render_policy"]["cover"]["soft_cover_epoch_id"]
        second_epoch = second["render_policy"]["cover"]["soft_cover_epoch_id"]
        self.assertEqual(first_epoch, second_epoch)
        self.assertEqual(enriched["counts"]["soft_cover_epochs"], 1)
        self.assertEqual(
            enriched["soft_cover_epochs"][0]["reconstruction_order"],
            [
                "temporal_clean_reference",
                "spatial_surface_reconstruction",
                "stable_soft_blur",
            ],
        )

    def test_distant_ui_rows_use_distinct_soft_cover_epochs(self) -> None:
        contract = {
            "video": {"fps": 30.0},
            "render_tracks": [
                _track(
                    text_id="top_ui",
                    kind="ui",
                    roles=["ui_chip"],
                    start_frame=0,
                    end_frame=20,
                    geometry={"x": 0.10, "y": 0.15, "width": 0.20, "height": 0.04},
                ),
                _track(
                    text_id="bottom_ui",
                    kind="ui",
                    roles=["ui_chip"],
                    start_frame=0,
                    end_frame=20,
                    geometry={"x": 0.65, "y": 0.75, "width": 0.20, "height": 0.04},
                ),
            ],
        }

        enriched = enrich_phase4_render_policies(contract)
        epochs = {
            row["render_policy"]["cover"]["soft_cover_epoch_id"]
            for row in enriched["render_tracks"]
        }

        self.assertEqual(len(epochs), 2)
        self.assertEqual(enriched["counts"]["soft_cover_epochs"], 2)

    def test_stacked_editor_caption_sibling_keeps_cover_after_anchor_end(self) -> None:
        contract = {
            "video": {"fps": 30.0},
            "render_tracks": [
                _track(
                    text_id="compact_top",
                    kind="ui",
                    roles=["ui_chip"],
                    start_frame=1,
                    end_frame=62,
                    geometry={"x": 0.16, "y": 0.56, "width": 0.18, "height": 0.045},
                ),
                _track(
                    text_id="wide_anchor",
                    kind="ui",
                    roles=["generic"],
                    start_frame=23,
                    end_frame=62,
                    geometry={"x": 0.22, "y": 0.718, "width": 0.68, "height": 0.038},
                ),
            ],
        }

        enriched = enrich_phase4_render_policies(contract)
        sibling = next(
            row for row in enriched["render_tracks"] if row["text_id"] == "compact_top"
        )

        self.assertGreaterEqual(sibling["cover_end_frame"], 80)
        self.assertIn(
            "stacked_caption_sibling_cover_extension",
            sibling["render_policy"]["context"],
        )

    def test_caption_cover_timing_uses_semantic_observed_coverage_union(self) -> None:
        contract = {
            "video": {"fps": 30.0},
            "render_tracks": [
                _track(
                    text_id="sparse_caption",
                    kind="ui",
                    roles=["generic"],
                    start_frame=472,
                    end_frame=587,
                    geometry={"x": 0.15, "y": 0.747, "width": 0.74, "height": 0.03},
                    hit_frames=[472, 500, 539],
                    boundary_evidence={
                        "observed_first_frame": 472,
                        "observed_last_frame": 539,
                    },
                    coverage_authority={
                        "presence_ranges": [[470, 539], [572, 589]],
                    },
                )
            ],
        }

        enriched = enrich_phase4_render_policies(contract)
        row = enriched["render_tracks"][0]

        self.assertEqual(row["cover_start_frame"], 470)
        self.assertEqual(row["cover_end_frame"], 589)
        self.assertEqual(
            row["render_policy"]["context"]["cover_timing_authority"]["mode"],
            "semantic_observed_coverage_union",
        )
        self.assertEqual(
            row["render_policy"]["context"]["physical_presence_ranges"],
            [[470, 539], [572, 589]],
        )

    def test_semantic_dialogue_residual_keeps_approved_transcript_interval(self) -> None:
        contract = {
            "video": {"fps": 30.0},
            "render_tracks": [
                _track(
                    text_id="p2r_dialogue_residual",
                    kind="hardsub",
                    start_frame=1533,
                    end_frame=1674,
                    start_ms=51_100,
                    end_ms=55_833,
                    semantic_dialogue_residual_expanded=True,
                    hit_frames=[1560, 1561, 1562],
                    boundary_evidence={
                        "observed_first_frame": 1560,
                        "observed_last_frame": 1562,
                    },
                )
            ],
        }

        enriched = enrich_phase4_render_policies(contract)
        row = enriched["render_tracks"][0]

        self.assertEqual(row["cover_start_frame"], 1533)
        self.assertEqual(row["cover_end_frame"], 1674)
        self.assertEqual(
            row["render_policy"]["context"]["cover_timing_authority"]["mode"],
            "approved_transcript_segment_union",
        )

    def test_non_caption_ui_still_uses_observed_detector_interval(self) -> None:
        contract = {
            "video": {"fps": 30.0},
            "render_tracks": [
                _track(
                    text_id="ordinary_ui",
                    kind="ui",
                    roles=["ui_chip"],
                    start_frame=100,
                    end_frame=160,
                    start_ms=3_333,
                    end_ms=5_367,
                    geometry={"x": 0.72, "y": 0.20, "width": 0.16, "height": 0.04},
                    hit_frames=[121, 122, 123],
                    boundary_evidence={
                        "observed_first_frame": 121,
                        "observed_last_frame": 123,
                    },
                )
            ],
        }

        enriched = enrich_phase4_render_policies(contract)
        row = enriched["render_tracks"][0]

        self.assertEqual(row["cover_start_frame"], 121)
        self.assertEqual(row["cover_end_frame"], 123)
        self.assertEqual(
            row["render_policy"]["context"]["cover_timing_authority"]["mode"],
            "observed_detector_boundary",
        )

    def test_caption_lane_sibling_uses_coverage_tail_even_when_kind_is_ui(self) -> None:
        contract = {
            "video": {"fps": 30.0},
            "render_tracks": [
                _track(
                    text_id="compact_caption_sibling",
                    kind="ui",
                    roles=["ui_chip"],
                    start_frame=100,
                    end_frame=120,
                    geometry={"x": 0.24, "y": 0.62, "width": 0.20, "height": 0.02},
                    hit_frames=[102, 118],
                    boundary_evidence={
                        "observed_first_frame": 102,
                        "observed_last_frame": 118,
                    },
                    coverage_authority={"presence_ranges": [[98, 132]]},
                    visual_provenance={
                        "classification": "EDITOR_OVERLAY",
                        "confidence": 0.95,
                        "reasons": [
                            "caption_lane_provenance_overrides_dense_source_context"
                        ],
                    },
                )
            ],
        }

        row = enrich_phase4_render_policies(contract)["render_tracks"][0]

        self.assertEqual((row["cover_start_frame"], row["cover_end_frame"]), (98, 132))
        self.assertEqual(
            row["render_policy"]["context"]["cover_timing_authority"]["mode"],
            "semantic_observed_coverage_union",
        )

    def test_nested_editor_shadow_extension_survives_timing_enrichment(self) -> None:
        contract = {
            "video": {"fps": 30.0},
            "render_tracks": [
                _track(
                    text_id="editor_parent",
                    kind="hardsub",
                    roles=["hardsub"],
                    start_frame=1558,
                    end_frame=1588,
                    hit_frames=[1560, 1586],
                    boundary_evidence={
                        "observed_first_frame": 1560,
                        "observed_last_frame": 1586,
                    },
                    nested_shadow_timing_extension={
                        "shadow_text_id": "protected_child",
                        "start_frame": 1558,
                        "end_frame": 1610,
                        "policy_version": "nested_editor_shadow_timing_v1",
                    },
                )
            ],
        }

        enriched = enrich_phase4_render_policies(contract)
        row = enriched["render_tracks"][0]

        self.assertEqual(row["cover_start_frame"], 1558)
        self.assertEqual(row["cover_end_frame"], 1610)
        self.assertEqual(
            row["render_policy"]["context"]["cover_timing_authority"]["mode"],
            "observed_detector_boundary_nested_shadow_union",
        )

    def test_semantic_dialogue_cover_includes_observation_after_asr_end(self) -> None:
        contract = {
            "video": {"fps": 30.0},
            "render_tracks": [
                _track(
                    text_id="p2r_dialogue_tail",
                    kind="hardsub",
                    start_frame=5032,
                    end_frame=5129,
                    start_ms=167_733,
                    end_ms=171_000,
                    semantic_dialogue_residual_expanded=True,
                    hit_frames=list(range(5109, 5140)),
                    boundary_evidence={
                        "observed_first_frame": 5109,
                        "observed_last_frame": 5139,
                    },
                )
            ],
        }

        enriched = enrich_phase4_render_policies(contract)
        row = enriched["render_tracks"][0]

        self.assertEqual(row["cover_start_frame"], 5032)
        self.assertEqual(row["cover_end_frame"], 5139)
        self.assertEqual(
            row["render_policy"]["context"]["cover_timing_authority"][
                "effective_range"
            ],
            [5032, 5139],
        )

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
        self.assertEqual(
            {
                policy["cover"]["blur"][
                    "retry_sigma_frame_max_fraction"
                ]
                for policy in policies
            },
            {0.07},
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

    def test_repeated_coverage_width_promotes_near_half_width_caption(self) -> None:
        policy = plan_render_track(
            _track(
                geometry={"x": 0.323, "y": 0.418, "width": 0.489, "height": 0.025},
                roles=["generic"],
                kind="ui",
                text_vi="Cho mọi người xem túi nhỏ của mình!",
                coverage_authority={
                    "geometry_keyframes": [
                        {
                            "frame_index": index,
                            "geometry": {
                                "x": 0.29,
                                "y": 0.404,
                                "width": width,
                                "height": 0.052,
                            },
                        }
                        for index, width in enumerate(
                            [0.489, 0.53, 0.521, 0.528, 0.569]
                        )
                    ]
                },
            ),
            simultaneous_count=1,
        )

        self.assertTrue(policy["context"]["caption_row"])
        self.assertEqual(policy["layout"]["max_lines"], 2)

    def test_damage_budget_covers_larger_temporal_coverage_roi(self) -> None:
        policy = plan_render_track(
            _track(
                kind="ui",
                roles=["ui_chip"],
                geometry={
                    "x": 0.16,
                    "y": 0.558,
                    "width": 0.173,
                    "height": 0.047,
                },
                coverage_authority={
                    "geometry_keyframes": [
                        {
                            "frame_index": 0,
                            "geometry": {
                                "x": 0.165,
                                "y": 0.536,
                                "width": 0.186,
                                "height": 0.094,
                            },
                        }
                    ]
                },
            ),
            simultaneous_count=3,
        )

        assert policy["damage_budget"]["max_frame_change_fraction"] > 0.024

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
