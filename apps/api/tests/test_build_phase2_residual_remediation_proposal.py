from __future__ import annotations

import unittest

import numpy as np

from scripts.build_phase2_residual_remediation_proposal import (
    ResidualRemediationProposalError,
    _active_expansion_target,
    _same_content_translation,
    build_boundary_scan_frames,
    classify_phase1_geometry_overlap,
    cluster_residual_detections,
    cluster_reviewable_residual_detections,
    dominant_active_window,
    encoded_temporal_geometry_authority,
    has_approved_translation_authority,
    infer_contiguous_hit_window,
    match_source_box,
    match_source_cluster_crop,
    match_source_box_for_geometry_expansion,
    match_source_box_for_partial_caption_expansion,
    preflight_source_bound_temporal_matches,
    refine_hit_boundaries,
    select_residual_authority,
    source_match_cluster,
)


class _Box:
    def __init__(
        self,
        text: str,
        confidence: float,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        self.text = text
        self.confidence = confidence
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class Phase2ResidualRemediationProposalTests(unittest.TestCase):
    def test_reviewable_clusters_exclude_raw_protected_or_unreviewed_rows(self) -> None:
        detections = [
            {
                "frame_index": frame,
                "text": text,
                "confidence": 0.9,
                "geometry": geometry,
            }
            for frame, text, geometry in [
                (10, "保留源文字", {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.04}),
                (11, "保留源文字", {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.04}),
                (20, "编辑字幕", {"x": 0.2, "y": 0.8, "width": 0.4, "height": 0.05}),
                (21, "编辑字慕", {"x": 0.2, "y": 0.8, "width": 0.4, "height": 0.05}),
            ]
        ]
        review_objects = [
            {
                "content_id": "residual_content_editor",
                "text": "编辑字幕",
                "start_frame": 20,
                "end_frame": 21,
                "geometry": {"x": 0.2, "y": 0.8, "width": 0.4, "height": 0.05},
            }
        ]

        clusters = cluster_reviewable_residual_detections(
            detections,
            review_objects,
        )

        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["content_id"], "residual_content_editor")
        self.assertEqual(
            [row["frame_index"] for row in clusters[0]["detections"]],
            [20, 21],
        )

    def test_dense_long_encoded_caption_is_bounded_temporal_authority(self) -> None:
        geometry = {"x": 0.2, "y": 0.8, "width": 0.4, "height": 0.05}
        detections = [
            {
                "frame_index": frame,
                "text": "编辑字幕",
                "confidence": 0.9,
                "geometry": geometry,
                "temporal_confirmation": {
                    "status": "CONFIRMED_ON_ADJACENT_FRAME",
                    "match": {"frame_index": frame - 1, "geometry": geometry},
                },
            }
            for frame in range(100, 132)
        ]
        cluster = {
            "review_object": {
                "geometry": geometry,
                "start_frame": 100,
                "end_frame": 131,
            },
            "detections": detections,
        }

        authority = encoded_temporal_geometry_authority(cluster, frame_count=500)

        self.assertIsNotNone(authority)
        assert authority is not None
        self.assertEqual(authority["mode"], "dense_temporal_object")
        self.assertEqual(
            (authority["start_frame"], authority["end_frame"]),
            (100, 131),
        )

    def test_sparse_long_encoded_noise_is_not_geometry_authority(self) -> None:
        geometry = {"x": 0.2, "y": 0.8, "width": 0.4, "height": 0.05}
        cluster = {
            "review_object": {"geometry": geometry},
            "detections": [
                {
                    "frame_index": frame,
                    "text": "编辑字幕",
                    "confidence": 0.9,
                    "geometry": geometry,
                    "temporal_confirmation": {},
                }
                for frame in (100, 115, 131)
            ],
        }

        self.assertIsNone(
            encoded_temporal_geometry_authority(cluster, frame_count=500)
        )

    def test_bounded_half_sampled_caption_with_adjacent_confirmation_is_authority(self) -> None:
        geometry = {"x": 0.2, "y": 0.8, "width": 0.4, "height": 0.05}
        frames = list(range(100, 151, 2))
        cluster = {
            "review_object": {"geometry": geometry},
            "detections": [
                {
                    "frame_index": frame,
                    "text": "编辑字幕",
                    "confidence": 0.9,
                    "geometry": geometry,
                    "temporal_confirmation": {
                        "status": "CONFIRMED_ON_ADJACENT_FRAME",
                        "match": {"frame_index": frame - 1, "geometry": geometry},
                    },
                }
                for frame in frames
            ],
        }

        authority = encoded_temporal_geometry_authority(cluster, frame_count=500)

        self.assertIsNotNone(authority)
        assert authority is not None
        self.assertEqual(authority["mode"], "dense_temporal_object")

    def test_reuses_source_bound_adjacent_preflight_when_crop_reprobe_misses(self) -> None:
        detection = {
            "frame_index": 0,
            "text": "正饰分享",
            "confidence": 0.807,
            "geometry": {
                "x": 0.182,
                "y": 0.710,
                "width": 0.704,
                "height": 0.069,
            },
            "temporal_confirmation": {
                "status": "CONFIRMED_ON_ADJACENT_FRAME",
                "match": {
                    "frame_index": 1,
                    "text": "正饰分享",
                    "confidence": 0.807,
                    "geometry": {
                        "x": 0.182,
                        "y": 0.710,
                        "width": 0.704,
                        "height": 0.069,
                    },
                },
            },
        }
        cluster = cluster_residual_detections([detection])[0]
        residual = {
            "policy_version": "source_bound_temporal_cjk_confirmation_v2",
            "complete": True,
            "error": None,
            "source_detections": [
                {
                    "frame_index": 0,
                    "text": "正饰分享",
                    "confidence": 0.807,
                    "geometry": dict(detection["geometry"]),
                }
            ],
        }

        matches = preflight_source_bound_temporal_matches(
            residual,
            cluster,
            frame_count=100,
        )

        self.assertEqual([row["frame_index"] for row in matches], [0, 1])
        self.assertTrue(matches[0]["source_bound_preflight_authority"])

    def test_preflight_fallback_requires_same_frame_source_ocr(self) -> None:
        detection = {
            "frame_index": 0,
            "text": "耳饰分享",
            "confidence": 0.9,
            "geometry": {"x": 0.1, "y": 0.7, "width": 0.7, "height": 0.07},
            "temporal_confirmation": {
                "status": "CONFIRMED_ON_ADJACENT_FRAME",
                "match": {
                    "frame_index": 1,
                    "text": "耳饰分享",
                    "confidence": 0.9,
                    "geometry": {"x": 0.1, "y": 0.7, "width": 0.7, "height": 0.07},
                },
            },
        }
        residual = {
            "policy_version": "source_bound_temporal_cjk_confirmation_v2",
            "complete": True,
            "source_detections": [],
        }

        self.assertEqual(
            preflight_source_bound_temporal_matches(
                residual,
                cluster_residual_detections([detection])[0],
                frame_count=100,
            ),
            [],
        )

    def test_preflight_fallback_rejects_non_adjacent_confirmation(self) -> None:
        geometry = {"x": 0.1, "y": 0.7, "width": 0.7, "height": 0.07}
        detection = {
            "frame_index": 10,
            "text": "耳饰分享",
            "confidence": 0.9,
            "geometry": geometry,
            "temporal_confirmation": {
                "status": "CONFIRMED_ON_ADJACENT_FRAME",
                "match": {
                    "frame_index": 12,
                    "text": "耳饰分享",
                    "confidence": 0.9,
                    "geometry": geometry,
                },
            },
        }
        residual = {
            "policy_version": "source_bound_temporal_cjk_confirmation_v2",
            "complete": True,
            "source_detections": [
                {
                    "frame_index": 10,
                    "text": "耳饰分享",
                    "confidence": 0.9,
                    "geometry": geometry,
                }
            ],
        }

        self.assertEqual(
            preflight_source_bound_temporal_matches(
                residual,
                cluster_residual_detections([detection])[0],
                frame_count=100,
            ),
            [],
        )
    def test_protected_phase1_overlap_is_evidence_not_duplicate_render(self) -> None:
        self.assertEqual(
            classify_phase1_geometry_overlap(
                text_id="sub_01",
                existing_content={},
                residual_text="教程",
                active_render_text_ids={"sub_08"},
            ),
            "PROTECTED_EVIDENCE",
        )

    def test_active_phase1_overlap_still_fails_closed_on_conflicting_text(self) -> None:
        self.assertEqual(
            classify_phase1_geometry_overlap(
                text_id="sub_08",
                existing_content={"ocr_text_approved": "原有字幕"},
                residual_text="不同字幕",
                active_render_text_ids={"sub_08"},
            ),
            "CONFLICTING_RENDER_CONTENT",
        )

    def test_active_phase1_overlap_reuses_exact_render_content(self) -> None:
        self.assertEqual(
            classify_phase1_geometry_overlap(
                text_id="sub_08",
                existing_content={"ocr_text_approved": "教程"},
                residual_text="教程",
                active_render_text_ids={"sub_08"},
            ),
            "SAME_RENDER_CONTENT",
        )

    def test_boundary_scan_covers_stale_window_and_later_residual(self) -> None:
        frames, scan_start, scan_end = build_boundary_scan_frames(
            start_frame=424,
            end_frame=542,
            residual_frames=[434, 675],
            frame_count=1539,
            required_frames=[434],
        )

        self.assertEqual((scan_start, scan_end), (394, 705))
        self.assertIn(424, frames)
        self.assertIn(542, frames)
        self.assertIn(434, frames)
        self.assertIn(675, frames)
        self.assertIn(394, frames)
        self.assertIn(705, frames)
        self.assertLessEqual(len(frames), 126)

    def test_refines_coarse_boundaries_to_immediate_negative_frames(self) -> None:
        hit_frames = set(range(420, 681))
        start, end, before, after, probed = refine_hit_boundaries(
            start_frame=423,
            end_frame=678,
            frame_count=1000,
            is_hit=lambda frame_index: frame_index in hit_frames,
        )

        self.assertEqual((start, end), (420, 680))
        self.assertTrue(before)
        self.assertTrue(after)
        self.assertIn(419, probed)
        self.assertIn(681, probed)

    def test_suggestion_only_source_correction_preserves_residual_evidence(self) -> None:
        cluster = cluster_residual_detections(
            [
                {
                    "frame_index": 30,
                    "text": "花艺站模配一公",
                    "confidence": 0.9,
                    "geometry": {
                        "x": 0.05,
                        "y": 0.77,
                        "width": 0.27,
                        "height": 0.04,
                    },
                }
            ]
        )[0]

        corrected = source_match_cluster(
            cluster,
            {"花艺站模配一公": "蔬菜就搭配一份"},
        )

        self.assertEqual(corrected["signature"], "蔬菜就搭配一份")
        self.assertEqual(
            corrected["detections"],
            cluster["detections"],
        )
        self.assertFalse(
            corrected["source_text_correction"]["operator_approval_written"]
        )

    def test_reuses_one_approved_translation_for_duplicate_geometry(self) -> None:
        result = _same_content_translation(
            ["sub_10"],
            [
                {
                    "text_id": "sub_10",
                    "content_id": "ocr_content_010",
                    "text_vi": "Dáº§u hÃ o",
                    "translation_status": "TRANSLATION_APPROVED",
                }
            ],
        )

        self.assertEqual(result, ("ocr_content_010", "Dáº§u hÃ o"))

    def test_cluster_crop_projects_exact_ocr_box_to_full_frame(self) -> None:
        cluster = cluster_residual_detections(
            [
                {
                    "frame_index": 60,
                    "text": "中式减脂餐",
                    "confidence": 0.99,
                    "geometry": {
                        "x": 0.02,
                        "y": 0.86,
                        "width": 0.20,
                        "height": 0.05,
                    },
                }
            ]
        )[0]

        class Provider:
            def detect_frame(self, _path, *, frame_time_ms):
                self.frame_time_ms = frame_time_ms
                return type(
                    "Result",
                    (),
                    {
                        "boxes": [
                            _Box("中式减脂餐", 0.99, 0.08, 0.18, 0.84, 0.62)
                        ]
                    },
                )()

        provider = Provider()
        matched = match_source_cluster_crop(
            np.zeros((200, 400, 3), dtype=np.uint8),
            cluster,
            provider=provider,
            frame_time_ms=2000,
        )

        self.assertIsNotNone(matched)
        self.assertEqual(provider.frame_time_ms, 2000)
        self.assertGreater(matched["overlap"], 0.50)

    def test_expansion_target_requires_matching_approved_content(self) -> None:
        cluster = cluster_residual_detections(
            [
                {
                    "frame_index": 60,
                    "text": "中式减脂餐",
                    "confidence": 0.99,
                    "geometry": {
                        "x": 0.01,
                        "y": 0.86,
                        "width": 0.20,
                        "height": 0.05,
                    },
                }
            ]
        )[0]
        tracks = [
            {
                "text_id": "sub_03",
                "content_id": "content_03",
                "start_frame": 22,
                "end_frame": 98,
                "render_policy": {
                    "cover": {
                        "roi": {
                            "x": 0.21,
                            "y": 0.85,
                            "width": 0.40,
                            "height": 0.08,
                        }
                    }
                },
            }
        ]

        target = _active_expansion_target(
            cluster,
            tracks,
            {"content_03": {"ocr_text_approved": "香菇蒸滑鸡582千卡"}},
        )

        self.assertIsNone(target)

    def test_partial_caption_selects_approved_caption_row_not_overlapping_ui_chip(self) -> None:
        cluster = cluster_residual_detections(
            [
                {
                    "frame_index": 0,
                    "text": "王",
                    "confidence": 0.3073,
                    "geometry": {
                        "x": 0.5122,
                        "y": 0.7954,
                        "width": 0.0978,
                        "height": 0.0189,
                    },
                    "temporal_confirmation": {
                        "status": "CONFIRMED_ON_ADJACENT_FRAME",
                        "match": {"frame_index": 1},
                    },
                }
            ]
        )[0]
        caption_policy = {
            "context": {"caption_row": True},
            "cover": {
                "roi": {
                    "x": 0.0269,
                    "y": 0.6706,
                    "width": 0.9731,
                    "height": 0.1275,
                }
            },
        }
        ui_chip_policy = {
            "context": {"caption_row": False},
            "cover": {
                "roi": {
                    "x": 0.319,
                    "y": 0.762,
                    "width": 0.213,
                    "height": 0.060,
                }
            },
        }
        tracks = [
            {
                "text_id": "sub_02",
                "content_id": "caption",
                "start_frame": 0,
                "end_frame": 4,
                "geometry": {
                    "x": 0.1935,
                    "y": 0.7023,
                    "width": 0.5714,
                    "height": 0.0492,
                },
                "text_vi": "Makeup kiểu mắt mèo",
                "translation_status": "TRANSLATION_APPROVED",
                "render_policy": {
                    "context": {"caption_row": True},
                    "cover": {
                        "roi": {
                            "x": 0.0,
                            "y": 0.6566,
                            "width": 0.9676,
                            "height": 0.1241,
                        }
                    },
                },
            },
            {
                "text_id": "sub_03",
                "content_id": "caption",
                "start_frame": 0,
                "end_frame": 14,
                "geometry": {
                    "x": 0.1923,
                    "y": 0.7134,
                    "width": 0.6259,
                    "height": 0.0440,
                },
                "text_vi": "Makeup kiểu mắt mèo",
                "translation_status": "TRANSLATION_APPROVED",
                "render_policy": caption_policy,
            },
            {
                "text_id": "sub_04",
                "content_id": "chip",
                "start_frame": 0,
                "end_frame": 25,
                "geometry": {
                    "x": 0.3291,
                    "y": 0.7741,
                    "width": 0.1931,
                    "height": 0.0359,
                },
                "text_vi": "Vuông",
                "translation_status": "TRANSLATION_APPROVED",
                "render_policy": ui_chip_policy,
            },
        ]

        target = _active_expansion_target(
            cluster,
            tracks,
            {
                "caption": {"ocr_text_approved": "猫系美女妆"},
                "chip": {"ocr_text_approved": "正方形"},
            },
            source_detections=[
                {
                    "frame_index": 0,
                    "text": "教程",
                    "confidence": 0.9987,
                    "geometry": {
                        "x": 0.3704,
                        "y": 0.7660,
                        "width": 0.2222,
                        "height": 0.0498,
                    },
                }
            ],
        )

        self.assertIsNotNone(target)
        self.assertEqual(target["text_id"], "sub_02")
        association = target["_partial_caption_association"]
        self.assertEqual(association["source_detection"]["text"], "教程")
        self.assertEqual(association["confirmed_frame_range"], [0, 1])
        self.assertEqual(association["target_temporal_slack_frames"], 3)
        self.assertEqual(
            association["policy_version"],
            "preflight_partial_caption_association_v1",
        )
    def test_selects_encoded_output_residual_after_preview_qa_failure(self) -> None:
        source, residual = select_residual_authority(
            {"status": "READY_FOR_PHASE4"},
            output_qa={
                "status": "FAIL",
                "failed_checks": ["residual_cjk"],
                "residual_cjk": {"complete": True, "detections": [{"text": "盐"}]},
            },
            render_meta={
                "status": "VISUAL_PREVIEW_QA_FAILED",
                "visual_preview": True,
                "output_qa_status": "FAIL",
                "output_qa_failed_checks": ["residual_cjk"],
            },
        )

        self.assertEqual(source, "encoded_visual_preview_output_qa")
        self.assertEqual(residual["detections"][0]["text"], "盐")

    def test_rejects_non_residual_preview_failure_as_remediation_authority(self) -> None:
        with self.assertRaises(ResidualRemediationProposalError):
            select_residual_authority(
                {"status": "READY_FOR_PHASE4"},
                output_qa={
                    "status": "FAIL",
                    "failed_checks": ["temporal_flicker"],
                },
                render_meta={
                    "status": "VISUAL_PREVIEW_QA_FAILED",
                    "visual_preview": True,
                    "output_qa_status": "FAIL",
                    "output_qa_failed_checks": ["temporal_flicker"],
                },
            )

    def test_deterministic_number_unit_translation_is_approved_authority(self) -> None:
        self.assertTrue(
            has_approved_translation_authority(
                {"translation_status": "TRANSLATION_DETERMINISTIC"}
            )
        )
        self.assertTrue(
            has_approved_translation_authority(
                {"translation_status": "TRANSLATION_APPROVED"}
            )
        )
        self.assertFalse(
            has_approved_translation_authority(
                {"translation_status": "TRANSLATION_PENDING_REVIEW"}
            )
        )

    def test_infers_untracked_window_from_run_containing_residual_anchor(self) -> None:
        start, end, hits = infer_contiguous_hit_window(
            [0, 1, 2, 4, 20, 21],
            anchor_frame=0,
        )

        self.assertEqual((start, end), (0, 4))
        self.assertEqual(hits, [0, 1, 2, 4])

    def test_infers_window_from_every_second_frame_sampling(self) -> None:
        sampled_hits = list(range(220, 425, 2)) + [424]

        start, end, hits = infer_contiguous_hit_window(
            sampled_hits,
            anchor_frame=424,
        )

        self.assertEqual((start, end), (220, 424))
        self.assertEqual(hits[-1], 424)

    def test_untracked_window_requires_source_ocr_at_residual_anchor(self) -> None:
        with self.assertRaises(ResidualRemediationProposalError):
            infer_contiguous_hit_window([1, 2, 3], anchor_frame=0)

    def test_clusters_repeated_residual_and_matches_exact_source_signature(self) -> None:
        detections = [
            {
                "frame_index": 1293,
                "text": "170克Dam",
                "confidence": 0.99,
                "geometry": {"x": 0.06, "y": 0.88, "width": 0.23, "height": 0.04},
            },
            {
                "frame_index": 1298,
                "text": "170克Dam",
                "confidence": 0.98,
                "geometry": {"x": 0.061, "y": 0.881, "width": 0.23, "height": 0.04},
            },
        ]
        clusters = cluster_residual_detections(detections)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["signature"], "170克")
        self.assertEqual(len(clusters[0]["detections"]), 2)

        match = match_source_box(
            clusters[0],
            [
                _Box("170千卡", 0.99, 0.88, 0.47, 0.09, 0.03),
                _Box("170克", 0.998, 0.078, 0.89, 0.044, 0.025),
            ],
        )
        self.assertIsNotNone(match)
        self.assertEqual(match["text"], "170克")

    def test_source_text_must_match_exact_number_cjk_signature(self) -> None:
        cluster = cluster_residual_detections(
            [
                {
                    "frame_index": 10,
                    "text": "170克Dam",
                    "confidence": 0.99,
                    "geometry": {"x": 0.06, "y": 0.88, "width": 0.23, "height": 0.04},
                }
            ]
        )[0]
        self.assertIsNone(
            match_source_box(
                cluster,
                [_Box("170千卡", 0.99, 0.06, 0.88, 0.20, 0.04)],
            )
        )

    def test_matches_full_approved_line_for_geometry_expansion(self) -> None:
        cluster = cluster_residual_detections(
            [
                {
                    "frame_index": 344,
                    "text": "红柿",
                    "confidence": 0.99,
                    "geometry": {
                        "x": 0.53,
                        "y": 0.90,
                        "width": 0.07,
                        "height": 0.06,
                    },
                }
            ]
        )[0]

        match = match_source_box_for_geometry_expansion(
            expected_text="下入西红柿",
            residual=cluster,
            existing_geometry={
                "x": 0.38,
                "y": 0.895,
                "width": 0.15,
                "height": 0.078,
            },
            boxes=[_Box("下人西红柿", 0.99, 0.385, 0.90, 0.225, 0.061)],
        )

        self.assertIsNotNone(match)
        self.assertGreater(match["geometry"]["width"], 0.20)

    def test_matches_adjacent_full_source_line_for_partial_caption_expansion(self) -> None:
        cluster = cluster_residual_detections(
            [
                {
                    "frame_index": 0,
                    "text": "王",
                    "confidence": 0.3073,
                    "geometry": {
                        "x": 0.5122,
                        "y": 0.7954,
                        "width": 0.0978,
                        "height": 0.0189,
                    },
                }
            ]
        )[0]

        match = match_source_box_for_partial_caption_expansion(
            expected_text="教程",
            residual=cluster,
            source_anchor_geometry={
                "x": 0.3704,
                "y": 0.7660,
                "width": 0.2222,
                "height": 0.0498,
            },
            existing_geometry={
                "x": 0.1923,
                "y": 0.7134,
                "width": 0.6259,
                "height": 0.0440,
            },
            boxes=[_Box("教程", 0.998, 0.371, 0.766, 0.221, 0.050)],
        )

        self.assertIsNotNone(match)
        self.assertTrue(match["partial_caption_match"])
        self.assertGreater(match["expanded_area_ratio"], 1.05)

    def test_dominant_window_is_fail_closed_when_ambiguous(self) -> None:
        timeline = [
            {"start_frame": 1, "end_frame": 10},
            {"start_frame": 2, "end_frame": 10},
            {"start_frame": 3, "end_frame": 10},
        ]
        with self.assertRaises(ResidualRemediationProposalError):
            dominant_active_window(timeline, 5)

    def test_dominant_window_uses_shared_dense_ui_boundary(self) -> None:
        timeline = [
            {"start_frame": 1276, "end_frame": 1306},
            {"start_frame": 1276, "end_frame": 1306},
            {"start_frame": 1000, "end_frame": 1400},
        ]
        self.assertEqual(
            dominant_active_window(timeline, 1293),
            (1276, 1306, 2, 3),
        )


if __name__ == "__main__":
    unittest.main()
