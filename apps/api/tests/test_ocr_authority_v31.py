"""Exact-frame activation regressions derived from video 0014c4b6."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.ocr_filtering.box_timeline_tracker import (
    OcrObservation,
    TimedBox,
)
from src.media_pipeline.ocr_filtering.per_frame_position_authority import (
    activate_frame_from_observations,
    attach_text_to_current_frame_geometry,
    merge_endcard_candidate_boxes,
    position_cache_matches_video,
    read_frames_at_indices_sequentially,
    video_content_fingerprint,
)


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "ocr_authority_v31_frames.json").read_text(
        encoding="utf-8"
    )
)


class _FakeCapture:
    def __init__(self, count: int):
        self.frames = [
            np.full((2, 2, 3), index, dtype=np.uint8)
            for index in range(count)
        ]
        self.index = 0

    def read(self):
        if self.index >= len(self.frames):
            return False, None
        frame = self.frames[self.index]
        self.index += 1
        return True, frame


class OcrAuthorityV31Tests(unittest.TestCase):
    def test_f11_backfills_future_subtitle_only_with_current_local_evidence(self) -> None:
        fossil = FIXTURE["frames"]["11"]
        local = tuple(
            TimedBox(
                box["x"],
                box["y"],
                box["w"],
                box["h"],
            )
            for box in fossil["local_boxes"]
        )
        observations = [
            OcrObservation(
                time_ms=0,
                boxes=(TimedBox(0.35, 0.43, 0.39, 0.17, "什锦炒虾仁", 0.99),),
            ),
            OcrObservation(
                time_ms=772,
                boxes=(
                    TimedBox(
                        0.196,
                        0.916,
                        0.483,
                        0.084,
                        "这是个适合中国胃的减脂餐",
                        1.0,
                    ),
                ),
            ),
        ]

        activation = activate_frame_from_observations(
            frame_index=11,
            time_ms=fossil["time_ms"],
            local_boxes=local,
            observations=observations,
            duration_ms=29261,
        )

        self.assertEqual(activation["frame_state"], "hardsub")
        self.assertEqual(activation["boxes"][0].text, "这是个适合中国胃的减脂餐")
        self.assertEqual(activation["activation_source"], "future_ocr+current_local")

    def test_future_subtitle_is_not_backfilled_without_current_evidence(self) -> None:
        activation = activate_frame_from_observations(
            frame_index=10,
            time_ms=386,
            local_boxes=(),
            observations=[
                OcrObservation(
                    time_ms=772,
                    boxes=(TimedBox(0.196, 0.916, 0.483, 0.084, "字幕", 1.0),),
                )
            ],
            duration_ms=29261,
        )
        self.assertEqual(activation["boxes"], [])
        self.assertEqual(activation["frame_state"], "blank")

    def test_local_verified_mid_title_activates_without_cloud_mid_title(self) -> None:
        """Opening mid-titles must activate from local CTC CJK even if Cloud only has hardsub."""
        activation = activate_frame_from_observations(
            frame_index=0,
            time_ms=0,
            local_boxes=(
                TimedBox(0.35, 0.42, 0.30, 0.08, text="鸡蛋拌饭", confidence=0.92),
                TimedBox(0.40, 0.52, 0.20, 0.05, text="510千卡", confidence=0.90),
            ),
            observations=[
                OcrObservation(
                    time_ms=0,
                    boxes=(
                        TimedBox(0.20, 0.92, 0.60, 0.06, text="这是一个适合中国胃的减脂餐", confidence=0.99),
                    ),
                )
            ],
            duration_ms=27000,
        )
        self.assertEqual(activation["frame_state"], "title")
        self.assertGreaterEqual(len(activation["boxes"]), 1)
        self.assertTrue(any("鸡蛋" in str(box.text or "") for box in activation["boxes"]))
        self.assertEqual(activation["activation_source"], "local_verified_title")

    def test_merge_keeps_local_recognition_text_for_mid_title_authority(self) -> None:
        """Position-row CTC text must survive into merge or opening thumbnails stay blank."""
        from src.media_pipeline.ocr_filtering.per_frame_position_authority import (
            _position_boxes_from_row,
            merge_position_and_observation_timelines,
        )

        row = {
            "frame_index": 0,
            "time_ms": 0,
            "boxes": [
                {
                    "x": 0.35,
                    "y": 0.42,
                    "w": 0.30,
                    "h": 0.08,
                    "text": "鸡蛋拌饭",
                    "confidence": 0.95,
                }
            ],
        }
        parsed = _position_boxes_from_row(row)
        self.assertEqual(parsed[0].text, "鸡蛋拌饭")
        self.assertGreaterEqual(parsed[0].confidence, 0.95)

        merged = merge_position_and_observation_timelines(
            [row],
            [
                OcrObservation(
                    time_ms=0,
                    boxes=(
                        TimedBox(
                            0.20,
                            0.92,
                            0.60,
                            0.06,
                            text="这是一个适合中国胃的减脂餐",
                            confidence=0.99,
                        ),
                    ),
                )
            ],
            duration_ms=27000,
            observation_sources={0: 391},
            visual_signatures={},
        )
        self.assertEqual(merged[0]["frame_state"], "title")
        self.assertEqual(merged[0]["activation_source"], "local_verified_title")
        self.assertTrue(
            any("鸡蛋" in str(box.get("text") or "") for box in merged[0]["boxes"])
        )

    def test_f25_uses_high_resolution_current_frame_geometry(self) -> None:
        fossil = FIXTURE["frames"]["25"]
        local = tuple(
            TimedBox(box["x"], box["y"], box["w"], box["h"])
            for box in fossil["high_res_boxes"]
        )
        activation = activate_frame_from_observations(
            frame_index=25,
            time_ms=fossil["time_ms"],
            local_boxes=local,
            observations=[
                OcrObservation(
                    time_ms=772,
                    boxes=(
                        TimedBox(
                            0.196,
                            0.916,
                            0.483,
                            0.084,
                            "这是个适合中国胃的减脂餐",
                            1.0,
                        ),
                    ),
                )
            ],
            duration_ms=29261,
        )
        self.assertEqual(activation["frame_state"], "hardsub")
        self.assertAlmostEqual(activation["boxes"][0].x, local[0].x)
        self.assertAlmostEqual(activation["boxes"][0].y, local[0].y)

    def test_hardsub_activates_with_weak_glyph_when_local_bottom_signal_exists(
        self,
    ) -> None:
        """f132 regression: visible hardsub must not die solely on glyph mismatch."""
        current = np.zeros((48, 64), dtype=np.uint8)
        current[40:47, 8:56] = 255
        source = np.zeros((48, 64), dtype=np.uint8)
        source[0:8, 0:40] = 255
        local = (TimedBox(0.29, 0.92, 0.26, 0.03),)
        activation = activate_frame_from_observations(
            frame_index=132,
            time_ms=4400,
            local_boxes=local,
            observations=[
                OcrObservation(
                    time_ms=4466,
                    boxes=(
                        TimedBox(
                            0.11,
                            0.91,
                            0.55,
                            0.05,
                            "让你解馋的同时还没有多少热量",
                            0.99,
                        ),
                    ),
                )
            ],
            duration_ms=38500,
            current_glyph_mask=current,
            candidate_glyph_masks={4466: source},
            observation_sources={4466: 4466},
        )
        self.assertEqual(activation["frame_state"], "hardsub")
        self.assertIn("解馋", activation["boxes"][0].text)
        self.assertEqual(activation["activation_source"], "future_ocr+current_local")

    def test_f745_cloud_text_uses_current_frame_local_geometry(self) -> None:
        fossil = FIXTURE["frames"]["745"]
        cloud = fossil["cloud_rice_box"]
        local = fossil["local_rice_box"]
        attached = attach_text_to_current_frame_geometry(
            [
                TimedBox(
                    cloud["x"],
                    cloud["y"],
                    cloud["w"],
                    cloud["h"],
                    "米饭",
                    0.9999,
                )
            ],
            [
                TimedBox(
                    local["x"],
                    local["y"],
                    local["w"],
                    local["h"],
                ),
                TimedBox(0.90, 0.71, 0.07, 0.015),
                TimedBox(0.033, 0.439, 0.024, 0.011),
            ],
            require_all=True,
            include_unmatched=True,
        )
        self.assertEqual(len(attached), 2)
        self.assertEqual(attached[0].text, "米饭")
        self.assertAlmostEqual(attached[0].x, local["x"])
        self.assertGreater(attached[0].x, cloud["x"] + 0.04)
        self.assertTrue(attached[1].cover_only)
        self.assertGreater(attached[1].x, 0.80)

    def test_cjk_endcard_label_prefers_taller_local_label_over_weight(self) -> None:
        attached = attach_text_to_current_frame_geometry(
            [TimedBox(0.0, 0.856, 0.042, 0.059, "鸡蛋", 0.99)],
            [
                TimedBox(0.082, 0.830, 0.031, 0.020),
                TimedBox(0.082, 0.881, 0.051, 0.013),
            ],
            require_all=True,
        )
        self.assertEqual(len(attached), 1)
        self.assertAlmostEqual(attached[0].y, 0.830)

    def test_combined_local_line_can_carry_two_cloud_tokens(self) -> None:
        attached = attach_text_to_current_frame_geometry(
            [
                TimedBox(0.204, 0.201, 0.037, 0.031, "27%", 1.0),
                TimedBox(0.262, 0.202, 0.050, 0.031, "36.1克", 1.0),
            ],
            [
                TimedBox(0.212, 0.222, 0.090, 0.011),
                TimedBox(0.261, 0.259, 0.040, 0.011),
            ],
            require_all=True,
        )
        self.assertEqual(len(attached), 1)
        self.assertEqual(attached[0].text, "27% 36.1克")

    def test_cjk_nutrition_label_prefers_same_column_over_taller_value(self) -> None:
        attached = attach_text_to_current_frame_geometry(
            [TimedBox(0.0875, 0.270, 0.078, 0.035, "碳水化合物", 1.0)],
            [
                TimedBox(0.1135, 0.294, 0.0615, 0.011),
                TimedBox(0.2115, 0.291, 0.051, 0.015),
            ],
            require_all=True,
        )
        self.assertEqual(len(attached), 1)
        self.assertAlmostEqual(attached[0].x, 0.1135)

    def test_exact_overlay_reader_never_seeks_and_returns_requested_frames(self) -> None:
        capture = _FakeCapture(6)
        frames = read_frames_at_indices_sequentially(capture, {1, 4})
        self.assertEqual(sorted(frames), [1, 4])
        self.assertEqual(int(frames[1][0, 0, 0]), 1)
        self.assertEqual(int(frames[4][0, 0, 0]), 4)

    def test_fixture_records_the_f738_seek_mismatch(self) -> None:
        fossil = FIXTURE["frames"]["738"]
        self.assertGreater(fossil["sequential_white_fraction"], 0.80)
        self.assertLess(fossil["timestamp_seek_white_fraction"], 0.02)
        self.assertEqual(fossil["expected_state"], "endcard")

    def test_endcard_consensus_clips_bounds_and_prefers_complete_text(self) -> None:
        merged = merge_endcard_candidate_boxes(
            [
                [
                    TimedBox(0.94, 0.40, 0.10, 0.05, "232千", 0.88),
                    TimedBox(0.65, 0.22, 0.06, 0.05, "525", 1.0),
                ],
                [
                    TimedBox(0.94, 0.40, 0.06, 0.05, "232千卡", 0.97),
                    TimedBox(0.65, 0.22, 0.07, 0.05, "525千卡", 0.98),
                ],
            ]
        )
        self.assertEqual({box.text for box in merged}, {"232千卡", "525千卡"})
        self.assertTrue(all(0.0 <= box.x <= 1.0 for box in merged))
        self.assertTrue(all(box.x + box.w <= 1.0 for box in merged))

    def test_position_cache_requires_matching_video_fingerprint(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "video.mp4"
            video.write_bytes(b"video-version-one")
            fingerprint = video_content_fingerprint(video)
            self.assertTrue(
                position_cache_matches_video(
                    {"video_fingerprint": fingerprint},
                    video,
                )
            )
            video.write_bytes(b"video-version-two")
            self.assertFalse(
                position_cache_matches_video(
                    {"video_fingerprint": fingerprint},
                    video,
                )
            )
            self.assertFalse(position_cache_matches_video({}, video))


if __name__ == "__main__":
    unittest.main()
