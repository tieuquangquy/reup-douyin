"""Per-frame position authority: geometry from local detect, text from sparse OCR."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

import numpy as np

from src.media_pipeline.ocr_filtering.box_timeline_tracker import OcrObservation, TimedBox
from src.media_pipeline.ocr_filtering.per_frame_position_authority import (
    EventDrivenPositionDetector,
    attach_text_to_position_boxes,
    append_raw_hardsub_geometry_keeps,
    bounded_high_res_targets,
    build_ocr_text_segments,
    choose_segment_observation,
    compose_hardsub_boxes_after_high_res,
    fallback_times_for_empty_observations,
    fill_hardsub_local_gaps,
    fill_title_local_gaps,
    horizontal_overlap_frac,
    keep_rejected_hardsub_geometry,
    merge_position_and_ocr_timelines,
    repair_adjacent_partial_text,
    review_overlay_layers,
    route_verified_glyph_segments,
)
from src.media_pipeline.ocr_filtering.hybrid_glyph_ocr import GlyphSegment


class PerFramePositionAuthorityTests(unittest.TestCase):
    def test_event_position_detector_reuses_only_with_current_frame_evidence(self) -> None:
        class _Detector:
            def __init__(self) -> None:
                self.calls = 0

            def detect(self, frame, **_kwargs):
                self.calls += 1
                if not np.count_nonzero(frame):
                    return []
                return [
                    SimpleNamespace(
                        x=0.25,
                        y=0.80 if frame.shape[0] > 100 else 0.50,
                        width=0.50,
                        height=0.12,
                    )
                ]

        detector = _Detector()
        event_detector = EventDrivenPositionDetector(detector, checkpoint_frames=20)
        text_frame = np.zeros((180, 320, 3), dtype=np.uint8)
        for x in range(90, 230, 24):
            text_frame[145:160, x : x + 8] = 255

        first, first_source = event_detector.detect(text_frame, frame_index=0)
        second, second_source = event_detector.detect(text_frame, frame_index=1)
        blank, blank_source = event_detector.detect(
            np.zeros_like(text_frame),
            frame_index=2,
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(blank, [])
        self.assertEqual(first_source, "dbnet_full")
        self.assertEqual(second_source, "dbnet_subtitle+current_frame_refine")
        self.assertEqual(blank_source, "dbnet_subtitle+current_frame_refine")
        self.assertEqual(detector.calls, 4)

    def test_build_ocr_text_segments_span_until_next_tick(self) -> None:
        obs = [
            OcrObservation(
                time_ms=0,
                boxes=(
                    TimedBox(0.1, 0.9, 0.8, 0.06, text="第一行", confidence=0.95),
                ),
            ),
            OcrObservation(
                time_ms=2000,
                boxes=(
                    TimedBox(0.1, 0.9, 0.8, 0.06, text="第二行", confidence=0.95),
                ),
            ),
        ]
        segments = build_ocr_text_segments(obs, duration_ms=3000)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].start_ms, 0)
        self.assertEqual(segments[0].end_ms, 2000)
        self.assertEqual(segments[1].start_ms, 2000)
        self.assertEqual(segments[1].end_ms, 3001)

    def test_empty_ocr_tick_ends_previous_caption_segment(self) -> None:
        obs = [
            OcrObservation(
                time_ms=0,
                boxes=(TimedBox(0.1, 0.9, 0.8, 0.06, text="字幕", confidence=0.95),),
            ),
            OcrObservation(time_ms=1000, boxes=()),
        ]
        segments = build_ocr_text_segments(obs, duration_ms=2000)

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].end_ms, 1000)
        self.assertEqual(segments[1].boxes, ())

    def test_first_stable_keyframe_applies_from_video_start(self) -> None:
        obs = [
            OcrObservation(
                time_ms=77,
                boxes=(TimedBox(0.2, 0.4, 0.6, 0.08, text="标题", confidence=0.95),),
            )
        ]
        segments = build_ocr_text_segments(obs, duration_ms=1000)
        self.assertEqual(segments[0].start_ms, 0)

    def test_empty_observation_gets_one_bounded_fallback_time(self) -> None:
        obs = [
            OcrObservation(time_ms=1000, boxes=()),
            OcrObservation(
                time_ms=1400,
                boxes=(TimedBox(0.1, 0.9, 0.8, 0.05, text="下一句", confidence=0.9),),
            ),
            OcrObservation(time_ms=2000, boxes=()),
        ]
        self.assertEqual(
            fallback_times_for_empty_observations(obs, duration_ms=2300, offset_ms=200),
            [(1000, 1200), (2000, 2200)],
        )

    def test_segment_uses_first_successful_ranked_candidate(self) -> None:
        segment = GlyphSegment(
            segment_id=4,
            start_ms=4400,
            end_ms=5200,
            candidate_times_ms=(4600, 4800, 5100),
        )
        candidates = {
            4600: OcrObservation(time_ms=4600, boxes=()),
            4800: OcrObservation(
                time_ms=4800,
                boxes=(TimedBox(0.3, 0.92, 0.5, 0.05, "黄瓜切片", 0.98),),
            ),
            5100: OcrObservation(
                time_ms=5100,
                boxes=(TimedBox(0.3, 0.92, 0.5, 0.05, "不应调用", 0.98),),
            ),
        }
        chosen = choose_segment_observation(segment, candidates)
        self.assertEqual(chosen.time_ms, 4400)
        self.assertEqual(chosen.boxes[0].text, "黄瓜切片")

    def test_adjacent_partial_ocr_inherits_longer_containing_text(self) -> None:
        observations = [
            OcrObservation(
                time_ms=4439,
                boxes=(TimedBox(0.49, 0.92, 0.21, 0.06, "改刀成片状", 0.99),),
            ),
            OcrObservation(
                time_ms=4902,
                boxes=(
                    TimedBox(
                        0.30,
                        0.92,
                        0.50,
                        0.06,
                        "先把黄瓜去籽改刀成片状",
                        0.99,
                    ),
                ),
            ),
        ]
        repaired = repair_adjacent_partial_text(observations, max_gap_ms=1200)
        self.assertEqual(repaired[0].boxes[0].text, "先把黄瓜去籽改刀成片状")
        self.assertEqual(repaired[0].boxes[0].x, 0.30)
        self.assertGreaterEqual(repaired[0].boxes[0].w, 0.50)

    def test_attach_text_only_when_position_overlaps_ocr_segment(self) -> None:
        pos = [TimedBox(0.12, 0.91, 0.75, 0.05, text="", confidence=0.0)]
        segments = build_ocr_text_segments(
            [
                OcrObservation(
                    time_ms=0,
                    boxes=(
                        TimedBox(0.1, 0.9, 0.8, 0.06, text="匹配", confidence=0.9),
                    ),
                ),
            ],
            duration_ms=1000,
        )
        matched = attach_text_to_position_boxes(pos, time_ms=500, segments=segments)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].text, "匹配")

        far = [TimedBox(0.02, 0.2, 0.2, 0.08, text="", confidence=0.0)]
        unmatched = attach_text_to_position_boxes(far, time_ms=500, segments=segments)
        self.assertEqual(unmatched[0].text, "")

    def test_merge_does_not_hold_forward_position_boxes(self) -> None:
        positions = [
            {"frame_index": 0, "time_ms": 0, "boxes": [{"x": 0.1, "y": 0.9, "w": 0.8, "h": 0.05}]},
            {"frame_index": 1, "time_ms": 40, "boxes": []},
        ]
        obs = [
            OcrObservation(
                time_ms=0,
                boxes=(TimedBox(0.1, 0.9, 0.8, 0.05, text="字幕", confidence=0.9),),
            ),
        ]
        segments = build_ocr_text_segments(obs, duration_ms=40)
        merged = merge_position_and_ocr_timelines(positions, segments)
        self.assertEqual(len(merged[0]["boxes"]), 1)
        self.assertEqual(merged[0]["boxes"][0]["text"], "字幕")
        self.assertEqual(merged[0]["position_source_frame"], 0)
        self.assertEqual(merged[1]["boxes"], [])
        self.assertNotIn("ocr_source_ms", merged[1])

    def test_horizontal_overlap_frac(self) -> None:
        a = TimedBox(0.1, 0.9, 0.5, 0.05)
        b = TimedBox(0.3, 0.9, 0.5, 0.05)
        self.assertGreater(horizontal_overlap_frac(a, b), 0.3)
        c = TimedBox(0.0, 0.9, 0.1, 0.05)
        self.assertLess(horizontal_overlap_frac(a, c), 0.1)

    def test_high_resolution_budget_keeps_endcards_and_samples_subtitles(self) -> None:
        selected, skipped = bounded_high_res_targets(
            {
                0: "hardsub",
                1: "hardsub",
                2: "hardsub",
                3: "hardsub",
                10: "endcard",
                11: "endcard",
            },
            max_frames=4,
        )
        self.assertEqual(len(selected), 4)
        self.assertEqual(selected[10], "endcard")
        self.assertEqual(selected[11], "endcard")
        self.assertEqual(skipped, 2)

    def test_cloud_routes_only_verified_or_uncertain_glyph_events(self) -> None:
        segments = [
            GlyphSegment(1, 0, 900, (100, 300, 500), True),
            GlyphSegment(2, 900, 1800, (1000, 1200), True),
        ]
        rows = [
            {
                "frame_index": 3,
                "time_ms": 100,
                "local_verification": "verified",
                "boxes": [{"x": 0.2, "y": 0.9, "w": 0.6, "h": 0.05}],
            },
            {
                "frame_index": 30,
                "time_ms": 1000,
                "local_verification": "rejected",
                "boxes": [],
            },
        ]

        routed = route_verified_glyph_segments(segments, rows)

        self.assertEqual(len(routed), 1)
        self.assertEqual(routed[0].segment_id, 1)
        self.assertEqual(routed[0].candidate_times_ms, (100, 300))

    def test_cloud_budget_lock_skips_blank_and_keeps_main_plus_retry(self) -> None:
        segments = [
            GlyphSegment(1, 0, 900, (100, 300, 500), True),
            GlyphSegment(2, 900, 1800, (1000, 1200), True),
            GlyphSegment(3, 1800, 2400, (1900, 2100), True),
        ]
        rows = [
            {
                "frame_index": 3,
                "time_ms": 100,
                "local_verification": "verified",
                "boxes": [{"x": 0.2, "y": 0.9, "w": 0.6, "h": 0.05}],
            },
            {
                "frame_index": 30,
                "time_ms": 1000,
                "local_verification": "blank",
                "boxes": [],
            },
            {
                "frame_index": 57,
                "time_ms": 1900,
                "local_verification": "rejected",
                "boxes": [],
            },
        ]

        routed = route_verified_glyph_segments(segments, rows, max_candidates=2)

        self.assertEqual([segment.segment_id for segment in routed], [1])
        self.assertEqual(routed[0].candidate_times_ms, (100, 300))

    def test_review_overlay_is_authority_only_unless_diagnostic_enabled(self) -> None:
        entry = {
            "boxes": [{"x": 0.2, "y": 0.9, "w": 0.6, "h": 0.05}],
            "local_uncertain_boxes": [{"x": 0.4, "y": 0.3, "w": 0.1, "h": 0.1}],
        }

        self.assertEqual([kind for kind, _box in review_overlay_layers(entry)], ["authority"])
        self.assertEqual(
            [kind for kind, _box in review_overlay_layers(entry, diagnostic=True)],
            ["authority", "uncertain"],
        )

    def test_high_res_empty_keeps_prior_hardsub_geometry(self) -> None:
        """High-res refine must never wipe OCR-matched low-res hardsub evidence."""
        previous = [
            {"x": 0.40, "y": 0.45, "w": 0.30, "h": 0.08, "text": "标题"},
            {"x": 0.35, "y": 0.92, "w": 0.40, "h": 0.05, "text": "字幕"},
        ]
        boxes, source = compose_hardsub_boxes_after_high_res(previous, ())
        hardsubs = [box for box in boxes if float(box["y"]) >= 2.0 / 3.0]
        self.assertEqual(source, "low_res_fallback")
        self.assertEqual(len(hardsubs), 1)
        self.assertEqual(hardsubs[0]["text"], "字幕")
        self.assertEqual(len([box for box in boxes if float(box["y"]) < 2.0 / 3.0]), 1)

    def test_high_res_nonempty_replaces_prior_hardsub_geometry(self) -> None:
        previous = [
            {"x": 0.35, "y": 0.92, "w": 0.40, "h": 0.05, "text": "旧"},
        ]
        refined = (TimedBox(0.33, 0.94, 0.42, 0.04, text="新", confidence=0.9),)
        boxes, source = compose_hardsub_boxes_after_high_res(previous, refined)
        hardsubs = [box for box in boxes if float(box["y"]) >= 2.0 / 3.0]
        self.assertEqual(source, "high_res")
        self.assertEqual(len(hardsubs), 1)
        self.assertEqual(hardsubs[0]["text"], "新")

    def test_hardsub_local_gap_hold_fills_blank_between_same_caption(self) -> None:
        """Same caption with temporary local miss must keep boxes (no flicker)."""
        box = {
            "x": 0.30,
            "y": 0.92,
            "w": 0.40,
            "h": 0.05,
            "text": "稳定字幕",
            "confidence": 0.99,
        }
        frames = [
            {
                "frame_index": 10,
                "time_ms": 400,
                "boxes": [dict(box)],
                "frame_state": "hardsub",
                "evidence": "ocr+exact_frame_activation",
                "activation_source": "past_ocr+current_local",
            },
            {
                "frame_index": 11,
                "time_ms": 440,
                "boxes": [],
                "frame_state": "blank",
                "evidence": "none",
                "activation_source": "none",
                "ocr_candidate_count": 0,
                "local_hardsub_bottom": True,
                "local_hardsub_boxes": [
                    {"x": 0.31, "y": 0.93, "w": 0.38, "h": 0.04}
                ],
            },
            {
                "frame_index": 12,
                "time_ms": 480,
                "boxes": [dict(box)],
                "frame_state": "hardsub",
                "evidence": "ocr+exact_frame_activation",
                "activation_source": "past_ocr+current_local",
            },
        ]
        filled = fill_hardsub_local_gaps(frames, max_gap_ms=2000)
        self.assertEqual(filled[1]["frame_state"], "hardsub")
        self.assertEqual(filled[1]["boxes"][0]["text"], "稳定字幕")
        self.assertEqual(filled[1]["activation_source"], "hardsub_local_gap_hold")
        self.assertEqual(filled[1]["evidence"], "ocr+neighbor_hardsub_hold")
        self.assertAlmostEqual(filled[1]["boxes"][0]["x"], 0.31)
        self.assertEqual(filled[1]["position_source_frame"], 11)

    def test_hardsub_local_gap_hold_fuzzy_matches_partial_ocr_variants(self) -> None:
        """f82 regression: Cloud OCR partial readings of the same caption must hold."""
        frames = [
            {
                "frame_index": 78,
                "time_ms": 2600,
                "boxes": [
                    {
                        "x": 0.11,
                        "y": 0.91,
                        "w": 0.55,
                        "h": 0.05,
                        "text": "让你解的同时少热量",
                        "confidence": 0.95,
                    }
                ],
                "frame_state": "hardsub",
                "activation_source": "past_ocr+current_local",
            },
            {
                "frame_index": 82,
                "time_ms": 2733,
                "boxes": [],
                "frame_state": "blank",
                "activation_source": "none",
                "local_hardsub_bottom": True,
                "local_hardsub_boxes": [
                    {"x": 0.29, "y": 0.92, "w": 0.26, "h": 0.03}
                ],
            },
            {
                "frame_index": 91,
                "time_ms": 3033,
                "boxes": [
                    {
                        "x": 0.38,
                        "y": 0.91,
                        "w": 0.34,
                        "h": 0.05,
                        "text": "让你解疼的同时还没有多少热量",
                        "confidence": 0.99,
                    }
                ],
                "frame_state": "hardsub",
                "activation_source": "future_ocr+current_local",
            },
        ]
        filled = fill_hardsub_local_gaps(frames, max_gap_ms=2000)
        self.assertEqual(filled[1]["frame_state"], "hardsub")
        self.assertEqual(filled[1]["activation_source"], "hardsub_local_gap_hold")
        # Longer compatible reading, but geometry stays on the current frame.
        self.assertEqual(
            filled[1]["boxes"][0]["text"],
            "让你解疼的同时还没有多少热量",
        )
        self.assertAlmostEqual(filled[1]["boxes"][0]["x"], 0.29)
        self.assertAlmostEqual(filled[1]["boxes"][0]["w"], 0.26)
        self.assertEqual(filled[1]["position_source_frame"], 82)

    def test_hardsub_local_gap_hold_skips_without_current_bottom_geometry(self) -> None:
        """f79/f821: never paste neighbor boxes onto frames with no bottom local proof."""
        frames = [
            {
                "frame_index": 78,
                "time_ms": 2600,
                "boxes": [
                    {
                        "x": 0.2,
                        "y": 0.91,
                        "w": 0.5,
                        "h": 0.05,
                        "text": "让你解的同时少热量",
                        "confidence": 0.95,
                    }
                ],
                "frame_state": "hardsub",
                "activation_source": "past_ocr+current_local",
            },
            {
                "frame_index": 79,
                "time_ms": 2633,
                "boxes": [],
                "frame_state": "blank",
                "activation_source": "none",
                "local_hardsub_bottom": False,
            },
            {
                "frame_index": 91,
                "time_ms": 3033,
                "boxes": [
                    {
                        "x": 0.38,
                        "y": 0.91,
                        "w": 0.34,
                        "h": 0.05,
                        "text": "让你解疼的同时还没有多少热量",
                        "confidence": 0.99,
                    }
                ],
                "frame_state": "hardsub",
                "activation_source": "future_ocr+current_local",
            },
        ]
        filled = fill_hardsub_local_gaps(frames, max_gap_ms=2000)
        self.assertEqual(filled[1]["frame_state"], "blank")
        self.assertEqual(filled[1]["boxes"], [])

    def test_hardsub_local_gap_hold_with_bottom_geometry_from_prev_only(self) -> None:
        """Visible bottom geometry may hold the prior caption without a next anchor."""
        frames = [
            {
                "frame_index": 1,
                "time_ms": 100,
                "boxes": [
                    {
                        "x": 0.2,
                        "y": 0.91,
                        "w": 0.5,
                        "h": 0.05,
                        "text": "先给水饺皮挤上虾滑",
                        "confidence": 0.99,
                    }
                ],
                "frame_state": "hardsub",
                "activation_source": "past_ocr+current_local",
            },
            {
                "frame_index": 2,
                "time_ms": 200,
                "boxes": [],
                "frame_state": "blank",
                "activation_source": "none",
                "local_hardsub_bottom": True,
                "local_hardsub_boxes": [
                    {"x": 0.22, "y": 0.92, "w": 0.48, "h": 0.04}
                ],
            },
            {
                "frame_index": 3,
                "time_ms": 2500,
                "boxes": [],
                "frame_state": "blank",
                "activation_source": "none",
                "local_hardsub_bottom": False,
            },
        ]
        filled = fill_hardsub_local_gaps(frames, max_gap_ms=2000)
        self.assertEqual(filled[1]["frame_state"], "hardsub")
        self.assertIn("水饺皮", filled[1]["boxes"][0]["text"])
        self.assertAlmostEqual(filled[1]["boxes"][0]["x"], 0.22)
        # Beyond budget / no local proof: stay blank.
        self.assertEqual(filled[2]["frame_state"], "blank")

    def test_hardsub_local_gap_hold_skips_when_caption_changes(self) -> None:
        frames = [
            {
                "frame_index": 1,
                "time_ms": 100,
                "boxes": [{"x": 0.3, "y": 0.9, "w": 0.4, "h": 0.05, "text": "第一句"}],
                "frame_state": "hardsub",
                "evidence": "ocr+exact_frame_activation",
                "activation_source": "past_ocr+current_local",
            },
            {
                "frame_index": 2,
                "time_ms": 140,
                "boxes": [],
                "frame_state": "blank",
                "evidence": "none",
                "activation_source": "none",
                "local_hardsub_bottom": True,
            },
            {
                "frame_index": 3,
                "time_ms": 180,
                "boxes": [{"x": 0.3, "y": 0.9, "w": 0.4, "h": 0.05, "text": "第二句"}],
                "frame_state": "hardsub",
                "evidence": "ocr+exact_frame_activation",
                "activation_source": "past_ocr+current_local",
            },
        ]
        filled = fill_hardsub_local_gaps(frames, max_gap_ms=2000)
        self.assertEqual(filled[1]["frame_state"], "blank")
        self.assertEqual(filled[1]["boxes"], [])

    def test_title_local_gap_hold_keeps_thumbnail_until_hardsub(self) -> None:
        """Opening mid-title must hold across short blanks before first hardsub."""
        title_box = {
            "x": 0.35,
            "y": 0.42,
            "w": 0.30,
            "h": 0.08,
            "text": "鸡蛋拌饭",
            "confidence": 0.95,
        }
        frames = [
            {
                "frame_index": 0,
                "time_ms": 0,
                "boxes": [dict(title_box)],
                "frame_state": "title",
                "evidence": "ocr+exact_frame_activation",
                "activation_source": "local_verified_title",
                "local_mid_title": True,
            },
            {
                "frame_index": 1,
                "time_ms": 80,
                "boxes": [],
                "frame_state": "blank",
                "evidence": "none",
                "activation_source": "none",
                # CTC flickered but mid-title geometry is still present.
                "local_mid_title": True,
            },
            {
                "frame_index": 2,
                "time_ms": 160,
                "boxes": [],
                "frame_state": "blank",
                "evidence": "none",
                "activation_source": "none",
                "local_mid_title": True,
            },
            {
                "frame_index": 3,
                "time_ms": 350,
                "boxes": [
                    {
                        "x": 0.3,
                        "y": 0.92,
                        "w": 0.4,
                        "h": 0.05,
                        "text": "底部字幕",
                        "confidence": 0.99,
                    }
                ],
                "frame_state": "hardsub",
                "evidence": "ocr+exact_frame_activation",
                "activation_source": "past_ocr+current_local",
                "local_mid_title": False,
            },
        ]
        filled = fill_title_local_gaps(frames, max_gap_ms=2000)
        self.assertEqual(filled[1]["frame_state"], "title")
        self.assertEqual(filled[1]["boxes"][0]["text"], "鸡蛋拌饭")
        self.assertEqual(filled[1]["activation_source"], "title_local_gap_hold")
        self.assertEqual(filled[2]["frame_state"], "title")
        self.assertEqual(filled[3]["frame_state"], "hardsub")

    def test_local_geometry_includes_uncertain_bottom_band_proposals(self) -> None:
        from src.media_pipeline.ocr_filtering.per_frame_position_authority import (
            _local_geometry_boxes_from_row,
        )

        row = {
            "boxes": [{"x": 0.3, "y": 0.5, "w": 0.1, "h": 0.05, "text": "ok"}],
            "local_uncertain_boxes": [
                {"x": 0.29, "y": 0.92, "w": 0.26, "h": 0.03},
                {"x": 0.1, "y": 0.1, "w": 0.05, "h": 0.02},
            ],
        }
        boxes = _local_geometry_boxes_from_row(row)
        self.assertEqual(len(boxes), 2)
        self.assertAlmostEqual(boxes[1].y, 0.92)

    def test_rejected_wide_bottom_hardsub_kept_as_geometry(self) -> None:
        """f83/f132: CTC reject must not erase wide bottom proposals used for hold."""
        # Visible hardsub line (position cache f84 / f132).
        self.assertTrue(
            keep_rejected_hardsub_geometry(TimedBox(0.3875, 0.922222, 0.25, 0.027778))
        )
        # f79 mid-frame crumb / f821 narrow fragment — do not unlock hold.
        self.assertFalse(
            keep_rejected_hardsub_geometry(TimedBox(0.421875, 0.75, 0.071875, 0.044444))
        )
        self.assertFalse(
            keep_rejected_hardsub_geometry(TimedBox(0.475, 0.933333, 0.078125, 0.016667))
        )

    def test_raw_hardsub_geometry_kept_when_verifier_blank_skips(self) -> None:
        """Ink/CTC blank-skip returns no decisions; still keep wide bottom raw boxes."""
        uncertain: list[TimedBox] = []
        append_raw_hardsub_geometry_keeps(
            raw_boxes=[
                TimedBox(0.3875, 0.922222, 0.25, 0.027778),
                TimedBox(0.421875, 0.75, 0.071875, 0.044444),
            ],
            accepted=[],
            uncertain=uncertain,
        )
        self.assertEqual(len(uncertain), 1)
        self.assertAlmostEqual(uncertain[0].w, 0.25)

    def test_title_local_gap_hold_does_not_paste_on_food_without_mid_title_local(
        self,
    ) -> None:
        """f4 regression: after title fades, do not hold a box over food."""
        frames = [
            {
                "frame_index": 3,
                "time_ms": 100,
                "boxes": [
                    {
                        "x": 0.23,
                        "y": 0.36,
                        "w": 0.62,
                        "h": 0.29,
                        "text": "虾滑大宽面",
                        "confidence": 0.99,
                    }
                ],
                "frame_state": "title",
                "activation_source": "past_ocr+current_local",
                "local_mid_title": True,
            },
            {
                "frame_index": 4,
                "time_ms": 133,
                "boxes": [],
                "frame_state": "blank",
                "activation_source": "none",
                "local_mid_title": False,
            },
        ]
        filled = fill_title_local_gaps(frames, max_gap_ms=2000)
        self.assertEqual(filled[1]["frame_state"], "blank")
        self.assertEqual(filled[1]["boxes"], [])
        self.assertEqual(filled[1]["activation_source"], "none")

    def test_title_local_gap_hold_stops_after_max_gap(self) -> None:
        frames = [
            {
                "frame_index": 0,
                "time_ms": 0,
                "boxes": [
                    {
                        "x": 0.35,
                        "y": 0.42,
                        "w": 0.30,
                        "h": 0.08,
                        "text": "标题",
                        "confidence": 0.95,
                    }
                ],
                "frame_state": "title",
                "activation_source": "local_verified_title",
                "local_mid_title": True,
            },
            {
                "frame_index": 1,
                "time_ms": 2500,
                "boxes": [],
                "frame_state": "blank",
                "activation_source": "none",
                "local_mid_title": True,
            },
        ]
        filled = fill_title_local_gaps(frames, max_gap_ms=2000)
        self.assertEqual(filled[1]["frame_state"], "blank")
        self.assertEqual(filled[1]["boxes"], [])


if __name__ == "__main__":
    unittest.main()
